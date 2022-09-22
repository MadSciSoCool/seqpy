from seqpy import *
import numpy as np
from zhinst.toolkit import Session
from BaseDriver import LabberDriver
import os
import hashlib


def hash_file(filename, blocksize=65536):
    with open(filename, "rb") as f:
        file_hash = hashlib.blake2b()
        for block in iter(lambda: f.read(blocksize), b""):
            file_hash.update(block)
    return file_hash.hexdigest()


# change this value in case you are not using 'localhost'
HOST = "localhost"


class Driver(LabberDriver):
    """ This class implements a Labber driver"""

    def performOpen(self, options={}):
        """Perform the operation of opening the instrument connection"""
        session = Session(HOST)
        self.controller = session.connect_device(self.comCfg.address[:7])
        self.last_length = [0] * 2
        self.change_flag = False
        self.old_hash = ""
        self.sequence = Sequence()
        self.data_buffer = [np.array([])] * 2

    def performClose(self, bError=False, options={}):
        """Perform the close instrument connection operation"""
        pass

    def initSetConfig(self):
        """This function is run before setting values in Set Config"""
        pass

    def performSetValue(self, quant, value, sweepRate=0.0, options={}):
        """Perform the Set Value instrument operation. This function should
        return the actual value set by the instrument"""

        quant.setValue(value)

        if self.isFirstCall(options):
            self.sequencer_updated = False
            self.waveforms_updated = [False] * 2
            self.replace_waveform = False

        loop_index, n_HW_loop = self.getHardwareLoopIndex(options)

        # if a 'set_cmd' is defined, just set the node
        if quant.set_cmd:
            value = self.set_node_value(quant, value)

        # TODO implementing these functions
        # # sequencer outputs
        # if quant.name == "Control - Output 1":
        #     self.controller.awg.output1(int(value))

        # if quant.name == "Control - Output 2":
        #     self.controller.awg.output2(int(value))

        # # sequencer gains
        # if quant.name == "Control - Gain 1":
        #     self.controller.awg.gain1(value)

        # if quant.name == "Control - Gain 2":
        #     self.controller.awg.gain2(value)

        # crosstalk - reset button
        if quant.name == "Crosstalk - Reset":
            self.set_cosstalk_matrix(np.eye(10))

        # integration time
        if quant.name == "Integration - Length":
            self.controller.qas[0].integration.length(int(value))
            value = self.controller.qas[0].integration.length()

        # sequencer start / stop
        if quant.name.endswith("Run"):
            self.update_zhinst_uhfqa()
            value = self.awg_start_stop(quant, value)

        # channel parameters for integration weights
        if quant.name.startswith("Channel"):
            name = quant.name.split(" ")
            i = int(name[1]) - 1
            if name[3] in ("Frequency", "Amplitude", "Phase"):
                self.update_integration_weights(i)
                self.sequencer_updated = True
            if name[3] == "Enable":
                pass

        if quant.name.startswith("SeqPy"):
            self.change_flag = True

        if quant.name.endswith("Update AWG"):
            self.update_zhinst_uhfqa()

        if self.isFinalCall(options):
            self.update_zhinst_uhfqa()
            self.awg_start_stop(quant, 1)

        # return the value that was set on the device ...
        return value

    def performGetValue(self, quant, options={}):
        """Perform the Get Value instrument operation"""
        if quant.get_cmd:
            # if a 'get_cmd' is defined, use it to return the node value
            node = self.controller.root.raw_path_to_node(quant.set_cmd)
            return node()
        elif quant.name.startswith("Result Vector - QB"):
            self.performArm()
            # get the result vector
            i = int(quant.name[-2:]) - 1
            while True:
                if self.controller.qas[0].result.acquired() == 0:
                    value = self.controller.qas[0].result.data[i].wave()
                    break
            return quant.getTraceDict(value, x0=0, dx=1)
        elif quant.name.startswith("Result Avg - QB"):
            self.performArm()
            # get the _averaged_ result vector
            i = int(quant.name[-2:]) - 1
            while True:
                if self.controller.qas[0].result.acquired() == 0:
                    value = self.controller.qas[0].result.data[i].wave()
                    break
            if self.isHardwareLoop(options):
                index, _ = self.getHardwareLoopIndex(options)
                return value[index]
            else:
                return np.mean(value)
        elif quant.name == "Result Demod 1-2":
            # calculate 'demod 1-2' value
            return self.get_demod_12()
        elif quant.name == "QA Monitor - Inputs":
            ch1, ch2 = self.get_qa_monitor_inputs()
            combined = np.array([ch1, ch2])
            return quant.getTraceDict(combined, dt=1/1.8e9)
        else:
            return quant.getValue()

    def update_integration_weights(self, i):
        # set the i-th integration weights
        frequency = self.getValue(f"Channel {i+1} - Frequency")
        amplitude = self.getValue(f"Channel {i+1} - Amplitude")
        phase_shift = self.getValue(f"Channel {i+1} - Phase Shift")
        phase_in_rad = phase_shift * np.pi / 180
        samp_freq = 1.8e9
        x = np.arange(4097)
        real_part = amplitude * \
            np.cos(phase_in_rad + x * 2 * np.pi * frequency / samp_freq)
        imag_part = amplitude * \
            np.sin(phase_in_rad + x * 2 * np.pi * frequency / samp_freq)
        self.controller.qas[0].integration.weights[i].real(real_part)
        self.controller.qas[0].integration.weights[i].imag(imag_part)

    def get_qa_monitor_inputs(self):
        self.performArm()
        while True:
            if self.controller.qas[0].monitor.acquired() == 0:
                ch1 = self.controller.qas[0].monitor.inputs[0].wave()
                ch2 = self.controller.qas[0].monitor.inputs[1].wave()
                return (ch1, ch2)

    def performArm(self):
        """Perform the instrument arm operation"""
        if self.getValue("QA Monitor - Enable"):
            self.controller.qas[0].monitor.reset(1)
            self.controller.qas[0].monitor.enable(1, deep=True)
        if self.getValue("QA Results - Enable"):
            self.controller.qas[0].result.reset(1)
            self.controller.qas[0].result.enable(1, deep=True)
            self.controller.arm()
        # if self.getValue("Sequencer - Trigger Mode") == "External Trigger":
        #     self.controller.awg.run()

    def set_node_value(self, quant, value):
        node = self.controller.root.raw_path_to_node(quant.set_cmd)
        if quant.datatype == quant.COMBO:
            i = quant.getValueIndex(value)
            if len(quant.cmd_def) == 0:
                node(i)
            else:
                node(quant.cmd_def[i])
        else:
            node(value)
        return node()

    def awg_start_stop(self, quant, value):
        """Handles setting of nodes with 'set_cmd'."""
        if value:
            self.controller.awgs[0].enable(1)
        else:
            self.controller.awgs[0].enable(0)
        if self.controller.awgs[0].single():
            self.controller.awgs[0].wait_done()
        # return self.controller.awg.is_running

    def set_cosstalk_matrix(self, matrix):
        """Set the crosstalk matrix as a 2D numpy array."""
        rows, cols = matrix.shape
        for r in range(rows):
            for c in range(cols):
                self.setValue(f"Crosstalk - {r+1} , {c+1}", matrix[r, c])
        self.controller.qas[0].crosstalk_matrix(matrix)

    def get_demod_12(self):
        """Assembles a complex value from real valued data on channel 1 and 2.
        The returned data will be (channel 1) + i * (channel 2).
        """
        data1 = self.controller.channels[0].result()
        data2 = self.controller.channels[1].result()
        real = np.mean(np.real(data1))
        imag = np.mean(np.real(data2))
        return real + 1j * imag

    def update_sequence(self):
        json_path = self.getValue("SeqPy - Json Path")
        if json_path:
            self.sequence.load(json_path)
            for i in range(3):
                key = self.getValue(f"SeqPy - Sweepable {i+1} Name")
                value = self.getValue(f"SeqPy - Sweepable {i+1} Value")
                if key is not "":
                    self.sequence.subs(key, value)

    def update_zhinst_uhfqa(self):
        json_path = self.getValue("SeqPy - Json Path")
        if os.path.exists(json_path):
            current_hash = hash_file(json_path)
            if current_hash != self.old_hash:
                self.change_flag = True
                self.old_hash = current_hash
            if self.change_flag:
                self.update_sequence()
                for i in range(5):
                    try:
                        update_zhinst_uhfqa(
                            self.controller,
                            self.sequence,
                            path=os.path.expanduser("~"),
                            samp_freq=1.8e9)
                        self.change_flag = False
                        return
                    except Exception as e:
                        caught_exception = e
                raise caught_exception
