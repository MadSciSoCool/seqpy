from BaseDriver import LabberDriver, Error
import zhinst.toolkit as tk
from seqpy import *
import numpy as np
import os
import sys
import hashlib
import re


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

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.sequence = Sequence()
        # change flag for awg updating
        self.change_flag = False
        self.old_hash = ""

    def performOpen(self, options={}):
        """Perform the operation of opening the instrument connection"""
        # get the interface selected in UI, restrict to either 'USB' or '1GbE'
        interface = self.comCfg.interface
        if not interface == "USB":
            interface = "1GbE"
        # initialize controller and connect
        self.controller = tk.HDAWG(
            self.comCfg.name, self.comCfg.address[:
                                                  7], interface=interface, host=HOST
        )
        self.controller.setup()
        self.controller.connect_device()

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

        # if a 'set_cmd' is defined, just set the node
        if quant.set_cmd:
            value = self.set_node_value(quant, value)

        # sequencer outputs
        if "Sequencer" in quant.name and "Output" in quant.name:
            if int(quant.name[-1]) % 2:
                self.controller.awgs[0].output1(int(value))
            else:
                self.controller.awgs[0].output2(int(value))

        # sequencer start / stop
        if quant.name.endswith("Run"):
            self.update_zhinst_awg()
            value = self.awg_start_stop(quant, value)

        # compilation button
        if quant.name.endswith("Update AWG"):
            self.update_zhinst_awg()

        if quant.name.startswith("SeqPy"):
            self.change_flag = True

        if self.isFinalCall(options):
            self.update_zhinst_awg()
            self.awg_start_stop(quant, 1)

        return value

    def performGetValue(self, quant, options={}):
        """Perform the Set Value instrument operation. This function should
        return the actual value set by the instrument"""
        if quant.get_cmd:
            return self.controller._get(quant.get_cmd)
        elif quant.name.startswith("Waveforms"):
            self.update_sequence()
            n_channels = len(self.sequence.waveforms())
            if "Channel" in quant.name:
                index = int(quant.name[-1])
                if index > n_channels:
                    data = np.zeros(self.sequence.length())
                else:
                    data = self.sequence.waveforms()[index - 1]
            elif "Marker" in quant.name:
                data = self.sequence.marker_waveform(delay=False)
            left = self.sequence.left
            right = self.sequence.right
            freq = self.getValue("Device - Sample Clock")
            left = left / freq
            right = right / freq
            return quant.getTraceDict(data, x0=left, x1=right)
        else:
            return quant.getValue()

    def set_node_value(self, quant, value):
        """Handles setting of nodes with 'set_cmd'."""
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
        """Starts or stops the respective AWG Core depending on the value."""
        if value:
            self.controller.awgs[0].run()
        else:
            self.controller.awgs[0].stop()
        if self.controller._get(f"awgs/{0}/single"):
            self.controller.awgs[0].wait_done()
        return self.controller.awgs[0].is_running

    def update_sequence(self):
        json_path = self.getValue("SeqPy - Json Path")
        if json_path:
            self.sequence.load(json_path)
            for i in range(3):
                key = self.getValue(f"SeqPy - Sweepable {i+1} Name")
                value = self.getValue(f"SeqPy - Sweepable {i+1} Value")
                if key is not "":
                    self.sequence.subs(key, value)
            self.sequence.samp_freq = self.getValue("Device - Sample Clock")

    def update_zhinst_awg(self):
        json_path = self.get_json_path()
        if os.path.exists(json_path):
            current_hash = hash_file(json_path)
            if current_hash != self.old_hash:
                self.change_flag = True
                self.old_hash = current_hash
            if self.change_flag:
                # require for using trigger signal
                self.setValue("Marker Out - Signal 1", 4)
                self.update_sequence()
                # to avoid some random error seen in the measurement
                samp_freq = self.getValue("Device - Sample Clock")
                for i in range(15):
                    try:
                        update_zhinst_awg(
                            self.controller,
                            self.sequence,
                            self.getValue("SeqPy - Period") * samp_freq,
                            int(self.getValue("SeqPy - Repetitions")),
                            path=os.path.expanduser("~"),
                            samp_freq=samp_freq)
                        self.change_flag = False
                        break
                    except Exception as e:
                        raise(e)  # TODO: investigate the random error

    def get_json_path(self):
        # for sweeeping json file name
        index = str(int(self.getValue("SeqPy - File Index")))
        path, file = os.path.split(self.getValue("SeqPy - Json Path"))
        if self.getValue("SeqPy - Replace Index"):
            file = re.sub(r'\d+', index, file)
        return os.path.join(path, file)
