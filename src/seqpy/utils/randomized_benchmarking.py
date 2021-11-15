import numpy as np
from seqpy import Sequence

# all clifford gates
Clifford1 = ['wait0 ',
             'y90 x90 ',
             'xr90 yr90 ',
             'x180 ',
             'yr90 xr90 ',
             'x90 yr90 ',
             'y180 ',
             'yr90 x90 ',
             'x90 y90 ',
             'x180 y180 ',
             'y90 xr90 ',
             'xr90 y90 ',
             'y90 x180 ',
             'xr90 ',
             'x90 yr90 xr90 ',
             'yr90 ',
             'x90 ',
             'x90 y90 x90 ',
             'yr90 x180 ',
             'x90 y180 ',
             'x90 yr90 x90 ',
             'y90 ',
             'xr90 y180 ',
             'x90 y90 xr90 ']


def parse_gate_info(str):
    parsed_info = list()  # list of tuple (gate_amp, gate_phase)
    for gate in str.split(" "):
        gate_amp = 0
        gate_phase = 0
        if gate == "wait0":
            parsed_info.append((0, 0))
            continue
        # determine the phase of the gate
        if "x" in gate:
            pass
        elif "y" in gate:
            gate_phase += 90
        if "r" in gate:
            gate_phase += 180
         # determine the amplitude of the gate
        if gate.endswith("90"):
            gate_amp = 1/2
        elif gate.endswith("180"):
            gate_amp = 1
        parsed_info.append(gate_amp, gate_phase)
    return parsed_info


def find_shortest_rotation(x_destination, z_destination):
    """
    find the shortest rotation path from the initial state to the 
    destination state which we fix by choosing the destination of x
    and z. The two destinations are chosen in 
    {"+X", "-X", "+Z", "-Z", "+Y", "-Y"}.
    """
    plane_tuple = (x_destination[-1], z_destination[-1])
    plane = min(*plane_tuple) + max(*plane_tuple)
    parity = x_destination[0] == z_destination[0]
    # initially rotation to the desired plane
    rotation_to_plane = ""
    second_rotation = ""
    if plane == "XY":
        rotation_to_plane = "X90"
        second_axis = "Z"
    elif plane == "YZ":
        rotation_to_plane = "Z90"
        second_axis = "X"
    else:
        second_axis = "Y"
    if parity:
        # either case in "++" or "--"
        pass
    else:
        # either case in "+- or -+"
        if plane == "XZ":
            rotation_to_plane = "X90Z90"
        else:
            rotation_to_plane = "r" + rotation_to_plane
        if x_destination[0] == "-":
            second_rotation = second_axis + "180"


def elegant_clifford_sampling():
    """
    clifford group sampling: to determine an element U in C(1),
    we first choose U^+ X U, then U^+ Z U, which have 6 and 4 
    choices respectively, {+-X, +-Y, +-Z} and then exclude two
    selected ones.

    after determine this two we determine the gate operation by
    first 
    """
    P = {"+X", "-X", "+Z", "-Z", "+Y", "-Y"}


def randomized_benchmarking(length, x_pi, x_carrier, channel=0, n_qubits=1):
    # n_qubits is dummy now
    rb_seq = Sequence(channel + 1)
    rb_info = np.random.choice(Clifford1, length, replace=True)
    gate_width = x_pi.right - x_pi.left
    count = 0
    for clifford_gate in rb_info:
        physical_gates = parse_gate_info(clifford_gate)
        for physical_gate in physical_gates:
            gate_amp, gate_phase = physical_gate
            rb_seq.register(position=gate_width * count,
                            pulse=gate_amp * x_pi,
                            carrier_frequencies=x_carrier.frequencies,
                            carrier_phases=[gate_phase +
                                            p for p in x_carrier.phases],
                            channel=channel)
            count += 1
    return rb_seq
