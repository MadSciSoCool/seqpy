import sys
sys.path.append(r"/Users/pan/Projects/seqpy/zhinst")
# here add path to zhinst supporting functions
from BaseDriver import LabberDriver, Error
import zhinst.toolkit as tk
import zhinst.utils as zu
from zhinst_awg_wrapper import update_zhinst_awg
from seqc_generation import seqc_generation
from seqpy import *


# change this value in case you are not using 'localhost'
HOST = "localhost"


class Driver(LabberDriver):
    """ This class implements a Labber driver"""

    def __init__(self) -> None:
        super().__init__()
        self._sequence = Sequence()

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
        self.last_length = [0] * 8

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
            self.update_zhinst_awg(sequence=self._sequence)
            value = self.awg_start_stop(quant, value)

        if self.isFinalCall(options):
            self.update_zhinst_awg(sequence=self._sequence)
            # if any of AWGs is in the 'Send Trigger' mode, start this AWG and wait until it stops
            self.awg_start_stop(quant, 1)

        return value

    def performGetValue(self, quant, options={}):
        """Perform the Set Value instrument operation. This function should
        return the actual value set by the instrument"""
        if quant.get_cmd:
            return self.controller._get(quant.get_cmd)
        elif quant.name.startwith("Waveforms"):
            if "Channel1" in quant.name:
                return self._sequence.waveforms()[0]
            elif "Channel2" in quant.name:
                return self._sequence.waveforms()[0]
            elif "Marker" in quant.name:
                return self._sequence.marker_waveform(delay=False)
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
        self._sequence.load(self.getValue("SeqPy - Json Path"))
        self._sequence.period = self.getValue("SeqPy - Period")
        self._sequence.repetitions = int(self.getValue("SeqPy - Repetitions"))
        for i in range(3):
            key = self.getValue(f"Seqpy - Sweepable {i+1} name")
            value = self.getValue(f"Seqpy - Sweepable {i+1} name")
            if key is not "":
                self._sequence.subs(key, value)

    def update_zhinst_awg(self, sequence, path=""):
        self.update_sequence()
        update_zurich_awg(self.controller.awgs[0], self._sequence, path="")
