"""Fill Group12_Report_Template.docx with the GHZ results -> Group12_Quantum_Report.docx.

Numbers in the tables are read from results/*.csv, so re-running
ghz_experiments.py and then this script keeps the report in sync.
"""
import re
from copy import deepcopy
from pathlib import Path

import docx
import pandas as pd
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches
from docx.table import Table
from docx.text.paragraph import Paragraph

HERE = Path(__file__).resolve().parent
import sys
TEMPLATE = HERE / "templates" / "Group12_Report_Template.docx"
COVER = HERE / "templates" / "cover_page.docx"
LOGO = HERE / "assets" / "ramaiah_logo.png"
REPO_URL = "https://github.com/PPViveka/Quantum-project"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "report" / "Group12_Quantum_Report.docx"
OUT.parent.mkdir(exist_ok=True)
FIG = HERE / "figures"
RES = HERE / "results"

A = pd.read_csv(RES / "main_results.csv")
B = pd.read_csv(RES / "depth_results.csv")
C2 = pd.read_csv(RES / "logdepth_results.csv")

doc = docx.Document(TEMPLATE)
NOISE_NAME = {"N0": "N0 – None", "N1": "N1 – Low", "N2": "N2 – Moderate", "N3": "N3 – High"}


def pm(m, s):
    return f"{m:.3f} ± {s:.3f}"


def rowA(n, lvl):
    return A[(A.qubits == n) & (A.noise == lvl)].iloc[0]


# ---------------------------------------------------------------- helpers
def paras():
    return doc.paragraphs


def find(prefix, start_after=None):
    seen = start_after is None
    for p in paras():
        if not seen:
            seen = p._p is start_after
            continue
        if p.text.strip().startswith(prefix):
            return p
    raise KeyError(prefix)


# prototype empty body paragraph (Calibri 11, spacing after 80)
PROTO = deepcopy(find("Instruction: Explain in 150")._p.getnext())


def _run(text, b=False, i=False, mono=False, size=None):
    r = deepcopy(PROTO.find(qn("w:r")))
    rpr = r.find(qn("w:rPr"))
    if mono:
        f = rpr.find(qn("w:rFonts"))
        for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            f.set(qn(a), "Consolas")
    idx = 1
    for flag, tag in ((b, "w:b"), (i, "w:i")):
        if flag:
            rpr.insert(idx, OxmlElement(tag))
            idx += 1
    if size:
        rpr.find(qn("w:sz")).set(qn("w:val"), str(size))
        rpr.find(qn("w:szCs")).set(qn("w:val"), str(size))
    t = r.find(qn("w:t"))
    t.text = text
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return r


def _segments(text):
    """**bold**, *italic*, `code` inline markup."""
    out = []
    for part in re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)", text):
        if not part:
            continue
        if part.startswith("**"):
            out.append((part[2:-2], dict(b=True)))
        elif part.startswith("`"):
            out.append((part[1:-1], dict(mono=True, size=20)))
        elif part.startswith("*"):
            out.append((part[1:-1], dict(i=True)))
        else:
            out.append((part, {}))
    return out


def make_p(text="", kind="body"):
    p = deepcopy(PROTO)
    for r in p.findall(qn("w:r")):
        p.remove(r)
    ppr = p.find(qn("w:pPr"))
    if kind == "bullet":
        num = OxmlElement("w:numPr")
        il = OxmlElement("w:ilvl"); il.set(qn("w:val"), "0")
        ni = OxmlElement("w:numId"); ni.set(qn("w:val"), "1")
        num.append(il); num.append(ni)
        ppr.insert(0, num)
        ppr.find(qn("w:spacing")).set(qn("w:after"), "40")
    if kind in ("caption", "image", "center"):
        jc = OxmlElement("w:jc"); jc.set(qn("w:val"), "center")
        ppr.append(jc)
    if kind == "caption":
        ppr.find(qn("w:spacing")).set(qn("w:after"), "200")
    if kind == "code":
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear"); shd.set(qn("w:fill"), "F2F2F2")
        ppr.insert(0, shd)
        ppr.find(qn("w:spacing")).set(qn("w:after"), "0")
        p.append(_run(text, mono=True, size=17))
        return p
    if kind == "caption":
        p.append(_run(text, i=True, size=19))
        return p
    for seg, fmt in _segments(text):
        p.append(_run(seg, **fmt))
    return p


def code(block):
    return [("code", line) for line in block.strip("\n").split("\n")]


def insert_after(anchor_el, items):
    """items: str (body), ('bullet'|'code'|'caption'|'center', text), ('image', path, width_in),
    ('table', clone_from_table, rows) -> returns last element."""
    el = anchor_el
    for it in items:
        if isinstance(it, str):
            new = make_p(it)
        elif it[0] == "image":
            new = make_p("", "image")
            Paragraph(new, doc._body).add_run().add_picture(str(it[1]), width=Inches(it[2]))
        elif it[0] == "table":
            new = clone_table(it[1], it[2])
        else:
            new = make_p(it[1], it[0])
        el.addnext(new)
        el = new
    return el


def fill(instr_prefix, items, keep_instruction=False, start_after=None):
    """Replace the empty placeholder paragraphs following an instruction line."""
    ins = find(instr_prefix, start_after)._p
    nxt = ins.getnext()
    while nxt is not None and nxt.tag == qn("w:p") and not "".join(nxt.itertext()).strip() \
            and nxt.find(".//" + qn("w:drawing")) is None and nxt.find(".//" + qn("w:pStyle")) is None:
        after = nxt.getnext()
        ins.getparent().remove(nxt)
        nxt = after
    last = insert_after(ins, items)
    if not keep_instruction:
        ins.getparent().remove(ins)
    return last


def set_cell(cell, text, bold=None):
    lines = str(text).split("\n")
    p = cell.paragraphs[0]
    runs = p.runs
    if not runs:
        p.add_run("")
        runs = p.runs
    for r in runs[1:]:
        r._r.getparent().remove(r._r)
    runs[0].text = lines[0]
    if bold is not None:
        runs[0].bold = bold
    for extra in cell.paragraphs[1:]:
        extra._p.getparent().remove(extra._p)
    for line in lines[1:]:
        np_ = deepcopy(p._p)
        np_.findall(qn("w:r"))[0].find(qn("w:t")).text = line
        cell._tc.append(np_)


def resize_rows(table, n_data):
    """Make the table have exactly n_data rows below the header."""
    trs = table._tbl.findall(qn("w:tr"))
    proto = trs[-1]
    while len(table._tbl.findall(qn("w:tr"))) - 1 < n_data:
        table._tbl.append(deepcopy(proto))
    while len(table._tbl.findall(qn("w:tr"))) - 1 > n_data:
        table._tbl.remove(table._tbl.findall(qn("w:tr"))[-1])


