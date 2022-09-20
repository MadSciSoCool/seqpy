from sympy import Piecewise
from sympy.abc import x
from seqpy.pulses import Carrier
import numpy as np


def interpolating_linear(sym, xdata, ydata):
    sorted_ind = np.argsort(xdata)
    xdata = xdata[sorted_ind]
    ydata = ydata[sorted_ind]
    args = list()
    for i in range(len(xdata) - 1):
        xa, xb = xdata[i], xdata[i+1]
        ya, yb = ydata[i], ydata[i+1]
        cond = (sym >= xa) & (sym <= xb)
        expr = ya + (sym - xa) * (yb - ya) / (xb - xa)
        args.append((expr, cond))
    return Piecewise(*args)


class IQShifter:
    def __init__(self, shifted_channel="Q"):
        self.shifted_channel = shifted_channel
        self.amp_curve = lambda x: 1
        self.phase_curve = lambda x: 0

    def load_amplitude_calibration(self, freq, optimal_amp):
        self.amp_curve = interpolating_linear(x, freq, optimal_amp)

    def load_phase_calibration(self, freq, optimal_phase):
        self.phase_curve = interpolating_linear(x, freq, optimal_phase)

    def shift(self, I):
        frequency, phase = I.frequency, I.phase
        shifted_amp = self.amp_curve.subs(x, I.frequency)
        shifted_phase = self.phase_curve.subs(x, I.frequency)
        return shifted_amp * Carrier(frequency, phase - 90 + shifted_phase)
