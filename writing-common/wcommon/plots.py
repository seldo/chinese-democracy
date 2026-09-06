"""Shared figures. Palette: fixed categorical slots; one axis per chart; thin marks."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

from .config import Model

ORIGIN_COLOR = {"china": "#eb6834", "west": "#2a78d6"}
GROUP_COLOR = {"china": "#eb6834", "control": "#eda100", "neutral": "#1baf7a"}
SLOT_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#4a3aa7", "#c2185b", "#52514e", "#8a8a86"]
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#e6e6e3", "grid.linewidth": 0.6, "axes.axisbelow": True, "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "text.color": "#0b0b0b", "axes.labelcolor": "#52514e", "xtick.color": "#52514e", "ytick.color": "#52514e"})


def delta_dotwhisker(deltas: pd.DataFrame, models: list[Model], metric: str, xlabel: str, title: str, path: Path, scale: float = 100.0, extra_series: list[tuple[str, str, str]] | None = None, primary: tuple[str, str, str] = ("china_minus_control", "o", "china minus control"), refline: float = 0.0) -> None:
    """One row per model, marker at the value with a 95% CI whisker. deltas has columns model_key, target, {metric}, {metric}_lo, {metric}_hi.
    extra_series: [(target_name, marker, label)] for additional targets on the same row (offset). refline: x of the reference line (0 for deltas, 1 for ratios)."""
    series = [primary] + (extra_series or [])
    fig, ax = plt.subplots(figsize=(7.5, 0.55 * len(models) + 1.8))
    ys = np.arange(len(models))[::-1]
    offs = np.linspace(0.2, -0.2, len(series)) if len(series) > 1 else [0.0]
    for y, m in zip(ys, models):
        d = deltas[deltas.model_key == m.key].set_index("target")
        for (tgt, mk, _), off in zip(series, offs):
            if tgt not in d.index:
                continue
            r = d.loc[tgt]
            p, lo, hi = r[metric] * scale, r[f"{metric}_lo"] * scale, r[f"{metric}_hi"] * scale
            if np.isnan(p):
                continue
            c = ORIGIN_COLOR[m.origin]
            ax.plot([lo, hi], [y + off, y + off], color=c, lw=2, solid_capstyle="butt")
            ax.plot(p, y + off, marker=mk, color=c, ms=7, markeredgecolor="#fcfcfb", markeredgewidth=1)
    ax.axvline(refline, color="#52514e", lw=0.8)
    ax.set_yticks(ys)
    ax.set_yticklabels([f"{m.key} ({m.origin})" for m in models])
    ax.set_xlabel(xlabel)
    leg = [Line2D([], [], color=ORIGIN_COLOR["china"], lw=3, label="Chinese-developed"), Line2D([], [], color=ORIGIN_COLOR["west"], lw=3, label="Western-developed")]
    if len(series) > 1:
        leg = [Line2D([], [], marker=mk, color="#52514e", ls="", label=lab) for _, mk, lab in series] + leg
    ax.legend(handles=leg, frameon=False, fontsize=8, loc="best")
    ax.set_title(title, loc="left", fontsize=10)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)


def grouped_bars(df: pd.DataFrame, models: list[Model], value_col: str, cat_col: str, cats: list[str], ylabel: str, title: str, path: Path, group_col: str = "group", groups: tuple[str, ...] = ("china", "control", "neutral"), scale: float = 100.0, lo_col: str | None = None, hi_col: str | None = None) -> None:
    """Small multiples: one panel per model; bars = cats on x, colored by group (china/control/neutral)."""
    n = len(models)
    cols = 4 if n > 4 else n
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(4.2 * cols, 3.2 * rows), sharey=True, squeeze=False)
    w = 0.8 / len(groups)
    for ax, m in zip(axes.flat, models):
        d = df[df.model_key == m.key]
        x = np.arange(len(cats))
        for gi, g in enumerate(groups):
            s = d[d[group_col] == g].set_index(cat_col).reindex(cats)
            y = s[value_col].to_numpy(dtype=float) * scale
            err = None
            if lo_col and hi_col:
                err = np.nan_to_num(np.vstack([y - s[lo_col].to_numpy(dtype=float) * scale, s[hi_col].to_numpy(dtype=float) * scale - y]))
            ax.bar(x + (gi - (len(groups) - 1) / 2) * w, np.nan_to_num(y), width=w * 0.95, color=GROUP_COLOR.get(g, SLOT_COLORS[gi]), label=g, yerr=err, error_kw={"elinewidth": 0.7, "ecolor": "#52514e", "capsize": 0})
        ax.set_title(f"{m.key} ({m.origin})", fontsize=9.5, loc="left")
        ax.set_xticks(x)
        ax.set_xticklabels(cats, rotation=45, ha="right", fontsize=7.5)
    for ax in axes.flat[n:]:
        ax.axis("off")
    for ax in axes[:, 0]:
        ax.set_ylabel(ylabel)
    handles = [plt.Rectangle((0, 0), 1, 1, color=GROUP_COLOR.get(g, SLOT_COLORS[i])) for i, g in enumerate(groups)]
    fig.legend(handles, list(groups), loc="upper right", ncol=len(groups), frameon=False, fontsize=8)
    fig.suptitle(title, x=0.01, ha="left", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)
    plt.close(fig)
