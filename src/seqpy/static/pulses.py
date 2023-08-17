import copy
import numpy as np
from ..utils.math_util import *

def constant_waveform(const):
    if type(const) not in (int, float, complex):
        raise Exception(f"{const} is not a legal number")
    def waveform(x):
        return const
    return waveform

class Pulse:

    def __init__(self, left, right, waveform=None) -> None:
        super().__init__()
        self._left = left
        self._right = right
        if not waveform:
            waveform = constant_waveform(0)
        self._waveform = waveform

    def shift(self, length):
        def n_waveform(x):
            return self._waveform(x-length)
        self._waveform = n_waveform
        self._left += length
        self._right += length

    # -------------- Handle arithmetic Operation --------------

    def __add__(self, other):
        if isinstance(other, Pulse):
            waveform_other = other._waveform
        else:
            waveform_other = constant_waveform(other)
        def n_waveform(x):
            return self.waveform(x) + waveform_other(x)
        return Pulse(min(self._left, other._left), max(self._right, other._right), n_waveform)

    def __radd__(self, other):
        return self.__add__(other)

    def __mul__(self, other):
        if isinstance(other, Pulse):
            waveform_other = other._waveform
        else:
            waveform_other = constant_waveform(other)
        def n_waveform(x):
            return self.waveform(x) * waveform_other(x)
        return Pulse(min(self._left, other._left), max(self._right, other._right), n_waveform)

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

    def waveform(self, time_axis):
        return self._waveform(time_axis)

# ------------------------------------------------
#
#        Carrier as a special Pulse
#
# ------------------------------------------------

class Carrier(Pulse):
    def __init__(self, frequency, phase) -> None:
        def waveform(x):
            phase_in_rad = phase * np.pi / 180
            return np.cos(2 * np.pi * frequency * x + phase_in_rad)
        super().__init__(np.inf, -np.inf, waveform)


# ------------------------------------------------
#
#        Define different kind of pulses
#
# ------------------------------------------------


class Gaussian(Pulse):
    def __init__(self, width: float, plateau: float = 0, cutoff: float = 5.) -> None:
        self.width = width
        self.plateau = plateau
        left = -plateau/2 - cutoff*width/2
        right = -left
        def waveform(x):
            return gauss(x, width, plateau)
        super().__init__(left, right, waveform)


class Drag(Pulse):
    def __init__(self, width: float, cutoff: float = 5.) -> None:
        self.width = width
        left = -cutoff*width/2
        right = -left
        def waveform(x):
            return drag(x, width)
        super().__init__(left, right, waveform)


class Rect(Pulse):
    def __init__(self, width: float) -> None:
        self.width = width
        left = -width/2
        right = -left
        def waveform(x):
            return rectangle(x, width)
        super().__init__(left, right, waveform)


class Cosine(Pulse):
    def __init__(self, width: float, plateau: float = 0) -> None:
        left = (-plateau / 2 - width)
        right = -left
        def waveform(x):
            return cos(x, width, plateau)
        super().__init__(left, right, waveform)


class Ramp(Pulse):
    def __init__(self, width: float, amplitude_start: float, amplitude_end: float) -> None:
        left = -width / 2
        right = -left
        def waveform(x):
            return ramp(x, width, amplitude_start, amplitude_end)       
        super().__init__(left, right, waveform)