def fill_table(table, header, rows):
    if header:
        for c, h in zip(table.rows[0].cells, header):
            set_cell(c, h)
    resize_rows(table, len(rows))
    for r, vals in zip(table.rows[1:], rows):
        for c, v in zip(r.cells, vals):
            set_cell(c, v, bold=False)


def clone_table(src, spec):
    header, rows = spec
    new = deepcopy(src._tbl)
    t = Table(new, doc._body)
    fill_table(t, header, rows)
    return new


def table_after_heading(heading):
    h = find(heading)._p
    el = h.getnext()
    while el.tag != qn("w:tbl"):
        el = el.getnext()
    return Table(el, doc._body)


def kv_table(table, values):
    for r, v in zip(table.rows, values):
        if v is not None:
            set_cell(r.cells[1], v, bold=False)


T = doc.tables  # original tables, by index (see template)

# ---------------------------------------------------------------- top note
ins = find("Instruction: Replace the text in grey boxes")._p
ins.getparent().remove(ins)

# ---------------------------------------------------------------- 1. Problem
fill("Instruction: Explain in 150", [
    "A Greenberger–Horne–Zeilinger (GHZ) state is an equal superposition of all n qubits in |0⟩ and all n "
    "qubits in |1⟩: |GHZ⟩ = (|0…0⟩ + |1…1⟩)/√2. It is the simplest maximally entangled multi-qubit state. It is "
    "used in quantum metrology, quantum secret sharing and error-correcting codes, and it is a standard benchmark "
    "for quantum hardware: a device that cannot prepare a high-fidelity GHZ state cannot run larger entangled "
    "algorithms.",
    "GHZ states are also very fragile. A single phase error on any one qubit reverses the sign of the "
    "superposition, and every extra qubit adds one more two-qubit gate and one more noisy measurement. As a "
    "result, the useful size of a GHZ state, and of the entangled registers inside real algorithms, is limited "
    "by how noise accumulates with qubit count.",
    "This project studies that limit under controlled conditions. We prepare GHZ states on 2, 3, 4 and 6 qubits "
    "in Qiskit and simulate them with Qiskit Aer under four noise levels (N0–N3) defined by the course "
    "guidelines. We measure how the output distribution, the coherence of the state and the state fidelity "
    "degrade. Because the simulator lets us switch gate noise and readout noise separately, and compute the "
    "exact noisy density matrix, we can attribute each part of the loss to its source. Hardware experiments "
    "cannot do this. We also separate the effect of circuit depth from qubit count, and test readout-error "
    "mitigation and a log-depth circuit as low-cost improvements.",
])
fill("Instruction: List 3", [
    ("bullet", "**O1.** Build GHZ circuits for 2, 3, 4 and 6 qubits and record qubits, total gates, two-qubit "
               "gates and depth for each."),
    ("bullet", "**O2.** Run 16 controlled experiments (4 qubit counts × 4 noise levels, 1024 shots, 5 seeds) and "
               "report success probability, X-parity and fidelity as mean ± SD."),
    ("bullet", "**O3.** Quantify how much of the measured degradation comes from gate error vs readout error, "
               "using exact density-matrix fidelity as ground truth."),
    ("bullet", "**O4.** Test two improvements, readout-error mitigation and a log-depth GHZ construction, and "
               "measure their gain and overhead. Separately, measure the effect of depth alone."),
])
fill("Instruction: State 2", [
    "**RQ1.** How do success probability and state fidelity change as the GHZ size grows from 2 to 6 qubits "
    "under low, moderate and high noise? *H1: both fall monotonically with n, more steeply at higher noise.*",
    "**RQ2.** Is the coherence of the GHZ state (X-basis parity) more sensitive to noise than its "
    "computational-basis populations? *H2: yes, because a phase error on any single qubit destroys the coherence.*",
    "**RQ3.** Which noise source dominates the measured degradation, and can readout-error mitigation recover "
    "it at low cost? *H3: readout error dominates at the noise levels used, and mitigation recovers most of it.*",
])

# ---------------------------------------------------------------- 2. Literature
lit = [
    ["1", "T. Monz et al., 2011",
     "14-qubit entanglement: creation and coherence. Phys. Rev. Lett. 106, 130506. "
     "doi:10.1103/PhysRevLett.106.130506",
     "Trapped-ion GHZ states of 2–14 qubits; fidelity from populations plus parity oscillations.",
     "Coherence decays faster than linearly with qubit count (superdecoherence under correlated dephasing). "
     "Limitation: one platform, with noise specific to ion traps."],
    ["2", "C. Song et al., 2019",
     "Generation of multicomponent atomic Schrödinger cat states of up to 20 qubits. Science 365, 574–577. "
     "doi:10.1126/science.aay0600",
     "20-qubit superconducting processor; GHZ and cat states prepared via collective interactions.",
     "Genuine 20-qubit GHZ entanglement certified (fidelity > 0.5). Limitation: device-specific; noise sources "
     "are not separated."],
    ["3", "A. Omran et al., 2019",
     "Generation and manipulation of Schrödinger cat states in Rydberg atom arrays. Science 365, 570–574. "
     "doi:10.1126/science.aax9743",
     "Neutral Rydberg atoms (up to 20) with optimal-control pulses; parity-oscillation verification.",
     "GHZ states of up to 20 atoms above the 0.5 entanglement threshold. Limitation: analogue control, not a "
     "gate-based circuit model."],
    ["4", "K. X. Wei et al., 2020",
     "Verifying multipartite entangled GHZ states via multiple quantum coherences. Phys. Rev. A 101, 032343. "
     "doi:10.1103/PhysRevA.101.032343",
     "IBM 20-qubit superconducting device; multiple-quantum-coherence (MQC) fidelity measurement.",
     "18-qubit GHZ fidelity 0.5165 ± 0.0036; scalable verification. Limitation: hardware study; gate and readout "
     "contributions not isolated."],
    ["5", "G. J. Mooney et al., 2021",
     "Generation and verification of 27-qubit GHZ states in a superconducting quantum computer. J. Phys. Commun. "
     "5, 095004. doi:10.1088/2399-6528/ac1df7",
     "IBM ibmq_montreal (27 qubits); log-depth circuits, readout-error mitigation, MQC verification.",
     "27-qubit GHZ fidelity 0.546 ± 0.017 with readout mitigation. Limitation: result depends on mitigation and "
     "device calibration."],
    ["6", "P. D. Nation et al., 2021",
     "Scalable mitigation of measurement errors on quantum computers. PRX Quantum 2, 040326. "
     "doi:10.1103/PRXQuantum.2.040326",
     "Matrix-free measurement mitigation (M3) evaluated on IBM hardware.",
     "Readout mitigation that scales to many qubits. Limitation: corrects readout only, not gate errors."],
]
fill_table(T[4], None, lit)
fill("Instruction: Review at least 5", [
    "Six peer-reviewed papers (2011–2021) on GHZ-state generation, verification and measurement-error "
    "mitigation were reviewed. DOIs were checked against the publisher or arXiv records.",
])
fill("Instruction: In one paragraph, state what the reviewed papers", [
    "The reviewed studies report GHZ fidelity on physical devices, where gate errors, readout errors, idle "
    "decoherence and crosstalk act at the same time, so their individual contributions cannot be separated. "
    "They also report a single verified fidelity per size, without comparing a cheap measured estimate against "
    "the true state fidelity. None of them separates the effect of circuit depth from qubit count at a fixed "
    "target state. This project addresses these gaps in simulation. It uses calibrated, switchable noise levels "
    "(N0–N3) and exact density-matrix fidelity as ground truth, which lets us split the measured loss into gate "
    "and readout parts, validate a two-setting fidelity estimator, and isolate depth through identity-padded "
    "circuits.",
])

