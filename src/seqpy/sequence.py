from .pulses import (Pulse, Carrier, Sweepable, SweepableExpr, config)
from .utils.pulse_reconstruction import reconstruct, str2expr, collect_sym
import numpy as np
import matplotlib.pyplot as plt
import json


class Sequence(SweepableExpr):
    def __init__(self, n_channels: int = 1):
        super().__init__()
        n_channels = int(n_channels)
        if n_channels < 0:
            raise Exception("n_channels could only be a postive integer")
        self._pulses = list()
        [self._pulses.append(list()) for i in range(n_channels)]
        self._trigger_pos = 0
        self.left = 0
        self.right = 0
        self._changed = False
        self._waveforms = list()
        self._samp_freq = None
        self._cached_samp_freq = 0
        [self._waveforms.append(np.array([])) for i in range(n_channels)]

    def register(self, position, pulse, carrier=None, frequency=None, phase=None, channel=None):
        if not carrier:
            if frequency is None or phase is None:
                raise Exception("Please provide information for carrier!")
            carrier = Carrier(frequency, phase)
        if not channel and not isinstance(channel, int):
            for c in self._pulses:
                c.append((position, pulse, carrier))
        else:
            self._pulses[channel].append((position, pulse, carrier))
        self._changed = True

    def subs(self, sym, value):
        super().subs(sym, value)
        self._changed = True

    @property
    def trigger_pos(self):
        return self.retrieve_value(self._trigger_pos)

    @trigger_pos.setter
    def trigger_pos(self, position: int):
        self._trigger_pos = position

    def length(self):
        return len(self.waveforms()[0])

    def waveforms(self, samp_freq=None):
        if samp_freq:
            self.samp_freq = samp_freq
        freq_changed_flag = False
        if self.samp_freq != self._cached_samp_freq:
            freq_changed_flag = True
            self._cached_samp_freq = self.samp_freq
        if self._changed or config.is_changed or freq_changed_flag:
            offset = 0 if config.retrieve(
                "PHASE_ALIGNMENT") == "Zero" else self.trigger_pos  # in time
            waveforms = list()
            for channel in self._pulses:
                base = Pulse(left=np.inf, right=-np.inf)
                for position, pulse, carrier in channel:
                    shifting_amount = self.retrieve_value(
                        position) - offset  # in time
                    shifted = pulse.shift(shifting_amount)  # in time
                    base += carrier * shifted
                waveforms.append(base)
            # update values of sweepables and sampling frequencies
            for wf in waveforms:
                wf.samp_freq = self.samp_freq
                for k, v in self._sweepable_mapping.items():
                    wf.subs(k, v)
            # padding all channels to have the same length
            left = np.inf
            right = -np.inf
            for wf in waveforms:
                if wf.left < left:
                    left = wf.left
                if wf.right > right:
                    right = wf.right
            # the range should include trigger position
            delay_offset = config.retrieve(
                "TRIGGER_DELAY")*self.samp_freq  # in samples
            trig_pos = self.trigger_pos*self.samp_freq if config.retrieve(
                "PHASE_ALIGNMENT") == "Zero" else 0  # in samples
            trig_left = trig_pos - delay_offset - 100  # in samples
            trig_right = trig_pos - delay_offset + 100  # in samples
            left = min(left, trig_left)
            right = max(right, trig_right)
            # padded to make the waveform to align with 16 samples (artifacts of zhinst)
            right += (left - right) % 16
            wf_data = [wf._pad(wf.waveform, int(left), int(right))
                       for wf in waveforms]
            self.right = right + offset * self.samp_freq  # in sample
            self.left = left + offset * self.samp_freq  # in sample
            self._waveforms = [self._cap(wf) for wf in wf_data]
            self._changed = False
        return self._waveforms

    @staticmethod
    def _cap(waveform):
        max_cap = np.ones(len(waveform))
        min_cap = -max_cap
        return np.minimum(np.maximum(waveform, min_cap), max_cap)

    def plot(self):
        fig, ax = plt.subplots()
        waveforms = self.waveforms()
        x_axis = np.arange(self.left, self.right) / self.samp_freq
        for i in range(len(waveforms)):
            plt.plot(x_axis, waveforms[i], label=f"channel{i}")
        ax.plot(x_axis, self.marker_waveform(delay=False), label="marker")
        fig.legend()
        return fig

    def marker_waveform(self, delay=True):
        base = np.zeros(self.length())
        delay_offset = config.retrieve(
            "TRIGGER_DELAY")*self.samp_freq if delay else 0  # in samples
        base[int(self.trigger_pos*self.samp_freq - self.left-delay_offset):] = 1
        return base

    def dump(self, file):
        dumped = dict()
        dumped["trigger pos"] = str(self._trigger_pos)
        for i, channel in enumerate(self._pulses):
            dumped[i] = dict()
            for j, (position, pulse, carrier) in enumerate(channel):
                dumped[i][j] = dict()
                dumped[i][j]["position"] = str(position)
                dumped[i][j]["pulse"] = pulse.dump()
                dumped[i][j]["carrier"] = carrier.dump()
        with open(file, "w") as f:
            f.writelines(json.dumps(dumped, indent=4))

    def load(self, file):
        with open(file, "r") as f:
            sym_list = set()
            dumped = json.load(f)
            n_channels = len(dumped) - 1
            self.__init__(n_channels)
            self._trigger_pos = str2expr(dumped["trigger pos"])
            sym_list |= collect_sym(dumped["trigger pos"])
            for i in range(n_channels):
                for k, v in dumped[str(i)].items():
                    position = str2expr(v["position"])
                    sym_list |= collect_sym(v["position"])
                    pulse, syms = reconstruct(v["pulse"])
                    sym_list |= syms
                    carrier, syms = reconstruct(v["carrier"])
                    sym_list |= syms
                    self.register(position, pulse, carrier, channel=i)
            return [Sweepable(sym) for sym in sym_list]

    @property
    def samp_freq(self):
        return self._samp_freq if self._samp_freq else config.retrieve("SAMPLING_FREQUENCY")

    @samp_freq.setter
    def samp_freq(self, value):
        self._samp_freq = value
