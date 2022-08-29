from seqpy import *
import numpy as np
from BaseDriver import LabberDriver
import zhinst.toolkit as tk
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
        interface = self.comCfg.interface
        if not interface == "USB":
            interface = "1GbE"
        # initialize controller and connect
        self.controller = tk.UHFQA(
            self.comCfg.name, self.comCfg.address[:
                                                  7], interface=interface, host=HOST
        )
        self.controller.setup()
        self.controller.connect_device()
        self.last_length = [0] * 2
        self.change_flag = False
        self.old_hash = ""
        self.sequence = Sequence()

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

        # sequencer outputs
        if quant.name == "Control - Output 1":
            self.controller.awg.output1(int(value))

        if quant.name == "Control - Output 2":
            self.controller.awg.output2(int(value))

        # sequencer gains
        if quant.name == "Control - Gain 1":
            self.controller.awg.gain1(value)

        if quant.name == "Control - Gain 2":
            self.controller.awg.gain2(value)

        # crosstalk - reset button
        if quant.name == "Crosstalk - Reset":
            self.set_cosstalk_matrix(np.eye(10))

        # integration time
        if quant.name == "Integration - Time":
            self.controller.integration_time(value)
            value = self.controller.integration_time()

        # sequencer start / stop
        if quant.name.endswith("Run"):
            self.update_zhinst_qa()
            value = self.awg_start_stop(quant, value)

        # all channel parameters
        if quant.name.startswith("Channel"):
            name = quant.name.split(" ")
            i = int(name[1]) - 1
            channel = self.controller.channels[i]
            if name[3] == "Rotation":
                value = channel.rotation(value)
            if name[3] == "Threshold":
                value = channel.threshold(value)
            if name[3] == "Frequency":
                value = channel.readout_frequency(value)
                self.sequencer_updated = True
            if name[3] == "Amplitude":
                value = channel.readout_amplitude(value)
                self.sequencer_updated = True
            if name[3] == "Phase":
                value = channel.phase_shift(value)
                self.sequencer_updated = True
            if name[3] == "Enable":
                channel.enable() if value else channel.disable()

        if quant.name.startswith("SeqPy"):
            self.change_flag = True

        if quant.name.endswith("Update AWG"):
            self.update_zhinst_qa()

        if self.isFinalCall(options):
            self.update_zhinst_qa()
            self.awg_start_stop(quant, 1)

        # return the value that was set on the device ...
        return value

    def performGetValue(self, quant, options={}):
        """Perform the Get Value instrument operation"""
        if quant.get_cmd:
            # if a 'get_cmd' is defined, use it to return the node value
            return self.controller._get(quant.get_cmd)
        elif quant.name.startswith("Result Vector - QB"):
            self.performArm()
            # get the result vector
            i = int(quant.name[-2:]) - 1
            while True:
                if self.controller._get('/qas/0/result/acquired') == 0:
                    value = self.controller.channels[i].result()
                    break
            return quant.getTraceDict(value, x0=0, dx=1)
        elif quant.name.startswith("Result Avg - QB"):
            self.performArm()
            # get the _averaged_ result vector
            i = int(quant.name[-2:]) - 1
            while True:
                if self.controller._get('/qas/0/result/acquired') == 0:
                    value = self.controller.channels[i].result()
                    break
            if self.isHardwareLoop(options):
                index, _ = self.getHardwareLoopIndex(options)
                return value[index]
            else:
                return np.mean(value)
        elif quant.name == "Result Demod 1-2":
            # calculate 'demod 1-2' value
            return self.get_demod_12()
        elif quant.name == 'QA Monitor - Input 1':
            self.performArm()
            while True:
                if self.controller._get('/qas/0/monitor/acquired') == 0:
                    value = quant.getTraceDict(self.controller._get(
                        '/qas/0/monitor/inputs/0/wave'), dt=1/1.8e9)
                    break
            return value
        elif quant.name == 'QA Monitor - Input 2':
            self.performArm()
            while True:
                if self.controller._get('/qas/0/monitor/acquired') == 0:
                    value = quant.getTraceDict(self.controller._get(
                        '/qas/0/monitor/inputs/1/wave'), dt=1/1.8e9)
                    break
            return value
        else:
            return quant.getValue()

    def performArm(self):
        """Perform the instrument arm operation"""
        if self.getValue("QA Monitor - Enable"):
            self.controller._set("/qas/0/monitor/reset", 1)
            self.controller._set("/qas/0/monitor/enable", 1)
        if self.getValue("QA Results - Enable"):
            self.controller._set("/qas/0/result/reset", 1)
            self.controller._set("/qas/0/result/enable", 1)
            self.controller.arm()
        # if self.getValue("Sequencer - Trigger Mode") == "External Trigger":
        #     self.controller.awg.run()

    def set_node_value(self, quant, value):
        if quant.datatype == quant.COMBO:
            i = quant.getValueIndex(value)
            if len(quant.cmd_def) == 0:
                self.controller._set(quant.set_cmd, i)
            else:
                self.controller._set(quant.set_cmd, quant.cmd_def[i])
        else:
            self.controller._set(quant.set_cmd, value)
        return self.controller._get(quant.get_cmd)

    def awg_start_stop(self, quant, value):
        """Handles setting of nodes with 'set_cmd'."""
        if value:
            self.controller.awg.run()
        else:
            self.controller.awg.stop()
        if self.controller._get("awgs/0/single"):
            self.controller.awg.wait_done()
        return self.controller.awg.is_running

    def set_cosstalk_matrix(self, matrix):
        """Set the crosstalk matrix as a 2D numpy array."""
        rows, cols = matrix.shape
        for r in range(rows):
            for c in range(cols):
                self.setValue(f"Crosstalk - {r+1} , {c+1}", matrix[r, c])
        self.controller.crosstalk_matrix(matrix)

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

    def update_zhinst_qa(self):
        json_path = self.getValue("SeqPy - Json Path")
        if os.path.exists(json_path):
            current_hash = hash_file(json_path)
            if current_hash != self.old_hash:
                self.change_flag = True
                self.old_hash = current_hash
            if self.change_flag:
                self.update_sequence()
                for i in range(15):
                    try:
                        update_zhinst_qa(
                            self.controller,
                            self.sequence,
                            path=os.path.expanduser("~"),
                            samp_freq=1.8e9)
                        self.change_flag = False
                        break
                    except Exception as e:
                        pass
