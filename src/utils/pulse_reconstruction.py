# for resconstruction of pulses from dumped dictionary
from numpy.lib.ufunclike import _deprecate_out_named_y
from ..pulses import *


def dict2atom(dumped: dict):
    if dumped["type"] != "atom":
        raise Exception("A leaf in not an atomic pulse!")
    class_type = dumped["object type"].spilt(".")[-1]
    init_args = ", ".join(dumped["extra params"])
    base = eval(f"{class_type}({init_args})")
    return base.shift(dumped["displacement"]) * dumped["gain"] + dumped["offset"]


def reconstruct(dumped: dict):
    if dumped["type"] == "atom":
        return dict2atom(dumped)
    elif dumped["type"] == "add":
        return reconstruct(dumped["children"][0]) + reconstruct(dumped["children"][1])
    elif dumped["type"] == "mul":
        return reconstruct(dumped["children"][0]) * reconstruct(dumped["children"][1])