# ---------------------------------------------------------------- 3. Design
kv_table(T[5], [
    "No external dataset. GHZ circuits are generated in Qiskit, as specified in the group brief.",
    "Not applicable (no classification). Each configuration = 1024 shots × 5 seeds, measured in both the Z and the X basis.",
    "Not applicable",
    "Not applicable",
    "Not applicable (no training). Simulator seeds: 11, 22, 33, 44, 55.",
])
fill("Instruction: Describe the data encoding", [
    "**State preparation (no data encoding).** A Hadamard on q0 creates (|0⟩+|1⟩)/√2. A chain of n−1 CNOTs "
    "(q0→q1→…→q(n−1)) then copies this value to every qubit, giving (|0…0⟩+|1…1⟩)/√2. The entanglement pattern "
    "is linear nearest-neighbour, which suits devices with line connectivity. The circuit has no trainable "
    "parameters, so there is no ansatz, loss function or optimizer.",
    "**Measurement.** Every configuration is measured in two settings. (i) Z basis: gives the populations "
    "P(0…0) and P(1…1). (ii) X basis: an H on every qubit before measurement gives the parity ⟨X⊗n⟩ = "
    "Σ p(b)(−1)^|b|. Z-basis counts alone cannot tell a GHZ state from a classical 50/50 mixture, and the X-basis "
    "parity (ideal value 1, value 0 for a mixture) is what certifies coherence.",
    "**Metrics.** Success probability P(0…0)+P(1…1); Hellinger fidelity of the measured distribution vs the "
    "ideal 50/50 distribution; X-parity; estimated fidelity F ≈ ½[P(0…0)+P(1…1)+⟨X⊗n⟩], which includes "
    "readout error; and exact state fidelity ⟨GHZ|ρ|GHZ⟩ from a density-matrix simulation, which includes gate "
    "noise only.",
    "**Variants.** Set B (depth): each extra layer undoes and redoes the CNOT chain. The ideal state is "
    "unchanged, while depth and CNOT count each rise by 2(n−1). Set C2 (log-depth): each qubit that is already "
    "entangled entangles one new qubit per layer, so depth = 1+⌈log₂ n⌉ with the same n−1 CNOTs.",
])
fill("Instruction: Insert circuit diagrams", [
    ("image", FIG / "circuits" / "ghz_linear_2q.png", 3.2),
    ("caption", "Figure 1: Smallest configuration, 2-qubit GHZ (Bell) circuit: H, one CNOT, Z-basis measurement."),
    ("image", FIG / "circuits" / "ghz_linear_6q.png", 5.2),
    ("caption", "Figure 2: Largest configuration, 6-qubit linear GHZ circuit: depth 6, 5 CNOTs."),
    ("image", FIG / "circuits" / "ghz_xbasis_3q.png", 4.2),
    ("caption", "Figure 3: X-basis measurement setting (3 qubits): an H on every qubit before measurement."),
    ("image", FIG / "circuits" / "ghz_depth_padded_4q_L1.png", 6.4),
    ("caption", "Figure 4: Set B depth padding (4 qubits, one extra layer): the CNOT chain is undone and redone, "
                "leaving the ideal state unchanged (depth 4 → 10)."),
    ("image", FIG / "circuits" / "ghz_logdepth_6q.png", 4.4),
    ("caption", "Figure 5: Set C2 log-depth GHZ (6 qubits): depth 4 instead of 6, same 5 CNOTs."),
])
kv_table(T[6], [None,
    "2, 3, 4, 6", "Depth = n (linear chain); Set B: 4–28 at 4 qubits; log-depth: 1+⌈log₂ n⌉",
    "Not applicable", "1024", "N0, N1, N2, N3 (optional)", "11, 22, 33, 44, 55"])
for r, j in zip(T[6].rows[1:], [
        "Covers the brief (2, 3, 4, 6); 6 keeps exact density-matrix simulation cheap (64×64)",
        "Fixed by the GHZ construction; padding isolates depth from qubit count",
        "GHZ preparation has no trainable parameters",
        "Course standard; shot-noise SD ≈ 0.01 on a probability near 0.9",
        "Course noise levels; N3 used as a stress test",
        "5 seeds per course guideline; results reported as mean ± SD"]):
    set_cell(r.cells[2], j, bold=False)

# ---------------------------------------------------------------- 4. Implementation
kv_table(T[7], [None, "3.14.0", "2.6.2", "0.18.4", "scikit-learn not used; NumPy 2.5.5, Pandas 3.1.1, Matplotlib 3.11.2",
                "Qiskit Aer (AerSimulator); density_matrix method for exact fidelity",
                "No data split; simulator seeds 11, 22, 33, 44, 55 (X basis seed+500, calibration seed+2000)",
                "N1: 0.1% / 0.5% / 1%   N2: 1% / 2% / 3%   N3: 3% / 5% / 8%  (1-qubit / 2-qubit depolarizing / readout)",
                "AMD Ryzen 5 5500U, 15.3 GB RAM, Windows 11; full run ≈ 20 s"])
