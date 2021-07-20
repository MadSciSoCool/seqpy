import numpy as np
from functools import wraps

SAMPLING_FREQUENCY = 2.4e9
USE_RELATIVE_TIMING = False


def set_sampling_frequency(val: float):
    global SAMPLING_FREQUENCY
    SAMPLING_FREQUENCY = val


def use_relative_timing(val: bool):
    global USE_RELATIVE_TIMING
    USE_RELATIVE_TIMING = val


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


class Carrier:
    def __init__(self, phases, frequencies) -> None:
        if not hasattr(phases, '__iter__'):
            phases = (phases, )
        if not hasattr(frequencies, '__iter__'):
            frequencies = (frequencies, )
        self.phases = phases
        self.frequencies = frequencies

    def waveform(self, length):
        x = np.arange(length) / SAMPLING_FREQUENCY
        carrier = np.ones(length)
        for phase, frequency in zip(self.phases, self.frequencies):
            phase_in_rad = phase * np.pi / 180
            carrier = carrier * \
                np.cos(2 * np.pi * frequency * x + phase_in_rad)
        return carrier


class Pulse:
    def padding(f):
        @wraps(f)
        def wrapper(self, other):
            if isinstance(other, Pulse):
                left = min(self._left, other._left)
                right = max(self._right, other._right)
                self._pad(left, right)
                other._pad(left, right)
            return f(self, other)
        return wrapper

    def __init__(self, waveform, left, right) -> None:
        self._left = left
        self._right = right
        self._waveform = waveform

    def _pad(self, left, right):
        self._waveform = np.append(np.zeros(self._left - left), self._waveform)
        self._waveform = np.append(self._waveform, np.zeros(right-self._right))
        self._left = left
        self._right = right

    def append(self, other):
        return Pulse(np.append(self._waveform, other._waveform),
                     self._left,
                     self._right + other._right - other._left)

    @relative_timing
    def shift(self, length: int):
        return Pulse(self._waveform, self._left + length, self._right + length)

    @padding
    def __add__(self, other):
        other = other._waveform if isinstance(other, Pulse) else other
        return Pulse(self._waveform + other, self._left, self._right)

    def __radd__(self, other):
        return self.__add__(other)

    @padding
    def __mul__(self, other):
        other = other._waveform if isinstance(other, Pulse) else other
        return Pulse(self._waveform * other, self._left, self._right)

    def __rmul__(self, other):
        return self.__mul__(other)

    @padding
    def __sub__(self, other):
        other = other._waveform if isinstance(other, Pulse) else other
        return Pulse(self._waveform - other, self._left, self._right)

    def __rsub__(self, other):
        return other + (-self)

    def __pos__(self):
        return self

    def __neg__(self):
        return Pulse(-self._waveform, self._left, self._right)

    def __abs__(self):
        return Pulse(np.abs(self._waveform), self._left, self._right)

    @property
    def waveform(self):
        return self._cap(self._waveform)

    @waveform.setter
    def setter(self, val):
        pass

    def _cap(self, waveform):
        max_cap = np.ones(len(self._waveform))
        min_cap = -max_cap
        return np.minimum(np.maximum(waveform, min_cap), max_cap)


def broadcast(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if hasattr(args[0], "__iter__"):
            result_array = [f(arg0, *args[1:], **kwargs) for arg0 in args[0]]
            return np.array(result_array)
        else:
            return f(*args, **kwargs)
    return wrapper


@broadcast
def gauss(x: float, width: int, plateau: int):
    sigma = width / (2 * np.sqrt(2 * np.log(2)))
    if np.abs(x) <= plateau / 2:
        return 1
    elif np.abs(x) > plateau / 2:
        return np.exp(-(np.abs(x)-plateau/2) ** 2 / (2 * sigma ** 2))


@broadcast
def drag(x: float, width: int):
    sigma = width / (2 * np.sqrt(2 * np.log(2)))
    return - np.sqrt(np.e) * x * np.exp(- x ** 2 / (2 * sigma ** 2)) / sigma


@broadcast
def rectangle(x: float, width: int):
    if np.abs(x) <= width / 2:
        return 1
    else:
        return 0


@broadcast
def cos(x: float, width: int, plateau: int):
    if np.abs(x) <= plateau / 2:
        return 1
    elif np.abs(x) > plateau / 2 and np.abs(x) <= plateau / 2 + width:
        return (np.cos((np.abs(x)-plateau/2) * np.pi / width) + 1) / 2
    else:
        return 0


@broadcast
def ramp(x: float, width: int, amplitude_start: float, amplitude_end: float):
    if np.abs(x) < width / 2:
        avg = (amplitude_end + amplitude_start) / 2
        slope = (amplitude_end - amplitude_start) / width
        return x * slope + avg
    else:
        return 0


class Gaussian(Pulse):
    @relative_timing
    def __init__(sel, width: int, plateau: int = 0, cutoff: float = 5.) -> None:
        left = round(-plateau/2 - cutoff*width/2)
        right = -left + 1
        x = np.arange(left, right)
        waveform = gauss(x, width, plateau)
        super().__init__(waveform, left, right)


class Drag(Pulse):
    @relative_timing
    def __init__(self, width: int, cutoff: float = 5.) -> None:
        left = round(-cutoff*width/2)
        right = -left + 1
        x = np.arange(left, right)
        waveform = drag(x, width)
        super().__init__(waveform, left, right)


class Rect(Pulse):
    @relative_timing
    def __init__(self, width: int) -> None:
        left = round(-width/2)
        right = -left + 1
        x = np.arange(left, right)
        waveform = rectangle(x, width)
        super().__init__(waveform, left, right)


class Cosine(Pulse):
    @relative_timing
    def __init__(self, width: int, plateau: int = 0) -> None:
        left = round(-plateau/2 - width)
        right = -left + 1
        x = np.arange(left, right)
        waveform = cos(x, width, plateau)
        super().__init__(waveform, left, right)


class Ramp(Pulse):
    @relative_timing
    def __init__(self, width: int, amplitude_start: float, amplitude_end: float) -> None:
        left = round(-width/2)
        right = -left + 1
        x = np.arange(left, right)
        waveform = ramp(x, width, amplitude_start, amplitude_end)
        super().__init__(waveform, left, right)
