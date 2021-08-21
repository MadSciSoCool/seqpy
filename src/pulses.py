from ast import dump
from sympy import Symbol, Expr, symbols
from sympy.functions import Max, Min
from .utils.math_util import *
from warnings import warn
import copy


SAMPLING_FREQUENCY = 2.4e9
USE_RELATIVE_TIMING = True
PHASE_ALIGNMENT = "Trigger"


def sampling_frequency(val: float):
    global SAMPLING_FREQUENCY
    SAMPLING_FREQUENCY = val


def relative_timing(val: bool):
    global USE_RELATIVE_TIMING
    USE_RELATIVE_TIMING = val


def phase_alignment(val: str):
    if val not in ("Zero", "Trigger"):
        warn("phase alignment mode should be chosen in zero/trigger")
    else:
        global PHASE_ALIGNMENT
        PHASE_ALIGNMENT = val


def relative_timing(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        arg_index = 1  # accounting for the extra self argument
        for k, v in f.__annotations__.items():
            if v is int and not USE_RELATIVE_TIMING:
                if k in kwargs.keys():
                    kwargs[k] = int(kwargs[k] * SAMPLING_FREQUENCY)
                else:
                    args = args[:arg_index] + \
                        (int(args[arg_index] * SAMPLING_FREQUENCY),
                         ) + args[arg_index + 1:]
            arg_index = arg_index + 1
        return f(*args, **kwargs)
    return wrapper


class Sweepable(Symbol):
    def __new__(self, name):
        return Symbol.__new__(self, name)

    def __init__(self, name):
        Symbol.__init__(name)


def sweepables(number=1):
    names = " ".join(["x" + str(i) for i in range(int(number))])
    syms = symbols(names)
    if isinstance(syms, Symbol):
        return Sweepable(syms.name)
    else:
        return [Sweepable(sym.name) for sym in syms]


class SweepableExpr:
    def __init__(self) -> None:
        self._sweepable_mapping = dict()

    def retrieve_value(self, *args):
        return_exprs = list()
        for expr in args:
            if not isinstance(expr, Expr):
                return_exprs.append(expr)
            else:
                for k in expr.atoms(Symbol):
                    # default value is 0
                    v = self._sweepable_mapping[k] if k in self._sweepable_mapping else 0
                    expr = expr.subs(k, v)
                if "Int" in str(type(expr)):
                    expr = int(expr)
                else:
                    expr = float(expr)  # Float or Infinity
                return_exprs.append(expr)
        return return_exprs

    def subs(self, name, value):
        self._sweepable_mapping[name] = value


class Pulse(SweepableExpr):

    def __init__(self, left, right, gain=1, offset=0, type="atom", children=[]) -> None:
        super().__init__()
        self._left = left
        self._right = right
        self._gain = gain
        self._offset = offset
        self._displacement = 0
        self.is_atom = True if type == "atom" else False
        self.type = type
        self.children = children

    # -------------- Handle arithmetic Operation --------------

    def _pad(self, waveform, left, right):
        if self.left > self.right:
            waveform = np.zeros(right - left)
        else:
            waveform = np.append(np.zeros(self.left - left), waveform)
            waveform = np.append(waveform, np.zeros(right - self.right))
        return waveform

    @relative_timing
    def shift(self, length: int):
        new = copy.deepcopy(self)
        new._displacement += length
        new._left += length
        new._right += length
        return new

    def __add__(self, other):
        if isinstance(other, Pulse):
            return Pulse(Min(self._left, other._left), Max(self._right, other._right), type="add", children=[self, other])
        else:
            new = copy.deepcopy(self)
            new._offset += other
            return new

    def __radd__(self, other):
        return self.__add__(other)

    def __mul__(self, other):
        if isinstance(other, Pulse):
            return Pulse(Min(self._left, other._left), Max(self._right, other._right), type="mul", children=[self, other])
        else:
            new = copy.deepcopy(self)
            new._gain *= other
            return new

    def __rmul__(self, other):
        return self.__mul__(other)

    def __sub__(self, other):
        return self + (-other)

    def __rsub__(self, other):
        return other + (-self)

    def __pos__(self):
        return self

    def __neg__(self):
        return self * (-1)

    # ---------------- For Waveform Generation ----------------

    @property
    def waveform(self):
        if self.is_atom:
            if self.left > self.right:
                return np.array([])
            x = np.arange(self.left, self.right) - self.displacement
            return self._waveform(x) * self.gain + self.offset
        else:
            # -------------- Tree traversing --------------
            child1, child2 = [c.shift(self.displacement)
                              for c in self.children]
            wf1 = child1._pad(child1.waveform, self.left, self.right)
            wf2 = child2._pad(child2.waveform, self.left, self.right)
            if self.type == "add":
                return (wf1 + wf2) * self.gain + self.offset
            elif self.type == "mul":
                return (wf1 * wf2) * self.gain + self.offset

    @waveform.setter
    def setter(self, val):
        pass

    @property
    def left(self):
        left_val = self.retrieve_value(self._left)[0]
        return left_val if np.isinf(left_val) else round(left_val)

    @property
    def right(self):
        right_val = self.retrieve_value(self._right)[0]
        return right_val if np.isinf(right_val) else round(right_val)

    @property
    def displacement(self):
        return self.retrieve_value(self._displacement)[0]

    @property
    def gain(self):
        return self.retrieve_value(self._gain)[0]

    @property
    def offset(self):
        return self.retrieve_value(self._offset)[0]

    def _waveform(self, x):
        return np.zeros(len(x))

    def subs(self, name, value):
        super().subs(name, value)
        for child in self.children:
            child.subs(name, value)

    # ----------- For dumping waveforms information -----------

    def dump(self):
        dumped = dict()
        dumped["type"] = self.type
        dumped["object type"] = str(type(self))
        dumped["gain"] = self._gain
        dumped["offset"] = self._offset
        dumped["displacement"] = self._displacement
        dumped["extra params"] = self.extra_params
        dumped["children"] = [c.dump for c in self.children]
        return dumped

    @property
    def extra_params(self):
        return []


# ------------------------------------------------
#
#        Carrier as a special Pulse
#
# ------------------------------------------------


class Carrier(Pulse):
    def __init__(self, frequencies, phases) -> None:
        super().__init__(left=np.inf, right=-np.inf)
        if not hasattr(frequencies, '__iter__'):
            frequencies = (frequencies, )
        if not hasattr(phases, '__iter__'):
            phases = (phases, )
        self.frequencies = frequencies
        self.phases = phases

    def _waveform(self, x):
        x = x / SAMPLING_FREQUENCY
        carrier = np.ones(len(x))
        frequencies, phases = self.extra_params
        for frequency, phase in zip(frequencies, phases):
            phase_in_rad = phase * np.pi / 180
            carrier = carrier * \
                np.cos(2 * np.pi * frequency * x + phase_in_rad)
        return carrier

    def _pad(self, waveform, left, right):
        return self._waveform(np.arange(left, right))

    @property
    def extra_params(self):
        return (self.retrieve_value(*self.frequencies), self.retrieve_value(*self.phases))

# ------------------------------------------------
#
#        Define different kind of pulses
#
# ------------------------------------------------


class Gaussian(Pulse):
    @relative_timing
    def __init__(self, width: int, plateau: int = 0, cutoff: float = 5.) -> None:
        self.width = width
        self.plateau = plateau
        left = -plateau/2 - cutoff*width/2
        right = -left + 1
        super().__init__(left, right)

    def _waveform(self, x):
        return gauss(x, *self.extra_params)

    @property
    def extra_params(self):
        return self.retrieve_value(self.width, self.plateau)


class Drag(Pulse):
    @relative_timing
    def __init__(self, width: int, cutoff: float = 5.) -> None:
        self.width = width
        left = -cutoff*width/2
        right = -left + 1
        super().__init__(left, right)

    def _waveform(self, x):
        return drag(x, *self.extra_params)

    @property
    def extra_params(self):
        return self.retrieve_value(self.width)


class Rect(Pulse):
    @relative_timing
    def __init__(self, width: int) -> None:
        self.width = width
        left = -width/2
        right = -left + 1
        super().__init__(left, right)

    def _waveform(self, x):
        return rectangle(x, *self.extra_params)

    @property
    def extra_params(self):
        return self.retrieve_value(self.width)


class Cosine(Pulse):
    @relative_timing
    def __init__(self, width: int, plateau: int = 0) -> None:
        self.width = width
        self.plateau = plateau
        left = -plateau / 2 - width
        right = -left + 1
        self.is_atom = True
        super().__init__(left, right)

    def _waveform(self, x):
        return cos(x, *self.extra_params)

    @property
    def extra_params(self):
        return self.retrieve_value(self.width, self.plateau)


class Ramp(Pulse):
    @relative_timing
    def __init__(self, width: int, amplitude_start: float, amplitude_end: float) -> None:
        self.width = width
        self.amplitude_start = amplitude_start
        self.amplitude_end = amplitude_end
        left = -width / 2
        right = -left + 1
        self.is_atom = True
        super().__init__(left, right)

    def _waveform(self, x):
        return ramp(x, *self.extra_params)

    @property
    def extra_params(self):
        return self.retrieve_value(self.width, self.amplitude_start, self.amplitude_end)
