import zhinst.utils as zu
from .seqc_generation import seqc_generation


def update_zhinst_awg(awg_core, sequence, path=""):
    waveforms = sequence.waveforms()
    if len(waveforms) == 1:
        w1 = waveforms
        w2 = waveforms
    else:
        w1, w2 = waveforms
    waveform = zu.convert_awg_waveform(w1, w2, sequence.marker_waveform())
    seqc = seqc_generation(sequence, path)
    awg_core.set_sequence_params(sequence_type="Custom",
                                 path=seqc._filepath)
    awg_core.reset_queue()
    awg_core._waveforms = [waveform]
    awg_core.compile_and_upload_waveforms()
