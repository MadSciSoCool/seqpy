from .pulses import (Pulse, Carrier, relative_timing,
                     SAMPLING_FREQUENCY, USE_RELATIVE_TIMING, PHASE_ALIGNMENT, SweepableExpr)
from warnings import warn
import numpy as np
import matplotlib.pyplot as plt

TRIGGER_DELAY = 0


def set_trigger_delay(value):
    global TRIGGER_DELAY
    TRIGGER_DELAY = value


class Sequence(SweepableExpr):
    def __init__(self, n_channels: int = 1):
        super().__init__()
        n_channels = int(n_channels)
        if n_channels < 0 or n_channels > 2:
            raise Exception(
                "n_channels could only be a postive integer at most 8")
        self._pulses = list()
        [self._pulses.append(list()) for i in range(n_channels)]
        self._trigger_pos = 0
        self._period = 1e-6 * 2.4e9  # default
        self._repetitions = 1e3  # default
        self.left = 0
        self.right = 0

    @relative_timing
    def register(self, position: int, pulse: Pulse, carrier: Carrier = None, carrier_phases: tuple = (), carrier_frequencies: tuple = (), channel: "channel" = None):
        if not carrier:
            carrier = Carrier(carrier_phases, carrier_frequencies)
        if not channel and not isinstance(channel, int):
            for c in self._pulses:
                c.append((position, pulse, carrier))
        else:
            self._pulses[channel].append((position, pulse, carrier))

    @relative_timing
    def trigger_pos(self, position: int):
        self._trigger_pos = position

    @relative_timing
    def period(self, period: int):
        self._period = period

    def repetitions(self, repetitions: int):
        self._repetitions = repetitions

    def length(self):
        return len(self.waveforms()[0])

    def waveforms(self):
        self._update_sweepables_values()
        offset = 0 if PHASE_ALIGNMENT == "zero" else self._trigger_pos
        waveforms = list()
        for channel in self._pulses:
            base = Pulse(left=np.inf, right=-np.inf)
            for position, pulse, carrier in channel:
                shifted = pulse.shift(self.retrieve_value(position) - offset)
                base += shifted * carrier
            waveforms.append(base)
        # padding all channels to have the same length
        left = np.inf
        right = -np.inf
        for wf in waveforms:
            if wf.left < left:
                left = wf.left
            if wf.right > right:
                right = wf.right
        # acount for the trigger offset
        left = left - 1000
        # padded to make the waveform to align with 16 samples (artifacts of zhinst)
        right += (left - right) % 16
        wf_data = [wf._pad(wf.waveform, left, right) for wf in waveforms]
        self.right = right + offset
        self.left = left + offset
        return [self._cap(wf) for wf in wf_data]

    @staticmethod
    def _cap(waveform):
        max_cap = np.ones(len(waveform))
        min_cap = -max_cap
        return np.minimum(np.maximum(waveform, min_cap), max_cap)

    def plot(self):
        fig, ax = plt.subplots()
        waveforms = self.waveforms()
        x_axis = np.arange(self.left, self.right)
        if not USE_RELATIVE_TIMING:
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

    def _update_sweepables_values(self):
        for k, v in self._sweepable_mapping.items():
            for channel in self._pulses:
                for position, pulse, carrier in channel:
                    pulse.subs(k, v)
                    carrier.subs(k, v)

    # def save():

    # def load():
