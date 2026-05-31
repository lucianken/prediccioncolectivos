"""
Enfoque C: construcción offline de la lookup route_id → shape.

Algoritmo:
  Para cada route_id, acumula todos sus puntos GPS y evalúa cada shape candidato
  (filtrado por direction_id) en dos dimensiones ortogonales:

  1. Containment + Coverage (discrimina completos de fraccionados):
     - containment: fracción de puntos con perp < CONTAINED_PERP_M.
       Si bajo → el bus se "sale" del shape por los extremos → shape lo rechaza.
     - coverage: (max_dist_along - min_dist_along) / total_length.
       Si alto → el bus llena el shape de punta a punta.
     Regla: entre shapes con containment alto, el de mayor coverage gana.
     Un fraccionado (D) tiene coverage=100% sobre sí mismo y 40% sobre su padre (A).
     Un entero (A) tiene containment bajo sobre D → D se filtra antes de coverage.

  2. Voto-por-punto (discrimina entre completos similares):
     Cada punto GPS vota al shape con menor perp (argmin). En la zona exclusiva de A,
     todos los votos van a A; en la zona compartida se reparten. El margen del voto
     discrimina A de B/C sin necesitar zonas únicas amplias.

  Flujo de decisión:
    a. Filtrar candidatos a direction_id == route_id.direction_id.
    b. Calcular containment, coverage, y vote_frac para cada candidato.
    c. coverage_winner = argmax(coverage) sobre shapes con containment alto.
    d. Si coverage_winner es fraccionado → resolución por coverage_gap vs padre.
    e. Si coverage_winner es completo → resolución por vote_margin entre completos.
    f. Si el margen es insuficiente o hay pocos trips → status "pending".

Ref: research_ramal_id_approaches.md §Enfoque C y §El problema de los fraccionados.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from prediccion.pipeline.projector import ShapeIndex

# ── Parámetros por defecto ────────────────────────────────────────────────────

CONTAINED_PERP_M       = 30.0   # m: perp < esto → punto "contenido" en el shape
CONTAINMENT_THRESHOLD  = 0.60   # fracción mínima de puntos contenidos para ser candidato
VOTE_MARGIN_THRESHOLD  = 0.15   # margen mínimo de voto para resolver un completo
VOTE_TIE_TOLERANCE_M   = 3.0    # shapes dentro de este margen de perp comparten el voto en partes iguales
QUANTILE_P             = 0.95   # percentil alto del perp como discriminador alternativo al voto
QUANTILE_MARGIN        = 0.40   # margen relativo mínimo: (q_second - q_best) / q_second
COVERAGE_GAP_THRESHOLD = 0.20   # gap mínimo de coverage para resolver un fraccionado
MIN_TRIPS              = 3      # cold-start gate: trips mínimos antes de declarar algo


# ── Tipos ─────────────────────────────────────────────────────────────────────

@dataclass
class RouteEvidence:
    """Evidencia acumulada offline para un route_id."""
    route_id: str
    direction_id: int
    n_trips: int
    points: list[tuple[float, float]]   # (lat, lon) de todos los trips


@dataclass
class ShapeEntry:
    short_name: str                        # e.g. "39A"
    direction: int                         # 0 o 1 (implícito por orden en JSON)
    index: ShapeIndex
    is_fraccionado: bool = False
    parent_short_name: Optional[str] = None

    @property
    def key(self) -> str:
        return f"{self.short_name}-d{self.direction}"


@dataclass
class LookupEntry:
    route_id: str
    direction_id: int
    status: str                            # "resolved" | "pending"
    reason: Optional[str] = None          # por qué está pending

    # Solo si resolved:
    assigned_shape_key: Optional[str] = None   # e.g. "39A-d0"
    short_name: Optional[str] = None
    shape_direction: Optional[int] = None
    assignment_type: Optional[str] = None      # "completo" | "fraccionado"
    method: Optional[str] = None               # "vote+coverage" | "vote_only" | "coverage_gap"
    confidence: float = 0.0                    # vote_margin o coverage_gap según método

    # Métricas de diagnóstico
    vote_margin: float = 0.0
    quantile_margin: float = 0.0      # (q_second - q_best) / q_second
    q_best_m: float = 0.0             # p95 del shape ganador en metros
    coverage_winner_val: float = 0.0
    containment_winner_val: float = 0.0
    total_trips: int = 0
    total_points: int = 0
    top_candidates: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "route_id": self.route_id,
            "direction_id": self.direction_id,
            "status": self.status,
            "reason": self.reason,
            "assigned_shape_key": self.assigned_shape_key,
            "short_name": self.short_name,
            "shape_direction": self.shape_direction,
            "assignment_type": self.assignment_type,
            "method": self.method,
            "confidence": round(self.confidence, 3),
            "vote_margin": round(self.vote_margin, 3),
            "quantile_margin": round(self.quantile_margin, 3),
            "q_best_m": round(self.q_best_m, 1),
            "coverage_winner_val": round(self.coverage_winner_val, 3),
            "containment_winner_val": round(self.containment_winner_val, 3),
            "total_trips": self.total_trips,
            "total_points": self.total_points,
            "top_candidates": self.top_candidates,
        }


# ── I/O helpers ───────────────────────────────────────────────────────────────

def load_families(path: str | Path) -> dict[str, list[str]]:
    """Carga el mapa {parent_shortName: [child_shortName, ...]} desde JSON."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["families"]


