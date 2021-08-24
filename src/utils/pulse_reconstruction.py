# for resconstruction of pulses from dumped dictionary
from ..pulses import *
from sympy.parsing.sympy_parser import parse_expr
import re


def str2expr(string):
    if isinstance(string, list) or isinstance(string, tuple):
        return [str2expr(o) for o in string]
    else:
        expr = parse_expr(string)
        expr_type = str(type(expr))
        if "Int" in expr_type:
            return int(expr)
        elif ("Float" or "Infinity") in expr_type:
            return float(expr)  # Float or Infinity
        else:
            return expr  # a 'real' sympy expression


def collect_sym(expr):
    if isinstance(expr, list) or isinstance(expr, tuple):
        return set.union(*[collect_sym(e) for e in expr])
    else:
        syms = set()
        for sym in parse_expr(expr).atoms(Symbol):
            syms.add(sym.name)
        return syms


def dict2atom(dumped: dict):
    if dumped["type"] != "atom":
        raise Exception("A leaf in not an atomic pulse!")
    pattern = r"<class '(?:\w*\.)*(\w*)'>"
    class_type = re.match(pattern, dumped["object type"]).group(1)
    # resolve the exprs and collect the variables
    syms = collect_sym([dumped["displacement"],
                        dumped["gain"],
                        dumped["offset"],
                        dumped["extra params"]])
    if class_type == "Carrier":
        full_length = len(dumped["extra params"])
        init_params = str2expr(
            [dumped["extra params"][:int(full_length/2)],
             dumped["extra params"][int(full_length/2):]])
    else:
        init_params = str2expr(dumped["extra params"])
    base = eval(class_type)(*init_params)
    displacement = str2expr(dumped["displacement"])
    gain = str2expr(dumped["gain"])
    offset = str2expr(dumped["offset"])
    return (base.shift(displacement) * gain + offset, syms)


def reconstruct(dumped: dict):
    if dumped["type"] == "atom":
        return dict2atom(dumped)
    else:
        pulse1, syms1 = reconstruct(dumped["children"][0])
        pulse2, syms2 = reconstruct(dumped["children"][1])
        if dumped["type"] == "add":
            return pulse1 + pulse2, syms1 | syms2
        elif dumped["type"] == "mul":
            return pulse1 * pulse2, syms1 | syms2
