from os import path
import zhinst.utils as zu
import numpy as np

# ----------------------------------------------------------
#
#    helper .seQc file generation
#
# ----------------------------------------------------------


class SeqcFile:
    def __init__(self, n_channels, filepath="") -> None:
        self.file_string = ""
        self._indentation = False
        self._n_channels = n_channels
        self.make_header()
        self._filepath = path.join(filepath, "autogenerated.seqc")

    def make_file(self):
        with open(self._filepath, "w") as f:
            f.write(self.file_string)

    def make_header(self):
        self.comment_line("Auto generated by SeqPy")

    def define_placeholder(self, length):
        # declare placeholder
        for i in range(self._n_channels):
            self._writeline(f"wave w_{i+1} = placeholder({length:d}, true);")
        # assign placeholder
        # self._writeline(f"assignWaveIndex(w{index}_1, w{index}_2, 0);")

    def wait(self, samples):
        self._writeline(f"playZero({int(samples):d});")
        # PlayZero should be better for shorter wait time, otherwise use wait, while wait(1) is actually 3 clock cycles
        # self._writeline(f"wait({int(samples):d});")

    def play_wave(self):
        arguments = ", ".join(
            [f"{i+1}, w_{i+1}" for i in range(self._n_channels)])
        self._writeline(f"playWave({arguments});")

    def start_main_loop(self, iterations):
        self._writeline(f"repeat({int(iterations):d}){{")
        self._indentation = True

    def end_main_loop(self):
        self._indentation = False
        self._writeline("}")

    def comment_line(self, str):
        self._writeline(f"// {str}")

    def _writeline(self, str):
        if self._indentation:
            self.file_string += f"\t{str}\n"
        else:
            self.file_string += f"{str}\n"


def seqc_generation(sequence, n_channels, filepath=""):
    # write the .seqC file
    wave_length = sequence.length()
    seqc_file = SeqcFile(n_channels, filepath)
    seqc_file.define_placeholder(wave_length)
    seqc_file.start_main_loop(sequence.repetitions)
    seqc_file.play_wave()
    # offset to be confirmed
    seqc_file.wait(max(sequence.period - wave_length, 0))
    seqc_file.end_main_loop()
    return seqc_file

# ----------------------------------------------------------
#
#    zhinst wrapper
#
# ----------------------------------------------------------

# cheat the awg module


class WaveformContainer:
    def __init__(self, data) -> None:
        self.data = data


def update_zhinst_awg(awg, sequence, path=""):
    awg.reset_queue()
    waveforms = sequence.waveforms()
    n_channels = len(waveforms)
    if n_channels % 2 == 1:
        waveforms.append(np.zeros(sequence.length()))
        n_channels += 1
    for i in range(n_channels//2):
        waveform = zu.convert_awg_waveform(
            waveforms[2 * i], waveforms[2 * i + 1], sequence.marker_waveform())
        if "qcodes" in str(type(awg)):
            awg._awg._waveforms.append(WaveformContainer(waveform))
        else:
            awg._waveforms.append(WaveformContainer(waveform))
    seqc = seqc_generation(sequence, n_channels, path)
    seqc.make_file()
    awg.set_sequence_params(sequence_type="Custom",
                            path=seqc._filepath)
    awg.compile_and_upload_waveforms()

# ----------------------------------------------------------
#
#    delay calibration
#
# ----------------------------------------------------------


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
