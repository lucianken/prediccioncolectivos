"""Variantes `prior` del replay: reordenan la lista de `base` con el prior causal de ramal de la cabecera (medicion; no entrena nada).

Se calculan sobre las MISMAS predicciones de `base` (mismo modelo, mismos candidatos): solo cambia la presentacion. Para cada coche de
«puede venir» (ramal ambiguo) con una salida de cabecera conocida (experiments/prior_ramal_cabecera/causal: eventos.py + modelo.py),
P(pasa por la parada) = suma de las P(ramal) de sus shapes compatibles que sirven la parada (`passes`, de `ramales[].stops`; nunca por
geometria), con P(ramal) = prior causal de la cabecera de la que salio el coche, renormalizado sobre los shapes compatibles actuales
que salen de esa cabecera. Sin salida conocida o sin ningun shape compatible de esa cabecera: sin cambio.

Variantes (nombre = prior_{token|cadena}_{regla}):
  regla i    P < THR_LOW: el coche baja al final de la lista (despues de los demas de «puede venir»/provisional).
  regla ii   i, y ademas P >= THR_HIGH: pasa a «viene» (grupo seguro).
  regla iii  el primer arribo anunciado = el menor ETA entre los coches con P >= THR_FIRST (seguros con P = 1 y «puede venir» con prior);
             si no hay ninguno, el de siempre. La lista y los grupos no cambian.
  memonly_ii / memprior_{modo}_ii: ablacion con el ramal que el propio coche ya revelo con pings <= t (reveal_ts <= t): P = 1 para
             ese ramal. memonly: solo eso; memprior: eso y, si no revelo, el prior.
`modo` = como se encadena el contexto: token (previo no revelado = ficha "desconocido") o cadena (previo no revelado = su P predicha).
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

DGRID = [0, 120, 300, 600, 1200, 2400]
THR_LOW, THR_HIGH, THR_FIRST = 0.2, 0.8, 0.5
MAX_AGE_S = 9000.0       # una salida deja de aplicar a los 150 min (el viaje ya terminó)
LIST_MAX = 5
MODES = ("token", "cadena")
RULES = ("i", "ii", "iii")
# Controles de la regla iii (primer arribo = menor ETA entre «viene» y «puede venir»): sin P (ctrl_min) o sacando de ese mínimo a los
# «puede venir» con P < umbral. Nombre ctrl_min_{fuente}{umbral}: fuente tok|cad (prior causal), mem (ramal propio revelado), memtok.
CTRL = {"ctrl_min": (None, None, 0.0), "ctrl_min_tok02": ("prior", "token", 0.2), "ctrl_min_tok05": ("prior", "token", 0.5),
        "ctrl_min_cad02": ("prior", "cadena", 0.2), "ctrl_min_mem": ("memonly", "token", 0.2), "ctrl_min_memtok02": ("memprior", "token", 0.2)}
VARIANTS = tuple([f"prior_{m}_{r}" for m in MODES for r in RULES] + ["memonly_ii"] + [f"memprior_{m}_ii" for m in MODES] + list(CTRL))


def parse(var: str):
    """(kind, mode, rule): kind en prior | memonly | memprior."""
    p = var.split("_")
    if p[0] == "memonly":
        return "memonly", "token", p[1]
    return p[0], p[1], p[2]


def _origin(name: str) -> str:
    return re.split(r"\s*→", name.split(":", 1)[1].strip())[0].strip()


class PriorCtx:
    """Salidas de cabecera de un (día, línea) y sus P. ev: filas de P_eventos.parquet de ese día y línea."""

    def __init__(self, ev: pd.DataFrame, shapes: dict, meta: dict):
        self.shape_meta = {sid: (sh.short_name.replace(" ", ""), _origin(sh.name)) for sid, sh in shapes.items()}
        self.meta = meta
        self.by_vid: dict[str, list] = {}
        for r in ev.sort_values("det_ts").itertuples(index=False):
            self.by_vid.setdefault(str(r.vid), []).append(r)
        self.cols = {m: [f"P_{m}_{d}" for d in DGRID] for m in MODES}

    @classmethod
    def load(cls, day: str, line: str, shapes: dict, prior_dir) -> "PriorCtx":
        import json
        d = Path(prior_dir)
        ev = pd.read_parquet(d / "P_eventos.parquet")
        ev = ev[(ev.day == day) & (ev.line == line)]
        return cls(ev, shapes, json.loads((d / "meta.json").read_text(encoding="utf-8")))

    def event(self, vid: str, t: float):
        best = None
        for r in self.by_vid.get(str(vid), ()):
            if r.det_ts <= t:
                best = r
            else:
                break
        if best is None or t - best.det_ts > MAX_AGE_S:
            return None
        return best

    def weights(self, e, t: float, kind: str, mode: str, comp: list):
        """Peso por shape compatible (lista alineada con comp) o None si no hay información."""
        ram = self.meta.get(e.gkey, {}).get("ramales")
        if not ram:
            return None
        w = np.zeros(len(comp))
        sm = [self.shape_meta.get(k["shape_id"]) for k in comp]
        on_cab = [m is not None and m[1] == e.cab for m in sm]
        if kind in ("memonly", "memprior") and e.reveal_ts <= t and e.reveal_ramal:
            w = np.array([1.0 if (ok and m[0] == e.reveal_ramal) else 0.0 for ok, m in zip(on_cab, sm)])
            if w.sum() > 0 or kind == "memonly":
                return w if w.sum() > 0 else None
        if kind == "memonly":
            return None
        k = max(i for i, d in enumerate(DGRID) if d <= t - e.det_ts)
        p = np.asarray(getattr(e, self.cols[mode][k]), float)
        idx = {r: i for i, r in enumerate(ram)}
        w = np.array([p[idx[m[0]]] if (ok and m[0] in idx) else 0.0 for ok, m in zip(on_cab, sm)])
        return w if w.sum() > 0 else None

    def probs(self, preds: dict, t: float, kind: str, mode: str) -> dict:
        out = {}
        for vid, r in preds.items():
            if not r or r.get("group") != "puede_venir" or r.get("eta_s") is None:
                continue
            e = self.event(vid, t)
            if e is None:
                continue
            comp = r["compatible"]
            w = self.weights(e, t, kind, mode, comp)
            if w is None:
                continue
            out[vid] = float(sum(wi for wi, k in zip(w, comp) if k["passes"]) / w.sum())
        return out


def list_for(var: str, base_lst: dict, preds: dict, ctx: PriorCtx, t: float) -> dict:
    """Lista de la variante `var` a partir de la lista de base (misma estructura que core.build_list; opcional `first_any`: (eta, eta0))."""
    if var in CTRL:
        kind, mode, thr = CTRL[var]
        pr = ctx.probs(preds, t, kind, mode) if (kind and ctx is not None) else {}
        sure, others = list(base_lst["seguro"]), list(base_lst["otros"])
        out = {"eta0": base_lst["eta0"], "shown": base_lst["shown"], "seguro": sure, "otros": others}
        cand = list(sure) + [x for x in others if x[1] == "puede_venir" and pr.get(x[0], 1.0) >= thr]
        if cand:
            b = min(cand, key=lambda x: x[2])
            out["first_any"] = (b[2], base_lst["eta0"].get(b[0], b[2]))
        return out
    kind, mode, rule = parse(var)
    pr = ctx.probs(preds, t, kind, mode) if ctx is not None else {}
    sure, others = list(base_lst["seguro"]), list(base_lst["otros"])
    low = {v for v, p in pr.items() if p < THR_LOW}
    out = {"eta0": base_lst["eta0"]}
    if rule in ("i", "ii"):
        if rule == "ii":
            high = {v for v, p in pr.items() if p >= THR_HIGH}
            sure = sorted(sure + [(v, "seguro", eta) for v, g, eta in others if v in high], key=lambda x: x[2])
            others = [x for x in others if x[0] not in high]
        others.sort(key=lambda x: (x[0] in low, x[2]))
    shown = sure[:LIST_MAX]
    shown = shown + others[:LIST_MAX - len(shown)]
    out.update(shown=shown, seguro=sure, otros=others)
    if rule == "iii":
        cand = list(sure) + [x for x in others if pr.get(x[0], -1.0) >= THR_FIRST]
        if cand:
            b = min(cand, key=lambda x: x[2])
            out["first_any"] = (b[2], base_lst["eta0"].get(b[0], b[2]))
    return out
