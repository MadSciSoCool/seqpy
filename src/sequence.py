from .pulses import Pulse, Carrier, relative_timing, SAMPLING_FREQUENCY, USE_RELATIVE_TIMING
from warnings import warn
import numpy as np
import matplotlib.pyplot as plt

TRIGGER_DELAY = 0


def set_trigger_delay(value):
    global TRIGGER_DELAY
    TRIGGER_DELAY = value


class Sequence:
    def __init__(self, n_channels: int = 1):
        if n_channels > 2:
            warn("currently n_channels could only be 1/2")
        self._pulses = [[]] * n_channels
        self._trigger_pos = 0
        self._period = 1e-6 * 2.4e9  # default
        self._iterations = 1e3  # default
        self.left = 0
        self.right = 0
        self._alignment = "zero"

    @relative_timing
    def register(self, position: int, pulse: Pulse, carrier: Carrier = None, carrier_phases: tuple = (), carrier_frequencies: tuple = (), channel: int = None):
        if not carrier:
            carrier = Carrier(carrier_phases, carrier_frequencies)
        if channel is None:
            for channel in self._pulses:
                channel.append((position, pulse, carrier))
        else:
            self._pulses[channel-1].append((position, pulse, carrier))

    @relative_timing
    def trigger_pos(self, position: int):
        self._trigger_pos = position

    @relative_timing
    def period(self, period: int):
        self._period = period

    def iteration(self, iterations: int):
        self._iterations = iterations

    def phase_alignment(self, mode):
        if mode not in ("zero", "trigger"):
            warn("phase alignment mode should be chosen in zero/trigger")
        else:
            self._alignment = mode

    def length(self):
        return len(self.waveforms()[0])

    def waveforms(self):
        offset = 0 if self._alignment == "zero" else self._trigger_pos
        waveforms = list()
        for channel in self._pulses:
            base = Pulse([], left=0, right=0)
            for position, pulse, carrier in channel:
                shifted = pulse.shift(position - offset)
                shifted._waveform = shifted._waveform * \
                    carrier.waveform(len(shifted.waveform))
                base += shifted
            waveforms.append(base)
        # padding all channels to have the same length
        left = np.inf
        right = -np.inf
        for wf in waveforms:
            if wf._left < left:
                left = wf._left
            if wf._right > right:
                right = wf._right
        # acount for the trigger offset
        left = left - 1000
        # padded to make the waveform to align with 16 samples (artifacts of zhinst)
        right += (left - right) % 16
        for wf in waveforms:
            wf._pad(left, right)
        self.right = base._right + offset
        self.left = base._left + offset
        return [wf.waveform for wf in waveforms]

    def plot(self):
        fig, ax = plt.subplots()
        waveforms = self.waveforms()
        x_axis = np.arange(self.left, self.right)
        if USE_RELATIVE_TIMING:
            x_axis = x_axis / SAMPLING_FREQUENCY
        for i in range(len(waveforms)):
            plt.plot(x_axis, waveforms[i], label=f"channel{i}")
        ax.plot(x_axis, self.marker_waveform(delay=False), label="marker")
        fig.legend()
        return fig

    def marker_waveform(self, delay=True):
        base = np.zeros(self.length())
        delay_offset = TRIGGER_DELAY if delay else 0
        base[self._trigger_pos-self.left-delay_offset:] = 1
        return base
