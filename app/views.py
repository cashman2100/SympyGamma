from django.http import HttpResponse, Http404
from django.shortcuts import render_to_response, redirect
from django.template.loader import render_to_string
from django.utils import simplejson
from django import forms
import django

from google.appengine.api import users
from google.appengine.runtime import DeadlineExceededError

import sympy
from logic.utils import Eval
from logic.logic import SymPyGamma, mathjax_latex
from logic.resultsets import get_card, find_result_set
from latex2sympy.process_latex import process_sympy

import settings
import models

import os
import re
import random
import json
import urllib
import urllib2
import datetime
import traceback
import time 

# latex2sympy returns unevaluated integrals and derivatives,
# i.e. "Integral(x, x)". SympyGamma wants the evaluated
# integral: "integrate(x, x)".

# workaround begin
from sympy.printing.str import StrPrinter

def _print_Integral_workaround(self, expr):
    def _xab_tostr(xab):
        if len(xab) == 1:
            return self._print(xab[0])
        else:
            return self._print((xab[0],) + tuple(xab[1:]))
    L = ', '.join([_xab_tostr(l) for l in expr.limits])
    return 'integrate(%s, %s)' % (self._print(expr.function), L)

def _print_Derivative_workaround(self, expr):
    return 'diff(%s)' % ", ".join(map(self._print, expr.args))

def _print_Limit_workaround(self, expr):
    e, z, z0, dir = expr.args
    if str(dir) == "+":
        return "limit(%s, %s, %s)" % (e, z, z0)
    else:
        return "limit(%s, %s, %s, dir='%s')" % (e, z, z0, dir)

StrPrinter._print_Integral = _print_Integral_workaround
StrPrinter._print_Derivative = _print_Derivative_workaround
StrPrinter._print_Limit = _print_Limit_workaround
# workaround end

# better solution printing
from sympy.printing.latex import LatexPrinter

def _print_dict_better(self, d):
    if len(d) == 1 and isinstance(d.keys()[0], sympy.Symbol):
        key = d.keys()[0]
        return "%s = %s" % (self._print(key), self._print(d[key]))
    keys = sorted(d.keys(), key=default_sort_key)
    items = []

    for key in keys:
        val = d[key]
        items.append("%s : %s" % (self._print(key), self._print(val)))

    return r"\left \{ %s\right \}" % r", \quad ".join(items)
LatexPrinter._print_dict = _print_dict_better

class MobileTextInput(forms.widgets.TextInput):
    def render(self, name, value, attrs=None):
        if attrs is None:
            attrs = {}
        attrs['autocorrect'] = 'off'
        attrs['autocapitalize'] = 'off'
        return super(MobileTextInput, self).render(name, value, attrs)

class SearchForm(forms.Form):
    i = forms.CharField(required=False, widget=MobileTextInput())
    l = forms.CharField(required=False, widget=MobileTextInput())

def authenticate(view):
    def _wrapper(request, **kwargs):
        user = users.get_current_user()
        result = view(request, user, **kwargs)

        try:
            template, params = result
        except ValueError:
            return result

        if user:
            params['auth_url'] = users.create_logout_url("/")
            params['auth_message'] = "Logout"
        else:
            params['auth_url'] = users.create_login_url("/")
            params['auth_message'] = "Login"
        return template, params
    return _wrapper

def app_version(view):
    def _wrapper(request, **kwargs):
        result = view(request, **kwargs)
        version, deployed = os.environ['CURRENT_VERSION_ID'].split('.')
        deployed = datetime.datetime.fromtimestamp(long(deployed) / pow(2, 28))
        deployed = deployed.strftime("%d/%m/%y %X")

        try:
            template, params = result
            params['app_version'] = version
            params['app_deployed'] = deployed
            return render_to_response(template, params)
        except ValueError:
            return result
    return _wrapper

@app_version
@authenticate
def index(request, user):
    return HttpResponse(json.dumps({
        'state': "running",
    }), mimetype="application/json")

@app_version
@authenticate
def fast_input(request, user):
    if request.method == "GET":
        form = SearchForm(request.GET)
        if form.is_valid():
            latex = form.cleaned_data["i"]
            # query parameter which can show image on top
            latex_mathjax = ''.join(['<script type="math/tex; mode=display">',
                                   latex,
                              '</script>'])

            rLatex = [{
                "title": "Input",
                "input": latex,
                "output": latex_mathjax
            }]

            # For some reason the |random tag always returns the same result
            return ("result.html", {
                "input": latex,
                "wolfram": latex,
                "result": [],
                "rLatex": rLatex,
                "form": form,
                "MEDIA_URL": settings.MEDIA_URL
                })


