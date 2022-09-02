from scipy.interpolate import interp1d
from seqpy.pulses import Carrier


class IQShifter:
    def __init__(self, shifted_channel="Q", interpolation="1d"):
        self.shifted_channel = shifted_channel
        if interpolation == "1d":
            self.interpolation = interp1d
        self.amp_curve = lambda x: 1
        self.phase_curve = lambda x: 0

    def load_amplitude_calibration(self, freq, optimal_amp):
        self.amp_curve = self.interpolation(freq, optimal_amp)

    def load_phase_calibration(self, freq, optimal_phase):
        self.phase_curve = self.interpolation(freq, optimal_phase)

    def shift(self, I):
        frequency, phase = I.frequency, I.phase
        return self.amp_curve(frequency) * Carrier(frequency, phase - 90 + self.phase_curve(frequency))
