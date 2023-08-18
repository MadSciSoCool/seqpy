from .pulses import Pulse, Carrier
import numpy as np
import matplotlib.pyplot as plt


class Sequence:
    def __init__(self, n_channels: int = 1):
        super().__init__()
        n_channels = int(n_channels)
        if n_channels < 0:
            raise Exception("n_channels could only be a postive integer")
        # for each channel
        self._pulses = list()
        [self._pulses.append(list()) for i in range(n_channels)]
        # trigger related
        self._trigger_pos = [0]
        self.marker_width = 5e-8  # default value
        self.sample_frequency = 2.4e9
        # time range of the pulses
        self.left = 0
        self.right = 0
        # default sample frequency
        # output waveform related
        self._waveforms = list()
        [self._waveforms.append(np.array([])) for i in range(n_channels)]

    def register(
        self, position, pulse, carrier=None, frequency=None, phase=None, channel=None
    ):
        if not carrier:
            if frequency is None or phase is None:
                raise Exception("Please provide information for carrier!")
            carrier = Carrier(frequency, phase)
        if not channel and not isinstance(channel, int):
            for c in self._pulses:
                c.append((position, pulse, carrier))
        else:
            self._pulses[channel].append((position, pulse, carrier))

    @property
    def trigger_pos(self):
        return np.array(self._trigger_pos)

    @trigger_pos.setter
    def trigger_pos(self, position):
        # position: either list or float, will be converted to a iterable object anyway
        position = [position] if not hasattr(position, "__iter__") else position
        self._trigger_pos = position

    def _get_time_axis(self):
        len = np.ceil((self.right - self.left) * self.sample_frequency)
        # padded to make the waveform to align with 16 samples (artifacts of zhinst)
        padding = (-len % 16) / self.sample_frequency
        return np.arange(self.left, self.right + padding, 1 / self.sample_frequency)

    def length(self):
        return len(self._get_time_axis())

    def waveforms(self, samp_freq):
        self.sample_frequency = samp_freq
        seq = list()
        for ps in self._pulses:
            base = Pulse(left=np.inf, right=-np.inf)
            for position, pulse, carrier in ps:
                base += carrier * pulse.shift(position)
            seq.append(base)
        # padding all channels to have the same length
        left = np.inf
        right = -np.inf
        for ch in seq:
            if ch._left < left:
                left = ch._left
            if ch._right > right:
                right = ch._right
        # the range should include trigger position
        trig_left = np.min(self.trigger_pos)  # in samples
        trig_right = np.max(self.trigger_pos) + self.marker_width
        self.left = min(left, trig_left)
        self.right = max(right, trig_right)
        # converted to time axis
        time_axis = self._get_time_axis()
        return [self._cap(ch.waveform(time_axis)) for ch in seq]

    @staticmethod
    def _cap(waveform):
        max_cap = np.ones(len(waveform))
        min_cap = -max_cap
        return np.minimum(np.maximum(waveform, min_cap), max_cap)

    def plot(self):
        fig, ax = plt.subplots()
        waveforms = self.waveforms(self.sample_frequency)
        x_axis = self._get_time_axis()
        for i in range(len(waveforms)):
            ax.plot(x_axis, waveforms[i], label=f"channel{i}")
        ax.plot(x_axis, self.marker_waveform(), label="marker")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Relative Amplitude")
        fig.legend()
        return fig

    def marker_waveform(self):
        time_axis = self._get_time_axis()
        base = np.zeros(self.length())
        for trig in self.trigger_pos:
            trig_end = trig + self.marker_width
            base[np.all([time_axis < trig_end, time_axis >= trig], axis=0)] = 1
        return base
