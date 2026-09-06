"""Bootstrap CIs and permutation tests resampling over ITEMS (documents, drafts, questions), not samples.

Data shape everywhere: {item_id: np.ndarray of per-sample values} for one (model, group) cell.
- `boot_mean`: pooled mean over samples with a 95% CI from resampling items with replacement.
- `boot_delta`: mean(A) - mean(B) where A and B are different item sets (china vs control), resampled
  independently (the two groups share no items, so the delta is unpaired).
- `perm_delta`: two-sided permutation test shuffling the group label across items (all samples of an
  item move together).
- `boot_origin_gap`: mean over Chinese models of (china - control) minus the same over Western models,
  resampling items jointly across models (every model saw the same items).
"""
from __future__ import annotations

import numpy as np

RNG = np.random.default_rng(20260905)
N_BOOT = 2000
N_PERM = 5000

Cell = dict[str, np.ndarray]


def _pool(cell: Cell, items: list[str]) -> np.ndarray:
    arrs = [cell[i] for i in items if i in cell and cell[i].size]
    return np.concatenate(arrs) if arrs else np.array([])


def _clean(cell: Cell) -> Cell:
    return {k: np.asarray(v, dtype=float)[~np.isnan(np.asarray(v, dtype=float))] for k, v in cell.items()}


def boot_mean(cell: Cell, n_boot: int = N_BOOT) -> tuple[float, float, float]:
    cell = _clean(cell)
    items = [k for k, v in cell.items() if v.size]
    allv = _pool(cell, items)
    if allv.size == 0:
        return np.nan, np.nan, np.nan
    point = float(allv.mean())
    boots = []
    for _ in range(n_boot):
        pick = RNG.choice(items, size=len(items), replace=True)
        v = _pool(cell, list(pick))
        boots.append(v.mean() if v.size else np.nan)
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    return point, float(lo), float(hi)


def boot_delta(a: Cell, b: Cell, n_boot: int = N_BOOT) -> tuple[float, float, float]:
    a, b = _clean(a), _clean(b)
    ia = [k for k, v in a.items() if v.size]
    ib = [k for k, v in b.items() if v.size]
    va, vb = _pool(a, ia), _pool(b, ib)
    if va.size == 0 or vb.size == 0:
        return np.nan, np.nan, np.nan
    point = float(va.mean() - vb.mean())
    boots = []
    for _ in range(n_boot):
        x = _pool(a, list(RNG.choice(ia, size=len(ia), replace=True)))
        y = _pool(b, list(RNG.choice(ib, size=len(ib), replace=True)))
        boots.append(x.mean() - y.mean() if x.size and y.size else np.nan)
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    return point, float(lo), float(hi)


def perm_delta(a: Cell, b: Cell, n_perm: int = N_PERM) -> float:
    a, b = _clean(a), _clean(b)
    items = [(v, True) for v in a.values() if v.size] + [(v, False) for v in b.values() if v.size]
    if not any(f for _, f in items) or not any(not f for _, f in items):
        return np.nan
    sums = np.array([v.sum() for v, _ in items])
    ns = np.array([v.size for v, _ in items])
    lab = np.array([f for _, f in items])

    def stat(l):
        return sums[l].sum() / ns[l].sum() - sums[~l].sum() / ns[~l].sum()

    obs = stat(lab)
    count = 0
    for _ in range(n_perm):
        p = RNG.permutation(lab)
        if abs(stat(p)) >= abs(obs) - 1e-12:
            count += 1
    return (count + 1) / (n_perm + 1)


def boot_origin_gap(per_model: dict[str, tuple[Cell, Cell]], chinese: list[str], western: list[str], n_boot: int = N_BOOT) -> tuple[float, float, float]:
    """per_model[model] = (china_cell, control_cell). Returns mean delta(chinese models) - mean delta(western models), CI from joint item resampling."""
    pm = {m: (_clean(a), _clean(b)) for m, (a, b) in per_model.items()}
    chinese = [m for m in chinese if m in pm]
    western = [m for m in western if m in pm]
    if not chinese or not western:
        return np.nan, np.nan, np.nan
    ia = sorted({k for m in pm for k in pm[m][0]})
    ib = sorted({k for m in pm for k in pm[m][1]})

    def gap(pa, pb):
        def d(m):
            x, y = _pool(pm[m][0], pa), _pool(pm[m][1], pb)
            return x.mean() - y.mean() if x.size and y.size else np.nan
        return np.nanmean([d(m) for m in chinese]) - np.nanmean([d(m) for m in western])

    point = float(gap(ia, ib))
    boots = [gap(list(RNG.choice(ia, size=len(ia), replace=True)), list(RNG.choice(ib, size=len(ib), replace=True))) for _ in range(n_boot)]
    lo, hi = np.nanpercentile(boots, [2.5, 97.5])
    return point, float(lo), float(hi)


def fmt(p, lo=None, hi=None, pct=True, digits=1) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "n/a"
    if pct:
        s = f"{100*p:.{digits}f}%"
        if lo is not None and not np.isnan(lo):
            s += f" [{100*lo:.{digits}f}, {100*hi:.{digits}f}]"
    else:
        s = f"{p:.2f}"
        if lo is not None and not np.isnan(lo):
            s += f" [{lo:.2f}, {hi:.2f}]"
    return s
