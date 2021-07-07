import numpy as np
from functools import wraps, partial
from scipy.misc import derivative

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

    def _carrier(self, length):
        x = np.arange(length) / SAMPLING_FREQUENCY
        carrier = np.ones(length)
        for phase, frequency in zip(self.phases, self.frequencies):
            phase_in_rad = phase * np.pi / 180
            carrier = carrier * \
                np.cos(2 * np.pi * frequency * x + phase_in_rad)
        return carrier


class Pulse:
    def padding_length(f):
        @wraps(f)
        def wrapper(self, other):
            if isinstance(other, Pulse):
                if self._len > other._len:
                    other._pad(self._len)
                else:
                    self._pad(other._len)
            return f(self, other)
        return wrapper

    def __init__(self, waveform, carrier_phases=(), carrier_frequencies=()) -> None:
        self._waveform = waveform
        self._len = len(self._waveform)
        self.carrier = Carrier(carrier_phases, carrier_frequencies)

    def _pad(self, length):
        if length > self._len:
            self._waveform = np.append(
                self._waveform, np.zeros(length-self._len))
            self._len = length

    @padding_length
    def __add__(self, other):
        other = other.waveform if isinstance(other, Pulse) else other
        return Pulse(self.waveform + other)

    def __radd__(self, other):
        return self.__add__(other)

    @padding_length
    def __mul__(self, other):
        other = other.waveform if isinstance(other, Pulse) else other
        return Pulse(self.waveform * other)

    def __rmul__(self, other):
        return self.__mul__(other)

    @padding_length
    def __sub__(self, other):
        other = other.waveform if isinstance(other, Pulse) else other
        return Pulse(self.waveform - other)

    def __rsub__(self, other):
        return other + (-self)

    def __pos__(self):
        return self

    def __neg__(self):
        return Pulse(-self.waveform)

    def __abs__(self):
        return Pulse(np.abs(self.waveform))

    @property
    def waveform(self):
        return self._cap(self._waveform * self.carrier._carrier(self._len))

    @waveform.setter
    def setter(self, val):
        pass

    def _cap(self, waveform):
        max_cap = np.ones(self._len)
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
def gauss(x: float, pos: int, width: int, plateau: int, cutoff: float):
    sigma = width / (2 * np.sqrt(2 * np.log(2)))
    dist = np.abs(x - pos)
    if dist <= plateau / 2:
        return 1
    elif dist > plateau / 2 and dist <= plateau / 2 + cutoff * width / 2:
        return np.exp(-(dist-plateau/2) ** 2 / (2 * sigma ** 2))
    else:
        return 0


@broadcast
def drag(x: float, pos: int, width: int, cutoff: float):
    sigma = width / (2 * np.sqrt(2 * np.log(2)))
    return - np.sqrt(np.e) * (pos - x) * np.exp(-(x - pos) ** 2 / (2 * sigma ** 2)) / sigma


@broadcast
def rectangle(x: float, pos: int, width: int):
    dist = np.abs(x - pos)
    if dist <= width / 2:
        return 1
    else:
        return 0


@broadcast
def cos(x: float, pos: int, width: int, plateau: int):
    dist = np.abs(x - pos)
    if dist <= plateau / 2:
        return 1
    elif dist > plateau / 2 and dist <= plateau / 2 + width:
        return (np.cos((dist-plateau/2) * np.pi / width) + 1) / 2
    else:
        return 0


@broadcast
def ramp(x: float, pos: int, width: int, amplitude_start: float, amplitude_end: float):
    if np.abs(x - pos) < width / 2:
        avg = (amplitude_end + amplitude_start) / 2
        slope = (amplitude_end - amplitude_start) / width
        return (x - pos) * slope + avg
    else:
        return 0


class Gaussian(Pulse):
    @relative_timing
    def __init__(sel, width: int, pos: int = 0, plateau: int = 0, cutoff: float = 5., carrier_phases=(), carrier_frequencies=()) -> None:
        length = int(pos + plateau / 2 + cutoff * width / 2)
        x = np.arange(length)
        waveform = gauss(x, pos, width, plateau, cutoff)
        super().__init__(waveform=waveform, carrier_phases=carrier_phases,
                         carrier_frequencies=carrier_frequencies)


class Drag(Pulse):
    @relative_timing
    def __init__(self, width: int, pos: int = 0, cutoff: float = 5., carrier_phases=(), carrier_frequencies=()) -> None:
        length = int(pos + cutoff * width / 2)
        x = np.arange(length)
        waveform = drag(x, pos, width, cutoff)
        super().__init__(waveform=waveform, carrier_phases=carrier_phases,
                         carrier_frequencies=carrier_frequencies)


class Rect(Pulse):
    @relative_timing
    def __init__(self, width: int, pos: int = 0, carrier_phases=(), carrier_frequencies=()) -> None:
        length = int(pos + width / 2)
        x = np.arange(length)
        waveform = rectangle(x, pos, width)
        super().__init__(waveform=waveform, carrier_phases=carrier_phases,
                         carrier_frequencies=carrier_frequencies)


class Cosine(Pulse):
    @relative_timing
    def __init__(self, width: int, pos: int = 0, plateau: int = 0, carrier_phases=(), carrier_frequencies=()) -> None:
        length = int(pos + plateau / 2 + width)
        x = np.arange(length)
        waveform = cos(x, pos, width, plateau)
        super().__init__(waveform=waveform, carrier_phases=carrier_phases,
                         carrier_frequencies=carrier_frequencies)


class Ramp(Pulse):
    @relative_timing
    def __init__(self, width: int, amplitude_start: float, amplitude_end: float, pos: int = 0, carrier_phases=(), carrier_frequencies=()) -> None:
        length = int(pos + width)
        x = np.arange(length)
        waveform = ramp(x, pos, width, amplitude_start, amplitude_end)
        super().__init__(waveform=waveform, carrier_phases=carrier_phases,
                         carrier_frequencies=carrier_frequencies)
