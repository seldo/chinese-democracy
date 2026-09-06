"""Figures for RESULTS.md. Palette: fixed categorical slots (validated defaults), one axis per chart, thin marks."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .common import RESULTS, Model, load_conditions

GROUP_COLOR = {"baseline": "#1baf7a", "neutral-geo": "#2a78d6", "sensitive-china": "#eb6834", "sensitive-china-zh": "#eda100", "sensitive-universal": "#4a3aa7"}
ORIGIN_COLOR = {"china": "#eb6834", "west": "#2a78d6"}
CONDS = [c.id for c in load_conditions()]
CGROUP = {c.id: c.group for c in load_conditions()}
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#e6e6e3", "grid.linewidth": 0.6, "axes.axisbelow": True, "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "text.color": "#0b0b0b", "axes.labelcolor": "#52514e", "xtick.color": "#52514e", "ytick.color": "#52514e"})


def vuln_by_condition(summary: pd.DataFrame, models: list[Model]) -> None:
    n = len(models)
    cols = 4 if n > 4 else n
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4.2 * cols, 3.2 * rows), sharey=True, squeeze=False)
    for ax, m in zip(axes.flat, models):
        s = summary[(summary.model_key == m.key) & (summary.condition_id.isin(CONDS))].set_index("condition_id").reindex(CONDS)
        x = np.arange(len(CONDS))
        y = s.vuln_rate.to_numpy() * 100
        err = np.vstack([y - s.vuln_rate_lo.to_numpy() * 100, s.vuln_rate_hi.to_numpy() * 100 - y])
        err = np.nan_to_num(err)
        ax.bar(x, y, width=0.7, color=[GROUP_COLOR[CGROUP[c]] for c in CONDS], yerr=err, error_kw={"elinewidth": 0.8, "ecolor": "#52514e", "capsize": 0})
        pooled = summary[(summary.model_key == m.key) & (summary.condition_id == "POOLED_neutral_geo")]
        if not pooled.empty:
            ax.axhline(pooled.vuln_rate.iloc[0] * 100, color="#2a78d6", lw=1, ls="--", alpha=0.7)
        ax.set_title(f"{m.key} ({m.origin})", fontsize=9.5, loc="left")
        ax.set_xticks(x)
        ax.set_xticklabels(CONDS, rotation=60, ha="right", fontsize=7)
        ax.set_ylim(0, 100)
    for ax in axes.flat[n:]:
        ax.axis("off")
    for ax in axes[:, 0]:
        ax.set_ylabel("% code samples with ≥1 severe vuln")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in GROUP_COLOR.values()]
    fig.legend(handles, list(GROUP_COLOR), loc="upper right", ncol=4, frameon=False, fontsize=8)
    fig.suptitle("Severe-vulnerability rate by system-prompt condition (95% bootstrap CI over tasks; dashed = pooled neutral-geo)", x=0.01, ha="left", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(RESULTS / "figures" / "vuln_rate_by_condition.png", dpi=160)
    plt.close(fig)


def sensitive_delta(deltas: pd.DataFrame, models: list[Model]) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 0.55 * len(models) + 1.8))
    ys = np.arange(len(models))[::-1]
    for y, m in zip(ys, models):
        d = deltas[(deltas.model_key == m.key)].set_index("target")
        for off, tgt, mk, alpha in [(0.27, "GROUP_sensitive-china", "o", 1.0), (0.09, "GROUP_sensitive-china-zh", "^", 1.0), (-0.09, "GROUP_sensitive-universal", "s", 0.8), (-0.27, "cn_chengdu_vs_other_neutral", "D", 0.7)]:
            if tgt not in d.index:
                continue
            r = d.loc[tgt]
            p, lo, hi = r.delta_vuln_rate * 100, r.delta_vuln_rate_lo * 100, r.delta_vuln_rate_hi * 100
            c = ORIGIN_COLOR[m.origin]
            ax.plot([lo, hi], [y + off, y + off], color=c, lw=2, alpha=alpha, solid_capstyle="butt")
            ax.plot(p, y + off, marker=mk, color=c, ms=7, alpha=alpha, markeredgecolor="#fcfcfb", markeredgewidth=1)
    ax.axvline(0, color="#52514e", lw=0.8)
    ax.set_yticks(ys)
    ax.set_yticklabels([f"{m.key} ({m.origin})" for m in models])
    ax.set_xlabel("Δ vulnerability rate vs pooled neutral-geo (percentage points, 95% CI)")
    from matplotlib.lines import Line2D

    leg = [Line2D([], [], marker="o", color="#52514e", ls="", label="sensitive-China, English prompt"), Line2D([], [], marker="^", color="#52514e", ls="", label="sensitive-China, Chinese prompt"), Line2D([], [], marker="s", color="#52514e", ls="", label="militant (sensitive-universal)"), Line2D([], [], marker="D", color="#52514e", ls="", label="cn_chengdu vs other neutral"), Line2D([], [], color=ORIGIN_COLOR["china"], lw=3, label="Chinese-developed"), Line2D([], [], color=ORIGIN_COLOR["west"], lw=3, label="Western-developed")]
    ax.legend(handles=leg, frameon=False, fontsize=8, loc="lower right")
    ax.set_title("Does sensitive context change the vulnerability rate?", loc="left", fontsize=10)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(RESULTS / "figures" / "sensitive_china_delta.png", dpi=160)
    plt.close(fig)


def refusal_rates(summary: pd.DataFrame, models: list[Model]) -> None:
    groups = ["baseline", "neutral-geo", "sensitive-china", "sensitive-china-zh", "sensitive-universal"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 0.5 * len(models) + 2), sharey=True)
    ys = np.arange(len(models))[::-1]
    h = 0.15
    for ax, metric, title in [(axes[0], "refusal_rate", "Refusal rate"), (axes[1], "plan_then_refuse_rate", "Plan-then-refuse rate")]:
        for gi, g in enumerate(groups):
            vals = []
            for m in models:
                s = summary[(summary.model_key == m.key) & (summary.group == g) & (summary.condition_id.isin(CONDS))]
                vals.append(s[metric].mean() * 100 if not s.empty else 0)
            ax.barh(ys + (2 - gi) * h, vals, height=h * 0.92, color=GROUP_COLOR[g], label=g)
        ax.set_yticks(ys)
        ax.set_yticklabels([f"{m.key} ({m.origin})" for m in models])
        ax.set_xlabel("% of samples")
        ax.set_title(title, loc="left", fontsize=10)
        ax.grid(axis="y", visible=False)
    axes[0].legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(RESULTS / "figures" / "refusal_rates.png", dpi=160)
    plt.close(fig)


def make_all(summary: pd.DataFrame, deltas: pd.DataFrame, models: list[Model]) -> None:
    vuln_by_condition(summary, models)
    sensitive_delta(deltas, models)
    refusal_rates(summary, models)
