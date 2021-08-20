import zhinst.utils as zu
import numpy as np
import time


seq_length = 2400

seqc = f"""
// Trigger delay calibration sequence
wave w0_1 = placeholder({2*seq_length}, true);
wave w0_2 = placeholder({2*seq_length}, true);
repeat(1000){{
	playWave(w0_1, w0_2);
	playZero(120000);
}}
"""


def delay_calibration(awg, qa):
    waveform = np.zeros(2*seq_length)
    waveform[:seq_length] = np.linspace(0, 1, seq_length)
    waveform[seq_length:] = np.linspace(1, 0, seq_length)
    marker = np.ones(2*seq_length)
    waveform = zu.convert_awg_waveform(waveform, waveform, marker)

    # write the sequence file
    with open("calibration.seqc", "w") as f:
        f.write(seqc)

    awg.single(0)
    awg.set_sequence_params(sequence_type="Custom",
                            path="calibration.seqc")
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
    awg.run()

    # now capture the trace
    qa.qas[0].monitor.reset(1)
    qa.qas[0].monitor.averages(2048)
    qa.qas[0].monitor.length(4096)
    while True:
        if qa.qas[0].monitor.acquired() == 0:
            result = qa.qas[0].monitor.inputs[0].wave()
            break

    # now processing the data
    occurence = np.argmax(result)
    delay = seq_length/2.4e9 - occurence / 1.8e9

    return delay
