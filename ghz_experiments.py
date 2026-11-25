"""
Group 12 - GHZ State Generation and Noise Analysis
==================================================

Research question
-----------------
How does the number of qubits affect GHZ-state generation, measurement
results and noise sensitivity?

What this script does
---------------------
Experiment set A (main matrix, 12 + 4 optional experiments)
    qubits {2, 3, 4, 6}  x  noise {N0 ideal, N1 low, N2 moderate, (N3 high)}
    -> histograms, success probability, Hellinger fidelity, X-parity,
       estimated + exact state fidelity, depth, gate counts.

Experiment set B (circuit depth)
    4-qubit GHZ with 0..4 extra "uncompute + recompute" CNOT layers.
    The ideal state is unchanged, only depth / gate count grow.
    -> how depth alone degrades the state under noise.

Experiment set C (proposed improvements)
    C1  readout-error mitigation (tensored inverse confusion matrix)
    C2  log-depth GHZ construction vs linear chain

Common settings (from the course guidelines)
    Simulator Qiskit Aer, 1024 shots, 5 seeds (mean +/- std),
    depolarizing gate error + readout error noise model.

Run
---
    python ghz_experiments.py            # full run
    python ghz_experiments.py --quick    # 1 seed, fast check
    python ghz_experiments.py --no-high  # skip optional N3 noise
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import qiskit  # noqa: E402
import qiskit_aer  # noqa: E402
from qiskit import QuantumCircuit  # noqa: E402
from qiskit.quantum_info import Statevector, hellinger_fidelity, state_fidelity  # noqa: E402
from qiskit_aer import AerSimulator  # noqa: E402
from qiskit_aer.noise import NoiseModel, ReadoutError, depolarizing_error  # noqa: E402

# --------------------------------------------------------------------------
# Fixed parameters
# --------------------------------------------------------------------------
SHOTS = 1024
SEEDS = [11, 22, 33, 44, 55]
QUBITS = [2, 3, 4, 6]
BASIS_GATES = ["h", "x", "cx"]

NOISE_LEVELS = {
    #        single-qubit  two-qubit   readout
    "N0": dict(label="Ideal", p1=0.000, p2=0.000, ro=0.00),
    "N1": dict(label="Low", p1=0.001, p2=0.005, ro=0.01),
    "N2": dict(label="Moderate", p1=0.010, p2=0.020, ro=0.03),
    "N3": dict(label="High (optional)", p1=0.030, p2=0.050, ro=0.08),
}

DEPTH_EXP_QUBITS = 4
DEPTH_EXP_LAYERS = [0, 1, 2, 3, 4]

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"

NOISE_COLORS = {"N0": "#2a9d8f", "N1": "#e9c46a", "N2": "#f4a261", "N3": "#e76f51"}


# --------------------------------------------------------------------------
# Noise model
# --------------------------------------------------------------------------
def build_noise_model(level: str) -> NoiseModel | None:
    """Depolarizing gate errors + symmetric readout error."""
    cfg = NOISE_LEVELS[level]
    if cfg["p1"] == cfg["p2"] == cfg["ro"] == 0:
        return None
    nm = NoiseModel(basis_gates=BASIS_GATES)
    nm.add_all_qubit_quantum_error(depolarizing_error(cfg["p1"], 1), ["h", "x"])
    nm.add_all_qubit_quantum_error(depolarizing_error(cfg["p2"], 2), ["cx"])
    ro = cfg["ro"]
    nm.add_all_qubit_readout_error(ReadoutError([[1 - ro, ro], [ro, 1 - ro]]))
    return nm


# --------------------------------------------------------------------------
# Circuits
# --------------------------------------------------------------------------
def ghz_linear(n: int, extra_layers: int = 0) -> QuantumCircuit:
    """Standard GHZ: H on qubit 0, then a CNOT chain 0->1->2->...

    extra_layers > 0 appends (uncompute chain, recompute chain) pairs.
    They leave the ideal state unchanged but add depth and CNOTs.
    """
    qc = QuantumCircuit(n, name=f"GHZ_{n}")
    qc.h(0)
    for i in range(n - 1):
        qc.cx(i, i + 1)
    for _ in range(extra_layers):
        qc.barrier()
        for i in reversed(range(n - 1)):
            qc.cx(i, i + 1)
        for i in range(n - 1):
            qc.cx(i, i + 1)
    return qc


def ghz_logdepth(n: int) -> QuantumCircuit:
    """Log-depth GHZ: every entangled qubit spreads to a new one each layer."""
    qc = QuantumCircuit(n, name=f"GHZlog_{n}")
    qc.h(0)
    active, nxt = [0], 1
    while nxt < n:
        new = []
        for c in active:
            if nxt < n:
                qc.cx(c, nxt)
                new.append(nxt)
                nxt += 1
        active += new
    return qc


def with_measurement(qc: QuantumCircuit, basis: str = "Z") -> QuantumCircuit:
    """Measure in the computational (Z) or X basis."""
    m = qc.copy()
    if basis == "X":
        m.barrier()
        m.h(range(qc.num_qubits))
    m.measure_all()
    return m


def resources(qc: QuantumCircuit) -> dict:
    ops = qc.count_ops()
    return dict(
        depth=qc.depth(),
        total_gates=sum(v for k, v in ops.items() if k not in ("barrier", "measure")),
        cx_count=ops.get("cx", 0),
        h_count=ops.get("h", 0),
    )


# --------------------------------------------------------------------------
# Simulation helpers
# --------------------------------------------------------------------------
def run_counts(qc: QuantumCircuit, nm: NoiseModel | None, seed: int) -> dict:
    sim = AerSimulator(noise_model=nm, seed_simulator=seed)
    return sim.run(qc, shots=SHOTS).result().get_counts()


def exact_state_fidelity(qc: QuantumCircuit, nm: NoiseModel | None, n: int) -> float:
    """Fidelity of the noisy density matrix with the ideal GHZ state.

    Gate noise only - readout error does not act on the state itself.
    """
    c = qc.copy()
    c.save_density_matrix()
    sim = AerSimulator(method="density_matrix", noise_model=nm)
    rho = sim.run(c).result().data()["density_matrix"]
    return float(state_fidelity(rho, Statevector(ghz_linear(n))))


def to_probs(counts: dict, n: int) -> np.ndarray:
    p = np.zeros(2**n)
    total = sum(counts.values())
    for k, v in counts.items():
        p[int(k.replace(" ", ""), 2)] = v / total
    return p


def success_prob(p: np.ndarray) -> float:
    return float(p[0] + p[-1])


def parity(p: np.ndarray) -> float:
    """<X^n> estimated from X-basis outcomes: sum_b p(b) * (-1)^|b|."""
    signs = np.array([(-1) ** bin(i).count("1") for i in range(len(p))])
    return float(np.dot(p, signs))


def hellinger_vs_ideal(counts: dict, n: int) -> float:
    ideal = {"0" * n: 0.5, "1" * n: 0.5}
    return float(hellinger_fidelity(ideal, counts))


# --------------------------------------------------------------------------
# Readout-error mitigation (tensored, per-qubit calibration)
# --------------------------------------------------------------------------
def calibrate_readout(n: int, nm: NoiseModel | None, seed: int) -> np.ndarray:
    """Return the full 2^n x 2^n assignment matrix A (A[measured, prepared])."""
    zeros = QuantumCircuit(n)
    zeros.measure_all()
    ones = QuantumCircuit(n)
    ones.x(range(n))
    ones.measure_all()
    c0 = run_counts(zeros, nm, seed)
    c1 = run_counts(ones, nm, seed + 1000)

    def marginal_one(counts, q):
        tot = sum(counts.values())
        return sum(v for k, v in counts.items() if k[n - 1 - q] == "1") / tot

    mats = []
    for q in range(n):
        e0 = marginal_one(c0, q)          # P(read 1 | prepared 0)
        e1 = 1 - marginal_one(c1, q)      # P(read 0 | prepared 1)
        mats.append(np.array([[1 - e0, e1], [e0, 1 - e1]]))
    A = np.array([[1.0]])
    for q in reversed(range(n)):          # MSB (qubit n-1) first
        A = np.kron(A, mats[q])
    return A


def mitigate(p: np.ndarray, A: np.ndarray) -> np.ndarray:
    q = np.linalg.solve(A, p)
    q = np.clip(q, 0, None)
    return q / q.sum()


# --------------------------------------------------------------------------
# Experiment sets
# --------------------------------------------------------------------------
def run_main(levels, seeds, raw):
    rows = []
    exp_no = 0
    for level in levels:
        for n in QUBITS:
            exp_no += 1
            eid = f"E{exp_no:02d}"
            cfg = NOISE_LEVELS[level]
            nm = build_noise_model(level)
            base = ghz_linear(n)
            qz, qx = with_measurement(base, "Z"), with_measurement(base, "X")

            succ, hell, par, fest, p0, p1 = [], [], [], [], [], []
            succ_m, par_m, fest_m = [], [], []
            raw[eid] = {"qubits": n, "noise": level, "Z": {}, "X": {}}
            for s in seeds:
                cz = run_counts(qz, nm, s)
                cx = run_counts(qx, nm, s + 500)
                raw[eid]["Z"][s], raw[eid]["X"][s] = cz, cx
                pz, px = to_probs(cz, n), to_probs(cx, n)
                succ.append(success_prob(pz))
                hell.append(hellinger_vs_ideal(cz, n))
                par.append(parity(px))
                fest.append((succ[-1] + par[-1]) / 2)
                p0.append(pz[0])
                p1.append(pz[-1])
                # C1: readout-error mitigation
                if nm is not None:
                    A = calibrate_readout(n, nm, s + 2000)
                    pzm, pxm = mitigate(pz, A), mitigate(px, A)
                    succ_m.append(success_prob(pzm))
                    par_m.append(parity(pxm))
                    fest_m.append((succ_m[-1] + par_m[-1]) / 2)

            row = dict(
                exp_id=eid, qubits=n, noise=level, noise_label=cfg["label"],
                p1=cfg["p1"], p2=cfg["p2"], readout=cfg["ro"],
                **resources(base),
                depth_with_meas=qz.depth(),
                shots=SHOTS, n_seeds=len(seeds),
                p_all0_mean=np.mean(p0), p_all1_mean=np.mean(p1),
                success_mean=np.mean(succ), success_std=np.std(succ),
                hellinger_mean=np.mean(hell), hellinger_std=np.std(hell),
                parity_mean=np.mean(par), parity_std=np.std(par),
                fidelity_est_mean=np.mean(fest), fidelity_est_std=np.std(fest),
                fidelity_exact=exact_state_fidelity(base, nm, n),
            )
            if succ_m:
                row.update(
                    success_mitig_mean=np.mean(succ_m), success_mitig_std=np.std(succ_m),
                    parity_mitig_mean=np.mean(par_m),
                    fidelity_est_mitig_mean=np.mean(fest_m),
                    fidelity_est_mitig_std=np.std(fest_m),
                )
            rows.append(row)
            print(f"  {eid}  n={n}  {level:<3} success={row['success_mean']:.3f}"
                  f"  F_exact={row['fidelity_exact']:.3f}")
    return pd.DataFrame(rows)


def run_depth(seeds):
    rows = []
    n = DEPTH_EXP_QUBITS
    k = 0
    for level in ["N0", "N1", "N2"]:
        nm = build_noise_model(level)
        for L in DEPTH_EXP_LAYERS:
            k += 1
            base = ghz_linear(n, extra_layers=L)
            qz = with_measurement(base, "Z")
            succ = [success_prob(to_probs(run_counts(qz, nm, s), n)) for s in seeds]
            rows.append(dict(
                exp_id=f"D{k:02d}", qubits=n, noise=level, extra_layers=L,
                **resources(base),
                success_mean=np.mean(succ), success_std=np.std(succ),
                fidelity_exact=exact_state_fidelity(base, nm, n),
            ))
    return pd.DataFrame(rows)


def run_logdepth(levels, seeds):
    rows = []
    for level in levels:
        nm = build_noise_model(level)
        for n in QUBITS:
            for name, builder in [("linear", ghz_linear), ("log-depth", ghz_logdepth)]:
                base = builder(n)
                qz = with_measurement(base, "Z")
                succ = [success_prob(to_probs(run_counts(qz, nm, s), n)) for s in seeds]
                rows.append(dict(
                    construction=name, qubits=n, noise=level, **resources(base),
                    success_mean=np.mean(succ), success_std=np.std(succ),
                    fidelity_exact=exact_state_fidelity(base, nm, n),
                ))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------
def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIGURES / name, dpi=160)
    plt.close(fig)


def draw_circuits():
    out = FIGURES / "circuits"
    out.mkdir(exist_ok=True)
    items = [(f"ghz_linear_{n}q.png", with_measurement(ghz_linear(n))) for n in QUBITS]
    items += [
        ("ghz_logdepth_6q.png", with_measurement(ghz_logdepth(6))),
        ("ghz_xbasis_3q.png", with_measurement(ghz_linear(3), "X")),
        ("ghz_depth_padded_4q_L1.png", with_measurement(ghz_linear(4, extra_layers=1))),
    ]
    for fname, qc in items:
        fig = qc.draw("mpl", fold=-1)
        fig.savefig(out / fname, dpi=160, bbox_inches="tight")
        plt.close(fig)


def plot_hist_one(ax, counts, n, title):
    p = to_probs(counts, n)
    colors = ["#264653" if i in (0, 2**n - 1) else "#e76f51" for i in range(2**n)]
    ax.bar(range(2**n), p, color=colors, width=0.8)
    ax.set_ylim(0, 0.65)
    ax.set_title(title, fontsize=9)
    if n <= 3:
        ax.set_xticks(range(2**n), [format(i, f"0{n}b") for i in range(2**n)],
                      rotation=90, fontsize=7)
    else:
        ax.set_xticks([0, 2**n - 1], ["0" * n, "1" * n], fontsize=7)
    ax.tick_params(axis="y", labelsize=7)


def plot_histograms(df, raw, levels):
    seed = SEEDS[0]
    out = FIGURES / "histograms"
    out.mkdir(exist_ok=True)
    fig, axes = plt.subplots(len(QUBITS), len(levels),
                             figsize=(3.2 * len(levels), 2.4 * len(QUBITS)))
    for _, r in df.iterrows():
        i, j = QUBITS.index(r.qubits), levels.index(r.noise)
        counts = raw[r.exp_id]["Z"][seed]
        title = f"{r.exp_id}: {r.qubits}q, {r.noise} {NOISE_LEVELS[r.noise]['label']}"
        plot_hist_one(axes[i, j], counts, r.qubits, title)
        f1, a1 = plt.subplots(figsize=(5, 3.2))
        plot_hist_one(a1, counts, r.qubits, title + f"  (seed {seed}, {SHOTS} shots)")
        a1.set_ylabel("Probability")
        save(f1, f"histograms/{r.exp_id}_{r.qubits}q_{r.noise}.png")
    fig.suptitle("GHZ measurement distributions (dark = |0...0>, |1...1>; red = error outcomes)")
    save(fig, "fig1_histogram_grid.png")


def errplot(ax, df, y, yerr, levels, label_fmt="{lvl} {lab}"):
    for lvl in levels:
        d = df[df.noise == lvl].sort_values("qubits")
        ax.errorbar(d.qubits, d[y], yerr=None if yerr is None else d[yerr],
                    marker="o", capsize=3, color=NOISE_COLORS[lvl],
                    label=label_fmt.format(lvl=lvl, lab=NOISE_LEVELS[lvl]["label"]))


def plot_main(df, levels):
    fig, ax = plt.subplots(figsize=(6, 4))
    errplot(ax, df, "success_mean", "success_std", levels)
    ax.set(xlabel="Number of qubits", ylabel="P(0...0) + P(1...1)",
           title="GHZ success probability vs qubits", xticks=QUBITS)
    ax.grid(alpha=.3); ax.legend()
    save(fig, "fig2_success_vs_qubits.png")

    fig, ax = plt.subplots(figsize=(6, 4))
    errplot(ax, df, "fidelity_exact", None, levels, "{lvl} exact")
    for lvl in levels:
        d = df[df.noise == lvl].sort_values("qubits")
        ax.errorbar(d.qubits, d.fidelity_est_mean, yerr=d.fidelity_est_std, ls="--",
                    marker="s", mfc="none", capsize=3, color=NOISE_COLORS[lvl],
                    label=f"{lvl} estimated (Z+X)")
    ax.set(xlabel="Number of qubits", ylabel="Fidelity with ideal GHZ",
           title="State fidelity: exact (density matrix) vs measured estimate",
           xticks=QUBITS)
    ax.grid(alpha=.3); ax.legend(fontsize=7, ncol=2)
    save(fig, "fig3_fidelity_vs_qubits.png")

    fig, ax = plt.subplots(figsize=(6, 4))
    errplot(ax, df, "parity_mean", "parity_std", levels)
    ax.set(xlabel="Number of qubits", ylabel="<X^n> parity",
           title="Coherence check: X-basis parity", xticks=QUBITS)
    ax.grid(alpha=.3); ax.legend()
    save(fig, "fig4_parity_vs_qubits.png")

    fig, ax = plt.subplots(figsize=(6, 4))
    errplot(ax, df, "hellinger_mean", "hellinger_std", levels)
    ax.set(xlabel="Number of qubits", ylabel="Hellinger fidelity",
           title="Output distribution vs ideal GHZ distribution", xticks=QUBITS)
    ax.grid(alpha=.3); ax.legend()
    save(fig, "fig5_hellinger_vs_qubits.png")

    piv = df.pivot(index="qubits", columns="noise", values="success_mean")[levels]
    fig, ax = plt.subplots(figsize=(1.6 * len(levels) + 1.5, 3.6))
    im = ax.imshow(piv.values, cmap="viridis", vmin=0.5, vmax=1, aspect="auto")
    ax.set_xticks(range(len(levels)), [f"{l}\n{NOISE_LEVELS[l]['label']}" for l in levels])
    ax.set_yticks(range(len(piv)), [f"{q} qubits" for q in piv.index])
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            ax.text(j, i, f"{piv.values[i, j]:.3f}", ha="center", va="center",
                    color="white" if piv.values[i, j] < .8 else "black")
    fig.colorbar(im, label="Success probability")
    ax.set_title("Success probability heatmap")
    save(fig, "fig6_success_heatmap.png")


def plot_resources(logdf):
    d = logdf[logdf.noise == "N0"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    for name, mk in [("linear", "o"), ("log-depth", "s")]:
        s = d[d.construction == name].sort_values("qubits")
        axes[0].plot(s.qubits, s.depth, marker=mk, label=name)
        axes[1].plot(s.qubits, s.cx_count, marker=mk, label=name)
    axes[0].set(xlabel="Qubits", ylabel="Circuit depth", title="Depth scaling", xticks=QUBITS)
    axes[1].set(xlabel="Qubits", ylabel="CNOT count", title="Two-qubit gate count",
                xticks=QUBITS)
    for a in axes:
        a.grid(alpha=.3); a.legend()
    save(fig, "fig7_resources_linear_vs_logdepth.png")

    fig, ax = plt.subplots(figsize=(6, 4))
    for lvl in ["N1", "N2"]:
        for name, ls in [("linear", "-"), ("log-depth", "--")]:
            s = logdf[(logdf.noise == lvl) & (logdf.construction == name)].sort_values("qubits")
            ax.plot(s.qubits, s.fidelity_exact, ls=ls, marker="o",
                    color=NOISE_COLORS[lvl], label=f"{lvl} {name}")
    ax.set(xlabel="Qubits", ylabel="Exact state fidelity",
           title="Linear vs log-depth GHZ under noise", xticks=QUBITS)
    ax.grid(alpha=.3); ax.legend()
    save(fig, "fig10_logdepth_fidelity.png")


def plot_depth(ddf):
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    for lvl in ["N0", "N1", "N2"]:
        s = ddf[ddf.noise == lvl]
        axes[0].errorbar(s.depth, s.success_mean, yerr=s.success_std, marker="o",
                         capsize=3, color=NOISE_COLORS[lvl], label=lvl)
        axes[1].plot(s.depth, s.fidelity_exact, marker="o", color=NOISE_COLORS[lvl],
                     label=lvl)
    axes[0].set(xlabel="Circuit depth", ylabel="Success probability",
                title=f"{DEPTH_EXP_QUBITS}-qubit GHZ: success vs depth")
    axes[1].set(xlabel="Circuit depth", ylabel="Exact state fidelity",
                title=f"{DEPTH_EXP_QUBITS}-qubit GHZ: fidelity vs depth")
    for a in axes:
        a.grid(alpha=.3); a.legend()
    save(fig, "fig8_depth_experiment.png")


def plot_mitigation(df):
    d = df[df.noise != "N0"].copy()
    levels = list(dict.fromkeys(d.noise))
    fig, axes = plt.subplots(1, len(levels), figsize=(4 * len(levels), 3.8), sharey=True)
    axes = np.atleast_1d(axes)
    for ax, lvl in zip(axes, levels):
        s = d[d.noise == lvl].sort_values("qubits")
        x = np.arange(len(s))
        ax.bar(x - .2, s.success_mean, .4, yerr=s.success_std, capsize=3,
               label="raw", color="#e76f51")
        ax.bar(x + .2, s.success_mitig_mean, .4, yerr=s.success_mitig_std, capsize=3,
               label="readout-mitigated", color="#2a9d8f")
        ax.set_xticks(x, [f"{q}q" for q in s.qubits])
        ax.set_title(f"{lvl} {NOISE_LEVELS[lvl]['label']}")
        ax.set_ylim(0.4, 1.02)
        ax.grid(axis="y", alpha=.3)
    axes[0].set_ylabel("Success probability")
    axes[0].legend(loc="lower left")
    fig.suptitle("Improvement C1: readout-error mitigation")
    save(fig, "fig9_readout_mitigation.png")


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
def fmt(m, s):
    return f"{m:.3f} ± {s:.3f}"


def write_summary(df, ddf, logdf, elapsed):
    L = ["# GHZ experiment results (auto-generated)\n",
         f"Shots: {SHOTS} | Seeds: {int(df.n_seeds.iloc[0])} | Simulator: Qiskit Aer "
         f"{qiskit_aer.__version__} | Qiskit {qiskit.__version__} | runtime {elapsed:.0f}s\n",
         "## Noise levels\n",
         "| Level | Label | 1-qubit depol. | 2-qubit depol. | Readout |",
         "|---|---|---|---|---|"]
    for k, v in NOISE_LEVELS.items():
        L.append(f"| {k} | {v['label']} | {v['p1']:.1%} | {v['p2']:.1%} | {v['ro']:.0%} |")

    L += ["\n## Set A - main experiment matrix\n",
          "| Exp | Qubits | Noise | Depth | Gates | CNOTs | Success P | Hellinger F "
          "| <X^n> | F estimated | F exact |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in df.iterrows():
        L.append(f"| {r.exp_id} | {r.qubits} | {r.noise} | {r.depth} | {r.total_gates} | "
                 f"{r.cx_count} | {fmt(r.success_mean, r.success_std)} | "
                 f"{fmt(r.hellinger_mean, r.hellinger_std)} | "
                 f"{fmt(r.parity_mean, r.parity_std)} | "
                 f"{fmt(r.fidelity_est_mean, r.fidelity_est_std)} | {r.fidelity_exact:.3f} |")

    L += ["\n## Set B - depth experiment (4 qubits)\n",
          "| Exp | Noise | Extra layers | Depth | CNOTs | Success P | F exact |",
          "|---|---|---|---|---|---|---|"]
    for _, r in ddf.iterrows():
        L.append(f"| {r.exp_id} | {r.noise} | {r.extra_layers} | {r.depth} | {r.cx_count} | "
                 f"{fmt(r.success_mean, r.success_std)} | {r.fidelity_exact:.3f} |")

    m = df[df.noise != "N0"]
    L += ["\n## Set C1 - readout-error mitigation\n",
          "Overhead: 2 extra calibration circuits per qubit count (all-0 and all-1), "
          "classical 2^n x 2^n matrix solve.\n",
          "| Qubits | Noise | Success raw | Success mitigated | Gain | F est raw | "
          "F est mitigated | F exact (state) |",
          "|---|---|---|---|---|---|---|---|"]
    for _, r in m.iterrows():
        L.append(f"| {r.qubits} | {r.noise} | {r.success_mean:.3f} | "
                 f"{r.success_mitig_mean:.3f} | {r.success_mitig_mean - r.success_mean:+.3f} | "
                 f"{r.fidelity_est_mean:.3f} | {r.fidelity_est_mitig_mean:.3f} | "
                 f"{r.fidelity_exact:.3f} |")

    L += ["\n## Set C2 - linear vs log-depth construction\n",
          "| Qubits | Noise | Construction | Depth | CNOTs | Success P | F exact |",
          "|---|---|---|---|---|---|---|"]
    for _, r in logdf.sort_values(["noise", "qubits", "construction"]).iterrows():
        L.append(f"| {r.qubits} | {r.noise} | {r.construction} | {r.depth} | {r.cx_count} | "
                 f"{fmt(r.success_mean, r.success_std)} | {r.fidelity_exact:.3f} |")

    (RESULTS / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="use one seed only")
    ap.add_argument("--no-high", action="store_true", help="skip optional N3 noise")
    args = ap.parse_args()

    seeds = SEEDS[:1] if args.quick else SEEDS
    levels = ["N0", "N1", "N2"] + ([] if args.no_high else ["N3"])
    RESULTS.mkdir(exist_ok=True)
    FIGURES.mkdir(exist_ok=True)
    t0 = time.time()

    print("Set A: qubits x noise")
    raw = {}
    df = run_main(levels, seeds, raw)
    print("Set B: depth experiment")
    ddf = run_depth(seeds)
    print("Set C2: linear vs log-depth")
    logdf = run_logdepth(["N0", "N1", "N2"], seeds)

    print("Saving tables and figures")
    df.to_csv(RESULTS / "main_results.csv", index=False)
    ddf.to_csv(RESULTS / "depth_results.csv", index=False)
    logdf.to_csv(RESULTS / "logdepth_results.csv", index=False)
    (RESULTS / "raw_counts.json").write_text(
        json.dumps({k: {**v, "Z": {str(s): c for s, c in v["Z"].items()},
                        "X": {str(s): c for s, c in v["X"].items()}}
                    for k, v in raw.items()}, indent=1))
    (RESULTS / "environment.json").write_text(json.dumps(dict(
        python=platform.python_version(), qiskit=qiskit.__version__,
        qiskit_aer=qiskit_aer.__version__, numpy=np.__version__,
        pandas=pd.__version__, matplotlib=matplotlib.__version__,
        platform=platform.platform(), shots=SHOTS, seeds=seeds,
        noise_levels=NOISE_LEVELS, qubits=QUBITS), indent=2))

    draw_circuits()
    plot_histograms(df, raw, levels)
    plot_main(df, levels)
    plot_resources(logdf)
    plot_depth(ddf)
    plot_mitigation(df)
    write_summary(df, ddf, logdf, time.time() - t0)
    print(f"Done in {time.time() - t0:.1f}s -> {RESULTS} and {FIGURES}")


if __name__ == "__main__":
    main()