@app_version
@authenticate
def input(request, user):
    if request.method == "GET":
        form = SearchForm(request.GET)
        if form.is_valid():
            raw_in = form.cleaned_data["i"]

            # remove question number
            raw_in = raw_in.rstrip("=")
            raw_in = re.sub(r"^\s*(?:[a-zA-Z]\s*[\).]|\d+\s*(?:\)|\.(?!\d)))", "", raw_in)
            raw_in = re.sub(r"[.,]+\s*\Z", r"", raw_in)
            try:
                # sympy doesn't care about 'y =' or 'f(x) =', ignore this
                pre_sym = raw_in.lstrip("y =")
                pre_sym = re.sub(r"\A[a-zA-Z][\s]*[(][\s]*[xyz][\s]*[)][\s]*[=]", r"", pre_sym)

                expr = process_sympy(pre_sym)
                expr = expr.subs([(sympy.Symbol('e'), sympy.E), (sympy.Symbol('i'), sympy.I)])
                wild = sympy.Wild('w')
                expr = expr.replace(wild ** sympy.Symbol('circ'), (sympy.pi / 180) * wild)
                if isinstance(expr, sympy.Eq):
                    input = 'solve(%s,dict=True)' % str(expr.args[0] - expr.args[1])
                else:
                    input = str(expr)
            except Exception as e:
                print(e)
                input = raw_in

            # possible query parameter
            latex =  raw_in
            # query parameter which can show image on top
            latex_mathjax = ''.join(['<script type="math/tex; mode=display">',
                                   latex,
                              '</script>'])

            if input.strip().lower() in ('random', 'example', 'random example'):
                return redirect('/random')

            g = SymPyGamma()
            
            r = None
            rLatex = []
            if latex:
                rLatex = [{
                "title": "Input",
                "input": input,
                "output": latex_mathjax
                }]

                
            t0 = time.time()
            r_new = g.eval(input)
            t1 = time.time()
            print("Time evaluating: " + str(t1 - t0))
            if r_new:
                if r:
                    r.extend(r_new)
                else:
                    r = r_new

            if not r:
                r = [{
                    "title": "Input",
                    "input": input,
                    "output": "Can't handle the input."
                }]

            r = [elem for elem in r if elem["title"] not in ["Error", "Input"]]

            # For some reason the |random tag always returns the same result
            return ("result.html", {
                "input": input,
                "wolfram": raw_in,
                "result": r,
                "rLatex": rLatex,
                "form": form,
                "MEDIA_URL": settings.MEDIA_URL
                })

@app_version
def request(req, image_id):
    return ("request.html", {
        "MEDIA_URL": settings.MEDIA_URL,
        "image_id": image_id
    })

@app_version
def user_request(req, uuid):
    return ("user_request.html", {
        "MEDIA_URL": settings.MEDIA_URL,
        "uuid": uuid
    })

def _process_card(request, card_name):
    variable = request.GET.get('variable')
    expression = request.GET.get('expression')
    if not variable or not expression:
        raise Http404

    variable = urllib2.unquote(variable)
    expression = urllib2.unquote(expression)

    g = SymPyGamma()

    parameters = {}
    for key, val in request.GET.items():
        parameters[key] = ''.join(val)

    return g, variable, expression, parameters


def eval_card(request, card_name):
    g, variable, expression, parameters = _process_card(request, card_name)

    try:
        result = g.eval_card(card_name, expression, variable, parameters)
    except ValueError as e:
        return HttpResponse(json.dumps({
            'error': e.message
        }), mimetype="application/json")
    except DeadlineExceededError:
        return HttpResponse(json.dumps({
            'error': 'Computation timed out.'
        }), mimetype="application/json")
    except:
        trace = traceback.format_exc(5)
        return HttpResponse(json.dumps({
            'error': ('There was an error in Gamma. For reference'
                      'the last five traceback entries are: ' + trace)
        }), mimetype="application/json")

    return HttpResponse(json.dumps(result), mimetype="application/json")

def get_card_info(request, card_name):
    g, variable, expression, _ = _process_card(request, card_name)

    try:
        result = g.get_card_info(card_name, expression, variable)
    except ValueError as e:
        return HttpResponse(json.dumps({
            'error': e.message
        }), mimetype="application/json")
    except DeadlineExceededError:
        return HttpResponse(json.dumps({
            'error': 'Computation timed out.'
        }), mimetype="application/json")
    except:
        trace = traceback.format_exc(5)
        return HttpResponse(json.dumps({
            'error': ('There was an error in Gamma. For reference'
                      'the last five traceback entries are: ' + trace)
        }), mimetype="application/json")

    return HttpResponse(json.dumps(result), mimetype="application/json")

def get_card_full(request, card_name):
    g, variable, expression, parameters = _process_card(request, card_name)

    try:
        card_info = g.get_card_info(card_name, expression, variable)
        result = g.eval_card(card_name, expression, variable, parameters)
        card_info['card'] = card_name
        card_info['cell_output'] = result['output']

        html = render_to_string('card.html', {
            'cell': card_info,
            'input': expression
        })
    except ValueError as e:
        card_info = g.get_card_info(card_name, expression, variable)
        return HttpResponse(render_to_string('card.html', {
            'cell': {
                'title': card_info['title'],
                'input': card_info['input'],
                'card': card_name,
                'variable': variable,
                'error': e.message
            },
            'input': expression
        }), mimetype="text/html")
    except DeadlineExceededError:
        return HttpResponse('Computation timed out.',
                            mimetype="text/html")
    except:
        trace = traceback.format_exc(5)
        return HttpResponse(render_to_string('card.html', {
            'cell': {
                'card': card_name,
                'variable': variable,
                'error': trace
            },
            'input': expression
        }), mimetype="text/html")

    response = HttpResponse(html, mimetype="text/html")
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = 'Content-Type, X-Requested-With'

    return response

@app_version
def view_404(request):
    return ("404.html", {})

@app_version
def view_500(request):
    return ("500.html", {})