def build_shape_entries(shapes: dict, line: str, families: dict[str, list[str]]) -> list[ShapeEntry]:
    """
    Construye ShapeEntry para cada shape de la línea.
    direction es implícito: primera ocurrencia de cada shortName = d0, segunda = d1.
    Mismo convenio que analisis_ramal_39.py.
    """
    fraccionado_names = {c for children in families.values() for c in children}
    parent_map = {c: p for p, children in families.items() for c in children}

    direction_counter: dict[str, int] = {}
    entries: list[ShapeEntry] = []
    for r in shapes[line]["ramales"]:
        sn = r["shortName"]
        d = direction_counter.get(sn, 0)
        direction_counter[sn] = d + 1
        entries.append(ShapeEntry(
            short_name=sn,
            direction=d,
            index=ShapeIndex([tuple(p) for p in r["points"]]),
            is_fraccionado=sn in fraccionado_names,
            parent_short_name=parent_map.get(sn),
        ))
    return entries


# ── Algoritmo core ────────────────────────────────────────────────────────────

def build_lookup(
    evidence: dict[str, RouteEvidence],
    shape_entries: list[ShapeEntry],
    families: dict[str, list[str]],
    *,
    contained_perp_m: float = CONTAINED_PERP_M,
    containment_threshold: float = CONTAINMENT_THRESHOLD,
    vote_margin_threshold: float = VOTE_MARGIN_THRESHOLD,
    coverage_gap_threshold: float = COVERAGE_GAP_THRESHOLD,
    min_trips: int = MIN_TRIPS,
    vote_tie_tolerance_m: float = VOTE_TIE_TOLERANCE_M,
    quantile_p: float = QUANTILE_P,
    quantile_margin_threshold: float = QUANTILE_MARGIN,
) -> dict[str, LookupEntry]:
    """
    Construye la lookup offline route_id → shape para una línea.

    evidence: {route_id: RouteEvidence} — acumulado de todos los días disponibles.
    Retorna {route_id: LookupEntry} con status "resolved" o "pending".
    """
    parent_map = {c: p for p, children in families.items() for c in children}
    entries_by_key = {e.key: e for e in shape_entries}

    lookup: dict[str, LookupEntry] = {}

    for rid, ev in evidence.items():
        direction = ev.direction_id
        n_trips = ev.n_trips
        n_points = len(ev.points)

        # ── Cold-start gate ───────────────────────────────────────────────────
        if n_trips < min_trips:
            lookup[rid] = LookupEntry(
                route_id=rid, direction_id=direction,
                status="pending", reason="cold_start",
                total_trips=n_trips, total_points=n_points,
            )
            continue

        # ── Candidatos según direction_id ─────────────────────────────────────
        candidates = [e for e in shape_entries if e.direction == direction]
        if not candidates:
            lookup[rid] = LookupEntry(
                route_id=rid, direction_id=direction,
                status="pending", reason="no_shapes_for_direction",
                total_trips=n_trips, total_points=n_points,
            )
            continue

        if n_points == 0:
            lookup[rid] = LookupEntry(
                route_id=rid, direction_id=direction,
                status="pending", reason="no_points",
                total_trips=n_trips, total_points=n_points,
            )
            continue

        # ── Proyección sobre todos los shapes candidatos ──────────────────────
        perps: dict[str, list[float]] = {}
        dist_alongs: dict[str, list[float]] = {}
        for e in candidates:
            ps: list[float] = []
            ds: list[float] = []
            for lat, lon in ev.points:
                d_along, p = e.index.project(lat, lon)
                ds.append(d_along)
                ps.append(p)
            perps[e.key] = ps
            dist_alongs[e.key] = ds

        # ── Voto-por-punto: cada punto vota al argmin(perp) ─────────────────
        # Shapes dentro de vote_tie_tolerance_m del mínimo comparten el voto
        # en partes iguales. Evita que el primero de la lista acapare todos los
        # empates cuando A y B comparten los mismos nodos OSM (perp exactamente 0).
        votes: dict[str, float] = defaultdict(float)
        cand_keys = [e.key for e in candidates]
        for i in range(n_points):
            min_perp_i = min(perps[k][i] for k in cand_keys)
            tied = [k for k in cand_keys if perps[k][i] <= min_perp_i + vote_tie_tolerance_m]
            share = 1.0 / len(tied)
            for k in tied:
                votes[k] += share
        vote_fracs = {k: votes[k] / n_points for k in cand_keys}

        # ── Containment y coverage por shape ─────────────────────────────────
        containment: dict[str, float] = {}
        coverage: dict[str, float] = {}
        for e in candidates:
            k = e.key
            containment[k] = sum(1 for p in perps[k] if p < contained_perp_m) / n_points
            total_len = e.index.total_length_m
            ds_arr = np.array(dist_alongs[k])
            # p2/p98 en vez de min/max: robusto a puntos GPS outlier (teletransporte,
            # salida de depósito) que de otro modo arrastran min o max al valor extremo.
            coverage[k] = (np.percentile(ds_arr, 98) - np.percentile(ds_arr, 2)) / total_len if total_len > 0 else 0.0

        # ── Cuantil alto del perp por shape ──────────────────────────────────
        # p95 del error perpendicular: ignora el troncal compartido (perp≈0 en todos)
        # y se queda con la cola donde vive la discriminación (tramo exclusivo).
        # El shape correcto tiene q_high bajo; los incorrectos tienen q_high alto.
        q_high: dict[str, float] = {
            k: float(np.percentile(perps[k], quantile_p * 100))
            for k in cand_keys
        }

        # ── Top candidatos para diagnóstico ───────────────────────────────────
        top_candidates = sorted(
            [{
                "key": e.key,
                "containment": round(containment[e.key], 3),
                "coverage": round(coverage[e.key], 3),
                "vote_frac": round(vote_fracs[e.key], 3),
                "q_high_m": round(q_high[e.key], 1),
                "is_fraccionado": e.is_fraccionado,
            } for e in candidates],
            key=lambda x: x["q_high_m"],
        )

        # ── Filtrar a candidatos con containment alto ─────────────────────────
        high_cont = [k for k in cand_keys if containment[k] >= containment_threshold]

        if not high_cont:
            lookup[rid] = LookupEntry(
                route_id=rid, direction_id=direction,
                status="pending", reason="no_high_containment",
                total_trips=n_trips, total_points=n_points,
                top_candidates=top_candidates,
            )
            continue

        # ── Score = coverage × containment → shape más ajustado ──────────────
        # Producto: penaliza tanto no llenar el shape (coverage bajo) como salirse de él
        # (containment bajo). Resuelve el caso donde D, E, F tienen coverage similar
        # pero D tiene containment=1.0 mientras E/F tienen containment menor.
        cov_winner_key = max(high_cont, key=lambda k: coverage[k] * containment[k])
        cov_winner_entry = entries_by_key[cov_winner_key]

        # ── Decisión: fraccionado o completo ──────────────────────────────────

        if cov_winner_entry.is_fraccionado:
            # El route_id llena mejor un shape fraccionado que su padre →
            # probablemente es un fraccionado. Verificar con coverage_gap.
            parent_sn = cov_winner_entry.parent_short_name
            parent_key = f"{parent_sn}-d{direction}" if parent_sn else None
            cov_frac = coverage[cov_winner_key]
            cov_parent = coverage.get(parent_key, 0.0)
            coverage_gap = cov_frac - cov_parent

            if coverage_gap >= coverage_gap_threshold:
                lookup[rid] = LookupEntry(
                    route_id=rid, direction_id=direction,
                    status="resolved",
                    assigned_shape_key=cov_winner_key,
                    short_name=cov_winner_entry.short_name,
                    shape_direction=direction,
                    assignment_type="fraccionado",
                    method="coverage_gap",
                    confidence=coverage_gap,
                    vote_margin=vote_fracs.get(cov_winner_key, 0.0),
                    coverage_winner_val=cov_frac,
                    containment_winner_val=containment[cov_winner_key],
                    total_trips=n_trips, total_points=n_points,
                    top_candidates=top_candidates,
                )
            else:
                lookup[rid] = LookupEntry(
                    route_id=rid, direction_id=direction,
                    status="pending", reason="ambiguous_fraccionado",
                    total_trips=n_trips, total_points=n_points,
                    top_candidates=top_candidates,
                )

        else:
            # El route_id es probablemente un completo.
            # Discriminador 1 — voto-por-punto entre candidatos con containment alto.
            by_vote = sorted(high_cont, key=lambda k: vote_fracs[k], reverse=True)
            v_winner_key = by_vote[0]
            v_second_key = by_vote[1] if len(by_vote) > 1 else None
            v_margin = vote_fracs[v_winner_key] - (vote_fracs[v_second_key] if v_second_key else 0.0)

            # Discriminador 2 — cuantil alto del perp entre candidatos con containment alto.
            # El shape correcto tiene q_high bajo (sus puntos exclusivos son también cercanos);
            # los incorrectos tienen q_high alto (sus tramos exclusivos están lejos del bus).
            by_q = sorted(high_cont, key=lambda k: q_high[k])
            q_winner_key = by_q[0]
            q_second_key = by_q[1] if len(by_q) > 1 else None
            q_best = q_high[q_winner_key]
            q_second = q_high[q_second_key] if q_second_key else q_best
            # margen relativo: cuánto mejor es el ganador respecto al segundo
            q_margin = (q_second - q_best) / q_second if q_second > 0 else 0.0

            # Elegir método: preferir el que supera su umbral; si ambos, tomar el que coincide con cov_winner
            vote_ok = v_margin >= vote_margin_threshold
            q_ok    = q_margin >= quantile_margin_threshold

            if vote_ok or q_ok:
                # Ganador: si ambos coinciden → el mismo; si difieren → preferir cuantil (señal más limpia)
                winner_key = v_winner_key if (vote_ok and v_winner_key == q_winner_key) else \
                             (q_winner_key if q_ok else v_winner_key)
                parts = []
                if vote_ok: parts.append("vote")
                if q_ok:    parts.append("q95")
                if winner_key == cov_winner_key: parts.append("cov")
                method = "+".join(parts)

                lookup[rid] = LookupEntry(
                    route_id=rid, direction_id=direction,
                    status="resolved",
                    assigned_shape_key=winner_key,
                    short_name=entries_by_key[winner_key].short_name,
                    shape_direction=direction,
                    assignment_type="completo",
                    method=method,
                    confidence=max(v_margin, q_margin),
                    vote_margin=v_margin,
                    quantile_margin=q_margin,
                    q_best_m=q_best,
                    coverage_winner_val=coverage[cov_winner_key],
                    containment_winner_val=containment[winner_key],
                    total_trips=n_trips, total_points=n_points,
                    top_candidates=top_candidates,
                )
            else:
                lookup[rid] = LookupEntry(
                    route_id=rid, direction_id=direction,
                    status="pending", reason="ambiguous_completo",
                    vote_margin=v_margin,
                    quantile_margin=q_margin,
                    q_best_m=q_best,
                    total_trips=n_trips, total_points=n_points,
                    top_candidates=top_candidates,
                )

    return lookup
