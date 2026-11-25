# Report Outline: Group 12, GHZ State Generation and Noise Analysis

Section headings follow the 20-mark rubric. All numbers below come from
`results/summary.md` (5 seeds, 1024 shots). Re-running the script reproduces them exactly.

---

## 1. Problem understanding and objectives (2 marks)

**Problem statement.** GHZ states, (|0…0⟩ + |1…1⟩)/√2, are maximally entangled
multi-qubit states used in quantum metrology, error-correction codes and as hardware
benchmarks. Their coherence is known to be fragile: a single error on any qubit can
destroy the superposition. This project measures how that fragility scales with qubit count.

**Objectives**
1. Build GHZ circuits for 2, 3, 4 and 6 qubits in Qiskit and record their resources.
2. Measure computational-basis probabilities under ideal, low, moderate (and high) noise.
3. Quantify degradation using success probability, Hellinger fidelity, X-parity and state fidelity.
4. Separate the effect of qubit count from the effect of circuit depth.
5. Evaluate two improvements: readout-error mitigation and log-depth construction.

**Research questions**
- RQ1: How do success probability and fidelity change as the number of qubits grows?
- RQ2: Which noise source (gate or readout) dominates the measured degradation?
- RQ3: Is coherence (X-parity) more sensitive to noise than populations (Z-basis)?
- RQ4: Can low-cost techniques recover GHZ fidelity, and at what overhead?

---

## 2. Literature review (3 marks, minimum 5 papers)

Suggested papers. These are real publications, but **check every citation in Google
Scholar before submitting**, and read at least the abstract of each.

| # | Paper | Why it is relevant |
|---|---|---|
| 1 | Greenberger, Horne, Zeilinger, *Going beyond Bell's theorem* (1989), in *Bell's Theorem, Quantum Theory and Conceptions of the Universe* | Original GHZ state |
| 2 | Mermin, *Extreme quantum entanglement in a superposition of macroscopically distinct states*, Phys. Rev. Lett. 65, 1838 (1990) | GHZ non-locality, parity witness |
| 3 | Monz et al., *14-qubit entanglement: creation and coherence*, Phys. Rev. Lett. 106, 130506 (2011) | Coherence decays faster with more qubits (superdecoherence) |
| 4 | Song et al., *Generation of multicomponent atomic Schrödinger cat states of up to 20 qubits*, Science 365, 574 (2019) | Large GHZ on superconducting qubits |
| 5 | Omran et al., *Generation and manipulation of Schrödinger cat states in Rydberg atom arrays*, Science 365, 570 (2019) | GHZ on neutral atoms, fidelity scaling |
| 6 | Wei et al., *Verifying multipartite entangled GHZ states via multiple quantum coherences*, Phys. Rev. A 101, 032343 (2020) | GHZ fidelity measurement on IBM hardware |
| 7 | Mooney et al., *Generation and verification of 27-qubit GHZ states in a superconducting quantum computer*, J. Phys. Commun. 5, 095004 (2021) | Log-depth construction, readout mitigation |
| 8 | Nation et al., *Scalable mitigation of measurement errors on quantum computers*, PRX Quantum 2, 040326 (2021) | Readout-error mitigation (basis for improvement C1) |
| 9 | Javadi-Abhari et al., *Quantum computing with Qiskit*, arXiv:2405.08810 (2024) | Software framework |

**Research gap to state.** Hardware papers report GHZ fidelity on specific devices,
where noise sources are mixed together. Few student-scale studies *isolate* qubit count,
depth, gate noise and readout noise under controlled, reproducible noise models, or
compare measured fidelity estimates against exact state fidelity.

---

## 3. Algorithm / circuit design (3 marks)

- **GHZ circuit:** H on q0, then a CNOT chain q0→q1→…→q(n−1).
  Include `figures/circuits/ghz_linear_{2,3,4,6}q.png`.
- **Resources (linear):** depth = n, CNOTs = n−1, total gates = n. Resources grow linearly.
- **X-basis measurement:** an H on every qubit before measuring
  (`ghz_xbasis_3q.png`). Explain why this step is needed: Z-basis counts cannot tell a
  real GHZ state from a classical 50/50 mixture.
- **Fidelity estimate:** F ≈ [P(0…0)+P(1…1) + ⟨X⊗n⟩]/2.
- **Depth padding (set B):** uncompute + recompute the CNOT chain
  (`ghz_depth_padded_4q_L1.png`). This leaves the ideal state unchanged while depth goes 4→10→…→28.
- **Log-depth GHZ (set C2):** each entangled qubit spreads to a new one every layer, so
  depth = 1+⌈log₂n⌉ (`ghz_logdepth_6q.png`).
- **Noise model:** a table of N0–N3 and why depolarizing + readout error was chosen
  (it follows the course guidelines).

---

## 4. Qiskit implementation (4 marks)

- Code: `ghz_experiments.py`. Include screenshots of the key functions (`ghz_linear`,
  `build_noise_model`, `run_main`, `calibrate_readout`) and of the console output.