fill("Instruction: Summarise main functions", [
    "All experiments are in one script, `ghz_experiments.py` (≈ 600 lines), with `requirements.txt` for a clean "
    "environment. `python ghz_experiments.py` runs everything end-to-end and writes every table and figure.",
    ("bullet", "`ghz_linear(n, extra_layers)`, `ghz_logdepth(n)`, `with_measurement(qc, basis)`: build the circuits."),
    ("bullet", "`build_noise_model(level)`: depolarizing + readout noise for N0–N3."),
    ("bullet", "`run_counts()`, `exact_state_fidelity()`: shot-based and density-matrix simulation."),
    ("bullet", "`calibrate_readout()`, `mitigate()`: tensored readout-error mitigation."),
    ("bullet", "`run_main()`, `run_depth()`, `run_logdepth()`: experiment sets A, B and C2."),
    ("bullet", "Outputs: `results/` (CSV tables, summary.md, raw_counts.json, environment.json) and `figures/`."),
    f"**Repository:** {REPO_URL}",
])
fill("Instruction: Show the code snippet that builds the NoiseModel", code('''
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, ReadoutError, depolarizing_error

NOISE_LEVELS = {"N1": dict(p1=0.001, p2=0.005, ro=0.01),
                "N2": dict(p1=0.010, p2=0.020, ro=0.03),
                "N3": dict(p1=0.030, p2=0.050, ro=0.08)}

def build_noise_model(level):
    cfg = NOISE_LEVELS[level]
    nm = NoiseModel(basis_gates=["h", "x", "cx"])
    nm.add_all_qubit_quantum_error(depolarizing_error(cfg["p1"], 1), ["h", "x"])
    nm.add_all_qubit_quantum_error(depolarizing_error(cfg["p2"], 2), ["cx"])
    ro = cfg["ro"]
    nm.add_all_qubit_readout_error(ReadoutError([[1 - ro, ro], [ro, 1 - ro]]))
    return nm

# attaching the noise model to the simulator
sim = AerSimulator(noise_model=build_noise_model("N2"), seed_simulator=11)
counts = sim.run(qc, shots=1024).result().get_counts()
''') + [
    "Exact fidelity uses the same noise model with `AerSimulator(method=\"density_matrix\")` and "
    "`qc.save_density_matrix()`, compared with the ideal `Statevector` using `state_fidelity`.",
])
console = ["Set A: qubits x noise"] + [
    f"  {r.exp_id}  n={r.qubits}  {r.noise:<3} success={r.success_mean:.3f}  F_exact={r.fidelity_exact:.3f}"
    for r in A.itertuples()] + ["Set B: depth experiment", "Set C2: linear vs log-depth",
                                "Saving tables and figures", "Done in 19.9s"]
fill("Instruction: Insert screenshots", [
    "Console output of a full run (`python ghz_experiments.py`):",
] + [("code", l) for l in console], keep_instruction=True)

# ---------------------------------------------------------------- 5. Experiments
fill("Instruction: Minimum: 6 controlled", [])
order = [(n, l) for l in ["N0", "N1", "N2", "N3"] for n in [2, 3, 4, 6]]
cfg_rows = []
for k, (n, l) in enumerate(order, 1):
    note = "5 seeds; Z + X basis"
    if l != "N0":
        note += "; + readout mitigation"
    if l == "N3":
        note += "; optional stress test"
    cfg_rows.append([f"E{k:02d}", str(n), f"{n} (linear)", NOISE_NAME[l], "1024", note])
fill_table(T[8], None, cfg_rows)
note_p = find("Recommended matrix from the assignment document")._p
insert_after(note_p, [
    "",
    "The recommended matrix was adapted for GHZ states. Depth is fixed at n by the construction, so the two "
    "varied parameters are qubit count and noise level, giving 16 experiments (E01–E16). Two further sets were "
    "run with the same settings. **Set B (D01–D15):** 4 qubits with 0–4 extra identity CNOT layers (depth "
    "4–28) × N0–N2. **Set C:** readout-error mitigation applied to every noisy Set A run (C1), and linear vs "
    "log-depth construction for 2–6 qubits × N0–N2 (C2).",
])
note_p.getparent().remove(note_p)

res_rows = []
for k, (n, l) in enumerate(order, 1):
    r = rowA(n, l)
    res_rows.append([f"E{k:02d}", pm(r.success_mean, r.success_std),
                     f"{pm(r.parity_mean, r.parity_std)} / {r.fidelity_exact:.3f}",
                     str(r.total_gates), str(r.cx_count), str(r.depth), "1.000"])
fill_table(T[9], ["Exp.", "Success probability (mean ± SD)", "X-parity (mean ± SD) / exact fidelity",
                  "Total gates", "Two-qubit gates", "Depth", "Baseline (ideal GHZ)"], res_rows)

instr52 = find("Instruction: Report: State fidelity")._p
insert_after(instr52, [
    "Table 5.2 reports the 16 Set A experiments (5 seeds × 1024 shots). Success probability = P(0…0)+P(1…1) "
    "(parity success); X-parity = ⟨X⊗n⟩; exact fidelity from the density-matrix simulation. The baseline is the "
    "ideal GHZ state, for which all three metrics equal 1. The circuits use only the simulator basis gates "
    "{h, x, cx}, so the transpiled depth equals the logical depth shown. Measurement distributions are shown in "
    "Figure 6. Hellinger fidelity and the estimated fidelity are in `results/main_results.csv`.",
])
instr52.getparent().remove(instr52)

tbl52 = T[9]._tbl
d = B[B.noise != "N0"]
b_rows = [[r.exp_id, r.noise, str(r.extra_layers), str(r.depth), str(r.cx_count),
           pm(r.success_mean, r.success_std), f"{r.fidelity_exact:.3f}"] for r in d.itertuples()]
m = A[A.noise != "N0"]
c1_rows = [[str(r.qubits), r.noise, pm(r.success_mean, r.success_std),
            pm(r.success_mitig_mean, r.success_mitig_std), f"{r.fidelity_est_mean:.3f}",
            f"{r.fidelity_est_mitig_mean:.3f}", f"{r.fidelity_exact:.3f}"] for r in m.itertuples()]
c2_rows = []
for n in [2, 3, 4, 6]:
    lin = C2[(C2.qubits == n) & (C2.noise == "N2") & (C2.construction == "linear")].iloc[0]
    log = C2[(C2.qubits == n) & (C2.noise == "N2") & (C2.construction == "log-depth")].iloc[0]
    c2_rows.append([str(n), str(lin.depth), str(log.depth), str(lin.cx_count),
                    pm(lin.success_mean, lin.success_std), pm(log.success_mean, log.success_std),
                    f"{lin.fidelity_exact:.3f} / {log.fidelity_exact:.3f}"])
insert_after(tbl52, [
    "",
    "**Table 5.3: Set B, circuit depth at 4 qubits** (target state unchanged; at N0 all depths give 1.000).",
    ("table", T[9], (["Exp.", "Noise", "Extra layers", "Depth", "CNOTs", "Success P (mean ± SD)",
                      "Exact fidelity"], b_rows)),
    "",
    "**Table 5.4: Set C1, readout-error mitigation** (overhead: 2 calibration circuits per qubit count).",
    ("table", T[9], (["Qubits", "Noise", "Success raw", "Success mitigated", "F est. raw",
                      "F est. mitigated", "F exact"], c1_rows)),
    "",
    "**Table 5.5: Set C2, linear vs log-depth construction at N2.**",
    ("table", T[9], (["Qubits", "Depth (linear)", "Depth (log)", "CNOTs (both)", "Success linear",
                      "Success log-depth", "F exact lin / log"], c2_rows)),
])

