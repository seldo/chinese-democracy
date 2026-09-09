"""direct-questions figures: topic-by-model heatmap, response-class stacks, trace bars. Palette follows writing-common/wcommon/plots.py."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch

from wcommon.config import Model
from wcommon.plots import ORIGIN_COLOR  # noqa: F401  (rcParams are set on import)

SURFACE = "#fcfcfb"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
CLASS_COLOR = {"refusal": "#e34948", "official_line": "#eb6834", "deflection": "#eda100", "omission": "#e87ba4", "hedged": "#1baf7a", "factual": "#2a78d6"}
CLASS_LABEL = {"refusal": "refusal", "official_line": "official line", "deflection": "deflection", "omission": "omission", "hedged": "hedged", "factual": "factual"}
SEQ = LinearSegmentedColormap.from_list("blue_seq", ["#f4f8fd", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
GROUP_LABEL = {"china_core": "China, core", "china_embarrassing": "China, embarrassing", "china_favorable": "China, favorable", "control": "control", "neutral": "neutral"}
SHORT = {"deepseek_v4_pro": "DeepSeek V4 Pro", "qwen3_8_max": "Qwen3.8 Max", "kimi_k3": "Kimi K3", "glm_5_3": "GLM-5.3", "minimax_m3": "MiniMax M3", "gpt_oss_120b": "gpt-oss-120b", "nemotron_3_ultra": "Nemotron 3 Ultra", "nemotron_lightning_3_5": "Nemotron Lightning 3.5"}


def topic_heatmap(rates: pd.DataFrame, topics: list[dict], models: list[Model], value: str, title: str, path: Path) -> None:
    """rates: columns topic_id, model_key, lang, <value> (0..1). One row per topic, one column per (model, lang)."""
    cols = [(m.key, lang) for m in models for lang in ("en", "zh")]
    mat = np.full((len(topics), len(cols)), np.nan)
    idx = {(r.topic_id, r.model_key, r.lang): getattr(r, value) for r in rates.itertuples()}
    for i, t in enumerate(topics):
        for j, (mk, lang) in enumerate(cols):
            mat[i, j] = idx.get((t["id"], mk, lang), np.nan)
    fig_h = 0.26 * len(topics) + 2.6
    fig, ax = plt.subplots(figsize=(13, fig_h))
    im = ax.imshow(mat, cmap=SEQ, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(cols)))
    ax.xaxis.tick_top()
    ax.xaxis.set_label_position("top")
    ax.set_xticklabels([f"{SHORT.get(mk, mk)} · {lang}" for mk, lang in cols], fontsize=7.5, rotation=45, ha="left", rotation_mode="anchor")
    ax.set_yticks(range(len(topics)))
    ax.set_yticklabels([f"{t['topic']}" for t in topics], fontsize=7.5)
    ax.grid(False)
    for j in range(2, len(cols), 2):
        ax.axvline(j - 0.5, color=SURFACE, lw=2.5)
    n_china = sum(1 for m in models if m.origin == "china")
    ax.axvline(2 * n_china - 0.5, color=INK2, lw=1.2)
    prev = None
    for i, t in enumerate(topics):
        if t["group"] != prev:
            if i:
                ax.axhline(i - 0.5, color=INK2, lw=1.0)
            ax.text(len(cols) - 0.4, i - 0.1, GROUP_LABEL.get(t["group"], t["group"]), ha="left", va="top", fontsize=8, color=INK2, fontweight="bold", clip_on=False)
            prev = t["group"]
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            v = mat[i, j]
            if not np.isnan(v) and v >= 0.5:
                ax.text(j, i, f"{100*v:.0f}", ha="center", va="center", fontsize=6.5, color="white")
    ax.set_title(title, loc="left", fontsize=11, pad=70)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.09)
    cb.set_label("share of answers that were a refusal, official line or deflection", fontsize=8, color=INK2)
    cb.ax.tick_params(labelsize=7.5)
    cb.outline.set_visible(False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=170)
    plt.close(fig)


def class_stacks(dist: pd.DataFrame, models: list[Model], groups: list[str], title: str, path: Path) -> None:
    """dist: columns model_key, group, class, share. One panel per group; horizontal stacked bars, one per model."""
    classes = list(CLASS_COLOR)
    fig, axes = plt.subplots(1, len(groups), figsize=(4.6 * len(groups), 0.5 * len(models) + 1.9), sharey=True, squeeze=False)
    ys = np.arange(len(models))[::-1]
    for ax, g in zip(axes[0], groups):
        for y, m in zip(ys, models):
            d = dist[(dist.model_key == m.key) & (dist.group == g)].set_index("class")["share"]
            left = 0.0
            for c in classes:
                w = float(d.get(c, 0.0))
                if w <= 0:
                    continue
                ax.barh(y, w, left=left, height=0.62, color=CLASS_COLOR[c], edgecolor=SURFACE, linewidth=1.5)
                left += w
        ax.set_xlim(0, 1)
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.set_xticklabels(["0", "25", "50", "75", "100%"], fontsize=8)
        ax.set_yticks(ys)
        ax.set_yticklabels([f"{m.key} ({m.origin})" for m in models], fontsize=8.5)
        ax.set_title(GROUP_LABEL.get(g, g), loc="left", fontsize=10)
        ax.grid(axis="y", visible=False)
        ax.tick_params(length=0)
        ax.spines["left"].set_visible(False)
        n_china = sum(1 for m in models if m.origin == "china")
        ax.axhline(ys[n_china - 1] - 0.5, color=GRID, lw=0.8)
    fig.legend(handles=[Patch(color=CLASS_COLOR[c], label=CLASS_LABEL[c]) for c in classes], loc="upper right", ncol=len(classes), frameon=False, fontsize=8, bbox_to_anchor=(0.995, 1.0))
    fig.suptitle(title, x=0.01, ha="left", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=170)
    plt.close(fig)


def paired_lang_bars(summary: pd.DataFrame, models: list[Model], metric: str, group: str, ylabel: str, title: str, path: Path) -> None:
    """One panel; per model two bars (en, zh) for one metric in one group, with CI whiskers."""
    fig, ax = plt.subplots(figsize=(9, 4.2))
    x = np.arange(len(models))
    w = 0.36
    for k, (lang, col, lab) in enumerate((("en", "#2a78d6", "English prompt"), ("zh", "#eb6834", "Chinese prompt"))):
        vals, lo, hi = [], [], []
        for m in models:
            r = summary[(summary.model_key == m.key) & (summary.group == group) & (summary.lang == lang)]
            v = float(r[metric].iloc[0]) if len(r) else np.nan
            vals.append(100 * v)
            lo.append(100 * (v - float(r[f"{metric}_lo"].iloc[0])) if len(r) else 0)
            hi.append(100 * (float(r[f"{metric}_hi"].iloc[0]) - v) if len(r) else 0)
        ax.bar(x + (k - 0.5) * w, np.nan_to_num(vals), width=w * 0.94, color=col, label=lab, yerr=np.nan_to_num(np.vstack([lo, hi])), error_kw={"elinewidth": 0.8, "ecolor": INK2, "capsize": 0})
    ax.set_xticks(x)
    ax.set_xticklabels([m.key for m in models], rotation=30, ha="right", fontsize=8.5)
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, None)
    ax.set_title(title, loc="left", fontsize=11)
    ax.legend(frameon=False, fontsize=8.5, loc="upper right")
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=170)
    plt.close(fig)
