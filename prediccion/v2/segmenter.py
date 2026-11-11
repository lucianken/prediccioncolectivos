"""
Segmentador geométrico de viajes (v2). NO usa trip_id, start_time, start_date ni route_id.

Entrada: pings de UN vehículo (ya asignado a una línea por el sufijo del label) y los recorridos
(ShapeIndex) de esa línea. Salida: lista de Trip.

Orden proyectar / elegir recorrido (decisión): para segmentar se proyecta cada tramo continuo de pings sobre
TODOS los recorridos de la línea (después de un prefiltro de cobertura barato) y se sigue en paralelo el
progreso en cada recorrido "activo"; el viaje vive mientras algún recorrido siga activo. Recién después, cada
viaje ya cortado pasa por best_shape_for_trip (que ve el viaje completo) para fijar el recorrido definitivo.
Es lo más simple que no depende de adivinar el recorrido con una ventana corta: en tramos compartidos
(A/B/C del 39) varios recorridos quedan activos y se van descartando cuando el coche diverge.

Un viaje se corta cuando:
  1. hueco de datos > GAP_S (5 min);
  2. el coche llega al final de todos los recorridos activos (a END_TOL_M del final);
  3. invierte el sentido de forma sostenida: REV_N pings seguidos > REV_M metros por detrás de su máximo
     avance (retrocesos chicos por ruido GPS no cuentan);
  4. queda detenido más de STOP_S en una cabecera/terminal (a TERM_ZONE_M de un extremo);
  5. se sale de todos los recorridos (> FIT_M durante OFF_N pings seguidos).
Antes de segmentar se descartan los pings de depósito (quietos y a > FIT_M de todos los recorridos de la línea).
El inicio del viaje es la salida de la cabecera: el último ping antes de alejarse START_MOVE_M del punto
donde estaba parado (no el primer ping parado). Así time_since_start arranca en la salida.
"""

from __future__ import annotations

import math

import numpy as np

from prediccion.pipeline.projector import ShapeIndex, _forward_fraction
from prediccion.pipeline.segmenter import Trip, TripPoint

GAP_S = 300
STOP_S = 600
REV_M = 300.0
REV_N = 3
END_TOL_M = 250.0
TERM_ZONE_M = 400.0
OFF_N = 5
FIT_M = 150.0
START_MOVE_M = 100.0
STILL_M = 25.0
DEPOT_STILL_M = 100.0      # desplazamiento en +-2 pings por debajo del cual un ping fuera de recorrido es depósito
MIN_POINTS = 5
MIN_PROGRESS_M = 500.0
WINDOW_PINGS = 16
_M_PER_DEG = 111_320.0

# obs = (ts, lat, lon, speed, odo, direction_id, start_date, start_time, frame_ts, has_trip_id, route_id)
# Solo se leen ts, lat, lon, speed, odo, frame_ts (y route_id / direction_id como diagnóstico).


def _segment_chunk(lat, lon, ts, Dn: dict, Pn: dict, L: dict) -> list[tuple[int, int]]:
    """
    Devuelve [(i0, i1)] (índices inclusivos dentro del chunk). Dn/Pn: {shape_id: array} con la distancia a lo
    largo y el error perpendicular de cada ping del chunk sobre cada recorrido candidato.
    """
    m = len(lat)
    keep = list(Dn)
    if m < MIN_POINTS or not keep:
        return []
    D = {s: Dn[s].tolist() for s in keep}
    P = {s: Pn[s].tolist() for s in keep}
    valid_any = np.zeros(m, dtype=bool)
    for s in keep:
        valid_any |= Pn[s] <= FIT_M
    cos = math.cos(math.radians(float(lat.mean())))
    x = lon * _M_PER_DEG * cos
    y = lat * _M_PER_DEG
    step_d = np.hypot(np.diff(x), np.diff(y))             # step_d[k-1] = desplazamiento entre k-1 y k

    out: list[tuple[int, int]] = []
    i = 0
    while i < m - 1:
        # primer ping válido (sobre algún recorrido)
        j = i
        while j < m and not valid_any[j]:
            j += 1
        if j >= m - 1:
            break
        # salida de la cabecera: último ping antes de alejarse START_MOVE_M del punto de partida
        far = np.hypot(x[j + 1:] - x[j], y[j + 1:] - y[j]) > START_MOVE_M
        if not far.any():
            break
        start = j + int(np.argmax(far))          # = índice (j+1+argmax) - 1
        # recorridos activos al inicio: avanzan hacia adelante y ajustan en una ventana corta
        w_end = min(m, start + WINDOW_PINGS)
        active: dict[str, dict] = {}
        for s in keep:
            pw, dw = Pn[s][start:w_end], Dn[s][start:w_end]
            ok = pw <= FIT_M
            if ok.sum() < max(3, math.ceil(0.5 * len(pw))):
                continue
            if _forward_fraction(dw, pw, FIT_M) < 0.6:
                continue
            dv = dw[ok]
            if dv[-1] - dv[0] <= 0:
                continue
            active[s] = {"d0": float(dv[0]), "mx": float(dv[0]), "mxk": start, "rev": 0, "off": 0, "lastv": start}
        if not active:
            i = start + 1
            continue

        best_prog = 0.0
        last_move = start
        e = None
        cut_idx = None
        for k in range(start + 1, m):
            if step_d[k - 1] >= STILL_M:
                last_move = k
            cut_here = []
            for s in list(active):
                st = active[s]
                if P[s][k] > FIT_M:
                    st["off"] += 1
                    if st["off"] >= OFF_N:
                        cut_here.append(st["lastv"])
                        del active[s]
                    continue
                st["off"] = 0
                st["lastv"] = k
                d = D[s][k]
                if d > st["mx"]:
                    st["mx"], st["mxk"], st["rev"] = d, k, 0
                    best_prog = max(best_prog, d - st["d0"])
                elif d < st["mx"] - REV_M:
                    st["rev"] += 1
                    if st["rev"] >= REV_N:
                        cut_here.append(st["mxk"])
                        del active[s]
                        continue
                else:
                    st["rev"] = 0
                if d >= L[s] - END_TOL_M and st["mx"] - st["d0"] >= MIN_PROGRESS_M:
                    cut_here.append(k)
                    del active[s]
            if not active:
                cut_idx = max(cut_here) if cut_here else k
                break
            if ts[k] - ts[last_move] >= STOP_S:
                near = any(Pn[s][k] <= FIT_M and (Dn[s][k] < TERM_ZONE_M or Dn[s][k] > L[s] - TERM_ZONE_M)
                           for s in keep)
                if near:
                    cut_idx = last_move
                    break
        else:
            cut_idx = m - 1
        e = max(int(cut_idx), start)
        if e - start + 1 >= MIN_POINTS and best_prog >= MIN_PROGRESS_M:
            out.append((start, e))
        i = max(e, start + 1)
    return out