fill("Instruction: Insert labelled graphs", [
    ("image", FIG / "fig1_histogram_grid.png", 6.7),
    ("caption", "Figure 6: Measurement distributions for E01–E16 (seed 11, 1024 shots). Dark bars = GHZ outcomes "
                "|0…0⟩, |1…1⟩; red = error outcomes. Rows: qubits; columns: noise level."),
    ("image", FIG / "fig2_success_vs_qubits.png", 4.8),
    ("caption", "Figure 7: Success probability vs number of qubits for each noise level (mean ± SD, 5 seeds)."),
    ("image", FIG / "fig3_fidelity_vs_qubits.png", 5.0),
    ("caption", "Figure 8: Exact state fidelity (solid) vs measured two-setting estimate (dashed). The gap is "
                "readout error."),
    ("image", FIG / "fig4_parity_vs_qubits.png", 4.8),
    ("caption", "Figure 9: X-basis parity ⟨X⊗n⟩ (coherence) vs number of qubits."),
    ("image", FIG / "fig6_success_heatmap.png", 4.6),
    ("caption", "Figure 10: Success probability heatmap, qubits × noise level."),
    ("image", FIG / "fig8_depth_experiment.png", 6.4),
    ("caption", "Figure 11: Set B, success probability and exact fidelity vs circuit depth at 4 qubits."),
    ("image", FIG / "fig9_readout_mitigation.png", 6.4),
    ("caption", "Figure 12: Set C1, success probability before and after readout-error mitigation."),
    ("image", FIG / "fig7_resources_linear_vs_logdepth.png", 6.4),
    ("caption", "Figure 13: Set C2, depth and CNOT count, linear vs log-depth construction."),
])

# ---------------------------------------------------------------- 6. Comparison
fill("Instruction: Baseline for your group", [
    "The baseline is the ideal GHZ state (N0). To keep the comparison fair, every method below uses 6 qubits, "
    "N2 noise, the same 5 seeds and 1024 shots.",
])
r0, r2 = rowA(6, "N0"), rowA(6, "N2")
log6 = C2[(C2.qubits == 6) & (C2.noise == "N2") & (C2.construction == "log-depth")].iloc[0]
fill_table(T[10], None, [
    ["Ideal GHZ, 6 qubits, N0 (baseline)", f"Success {pm(r0.success_mean, r0.success_std)}; F = 1.000",
     "6 / 6 / 6 (5 CX)", "Reference: exact 50/50, parity 1"],
    ["Linear GHZ, 6 qubits, N2, raw", f"Success {pm(r2.success_mean, r2.success_std)}; "
     f"F est. {pm(r2.fidelity_est_mean, r2.fidelity_est_std)}; F exact {r2.fidelity_exact:.3f}",
     "6 / 6 / 6 (5 CX)", "−0.227 success vs baseline; most of the loss is readout"],
    ["Linear GHZ, 6 qubits, N2 + readout mitigation",
     f"Success {pm(r2.success_mitig_mean, r2.success_mitig_std)}; "
     f"F est. {pm(r2.fidelity_est_mitig_mean, r2.fidelity_est_mitig_std)}",
     "6 / 6 / 6 + 2 calibration circuits", "Recovers 0.142 success; estimate approaches exact 0.913"],
    ["Log-depth GHZ, 6 qubits, N2", f"Success {pm(log6.success_mean, log6.success_std)}; "
     f"F exact {log6.fidelity_exact:.3f}", "6 / 4 / 6 (5 CX)", "Depth −33%, no fidelity gain (no idle noise in model)"],
])
fill("Instruction: Discuss: How qubit count", [
    "**Qubit count (RQ1).** At N0 every size reproduces the ideal state exactly (Table 5.2, E01–E04), so all "
    f"loss is due to noise. Fidelity then falls monotonically with n at every noise level (Figures 7 and 8). At N2, "
    f"success drops from {rowA(2,'N2').success_mean:.3f} (2 qubits) to {rowA(6,'N2').success_mean:.3f} "
    f"(6 qubits), and exact fidelity from {rowA(2,'N2').fidelity_exact:.3f} to {rowA(6,'N2').fidelity_exact:.3f}. "
    f"At N3, success at 6 qubits is {rowA(6,'N3').success_mean:.3f}, so half of all shots are error outcomes "
    "(Figure 6). Each added qubit adds one noisy CNOT and one noisy readout, so error-free shots become rarer "
    "with size. The seed-to-seed SD stays at or below 0.02, so these differences are far larger than shot noise.",
    f"**Coherence vs populations (RQ2).** X-parity falls faster than success probability (Figure 9). For 6 qubits "
    f"at N2, success is {rowA(6,'N2').success_mean:.3f} but parity is only {rowA(6,'N2').parity_mean:.3f}. A "
    "phase error on any one qubit flips the sign between |0…0⟩ and |1…1⟩ and so cancels the coherence, whereas a "
    "bit flip only moves a shot out of the GHZ outcomes. This agrees with the faster coherence decay reported by "
    "Monz et al. [3]. Z-basis histograms alone therefore overstate entanglement quality.",
    f"**Gate vs readout noise (RQ3).** For 6 qubits at N2, the measured fidelity estimate is "
    f"{rowA(6,'N2').fidelity_est_mean:.3f} while the exact state fidelity is {rowA(6,'N2').fidelity_exact:.3f} "
    "(Figure 8). About three-quarters of the shortfall is readout error, not damage to the state. Readout "
    f"mitigation raises the estimate to {rowA(6,'N2').fidelity_est_mitig_mean:.3f} for two extra calibration "
    "circuits (Table 5.4, Figure 12). In all 12 noisy runs the mitigated estimate lies within 0.09 of the exact "
    "value, which also validates the two-setting estimator. Hellinger fidelity equals success probability to "
    "within 0.001, because it ignores coherence.",
    "**Depth and resources.** With the qubit count fixed at 4, raising depth from 4 to 28 lowers exact fidelity "
    f"at N2 from {B[(B.noise=='N2')&(B.extra_layers==0)].fidelity_exact.iloc[0]:.3f} to "
    f"{B[(B.noise=='N2')&(B.extra_layers==4)].fidelity_exact.iloc[0]:.3f}, about 1.3 percentage points per "
    "extra CNOT (Table 5.3, Figure 11). The log-depth construction cuts depth by up to 33% (Figure 13) but "
    "leaves fidelity unchanged (Table 5.5). The noise model charges errors per gate, the CNOT count is "
    "identical, and there is no idle-time decoherence to benefit from the shorter circuit. No quantum advantage "
    "is claimed. GHZ preparation is a benchmark of entanglement quality, not a computational task.",
])

