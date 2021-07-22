import zhinst.utils as zu
from .seqc_generation import seqc_generation


def update_zhinst_awg(awg, sequence, path=""):
    waveforms = sequence.waveforms()
    if len(waveforms) == 1:
        w1 = waveforms[0]
        w2 = waveforms[0]
    else:
        w1, w2 = waveforms
    waveform = zu.convert_awg_waveform(w1, w2, sequence.marker_waveform())
    seqc = seqc_generation(sequence, path)
    seqc.make_file()
    awg.set_sequence_params(sequence_type="Custom",
                            path=seqc._filepath)
    awg.reset_queue()
    # cheat the awg module

    class WaveformContainer:
        def __init__(self, data) -> None:
            self.data = data
    if "qcodes" in str(type(awg)):
        awg._awg._waveforms = [WaveformContainer(waveform)]
    else:
        awg._waveforms = [WaveformContainer(waveform)]
    awg.compile_and_upload_waveforms()
