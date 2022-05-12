from os import path
import zhinst.utils as zu
import numpy as np
import copy

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

    def define_placeholder(self, length, i, j, marker=True):
        # declare placeholder
        marker_option = "true" if marker else "false"
        self._writeline(
            f"wave w_{i:d}_{j:d} = placeholder({length:d}, {marker_option});")
        # assign placeholder
        # self._writeline(f"assignWaveIndex(w{index}_1, w{index}_2, 0);")

    def wait(self, samples):
        self._writeline(f"playZero({int(samples):d});")
        # PlayZero should be better for shorter wait time, otherwise use wait, while wait(1) is actually 3 clock cycles
        # self._writeline(f"wait({int(samples/8):d});")

    def awg_monitor_trig(self):
        self._writeline("waitDigTrigger(1, 1);")
        self._writeline("setTrigger(AWG_MONITOR_TRIGGER);")
        self._writeline("setTrigger(0);")

    def play_wave(self, *args):
        arguments = ", ".join(
            [f"{channel+1}, w_{i}_{j}" for (channel, i, j) in args])
        self._writeline(f"playWave({arguments});")

    def start_main_loop(self, iterations):
        if iterations < 0:
            self._writeline(f"while(true){{")
        else:
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


def seqc_generation(active_times, n_channels, total_length, repetitions, period, file_path=""):
    # write the .seqC file
    n_waveforms = len(active_times)
    seqc_file = SeqcFile(n_channels, file_path)
    # define all placeholders
    for i in range(n_channels):
        for j, (start, end) in enumerate(active_times):
            seqc_file.define_placeholder(end-start, i, j)
    seqc_file.start_main_loop(repetitions)
    for i in range(len(active_times)):
        args = [(j, j, i) for j in range(n_channels)]
        seqc_file.play_wave(*args)
        if i < n_waveforms - 1:
            seqc_file.wait(active_times[i+1][0] - active_times[i][1])
    # offset to be confirmed
    seqc_file.wait(max(period - total_length, 1))
    seqc_file.end_main_loop()
    return seqc_file


def readout_seqc_generation(total_length, file_path):
    seqc_file = SeqcFile(2, file_path)
    for i in range(2):
        seqc_file.define_placeholder(total_length, i, 0, marker=False)
    seqc_file.start_main_loop(-1)
    seqc_file.awg_monitor_trig()
    seqc_file.play_wave((0, 0, 0), (1, 1, 0))
    seqc_file.end_main_loop()
    return seqc_file


# ----------------------------------------------------------
#
#    zhinst wrapper
#
# ----------------------------------------------------------
def find_active_time(waveforms, threshold=150000):
    # find the period where at least one channel is not zero
    nonzero = np.any(np.array(waveforms), axis=0)
    nonzero_16 = np.any(nonzero.reshape(16, -1), axis=0)
    print(nonzero_16.shape)
    print(nonzero_16)
    length_16 = len(nonzero_16)
    active_times = list()
    active_flag = False
    p = 0  # current pointer position
    ps = 0  # starting position of this active period
    dead_l = 0  # length of the
    while p < length_16:
        if nonzero_16[p]:  # if current pointer is not zero
            dead_l = 0
            if not active_flag:
                active_flag = True  # if previously not a zero period, now entering one
                ps = p  # register the starting point
        else:  # if current pointer is zero
            if active_flag:
                dead_l = dead_l + 1
                if dead_l * 16 > threshold:
                    active_flag = False  # if previously a zero period, now exiting
                    # add this period if its length beyond the threshold
                    active_times.append((ps*16, (p+1-dead_l)*16))
                    dead_l = 0
        p = p + 1
    # handle last active period
    if active_flag:
        active_times.append((ps*16, p*16))
    return active_times

# cheat the awg module


class WaveformContainer:
    def __init__(self, data) -> None:
        self.data = data


def update_zhinst_awg(awg, sequence, period, repetitions, path="", samp_freq=None):
    waveforms = copy.deepcopy(sequence.waveforms(samp_freq=samp_freq))
    length = sequence.length()
    # pad one channel if odd
    n_channels = len(waveforms)
    if n_channels > 8:
        raise(Exception(
            "the maximum channel number supported for Zurich Instruments HDAWG is 8."))
    if n_channels % 2 == 1:
        waveforms.append(np.zeros(sequence.length()))
        n_channels += 1
    # here change the awg grouping
    awg.awgs[0].stop()  # need to stop before change channel grouping
    # check from toolkit or qcodes
    if "qcodes" in str(type(awg)):
        awg.system.awg.channelgrouping(
            np.log2(n_channels - 1))  # 0->2*4, 1->4*2, 2->8*1
    elif "toolkit" in str(type(awg)):
        awg.nodetree.system.awg.channelgrouping(np.log2(n_channels - 1))
    # pad waveform to multiple of 16 samples
    waveforms = np.hstack((waveforms, np.zeros((n_channels, -length % 16))))
    # find active time
    active_times = find_active_time(waveforms + [sequence.marker_waveform()])
    # upload the .seqc file
    seqc = seqc_generation(active_times=active_times,
                           n_channels=n_channels,
                           total_length=sequence.length(),
                           repetitions=repetitions,
                           period=period,
                           file_path=path)
    seqc.make_file()
    awg.awgs[0].set_sequence_params(sequence_type="Custom",
                                    path=seqc._filepath)
    # queue the waveforms
    for i in range(n_channels//2):
        awg.awgs[i].reset_queue()
    for i in range(n_channels//2):
        for start, end in active_times:
            waveform = zu.convert_awg_waveform(
                waveforms[2 * i][start:end],
                waveforms[2 * i + 1][start:end],
                sequence.marker_waveform()[start:end])
            if "qcodes" in str(type(awg)):
                awg.awgs[i]._awg._waveforms.append(WaveformContainer(waveform))
            else:
                awg.awgs[i]._waveforms.append(WaveformContainer(waveform))
    # compile the nominal awg
    awg.awgs[0].compile()
    # upload the waveforms
    for i in range(n_channels//2):
        awg.awgs[i].upload_waveforms()


def update_zhinst_qa(qa, sequence, path="", samp_freq=None):
    waveforms = copy.deepcopy(sequence.waveforms(samp_freq=samp_freq))
    n_channels = len(waveforms)
    if n_channels > 2:
        raise(Exception(
            "the maximum channel number supported for Zurich Instruments UHFQA is 2."))
    elif n_channels == 1:
        # padded to 2 channels
        waveforms.append(np.zeros(sequence.length()))
    seqc = readout_seqc_generation(
        total_length=sequence.length(), file_path=path)
    seqc.make_file()
    # compile the nominal awg
    qa.awg.set_sequence_params(sequence_type="Custom", path=seqc._filepath)
    # upload the waveforms
    qa.awg.reset_queue()
    qa.awg.queue_waveform(*waveforms)
    qa.awg.compile_and_upload_waveforms()