# ---------------------------------------------------------------- 7. Limitations
fill("Instruction: Simulator-only results", [
    ("bullet", "**Simulator only.** All results come from Qiskit Aer, with no real-hardware run."),
    ("bullet", "**Simplified noise model.** Depolarizing gate error plus symmetric readout error. It has no T1/T2 idle "
               "decoherence, crosstalk, leakage or correlated errors. This is why log-depth showed no gain."),
    ("bullet", "**No connectivity constraints.** Real devices need SWAPs to route the CNOT chain, adding gates; by "
               "Set B, each extra CNOT costs about 1.3 percentage points of fidelity at N2."),
    ("bullet", "**Approximate fidelity estimate.** The two-setting estimator also includes coherences between other "
               "complementary bit-string pairs. Parity oscillations or MQC give a rigorous bound."),
    ("bullet", "**Scalability.** n ≤ 6. Tensored mitigation needs a 2ⁿ × 2ⁿ matrix, and exact density-matrix "
               "simulation grows as 4ⁿ, so both are impractical much beyond 12–15 qubits."),
])
fill("Instruction: Propose one concrete", [
    "**Proposed improvement: add thermal relaxation (T1/T2) with gate durations and scheduling, then re-test "
    "the log-depth construction.**",
    "In the current model, errors are charged per gate, so two circuits with the same CNOT count have the same "
    "fidelity whatever their depth (Table 5.5). On real hardware, qubits also decohere while they wait. In the "
    "linear chain, qubit k sits idle for about k CNOT durations before it is entangled, while in the log-depth "
    "circuit no qubit waits more than ⌈log₂ n⌉ layers. With T1/T2 noise (e.g., T1 = 100 µs, T2 = 80 µs, "
    "CNOT = 300 ns, via `thermal_relaxation_error` and a scheduled circuit), the log-depth circuit should keep "
    "noticeably higher fidelity at 6+ qubits, which is what hardware studies such as Mooney et al. [7] rely on. "
    "This is a direct, falsifiable test of finding F7. It can be combined with readout mitigation, and scaled up "
    "using M3 [8] and a fake backend with a real coupling map so that routing overhead is included.",
])

# ---------------------------------------------------------------- 8. Key findings
fill("Instruction: This section helps faculty", [])
kv_table(T[11], [
    f"(1) Fidelity falls monotonically with qubit count: success at N2 drops from {rowA(2,'N2').success_mean:.3f} "
    f"to {rowA(6,'N2').success_mean:.3f} from 2 to 6 qubits. (2) Coherence is more fragile than populations: X-parity "
    f"{rowA(6,'N2').parity_mean:.3f} vs success {rowA(6,'N2').success_mean:.3f} (6 qubits, N2). (3) Readout dominates "
    f"the measured loss: F est. {rowA(6,'N2').fidelity_est_mean:.3f} vs exact {rowA(6,'N2').fidelity_exact:.3f}; "
    f"mitigation recovers {rowA(6,'N2').fidelity_est_mitig_mean:.3f}.",
    "For exact fidelity ≥ 0.9: all sizes up to 6 qubits at N1 and N2, but only n ≤ 3 at N3. With readout "
    "mitigation, measured fidelity ≥ 0.9 is reached up to 4 qubits at N2 (0.935). Recommended: shallowest "
    "circuit (log-depth) plus readout mitigation.",
    "Controlled separation of gate and readout contributions using exact density-matrix ground truth; "
    "validation of a cheap two-setting fidelity estimator; and depth isolated from qubit count by "
    "identity padding. Hardware studies [4]–[7] cannot separate these factors.",
    "The log-depth construction gives no fidelity gain under gate-only noise (same CNOT count). Hellinger "
    "fidelity is identical to success probability and blind to coherence.",
    "Table 5.2, Table 5.4; Figures 6, 8, 9, 11, 12.",
    "GHZ state; multipartite entanglement; quantum noise; depolarizing channel; readout-error mitigation; "
    "state fidelity; Qiskit Aer; quantum benchmarking",
])
concl = find("Conclusion")._p
nxt = concl.getnext()
while nxt is not None and not "".join(nxt.itertext()).strip() and nxt.find(".//" + qn("w:pStyle")) is None:
    after = nxt.getnext(); nxt.getparent().remove(nxt); nxt = after
insert_after(concl, [
    "GHZ states were prepared exactly at every size from 2 to 6 qubits in ideal simulation, with linear resource "
    "cost: depth n and n−1 CNOTs. Under the course noise levels, quality falls monotonically with both qubit "
    "count and depth. Coherence (X-parity) decays faster than computational-basis populations, so histograms "
    "alone overstate entanglement.",
    "Most of the measured loss comes from readout error rather than damage to the state. Low-cost tensored "
    "readout mitigation recovers most of it, bringing measured fidelity close to the exact value. Shortening "
    "the circuit with a log-depth construction only pays off once idle decoherence is modelled, which is the "
    "proposed next step. Every configuration kept exact fidelity above 0.5, the threshold for genuine "
    "multipartite entanglement.",
])

# ---------------------------------------------------------------- References
fill("Instruction: Use IEEE style", [
    "[1] D. M. Greenberger, M. A. Horne, and A. Zeilinger, “Going beyond Bell’s theorem,” in *Bell’s Theorem, "
    "Quantum Theory and Conceptions of the Universe*, M. Kafatos, Ed. Dordrecht: Kluwer, 1989, pp. 69–72, "
    "arXiv:0712.0921.",
    "[2] N. D. Mermin, “Extreme quantum entanglement in a superposition of macroscopically distinct states,” "
    "*Phys. Rev. Lett.*, vol. 65, p. 1838, 1990, doi: 10.1103/PhysRevLett.65.1838.",
    "[3] T. Monz et al., “14-qubit entanglement: Creation and coherence,” *Phys. Rev. Lett.*, vol. 106, "
    "p. 130506, 2011, doi: 10.1103/PhysRevLett.106.130506.",
    "[4] C. Song et al., “Generation of multicomponent atomic Schrödinger cat states of up to 20 qubits,” "
    "*Science*, vol. 365, pp. 574–577, 2019, doi: 10.1126/science.aay0600.",
    "[5] A. Omran et al., “Generation and manipulation of Schrödinger cat states in Rydberg atom arrays,” "
    "*Science*, vol. 365, pp. 570–574, 2019, doi: 10.1126/science.aax9743.",
    "[6] K. X. Wei et al., “Verifying multipartite entangled Greenberger-Horne-Zeilinger states via multiple "
    "quantum coherences,” *Phys. Rev. A*, vol. 101, p. 032343, 2020, doi: 10.1103/PhysRevA.101.032343.",
    "[7] G. J. Mooney, G. A. L. White, C. D. Hill, and L. C. L. Hollenberg, “Generation and verification of "
    "27-qubit Greenberger-Horne-Zeilinger states in a superconducting quantum computer,” *J. Phys. Commun.*, "
    "vol. 5, p. 095004, 2021, doi: 10.1088/2399-6528/ac1df7.",
    "[8] P. D. Nation, H. Kang, N. Sundaresan, and J. M. Gambetta, “Scalable mitigation of measurement errors "
    "on quantum computers,” *PRX Quantum*, vol. 2, p. 040326, 2021, doi: 10.1103/PRXQuantum.2.040326.",
    "[9] A. Javadi-Abhari et al., “Quantum computing with Qiskit,” arXiv:2405.08810, 2024, "
    "doi: 10.48550/arXiv.2405.08810.",
    "[10] Qiskit Aer contributors, *Qiskit Aer: high-performance simulators for Qiskit*, v0.18.4. "
    "[Online]. Available: https://github.com/Qiskit/qiskit-aer",
    "No external dataset was used; all circuits are generated in code.",
])

