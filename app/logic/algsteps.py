import sympy

q_wild = sympy.Wild('q')

def can_solve(expr, solve_var=sympy.Symbol('x')):
    if not isinstance(expr, sympy.Expr) or not expr.is_Equality:
        return

    if len(expr.free_symbols) < 0:
        return False

    return can_solve_side(expr.lhs, solve_var) and can_solve_side(expr.rhs, solve_var)

def can_solve_side(expr, solve_var):
    terms, _, _ = sympy.Add.flatten([expr])
    for t in terms:
        if t.has(solve_var):
            m = t.match(q_wild * solve_var)
            if not m:
                return False
            if m[q_wild].has(solve_var):
                return False
    return True

def is_solve_var(expr, var):
    m = expr.match(q_wild * var)
    return m and not m[q_wild].has(var)

def total_var_coeff(expr, var):
    q = sympy.Wild('q')
    total = sympy.Number(0)

    terms, _, _ = sympy.Add.flatten([expr])
    for t in terms:
        m = t.match(q * var)
        if m and m[q].is_Number:
            total += m[q]

    return total

def get_move_op(t):
    operation = 'Subtract'
    if t.is_Number:
        if t > 0:
            operation = 'Subtract'
        else:
            operation = 'Add'
    elif hasattr(t, 'args'):
        try:
            if t.args[0].is_Number and t.args[0] > 0:
                operation = 'Subtract'
            elif t.args[0].is_Number:
                operation = 'Add'
        except Exception:
            pass
    sign = 1 if operation == 'Subtract' else -1
    return operation, sign

def solve_simple_algebra(eq, solve_var):
    if not can_solve(eq, solve_var):
        raise "Can't solve"

    lhs_coeff = total_var_coeff(eq.lhs, solve_var)
    rhs_coeff = total_var_coeff(eq.rhs, solve_var)

    # variable to be solved for should be on the left?
    if lhs_coeff == 0 and rhs_coeff == 0:
        solve_left = eq.lhs.has(solve_var) 
    else:
        if eq.lhs.has(solve_var) and eq.rhs.has(solve_var):
            solve_left = lhs_coeff > rhs_coeff
        else:
            solve_left = eq.lhs.has(solve_var)
    
    steps = []
    iters = 0
    while True:
        iters += 1
        if iters > 30:
            return None # giving up

        lhs_simp = eq.lhs.simplify()
        if str(lhs_simp) != str(eq.lhs) and can_solve_side(lhs_simp, solve_var):
            steps.append({
                'desc': ['Simplify ', eq.lhs, ' to ', lhs_simp, ' (left side)'],
                'eq': sympy.Eq(lhs_simp, eq.rhs)
            })
            eq = sympy.Eq(lhs_simp, eq.rhs)
        rhs_simp = eq.rhs.simplify()
        if str(rhs_simp) != str(eq.rhs) and can_solve_side(lhs_simp, solve_var):
            steps.append({
                'desc': ['Simplify ', eq.rhs, ' to ', rhs_simp, ' (right side)'],
                'eq': sympy.Eq(eq.lhs, rhs_simp)
            })
            eq = sympy.Eq(eq.lhs, rhs_simp)

        lterms, _, _ = sympy.Add.flatten([eq.lhs])
        cont_outer = False
        for i, t in enumerate(lterms):
            if ((solve_left and (not is_solve_var(t, solve_var))) or
                ((not solve_left) and is_solve_var(t, solve_var))):
                operation, s = get_move_op(t)
                lhs = sympy.Add(eq.lhs, -t, evaluate=False)
                rhs = sympy.Add(eq.rhs, -t, evaluate=False)
                steps.append({
                    'desc': [operation, ' ', s*t, ' on both sides'],
                    'eq': sympy.Eq(lhs, rhs)
                })
                eq = sympy.Eq(lhs, rhs)
                cont_outer = True
                break
        if cont_outer:
            continue

        rterms, _, _ = sympy.Add.flatten([eq.rhs])
        cont_outer = False
        for i, t in enumerate(rterms):
            if (((not solve_left) and (not is_solve_var(t, solve_var))) or
                (solve_left and is_solve_var(t, solve_var))):
                operation, s = get_move_op(t)
                lhs = sympy.Add(eq.lhs, -t, evaluate=False)
                rhs = sympy.Add(eq.rhs, -t, evaluate=False)
                steps.append({
                    'desc': [operation, ' ', s*t, ' on both sides'],
                    'eq': sympy.Eq(lhs, rhs)
                })
                eq = sympy.Eq(lhs, rhs)
                cont_outer = True
                break
        if cont_outer:
            continue

        # almost done
        l_match = eq.lhs.match(q_wild*solve_var)
        l_match = ((not l_match[q_wild].has(solve_var)) and l_match[q_wild]!=1) if l_match else False

        r_match = eq.rhs.match(q_wild*solve_var)
        r_match = ((not r_match[q_wild].has(solve_var)) and r_match[q_wild]!=1) if r_match else False

        if ((solve_left and l_match) or (not solve_left and r_match)):
            if solve_left:
                coeff = eq.lhs.match(q_wild*solve_var)[q_wild]
            else:
                coeff = eq.rhs.match(q_wild*solve_var)[q_wild]

            if coeff != 1 and coeff != 0:
                lhs = sympy.Mul(sympy.Pow(coeff, -1, evaluate=False), eq.lhs, evaluate=False)
                rhs = sympy.Mul(sympy.Pow(coeff, -1, evaluate=False), eq.rhs, evaluate=False)
                eq = sympy.Eq(lhs, rhs)
                steps.append({
                    'desc': ['Divide by ', coeff],
                    'eq': eq
                })

            continue

        break

    return steps

import stepprinter

class AlgStepsPrinter(stepprinter.HTMLPrinter):
    def __init__(self):
        stepprinter.HTMLPrinter.__init__(self)

    def print_steps(self, steps):
        for step in steps:
            with self.new_step():
                s = ""
                for item in step['desc']:
                    if isinstance(item, sympy.Expr):
                        s += self.format_math(item)
                    else:
                        s += str(item)

                self.append(s)
                self.append(self.format_math_display(step['eq']))

def print_html_steps(expr, var):
    printer = AlgStepsPrinter()
    steps = solve_simple_algebra(expr, var)
    if not steps:
        raise Exception("Could not solve algebra")
    printer.print_steps(steps)
    return printer.finalize()
