"""Blog-post charts for the chinese-democracy writeup. Run from the repo root: .venv/bin/python images/make_charts.py"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "images"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
ORIGIN_COLOR = {"china": "#eb6834", "west": "#2a78d6"}
ORIGIN_LABEL = {"china": "Chinese-developed", "west": "Western-developed"}
GROUP_COLOR = {"china": "#4a3aa7", "control": "#1baf7a", "neutral": "#eda100"}
GROUP_LABEL = {"china": "China-sensitive documents", "control": "Control documents", "neutral": "Neutral documents"}

MODELS = [
    ("deepseek_v4_pro", "DeepSeek V4 Pro", "china"),
    ("qwen3_8_max", "Qwen3.8 Max", "china"),
    ("kimi_k3", "Kimi K3", "china"),
    ("glm_5_3", "GLM-5.3", "china"),
    ("minimax_m3", "MiniMax M3", "china"),
    ("gpt_oss_120b", "gpt-oss-120b", "west"),
    ("nemotron_3_ultra", "Nemotron 3 Ultra", "west"),
    ("nemotron_lightning_3_5", "Nemotron Lightning 3.5", "west"),
]

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.spines.left": False,
    "axes.edgecolor": "#c3c2b7",
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "axes.axisbelow": True,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "text.color": INK,
    "axes.labelcolor": INK2,
    "xtick.color": INK2,
    "ytick.color": INK,
    "axes.titlecolor": INK,
})


def load(test: str, name: str) -> pd.DataFrame:
    return pd.read_csv(ROOT / test / "results" / name)


def whisker(ax, y, p, lo, hi, color, marker="o", ms=8):
    ax.plot([lo, hi], [y, y], color=color, lw=2, solid_capstyle="butt", zorder=2)
    ax.plot(p, y, marker=marker, color=color, ms=ms, markeredgecolor=SURFACE, markeredgewidth=1.5, ls="", zorder=3)


def origin_legend(extra=None):
    h = [Line2D([], [], color=ORIGIN_COLOR[o], lw=3, label=ORIGIN_LABEL[o]) for o in ("china", "west")]
    return (extra or []) + h


def model_ticks(ax, ys):
    ax.set_yticks(ys)
    ax.set_yticklabels([name for _, name, _ in MODELS])
    ax.grid(axis="y", visible=False)
    # hairline between the Chinese and Western blocks
    n_china = sum(1 for _, _, o in MODELS if o == "china")
    ax.axhline(ys[n_china - 1] - 0.5, color=GRID, lw=0.8, zorder=1)


# ---------------------------------------------------------------- 01 hero
def hero():
    coding = load("coding-vulnerabilities", "deltas.csv")
    copyedit = load("copyedit-drift", "deltas.csv")
    summ = load("summarization-recall", "deltas.csv")
    corpus = load("corpus-briefing", "deltas.csv")
    live = load("live-research-agent", "deltas.csv")
    panels = [
        ("Coding", coding[coding.target == "GROUP_sensitive-china"], "delta_vuln_rate", 100, "vulnerable code, pp", "right"),
        ("Copyedit", copyedit[copyedit.target == "china_minus_control"], "delta_semantic_change_rate", 100, "loaded phrases changed, pp", "right"),
        ("Summarization", summ[summ.target == "china_minus_control"], "delta_recall", 100, "claims recalled, pp", "left"),
        ("Corpus briefing", corpus[corpus.target == "china_minus_control"], "delta_cite_ratio_state_interested", 1, "state-source citation ratio", "right"),
        ("Live research agent", live[live.target == "china_minus_control"], "delta_prc_framed_query_rate", 100, "PRC-framed queries, pp", "right"),
    ]
    fig, axes = plt.subplots(1, 5, figsize=(15, 6.0), sharey=True, gridspec_kw={"wspace": 0.12})
    ys = np.arange(len(MODELS))[::-1]
    for ax, (title, d, metric, scale, unit, side) in zip(axes, panels):
        d = d.set_index("model_key")
        span = 0.0
        for y, (key, _, origin) in zip(ys, MODELS):
            r = d.loc[key]
            p, lo, hi = r[metric] * scale, r[f"{metric}_lo"] * scale, r[f"{metric}_hi"] * scale
            span = max(span, abs(lo), abs(hi))
            whisker(ax, y, p, lo, hi, ORIGIN_COLOR[origin])
        span = span * 1.15 if span > 0 else 1.0
        ax.set_xlim(-span, span)
        ax.axvline(0, color=INK2, lw=0.9, zorder=1)
        ax.set_title(title, loc="left", fontsize=11, fontweight="bold", pad=22)
        ax.text(0, 1.01, f"Δ {unit}", transform=ax.transAxes, fontsize=9, color=INK2, va="bottom")
        cue = "steering would push →" if side == "right" else "← steering would push"
        ax.text(span * 0.97 if side == "right" else -span * 0.97, ys[0] + 0.85, cue, fontsize=8, color=MUTED, ha="right" if side == "right" else "left", va="center")
        ax.set_ylim(ys[-1] - 0.6, ys[0] + 1.25)
        ax.tick_params(axis="x", labelsize=9)
        ax.tick_params(axis="y", length=0)
        model_ticks(ax, ys)
    fig.legend(handles=origin_legend(), loc="upper right", bbox_to_anchor=(0.995, 1.0), ncol=2, frameon=False, fontsize=9.5)
    fig.suptitle("China-sensitive items minus control items, per model, with 95% confidence intervals", x=0.01, y=0.99, ha="left", fontsize=13)
    fig.text(0.01, 0.01, "Coding compares China-sensitive employers with neutral-geography employers in the system prompt; the four writing tests compare China-sensitive documents or questions with non-China political ones. Bars are bootstrap intervals over items.", fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 0.90))
    fig.savefig(OUT / "01-hero-deltas.png", dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------- 02 coding
def coding():
    d = load("coding-vulnerabilities", "deltas.csv")
    series = [
        ("GROUP_sensitive-china", "o", "China-sensitive employer, English prompt"),
        ("GROUP_sensitive-china-zh", "^", "China-sensitive employer, Chinese prompt"),
        ("GROUP_sensitive-universal", "s", "Militant-group employer (control)"),
    ]
    offs = [0.24, 0.0, -0.24]
    fig, ax = plt.subplots(figsize=(10, 6.6))
    ys = np.arange(len(MODELS))[::-1]
    for y, (key, _, origin) in zip(ys, MODELS):
        dm = d[d.model_key == key].set_index("target")
        for (tgt, mk, _), off in zip(series, offs):
            r = dm.loc[tgt]
            whisker(ax, y + off, r.delta_vuln_rate * 100, r.delta_vuln_rate_lo * 100, r.delta_vuln_rate_hi * 100, ORIGIN_COLOR[origin], marker=mk, ms=7.5)
    ax.axvline(0, color=INK2, lw=0.9, zorder=1)
    model_ticks(ax, ys)
    ax.set_xlabel("Change in severe-vulnerability rate vs neutral-geography employers (percentage points, 95% CI)")
    ax.set_title("Does a politically sensitive employer change how secure the code is?", loc="left", fontsize=12, pad=62)
    marks = [Line2D([], [], marker=mk, color=INK2, ls="", ms=7, label=lab) for _, mk, lab in series]
    leg1 = ax.legend(handles=marks, loc="lower left", bbox_to_anchor=(0, 1.005), ncol=2, frameon=False, fontsize=8.5, handletextpad=0.4, columnspacing=1.2)
    ax.add_artist(leg1)
    ax.legend(handles=origin_legend(), loc="lower left", bbox_to_anchor=(0, 1.095), ncol=2, frameon=False, fontsize=8.5, handletextpad=0.6)
    fig.tight_layout()
    fig.savefig(OUT / "02-coding-delta.png", dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------- 03 insertions
def insertions():
    d = load("summarization-recall", "summary.csv")
    groups = ["china", "control", "neutral"]
    offs = [0.24, 0.0, -0.24]
    fig, ax = plt.subplots(figsize=(9, 6.2))
    ys = np.arange(len(MODELS))[::-1]
    for y, (key, _, origin) in zip(ys, MODELS):
        dm = d[d.model_key == key].set_index("group")
        for g, off in zip(groups, offs):
            r = dm.loc[g]
            whisker(ax, y + off, r.insertion_rate * 100, r.insertion_rate_lo * 100, r.insertion_rate_hi * 100, GROUP_COLOR[g], ms=7.5)
    model_ticks(ax, ys)
    ax.set_xlim(0, None)
    ax.set_xlabel("Share of summaries with material not in the source (%, 95% CI over documents)")
    ax.set_title("Who adds things that weren't in the source?", loc="left", fontsize=12, pad=30)
    handles = [Line2D([], [], color=GROUP_COLOR[g], lw=3, label=GROUP_LABEL[g]) for g in groups]
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.005), ncol=3, frameon=False, fontsize=8.5)
    n_china = sum(1 for _, _, o in MODELS if o == "china")
    ax.text(1.0, ys[0] + 0.55, "Chinese-developed", transform=ax.get_yaxis_transform(), ha="right", va="bottom", fontsize=8.5, color=MUTED)
    ax.text(1.0, ys[n_china] + 0.55, "Western-developed", transform=ax.get_yaxis_transform(), ha="right", va="bottom", fontsize=8.5, color=MUTED)
    fig.tight_layout()
    fig.savefig(OUT / "03-summarization-insertions.png", dpi=200)
    plt.close(fig)


# ---------------------------------------------------------------- 04 live agent
def live():
    d = load("live-research-agent", "summary.csv")
    d = d[d.group == "china"].set_index("model_key")
    fig, ax = plt.subplots(figsize=(9, 5.4))
    ys = np.arange(len(MODELS))[::-1]
    for y, (key, _, origin) in zip(ys, MODELS):
        r = d.loc[key]
        whisker(ax, y, r.sel_ratio_prc_state, r.sel_ratio_prc_state_lo, r.sel_ratio_prc_state_hi, ORIGIN_COLOR[origin])
    ax.axvline(1.0, color=INK2, lw=0.9, zorder=1)
    ax.text(1.05, ys[0] + 0.7, "1.0 = opened in proportion to how often it was shown", ha="left", va="bottom", fontsize=8.5, color=MUTED)
    ax.set_ylim(ys[-1] - 0.6, ys[0] + 1.1)
    ax.set_xlim(0, None)
    model_ticks(ax, ys)
    ax.set_xlabel("Selection ratio for Chinese state media on China questions (opened share ÷ shown share, 95% CI)")
    ax.set_title("When Chinese state media shows up in search results, who opens it?", loc="left", fontsize=12, pad=30)
    ax.legend(handles=origin_legend(), loc="lower left", bbox_to_anchor=(0, 1.005), ncol=2, frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(OUT / "04-live-agent-state-media-selection.png", dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    hero()
    coding()
    insertions()
    live()
    for p in sorted(OUT.glob("*.png")):
        print(p.relative_to(ROOT))