# ---------------------------------------------------------------- Appendix B (AI disclosure)
set_cell(T[13].rows[0].cells[1],
         "Claude (Anthropic): helped write the Qiskit experiment script and plotting code, and draft the report "
         "text. All experiments were run by the group and all numbers come from the actual run outputs. "
         "[Group to confirm / edit]", bold=False)

# ---------------------------------------------------------------- author details / remove extras
AUTHOR, USN = "Vishalaachi P P", "1MS23CY075"
# the uploaded cover page replaces the template's title block + team table
first = doc.element.body[0]
while not (first.tag == qn("w:tbl") and "Course / Section" in "".join(first.itertext())):
    nxt = first.getnext(); first.getparent().remove(first); first = nxt
info = Table(first, doc._body)
kv_table(info, ["Quantum Computing (23CYE732), VII Semester, Dept. of CSE (Cyber Security)",
                None, None, "", REPO_URL])
# contents page: title, TOC field (filled by Word in tools/finalize_report.ps1), submission details
def toc_field():
    p = make_p("")
    def fld(kind):
        r = OxmlElement("w:r"); f = OxmlElement("w:fldChar"); f.set(qn("w:fldCharType"), kind)
        r.append(f); return r
    instr = OxmlElement("w:r"); it = OxmlElement("w:instrText")
    it.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    it.text = r' TOC \o "1-2" \h \z \u '
    instr.append(it)
    p.append(fld("begin")); p.append(instr); p.append(fld("separate"))
    p.append(_run("Right-click and choose Update Field to build the table of contents."))
    p.append(fld("end"))
    return p
first.addprevious(make_p("Contents", "center"))
first.addprevious(toc_field())
first.addprevious(make_p(""))
first.addprevious(make_p("Submission Details"))
fill_table(T[12], None, [[AUTHOR, "All work: literature review, circuit design, coding, experiments, "
                                  "analysis and report writing"]])
decl = find("We declare that this work is our own")
decl.runs[0].text = ("I declare that this work is my own, that all sources are cited, that experiments were "
                     "actually run and results are not fabricated, and that any use of AI tools (including code "
                     "assistants) is disclosed below. I consent to the use of this work, with acknowledgement, "
                     "in a research paper prepared by the faculty guide.")
for r in decl.runs[1:]:
    r._r.getparent().remove(r._r)
set_cell(T[13].rows[0].cells[1],
         "Claude (Anthropic): assisted with the Qiskit experiment script, plotting code and drafting of the "
         "report text. All experiments were run and all numbers come from the actual run outputs.", bold=False)
set_cell(T[13].rows[1].cells[0], "Signature")
# screenshot instruction line, submission checklist
ins = find("Instruction: Insert screenshots")._p
ins.getparent().remove(ins)
chk = find("Appendix C")._p
el = chk.getnext()
while el is not None and el.tag == qn("w:p") and "Evaluation" not in "".join(el.itertext()):
    nxt = el.getnext(); el.getparent().remove(el); el = nxt
chk.getparent().remove(chk)
# any remaining instruction lines
for p in list(paras()):
    if p.text.strip().startswith("Instruction:"):
        p._p.getparent().remove(p._p)
# collapse runs of 2+ empty paragraphs into one
prev_empty = False
for el in list(doc.element.body):
    empty = (el.tag == qn("w:p") and not "".join(el.itertext()).strip()
             and el.find(".//" + qn("w:drawing")) is None and el.find(".//" + qn("w:sectPr")) is None)
    if empty and prev_empty:
        el.getparent().remove(el)
    prev_empty = empty

# ---------------------------------------------------------------- fonts
# main headings: TNR 16 bold | subheadings: TNR 14 bold | content: TNR 12 bold
COVER_TITLES = {"Contents"}
SUB_TITLES = {"Submission Details"}


def style_of(p):
    s = p._p.find(f"{qn('w:pPr')}/{qn('w:pStyle')}")
    return s.get(qn("w:val")) if s is not None else ""


def apply_font(p, size_pt):
    half = str(size_pt * 2)
    ppr = p._p.get_or_add_pPr()
    targets = [r._r.get_or_add_rPr() for r in p.runs]
    mark = ppr.find(qn("w:rPr"))
    if mark is None:
        mark = OxmlElement("w:rPr"); ppr.append(mark)
    targets.append(mark)
    for rpr in targets:
        for tag in ("w:rFonts", "w:b", "w:bCs", "w:sz", "w:szCs"):
            old = rpr.find(qn(tag))
            if old is not None:
                rpr.remove(old)
        f = OxmlElement("w:rFonts")
        for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            f.set(qn(a), "Times New Roman")
        rpr.insert(0, f)
        # schema order: rFonts, b, bCs, i, iCs, ..., color, ..., sz, szCs
        rpr.insert(1, OxmlElement("w:b"))
        rpr.insert(2, OxmlElement("w:bCs"))
        for tag in ("w:sz", "w:szCs"):
            e = OxmlElement(tag); e.set(qn("w:val"), half)
            after = [c for c in rpr if c.tag in (qn("w:highlight"), qn("w:u"), qn("w:effect"), qn("w:bdr"),
                                                 qn("w:shd"), qn("w:fitText"), qn("w:vertAlign"), qn("w:rtl"),
                                                 qn("w:cs"), qn("w:em"), qn("w:lang"), qn("w:eastAsianLayout"),
                                                 qn("w:specVanish"), qn("w:oMath"))]
            if after:
                after[0].addprevious(e)
            else:
                rpr.append(e)