def depot_mask(x: np.ndarray, y: np.ndarray, off_route: np.ndarray) -> np.ndarray:
    """
    Pings de depósito/garage/playa: lejos de todos los recorridos (off_route) y casi quietos (desplazamiento
    < DEPOT_STILL_M en una ventana de +-2 pings). No forman parte de ningún viaje.
    """
    n = len(x)
    if n < 5:
        return np.zeros(n, dtype=bool)
    lo = np.clip(np.arange(n) - 2, 0, n - 1)
    hi = np.clip(np.arange(n) + 2, 0, n - 1)
    still = np.hypot(x[hi] - x[lo], y[hi] - y[lo]) < DEPOT_STILL_M
    return off_route & still


def segment_geometric(vehicle_id: str, obs: list[tuple], indices: dict[str, ShapeIndex],
                      gap_s: int = GAP_S, return_stats: bool = False):
    """
    Segmenta los pings (ts estrictamente crecientes) de un vehículo en viajes geométricos.
    Los pings de depósito (quietos y lejos de todo recorrido) se descartan antes de segmentar.
    Con return_stats=True devuelve (trips, {"pings", "depot", "moving_valid", "moving_total"}) para métricas de
    calidad de recorrido sobre pings en movimiento.
    """
    n = len(obs)
    st = {"pings": n, "depot": 0, "moving_valid": 0, "moving_total": 0}
    if n < MIN_POINTS or not indices:
        return ([], st) if return_stats else []
    ts = np.fromiter((o[0] for o in obs), dtype=np.int64, count=n)
    lat = np.fromiter((o[1] for o in obs), dtype=np.float64, count=n)
    lon = np.fromiter((o[2] for o in obs), dtype=np.float64, count=n)
    # recorridos candidatos: cobertura barata sobre una submuestra
    sub = slice(0, n, max(1, n // 60))
    keep = []
    for sid, ix in indices.items():
        _, p = ix.project_many(lat[sub], lon[sub])
        if (p <= FIT_M).mean() >= 0.05:
            keep.append(sid)
    if not keep:
        st["depot"] = 0
        st["moving_total"] = n
        return ([], st) if return_stats else []
    Dn, Pn, L = {}, {}, {}
    for sid in keep:
        d, p = indices[sid].project_many(lat, lon)
        Dn[sid], Pn[sid], L[sid] = d, p, indices[sid].total_length_m
    minperp = np.min(np.stack([Pn[s] for s in keep]), axis=0)
    cos = math.cos(math.radians(float(lat.mean())))
    x, y = lon * _M_PER_DEG * cos, lat * _M_PER_DEG
    depot = depot_mask(x, y, minperp > FIT_M)
    alive = np.flatnonzero(~depot)
    st["depot"] = int(depot.sum())
    st["moving_total"] = int(len(alive))
    st["moving_valid"] = int((minperp[alive] <= FIT_M).sum())
    trips: list[Trip] = []
    if len(alive) >= MIN_POINTS:
        cuts = np.flatnonzero(np.diff(ts[alive]) > gap_s) + 1
        bounds = [0, *cuts.tolist(), len(alive)]
        for a, b in zip(bounds[:-1], bounds[1:]):
            if b - a < MIN_POINTS:
                continue
            ii = alive[a:b]
            segs = _segment_chunk(lat[ii], lon[ii], ts[ii], {s: Dn[s][ii] for s in keep},
                                  {s: Pn[s][ii] for s in keep}, L)
            for i0, i1 in segs:
                seg = [obs[k] for k in ii[i0:i1 + 1]]
                trip = Trip(vehicle_id=vehicle_id, route_id=str(seg[0][10]) if len(seg[0]) > 10 else "",
                            direction_id=int(seg[0][5]), start_time=int(seg[0][0]))
                trip.points = [TripPoint(ts=o[0], lat=o[1], lon=o[2], speed=o[3], odo=o[4], frame_ts=o[8])
                               for o in seg]
                trips.append(trip)
    return (trips, st) if return_stats else trips
