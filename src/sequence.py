from .pulses import Pulse, Carrier, relative_timing
from warnings import warn


class Sequence:
    def __init__(self, n_channels: int = 1):
        if n_channels > 2:
            warn("currently n_channels could only be 1/2")
        self._pulses = [[]] * n_channels
        self._trigger_pos = 0
        self._alignment = "zero"

    @relative_timing
    def register(self, position: int, pulse: Pulse, carrier: Carrier = None, carrier_phases: tuple = (), carrier_frequencies=(), channel=None):
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

    def phase_alignment(self, mode):
        if mode not in ("zero", "trigger"):
            warn("phase alignment mode should be chosen in zero/trigger")
        else:
            self._alignment = mode
