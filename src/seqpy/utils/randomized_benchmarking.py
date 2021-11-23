import numpy as np
from seqpy import Sequence


"""
we define clifford gate by an 2-tuple of integers (m, n), 1<= m, n <= 6, m!=n mod 3,
the decoding is as [1~6] <-> [X,Y,Z,-X,-Y,-Z]
the two tuple means (X,Z) is sent to (O[m], o[n]) under the unitary transformation of the selected clifford gate

the idea is to sample the clifford gate within randint(6)*randint(4) space, and keep track of the axis permutation
after that we can directly know what is the total effect of the clifford sequence and find the inverse clifford gate
Then we could transform the 2-tuple representation to a physical gate implementation with gate set {+-X/2, +-Y/2, +-X, +-Y}
the gate series is also representate by a 2-tuple (gate_amp, gate_type)
"""


def clifford2gate(clifford):
    return gates_info


def parse_gate_info(str):
    parsed_info = list()  # list of tuple (gate_amp, gate_phase)
    for gate in str.split(" "):
        # unity
        if gate == "I":
            parsed_info.append((0, "I"))
            continue
        # determine the type of the gate
        if "X" in gate:
            gate_type = "X"
        else:
            gate_type = "Y"
         # determine the amplitude of the gate
        if gate.endswith("/2"):
            gate_amp = 1/2
        else:
            gate_amp = 1
        if "-" in gate:
            gate_amp *= -1
        parsed_info.append(gate_amp, gate_type)
    return parsed_info


def clifford1():
    """
    return the clifford(1) group
    here {X, Y, Z, I} <-> -i sigma_{x, y, z, i}
    => Z = X Y, Z/2 = X/2 Y/2 -X/2
    """
    pauli = ["I", "X", "Y", "X Y"]
    half_rotations = list()
    cycle_rotations = list()
    hadamard_like = list()
    for i in pauli[1:3]:
        half_rotations += [f"{i}/2", f"-{i}/2"]
    half_rotations += ["X/2 Y/2 -X/2", "X/2 -Y/2 -X/2"]
    for sign1 in ["", "-"]:
        for sign2 in ["", "-"]:
            cycle_rotations += [f"{sign1}X/2 {sign2}Y/2",
                                f"{sign1}Y/2 {sign2}X/2"]
    for c1, c2 in [("X", "Y"), ("Y", "X")]:
        for s in ["", "-"]:
            hadamard_like += [f"{c1} {s}{c2}/2"]
    hadamard_like += ["X/2 Y/2 X/2", "-X/2 Y/2 -X/2"]
    return pauli + half_rotations + cycle_rotations + hadamard_like


def simplify_clifford_expr(expr):
    gates_info = parse_gate_info(expr)
    # strip unity gate
    gates_info.remove((0, "I"))
    # simplify the gates recursively, each step contains two phases:
    # 1) absorb all same type of gates together, mod by 2 (using XX = YY = I)
    # 2)
    while len(gates_info) > 3:
        gates_info_rebuild = list()
        current = (0, "I")
        for gate in gates_info:
            if current[1] != gate[1]:
                current = (current[0] % 2, current[1])
                if current[0] != 0:
                    gates_info_rebuild.append(current)
                    current = gate
            else:
                current = (current[0] + gate[0], current[1])
        gates_info = gates_info_rebuild


def randomized_benchmarking(length, x_pi, x_carrier, channel=0, n_qubits=1):
    # n_qubits is dummy now
    rb_seq = Sequence(channel + 1)
    rb_info = np.random.choice(clifford1(), length, replace=True)
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