def all_paragraphs():
    for p in doc.paragraphs:
        yield p, True
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    yield p, False
    for s in doc.sections:
        for part in (s.header, s.footer):
            for p in part.paragraphs:
                yield p, False


seen = set()
for p, in_body in all_paragraphs():
    if p._p in seen:
        continue
    seen.add(p._p)
    st = style_of(p)
    if st in ("Heading1", "Title") or (in_body and p.text.strip() in COVER_TITLES):
        apply_font(p, 16)
    elif st in ("Heading2", "Heading3") or (in_body and p.text.strip() in SUB_TITLES):
        apply_font(p, 14)
    else:
        apply_font(p, 12)

# heading styles themselves (so Word's style pane agrees)
for name, size in (("Heading 1", 16), ("Heading 2", 14), ("Heading 3", 14)):
    try:
        s = doc.styles[name]
        s.font.name, s.font.bold = "Times New Roman", True
        s.font.size = docx.shared.Pt(size)
    except KeyError:
        pass

# ---------------------------------------------------------------- layout: pagination and spacing
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.shared import Pt  # noqa: E402

for p in doc.paragraphs:
    st, pf = style_of(p), p.paragraph_format
    ppr = p._p.pPr
    is_code = ppr is not None and ppr.find(qn("w:shd")) is not None and \
        ppr.find(qn("w:shd")).get(qn("w:fill")) == "F2F2F2"
    has_img = p._p.find(".//" + qn("w:drawing")) is not None
    if st == "Heading1":
        pf.page_break_before = True
        pf.keep_with_next = True
    elif st in ("Heading2", "Heading3") or p.text.strip() in SUB_TITLES:
        pf.keep_with_next = True
        pf.space_before = Pt(12)
    elif has_img or p.text.startswith("Table 5."):
        pf.keep_with_next = True
        pf.space_before = Pt(10)
    elif is_code:
        pf.line_spacing = 1.0
    elif p.text.strip() and pf.alignment != WD_ALIGN_PARAGRAPH.CENTER and st == "":
        pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        pf.line_spacing = 1.15
        pf.space_after = Pt(6)

# repeat dark header rows when a table breaks across pages
for t in doc.tables:
    tc0 = t.rows[0].cells[0]._tc
    shd = tc0.find(f"{qn('w:tcPr')}/{qn('w:shd')}")
    if shd is not None and shd.get(qn("w:fill")) == "1F3864":
        trpr = t.rows[0]._tr.get_or_add_trPr()
        if trpr.find(qn("w:tblHeader")) is None:
            trpr.append(OxmlElement("w:tblHeader"))

# ---------------------------------------------------------------- header: logo left, title right, rule below
hdr = doc.sections[0].header
for extra in hdr.paragraphs[1:]:
    extra._p.getparent().remove(extra._p)
hp = hdr.paragraphs[0]
for r in list(hp.runs):
    r._r.getparent().remove(r._r)
hp.alignment = WD_ALIGN_PARAGRAPH.LEFT
hp.add_run().add_picture(str(LOGO), height=Inches(0.45))
tab = hp.add_run()
pt_ = OxmlElement("w:ptab")
pt_.set(qn("w:relativeTo"), "margin"); pt_.set(qn("w:alignment"), "right"); pt_.set(qn("w:leader"), "none")
tab._r.append(pt_)
ht = hp.add_run("Quantum Computing  |  GHZ States and Noise")
ht.font.name, ht.font.size, ht.font.bold = "Times New Roman", Pt(12), True
ht._r.rPr.rFonts.set(qn("w:cs"), "Times New Roman")
ht.font.color.rgb = docx.shared.RGBColor(0x1F, 0x38, 0x64)
hppr = hp._p.get_or_add_pPr()
bdr = OxmlElement("w:pBdr")
bot = OxmlElement("w:bottom")
for k, v in (("w:val", "single"), ("w:sz", "8"), ("w:space", "4"), ("w:color", "1F3864")):
    bot.set(qn(k), v)
bdr.append(bot)
anchor = next((c for c in hppr if c.tag in (qn("w:shd"), qn("w:tabs"), qn("w:spacing"), qn("w:ind"),
                                            qn("w:jc"), qn("w:rPr"))), None)
anchor.addprevious(bdr) if anchor is not None else hppr.append(bdr)

# ---------------------------------------------------------------- cover page (own section: border, no page number)
cov = docx.Document(COVER)
for p in cov.paragraphs:
    if p.text.startswith("Period Finding"):
        p.runs[0].text = ("GHZ State Generation and Noise Analysis: Effect of Qubit Count, "
                          "Circuit Depth and Readout Error")
        for r in p.runs[1:]:
            r._r.getparent().remove(r._r)
    elif p.text.strip() == "Team Members":
        p.runs[0].text = "Submitted by"
        for r in p.runs[1:]:
            r._r.getparent().remove(r._r)
ct = cov.tables[0]
for tr in ct._tbl.findall(qn("w:tr"))[2:]:
    ct._tbl.remove(tr)
for c, v in zip(ct.rows[1].cells, ["1", AUTHOR, USN]):
    set_cell(c, v)
cbody = cov.element.body
csect = deepcopy(cbody.find(qn("w:sectPr")))
cover_els = [deepcopy(e) for e in cbody if e.tag != qn("w:sectPr")]
for e in cover_els:                       # fonts came from the cover's own defaults: make them explicit
    for r in e.iter(qn("w:r")):
        rpr = r.find(qn("w:rPr"))
        if rpr is None:
            rpr = OxmlElement("w:rPr"); r.insert(0, rpr)
        if rpr.find(qn("w:rFonts")) is None:
            f = OxmlElement("w:rFonts")
            for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
                f.set(qn(a), "Times New Roman")
            rpr.insert(0, f)
# drop trailing empty paragraphs so the cover stays one page
while cover_els and cover_els[-1].tag == qn("w:p") and not "".join(cover_els[-1].itertext()).strip():
    cover_els.pop()
main_sect = doc.element.body.find(qn("w:sectPr"))
for i, ref in enumerate(main_sect.findall(qn("w:headerReference"))):
    csect.insert(i, deepcopy(ref))
pg = OxmlElement("w:pgNumType"); pg.set(qn("w:start"), "1")
cols = main_sect.find(qn("w:cols"))
cols.addprevious(pg) if cols is not None else main_sect.find(qn("w:pgMar")).addnext(pg)
last = cover_els[-1]
if last.tag != qn("w:p"):
    last = OxmlElement("w:p"); cover_els.append(last)
lppr = last.find(qn("w:pPr"))
if lppr is None:
    lppr = OxmlElement("w:pPr"); last.insert(0, lppr)
lppr.append(csect)
body0 = doc.element.body[0]
for e in cover_els:
    body0.addprevious(e)

doc.save(OUT)
print("saved", OUT)