- Reproducibility: fixed seeds, `results/environment.json`, `results/raw_counts.json`,
  `requirements.txt`.
- Simulator: `AerSimulator` (shot-based) plus the `density_matrix` method for exact fidelity.

---

## 5. Experiments and visualization (3 marks)

- Table: Set A (16 experiments). Copy it from `summary.md`.
- Figures: fig1 (histogram grid), fig2 (success), fig3 (fidelity), fig4 (parity),
  fig6 (heatmap), fig8 (depth experiment).

---

## 6. Comparative analysis (2 marks), key findings

**F1. Ideal behaviour is exact at every size.** At N0, every n gives about 50/50 on
|0…0⟩ and |1…1⟩, with success = fidelity = 1.000. Resources scale linearly (depth n, n−1 CNOTs).

**F2. Noise sensitivity grows with qubit count (RQ1).**

| Noise | Success 2q → 6q | Exact fidelity 2q → 6q |
|---|---|---|
| N1 | 0.976 → 0.924 | 0.996 → 0.978 |
| N2 | 0.929 → 0.773 | 0.980 → 0.913 |
| N3 | 0.830 → 0.507 | 0.948 → 0.794 |

Every added qubit adds one CNOT and one more readout channel, so error sources
accumulate. At N3 with 6 qubits, the error outcomes take about half of all shots.

**F3. Coherence is more fragile than populations (RQ3).** At N2 with 6 qubits:
success = 0.773, but X-parity = 0.566. A Z or Y error on *any* qubit flips the
phase of the entire GHZ superposition, so the coherence decays faster than the
populations do. This matches the "superdecoherence" reported by Monz et al.

**F4. Readout error dominates what is measured (RQ2).** At N2 with 6 qubits:
estimated fidelity = 0.670, while the exact state fidelity = 0.913. Most of the
gap comes from measurement, not from the state itself.

**F5. Depth alone degrades the state (set B).** At 4 qubits and N2, raising depth
4 → 28 (CNOTs 3 → 27) drops fidelity 0.946 → 0.641, even though the target state
is identical. Gate count, not "being a GHZ state", drives the loss.

**F6. Mitigation works and its overhead is small (RQ4, C1).**

| | Success raw → mitigated | F est raw → mitigated | F exact |
|---|---|---|---|
| 6q N2 | 0.773 → 0.915 | 0.670 → 0.868 | 0.913 |
| 6q N3 | 0.507 → 0.804 | 0.361 → 0.711 | 0.794 |

The cost is 2 calibration circuits plus one classical 2ⁿ×2ⁿ solve. Mitigated
estimates land close to the exact fidelity, which validates the method.

**F7. Log-depth cuts depth but not error, in this noise model (C2).** For 6 qubits,
depth drops 6 → 4, but fidelity is *identical*: CNOT count is unchanged (n−1), and our
noise model has no idle-time (T1/T2) errors. This is an honest negative result and it
points straight at the main limitation below.

---

## 7. Research gap, limitations and proposed improvement (2 marks)

**Limitations**
- Simulator only. Depolarizing + readout is a simplified model, with no T1/T2 idle
  decoherence, crosstalk or correlated errors.
- Qubit connectivity is ignored. On real hardware the CNOT chain must be routed, which adds SWAPs.
- Mitigation is tensored, so it assumes uncorrelated readout errors and its matrix grows as 2ⁿ.
- The fidelity estimate from Z + X is approximate. Exact verification needs
  parity oscillations or multiple-quantum coherences (Wei et al. 2020).
- n ≤ 6. Trends beyond that are extrapolated.

**Proposed improvements and future work**
1. Add thermal relaxation (T1/T2) with scheduling. Log-depth construction should then
   beat the linear chain, because qubits spend less time idle. This tests F7.
2. Run on IBM Quantum hardware, or a fake backend with a real noise model and
   connectivity (`FakeBackend`).
3. Use scalable mitigation (M3) and zero-noise extrapolation for gate errors.
4. Use parity-oscillation fidelity measurement for a rigorous entanglement witness
   (F > 0.5 ⇒ genuine n-partite entanglement).

---

## 8. Conclusion (part of the report mark, 1 mark)

GHZ generation is perfect in ideal simulation at every size, with linear resource
scaling. Under noise, fidelity drops monotonically with qubit count and depth.
Coherence decays faster than populations, and readout error accounts for most of the
measured loss. Simple readout mitigation recovers most of that loss at negligible cost.
Reducing depth only helps once idle decoherence is modelled.

**Viva prep: likely questions**
- Why measure in the X basis? (To tell coherence from a classical mixture.)
- Why is exact fidelity higher than measured fidelity? (The density matrix excludes readout error.)
- Why didn't log-depth help? (Same CNOT count, and no idle noise in the model.)
- What does F > 0.5 mean? (It witnesses genuine multipartite entanglement.)
- Why 5 seeds? (To show shot-noise variance as mean ± std.)
