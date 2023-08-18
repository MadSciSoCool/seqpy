import numpy as np
from functools import wraps


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
def gauss(x, width, plateau, cutoff):
    range = plateau / 2 + cutoff * width / 2
    sigma = width / (2 * np.sqrt(2 * np.log(2)))
    if np.abs(x) <= plateau / 2:
        return 1
    elif np.abs(x) > range:
        return 0
    else:
        return np.exp(-((np.abs(x) - plateau / 2) ** 2) / (2 * sigma**2))


@broadcast
def drag(x, width, cutoff):
    range = cutoff * width / 2
    sigma = width / (2 * np.sqrt(2 * np.log(2)))
    if np.abs(x) > range:
        return 0
    else:
        return -np.sqrt(np.e) * x * np.exp(-(x**2) / (2 * sigma**2)) / sigma


@broadcast
def rectangle(x, width):
    if np.abs(x) <= width / 2:
        return 1
    else:
        return 0


@broadcast
def cos(x, width, plateau):
    if np.abs(x) <= plateau / 2:
        return 1
    elif np.abs(x) > plateau / 2 and np.abs(x) <= plateau / 2 + width:
        return (np.cos((np.abs(x) - plateau / 2) * np.pi / width) + 1) / 2
    else:
        return 0


@broadcast
def ramp(x, width, amplitude_start, amplitude_end):
    if np.abs(x) < width / 2:
        avg = (amplitude_end + amplitude_start) / 2
        slope = (amplitude_end - amplitude_start) / width
        return x * slope + avg
    else:
        return 0
