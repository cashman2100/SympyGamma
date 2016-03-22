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
            raw_in = re.sub(r"^\s*(?:[a-zA-Z]\s*[\).]|\d+\s*(?:\)|\.(?!\d)))", "", raw_in)
            try:
                # exponents
                pre_sym = re.sub(r"(?<![a-zA-Z])(e)", r"E", raw_in)

                # sympy doesn't care about 'y =' or 'f(x) =', ignore this
                pre_sym = pre_sym.lstrip("y =")
                pre_sym = pre_sym.rstrip("=")
                pre_sym = re.sub(r"\A[a-zA-Z][\s]*[(][\s]*[xyz][\s]*[)][\s]*[=]", r"", pre_sym)
                expr = process_sympy(pre_sym)
                if isinstance(expr, sympy.Eq):
                    input = 'solve(%s)' % str(expr.args[0] - expr.args[1])
                else:
                    input = str(expr)
            except:
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
