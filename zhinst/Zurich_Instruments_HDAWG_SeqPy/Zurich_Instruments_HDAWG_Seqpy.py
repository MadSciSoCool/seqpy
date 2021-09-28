from BaseDriver import LabberDriver, Error
import zhinst.toolkit as tk
from helpers import update_zhinst_awg
from seqpy import *
import numpy as np
import os
import sys
sys.path.append(r"D:\Labber\Drivers\Zurich_Instruments_HDAWG_SeqPy")

# here add path to zhinst supporting functions


# change this value in case you are not using 'localhost'
HOST = "localhost"


class Driver(LabberDriver):
    """ This class implements a Labber driver"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.sequence = Sequence()

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

        if quant.name.endswith("Sample Clock"):
            config.update("SAMPLING_FREQUENCY", value)

        # TODO: check what happened in a measurement cycle
#        if self.isFinalCall(options) and not self.isFirstCall(options):
        if self.isFinalCall(options):
            self.update_zhinst_awg()
            # if any of AWGs is in the 'Send Trigger' mode, start this AWG and wait until it stops
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
            if "Channel1" in quant.name:
                if n_channels >= 1:
                    data = self.sequence.waveforms()[0]
                else:
                    data = np.zeros(self.sequence.length())
            elif "Channel2" in quant.name:
                if n_channels >= 2:
                    data = self.sequence.waveforms()[1]
                else:
                    data = np.zeros(self.sequence.length())
            elif "Marker" in quant.name:
                data = self.sequence.marker_waveform(delay=False)
            left = self.sequence.left
            right = self.sequence.right
            if self.getValue("SeqPy - Display"):
                freq = config.retrieve("SAMPLING_FREQUENCY")
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
            # here the units is in seconds so use absolute timing
            self.sequence.period = self.getValue("SeqPy - Period")
            self.sequence.repetitions = int(
                self.getValue("SeqPy - Repetitions"))

            for i in range(3):
                key = self.getValue(f"SeqPy - Sweepable {i+1} Name")
                value = self.getValue(f"SeqPy - Sweepable {i+1} Value")
                if key is not "":
                    self.sequence.subs(key, value)

    def update_zhinst_awg(self):
        json_path = self.getValue("SeqPy - Json Path")
        if json_path:
            # require for using trigger signal
            self.setValue("Marker Out - Signal 1", 4)
            self.update_sequence()
            # to avoid some random error seen in the measurement
            for i in range(15):
                try:
                    update_zhinst_awg(
                        self.controller.awgs[0], self.sequence, path=os.path.expanduser("~"))
                    break
                except Exception:
                    pass
