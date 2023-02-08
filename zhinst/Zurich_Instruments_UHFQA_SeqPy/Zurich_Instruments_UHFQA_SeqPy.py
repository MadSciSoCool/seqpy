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
        self.session = Session(HOST)
        self.controller = self.session.connect_device(self.comCfg.address[:7])
        self.last_length = [0] * 2
        self.change_flag = False
        self.old_hash = ""
        self.sequence = Sequence()
        self.input_buffer = list()
        self.result_buffer = list()

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

        loop_index, n_HW_loop = self.getHardwareLoopIndex(options)

        # if a 'set_cmd' is defined, just set the node
        if quant.set_cmd:
            value = self.set_node_value(quant, value)

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

    def performArm(self, quant_names, options={}):
        # qa_monitor_ind = set()
        # qa_result_ind = set()
        # for name in quant_names:
        #     if name.startswith("Result Vector - QB"):
        #         i = int(name[-2:]) - 1
        #         qa_result_ind |= {i}
        #     elif name.startswith("Result Avg - QB"):
        #         i = int(name[-2:]) - 1
        #         qa_result_ind |= {i}
        #     elif name.startswith("QA Monitor - Input"):
        #         i = int(name[-1]) - 1
        #         qa_monitor_ind |= {i}
        # # arm the monitor nodes
        qa_monitor_flag = False
        qa_result_flag = False
        for name in quant_names:
            if name.startswith("Result Vector - QB") or name.startswith("Result Avg - QB"):
                qa_result_flag = True
            elif name.startswith("QA Monitor - Input"):
                qa_monitor_flag = True
        # arm the monitor nodes
        if qa_monitor_flag:
            monitor_wave_nodes = [
                self.controller.qas[0].monitor.inputs[i].wave for i in (0, 1)]
            for node in monitor_wave_nodes:
                node.subscribe()
            if self.getValue("QA Monitor - Enable"):
                self.controller.qas[0].monitor.reset(1)
                self.controller.qas[0].monitor.enable(1, deep=True)
        # arm the result nodes
        if qa_result_flag:
            result_wave_nodes = [
                self.controller.qas[0].result.data[ch].wave for ch in range(10)]
            for node in result_wave_nodes:
                node.subscribe()
            if self.getValue("QA Results - Enable"):
                self.controller.qas[0].result.reset(1)
                self.controller.qas[0].result.enable(1, deep=True)

    def performGetValue(self, quant, options={}):
        """Perform the Get Value instrument operation"""
        if quant.get_cmd:
            # if a 'get_cmd' is defined, use it to return the node value
            node = self.controller.root.raw_path_to_node(quant.set_cmd)
            value = node(enum=False)
        elif quant.name.startswith("Result Vector - QB"):
            if len(self.result_buffer) == 0:
                self.result_buffer = self.get_qa_result(range(10))
            i = int(quant.name[-2:]) - 1
            value = quant.getTraceDict(self.result_buffer[i], x0=0, dx=1)
        elif quant.name.startswith("Result Avg - QB"):
            # get the _averaged_ result vector
            i = int(quant.name[-2:]) - 1
            if len(self.result_buffer) == 0:
                self.result_buffer = self.get_qa_result(range(10))
            value = np.mean(self.result_buffer[i])
        elif quant.name == "Result Demod 1-2":
            # calculate 'demod 1-2' value
            value = self.get_demod_12()
        elif quant.name.startswith("QA Monitor - Input"):
            if len(self.input_buffer) == 0:
                self.input_buffer = self.get_qa_monitor_inputs()
            i = int(quant.name[-1]) - 1
            value = quant.getTraceDict(self.input_buffer[i], dt=1/1.8e9)
        else:
            value = quant.getValue()
        if self.isFinalCall(options):
            self.input_buffer = list()
            self.result_buffer = list()
        return value

    def get_qa_monitor_inputs(self):
        result_wave_nodes = [
            self.controller.qas[0].monitor.inputs[i].wave for i in (0, 1)]
        RESULT_LENGTH = self.controller.qas[0].monitor.length()
        captured_data = {path: [] for path in result_wave_nodes}
        capture_done = {path: False for path in result_wave_nodes}
        # for node in result_wave_nodes:
        #     node.subscribe()
        if self.getValue("QA Monitor - Enable"):
            # self.controller.qas[0].monitor.reset(1)
            # self.controller.qas[0].monitor.enable(1, deep=True)
            # main capture loop
            while not np.all(np.array(list(capture_done.values()))):
                # if start_time + timeout < time.time():
                #     raise TimeoutError('Timeout before all samples collected.')
                dataset = self.session.poll()
                for k, v in dataset.copy().items():
                    if k in captured_data.keys():
                        n_records = sum(len(x) for x in captured_data[k])
                        if n_records != RESULT_LENGTH:
                            captured_data[k].append(v[0]['vector'])
                            capture_done[k] = True
        self.controller.qas[0].monitor.enable(0, deep=True)
        self.controller.qas[0].monitor.inputs.unsubscribe()
        return list(captured_data.values())

    def get_qa_result(self, chs):
        result_wave_nodes = [
            self.controller.qas[0].result.data[ch].wave for ch in chs]
        RESULT_LENGTH = self.controller.qas[0].result.length()
        captured_data = {path: [] for path in result_wave_nodes}
        capture_done = {path: False for path in result_wave_nodes}
        # for node in result_wave_nodes:
        #     node.subscribe()
        if self.getValue("QA Results - Enable"):
            # self.controller.qas[0].result.reset(1)
            # self.controller.qas[0].result.enable(1, deep=True)
            # main capture loop
            while not np.all(np.array(list(capture_done.values()))):
                # if start_time + timeout < time.time():
                #     raise TimeoutError('Timeout before all samples collected.')
                dataset = self.session.poll()
                for k, v in dataset.copy().items():
                    if k in captured_data.keys():
                        n_records = sum(len(x) for x in captured_data[k])
                        if n_records != RESULT_LENGTH:
                            captured_data[k].append(v[0]['vector'])
                            capture_done[k] = True
        self.controller.qas[0].result.enable(0, deep=True)
        self.controller.qas[0].result.data.unsubscribe()
        return list(captured_data.values())

    def update_integration_weights(self, i):
        # set the i-th integration weights
        frequency = self.getValue(f"Channel {i+1} - Frequency")
        amplitude = self.getValue(f"Channel {i+1} - Amplitude")
        phase_shift = self.getValue(f"Channel {i+1} - Phase Shift")
        # phase_in_rad = phase_shift * np.pi / 180
        samp_freq = 1.8e9
        x = np.arange(4097)
        real_part = amplitude * \
            np.cos(phase_shift + x * 2 * np.pi * frequency / samp_freq)
        imag_part = np.sin(x * 2 * np.pi * frequency / samp_freq)
        self.controller.qas[0].integration.weights[i].real(real_part)
        self.controller.qas[0].integration.weights[i].imag(imag_part)

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
                            samp_freq=1.8e9)
                        self.change_flag = False
                        return
                    except Exception as e:
                        caught_exception = e
                raise caught_exception
