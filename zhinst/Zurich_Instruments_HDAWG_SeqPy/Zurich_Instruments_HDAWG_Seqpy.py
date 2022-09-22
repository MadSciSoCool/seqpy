from BaseDriver import LabberDriver
from zhinst.toolkit import Session
from seqpy import *
import numpy as np
import os
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
        session = Session(HOST)
        self.controller = session.connect_device(self.comCfg.address[:7])

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
            self.update_zhinst_hdawg()
            value = self.awg_start_stop(quant, value)

        if quant.name.startswith("SeqPy"):
            self.change_flag = True

        # compilation button
        if quant.name.endswith("Update AWG"):
            self.update_zhinst_hdawg()

        if self.isFinalCall(options):
            self.update_zhinst_hdawg()
            self.awg_start_stop(quant, 1)

        return value

    def performGetValue(self, quant, options={}):
        """Perform the Set Value instrument operation. This function should
        return the actual value set by the instrument"""
        if quant.get_cmd:
            node = self.controller.root.raw_path_to_node(quant.set_cmd)
            return node()
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
        """Starts or stops the respective AWG Core depending on the value."""
        if value:
            self.controller.awgs[0].enable(1)
        else:
            self.controller.awgs[0].enable(0)
        if self.controller.awgs[0].single():
            self.controller.awgs[0].wait_done()
        # return self.controller.awgs[0].is_running

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

    def update_zhinst_hdawg(self):
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
                for i in range(5):
                    try:
                        update_zhinst_hdawg(
                            self.controller,
                            self.sequence,
                            self.getValue("SeqPy - Period") * samp_freq,
                            int(self.getValue("SeqPy - Repetitions")),
                            samp_freq=samp_freq)
                        self.change_flag = False
                        return
                    except Exception as e:
                        caught_exception = e
                raise caught_exception

    def get_json_path(self):
        # for sweeeping json file name
        index = str(int(self.getValue("SeqPy - File Index")))
        path, file = os.path.split(self.getValue("SeqPy - Json Path"))
        if self.getValue("SeqPy - Replace Index"):
            file = re.sub(r'\d+', index, file)
        return os.path.join(path, file)
