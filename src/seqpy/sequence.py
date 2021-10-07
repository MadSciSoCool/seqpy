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
        self._period = 100e-6 * \
            config.retrieve("SAMPLING_FREQUENCY")  # default
        self._repetitions = 1e3  # default
        self.left = 0
        self.right = 0
        self._changed = False
        self._waveforms = list()
        [self._waveforms.append(np.array([])) for i in range(n_channels)]

    def register(self, position, pulse, carrier=None, carrier_phases=(), carrier_frequencies=(), channel=None):
        if not carrier:
            carrier = Carrier(carrier_phases, carrier_frequencies)
        if not channel and not isinstance(channel, int):
            for c in self._pulses:
                c.append((position, pulse, carrier))
        else:
            self._pulses[channel].append((position, pulse, carrier))
        self._changed = True

    @property
    def trigger_pos(self):
        return self.retrieve_value(self._trigger_pos)

    @trigger_pos.setter
    def trigger_pos(self, position: int):
        self._trigger_pos = position

    def length(self):
        return len(self.waveforms()[0])

    def waveforms(self):
        if self._changed:
            samp_freq = config.retrieve("SAMPLING_FREQUENCY")
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
            # update values of sweepables
            for k, v in self._sweepable_mapping.items():
                for wf in waveforms:
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
                "TRIGGER_DELAY")*samp_freq  # in samples
            trig_pos = self.trigger_pos*samp_freq if config.retrieve(
                "PHASE_ALIGNMENT") == "Zero" else 0  # in samples
            trig_left = trig_pos - delay_offset - 100  # in samples
            trig_right = trig_pos - delay_offset + 100  # in samples
            left = min(left, trig_left)
            right = max(right, trig_right)
            # padded to make the waveform to align with 16 samples (artifacts of zhinst)
            right += (left - right) % 16
            wf_data = [wf._pad(wf.waveform, int(left), int(right))
                       for wf in waveforms]
            self.right = right + offset*samp_freq  # in sample
            self.left = left + offset*samp_freq  # in sample
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
        x_axis = np.arange(self.left, self.right) / \
            config.retrieve("SAMPLING_FREQUENCY")
        for i in range(len(waveforms)):
            plt.plot(x_axis, waveforms[i], label=f"channel{i}")
        ax.plot(x_axis, self.marker_waveform(delay=False), label="marker")
        fig.legend()
        return fig

    def marker_waveform(self, delay=True):
        samp_freq = config.retrieve("SAMPLING_FREQUENCY")
        base = np.zeros(self.length())
        delay_offset = config.retrieve(
            "TRIGGER_DELAY")*samp_freq if delay else 0  # in samples
        base[int(self.trigger_pos*samp_freq - self.left-delay_offset):] = 1
        return base

    def dump(self, file):
        dumped = dict()
        dumped["trigger pos"] = str(self._trigger_pos)
        dumped["period"] = str(self._period)
        dumped["repetitions"] = str(self._repetitions)
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
            n_channels = len(dumped) - 3
            self.__init__(n_channels)
            self._trigger_pos = str2expr(dumped["trigger pos"])
            self._period = str2expr(dumped["period"])
            self._repetitions = str2expr(dumped["repetitions"])
            sym_list |= collect_sym(
                (dumped["trigger pos"], dumped["period"], dumped["repetitions"]))
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
