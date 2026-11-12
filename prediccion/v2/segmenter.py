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
from dataclasses import dataclass, field

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

# ── Segmentador versión 2 (ARQUITECTURA.md §6.2 paso 5). Solo se activa con segmenter_version=2; la versión 1
# (default) no cambia. Las cotas de unión de huecos salen de los datos (ver ARQUITECTURA §7, validación paso 5).
HEAD_ZONE_M = 300.0        # zona de cabecera: primeros metros del recorrido
HEAD_SUSTAIN_N = 3         # pings seguidos fuera de la zona para dar la salida por "sostenida"
HEAD_SUSTAIN_SLACK_M = 50.0
HEAD_BAD_MAX = 3           # pings inválidos (fuera de recorrido) tolerados dentro de la zona de espera
END_STOP_S = 120           # quieto este tiempo cerca del final del recorrido: el viaje terminó al llegar
JOIN_VMIN_MPS = 1.4        # velocidad implícita mínima para unir un hueco (~5 km/h)
JOIN_VMAX_MPS = 60 / 3.6   # y máxima (~60 km/h)
JOIN_BACK_M = 150.0        # retroceso tolerado (ruido GPS) al unir
JOIN_MAX_S = 3600          # hueco más largo que esto no se une (otro viaje)
JOIN_STILL_MAX_S = 900     # coche quieto durante el hueco (v < JOIN_VMIN) a mitad de recorrido: se une hasta esto
START_UNKNOWN_M = 1000.0   # un viaje que arranca a más de esto del inicio del recorrido tiene inicio desconocido


@dataclass
class TripV2(Trip):
    """Trip + metadatos del segmentador v2."""
    start_unknown: bool = False                 # arranca lejos del inicio del recorrido: time_since_start no es real
    joined_gaps: list = field(default_factory=list)   # [(ts_antes, ts_despues)] de los huecos que se unieron
    waiting: dict | None = None                 # espera en cabecera previa a la salida (no es parte del viaje)
    end_reason: str = ""                        # por qué terminó: gap | end | reverse | off | stop | data_end

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


def _segment_v2(lat, lon, ts, Dn: dict, Pn: dict, L: dict, gaps: list | None = None) -> list[dict]:
    """
    Segmentador v2 sobre TODA la secuencia de pings vivos de un coche (sin partirla por huecos).
    Devuelve [{"i0", "i1", "start_unknown", "wait": (wj, s, f) | None, "zone": [shape_id], "joined": [(ts, ts)]}]
    con índices inclusivos. Diferencias con _segment_chunk:
      A. un hueco > GAP_S se UNE si algún recorrido activo sigue ajustando y el avance es posible (ver JOIN_*);
         si no, el viaje se corta antes del hueco y el siguiente arranca después (start_unknown si arranca lejos).
      B. si el coche está en la zona de cabecera (primeros HEAD_ZONE_M de un recorrido), el viaje arranca en el
         último ping quieto antes de que salga de la zona y avance de forma sostenida; lo anterior es espera.
      C. cerca del final del recorrido, quieto >= END_STOP_S termina el viaje (no hay posiciones de espera final).
    gaps (opcional): se le agregan dicts {"dur", "joined", "adv", "v"} de cada hueco que cae dentro de un viaje.
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
    step_d = np.hypot(np.diff(x), np.diff(y))

    def zone_start(j):
        """(start, (wj, s, f), zone_shapes) si el coche está en cabecera en j y sale de la zona; si no, None."""
        Z = [s for s in keep if P[s][j] <= FIT_M and D[s][j] < HEAD_ZONE_M]
        if not Z:
            return None
        wj, bad, f, k = j, 0, None, j + 1
        while k < m:
            if ts[k] - ts[k - 1] > GAP_S:
                wj = k                                  # la espera se cuenta desde después del hueco
            inz = [s for s in Z if P[s][k] <= FIT_M and D[s][k] < HEAD_ZONE_M]
            if inz:
                bad = 0
                k += 1
                continue
            out = [s for s in Z if P[s][k] <= FIT_M and D[s][k] >= HEAD_ZONE_M
                   and all(D[s][q] >= HEAD_ZONE_M - HEAD_SUSTAIN_SLACK_M
                           for q in range(k, min(k + HEAD_SUSTAIN_N, m)))]
            if out:
                f = k
                break
            bad += 1
            if bad > HEAD_BAD_MAX or any(P[s][k] <= FIT_M for s in Z):
                return None                             # se fue a otro lado / volvió atrás
            k += 1
        if f is None:
            return None
        s_idx = wj
        for k in range(wj + 1, f):
            if step_d[k - 1] < STILL_M:
                s_idx = k
        return s_idx, (wj, s_idx, f), Z

    out: list[dict] = []
    i = 0
    while i < m - 1:
        j = i
        while j < m and not valid_any[j]:
            j += 1
        if j >= m - 1:
            break
        zs = zone_start(j)
        if zs is not None:
            start, wait, zone = zs
            if wait[1] <= wait[0]:
                wait = None
        else:
            wait, zone = None, []
            far = np.hypot(x[j + 1:] - x[j], y[j + 1:] - y[j]) > START_MOVE_M
            if not far.any():
                break
            start = j + int(np.argmax(far))
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
        start_unknown = min(st["d0"] for st in active.values()) > START_UNKNOWN_M

        best_prog = 0.0
        last_move = start
        cut_idx = None
        reason = ""
        next_i = None
        joined: list = []
        trip_gaps: list = []
        best_cut = (start, "off")           # el corte más avanzado de los recorridos que ya se descartaron

        def can_join(s, k):
            """(ok, avance, velocidad implícita) de seguir en el recorrido s en k desde su último ping válido."""
            lv = active[s]["lastv"]
            adv = D[s][k] - D[s][lv]
            dtt = ts[k] - ts[lv]
            v = max(adv, 0.0) / max(dtt, 1)
            mid = HEAD_ZONE_M <= D[s][lv] and D[s][k] <= L[s] - TERM_ZONE_M      # no en cabecera ni en el final
            moving_ok = JOIN_VMIN_MPS <= v <= JOIN_VMAX_MPS
            still_ok = v < JOIN_VMIN_MPS and mid and dtt <= JOIN_STILL_MAX_S
            ok = P[s][k] <= FIT_M and adv >= -JOIN_BACK_M and dtt <= JOIN_MAX_S and (moving_ok or still_ok)
            return ok, adv, v

        def last_valid():
            return max((st["lastv"] for st in active.values()), default=start)

        for k in range(start + 1, m):
            dt = ts[k] - ts[k - 1]
            if dt > GAP_S:
                okj, rec = [], []
                for s in active:
                    ok, adv, v = can_join(s, k)
                    rec.append((adv, v, D[s][active[s]["lastv"]], L[s]))
                    if ok:
                        okj.append(s)
                bi = max(range(len(rec)), key=lambda q: rec[q][0])
                trip_gaps.append({"kind": "gap", "dur": int(dt), "joined": bool(okj), "adv": float(rec[bi][0]),
                                  "v": float(rec[bi][1]), "d": float(rec[bi][2]), "L": float(rec[bi][3]),
                                  "ts": int(ts[k - 1])})
                if not okj:
                    cut_idx, next_i, reason = max(best_cut[0], last_valid()), k, "gap"
                    break
                lvs = [active[s]["lastv"] for s in okj]
                for s in list(active):
                    if s not in okj:
                        del active[s]
                    else:
                        active[s]["off"] = 0
                joined.append((int(ts[max(lvs)]), int(ts[k])))
                last_move = k
            if step_d[k - 1] >= STILL_M:
                last_move = k
            cut_here = []
            for s in list(active):
                st = active[s]
                if P[s][k] > FIT_M:
                    st["off"] += 1
                    continue
                if st["off"] >= OFF_N:
                    # volvió al recorrido tras una excursión fuera de él: se une si el avance es posible
                    ok, adv, v = can_join(s, k)
                    trip_gaps.append({"kind": "off", "dur": int(ts[k] - ts[st["lastv"]]), "joined": bool(ok),
                                      "adv": float(adv), "v": float(v), "d": float(D[s][st["lastv"]]),
                                      "L": float(L[s]), "ts": int(ts[st["lastv"]])})
                    if not ok:
                        cut_here.append((st["lastv"], "off"))
                        del active[s]
                        continue
                    joined.append((int(ts[st["lastv"]]), int(ts[k])))
                st["off"] = 0
                st["lastv"] = k
                d = D[s][k]
                if d > st["mx"]:
                    st["mx"], st["mxk"], st["rev"] = d, k, 0
                    best_prog = max(best_prog, d - st["d0"])
                elif d < st["mx"] - REV_M:
                    st["rev"] += 1
                    if st["rev"] >= REV_N:
                        cut_here.append((st["mxk"], "reverse"))
                        del active[s]
                        continue
                else:
                    st["rev"] = 0
                if d >= L[s] - END_TOL_M and st["mx"] - st["d0"] >= MIN_PROGRESS_M:
                    cut_here.append((k, "end"))
                    del active[s]
            # un recorrido lleva >= OFF_N pings fuera: se descarta como siempre, salvo que TODOS los activos estén
            # fuera a la vez (el coche se salió de la calle): ahí se espera, hasta JOIN_MAX_S, a que vuelva
            if active:
                any_valid_now = any(st["off"] == 0 for st in active.values())
                for s in list(active):
                    st = active[s]
                    if st["off"] >= OFF_N and (any_valid_now or ts[k] - ts[st["lastv"]] > JOIN_MAX_S):
                        cut_here.append((st["lastv"], "off"))
                        del active[s]
            if cut_here:
                best_cut = max(best_cut, max(cut_here))
            if not active:
                cut_idx, reason = best_cut if cut_here else (k, "off")
                break
            still_s = ts[k] - ts[last_move]
            if still_s >= END_STOP_S:
                near_end = best_prog >= MIN_PROGRESS_M and any(
                    Pn[s][k] <= FIT_M and Dn[s][k] > L[s] - TERM_ZONE_M for s in active)
                near_start = still_s >= STOP_S and any(
                    Pn[s][k] <= FIT_M and Dn[s][k] < TERM_ZONE_M for s in keep)
                if near_end or near_start:
                    cut_idx, reason = last_move, "stop"
                    break
        else:
            cut_idx, reason = max(best_cut[0], last_valid()), "data_end"
        e = max(int(cut_idx), start)
        if e - start + 1 >= MIN_POINTS and best_prog >= MIN_PROGRESS_M:
            if gaps is not None:
                gaps.extend(trip_gaps)          # solo los huecos de viajes que existen (no de fragmentos descartados)
            out.append({"i0": start, "i1": e, "start_unknown": bool(start_unknown), "wait": wait,
                        "zone": zone, "end_reason": reason, "joined": list(dict.fromkeys(g for g in joined if ts[start] <= g[0] and g[1] <= ts[e]))})
        i = next_i if next_i is not None else max(e, start + 1)
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
                      gap_s: int = GAP_S, return_stats: bool = False, segmenter_version: int = 1):
    """
    Segmenta los pings (ts estrictamente crecientes) de un vehículo en viajes geométricos.
    Los pings de depósito (quietos y lejos de todo recorrido) se descartan antes de segmentar.
    Con return_stats=True devuelve (trips, {"pings", "depot", "moving_valid", "moving_total"}) para métricas de
    calidad de recorrido sobre pings en movimiento.
    segmenter_version=1 (default): el segmentador de siempre. segmenter_version=2: une huecos coherentes, arranca el
    viaje al salir de la cabecera y marca start_unknown (ver _segment_v2); devuelve TripV2 y, con return_stats,
    además "gaps" (huecos dentro de viajes) y "waits" (esperas en cabecera).
    """
    n = len(obs)
    st = {"pings": n, "depot": 0, "moving_valid": 0, "moving_total": 0}
    v2 = segmenter_version == 2
    if v2:
        st["gaps"], st["waits"] = [], []
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
    if v2:
        if len(alive) >= MIN_POINTS:
            ii = alive
            segs = _segment_v2(lat[ii], lon[ii], ts[ii], {s: Dn[s][ii] for s in keep},
                               {s: Pn[s][ii] for s in keep}, L, st["gaps"])
            for sg in segs:
                seg = [obs[k] for k in ii[sg["i0"]:sg["i1"] + 1]]
                trip = TripV2(vehicle_id=vehicle_id, route_id=str(seg[0][10]) if len(seg[0]) > 10 else "",
                              direction_id=int(seg[0][5]), start_time=int(seg[0][0]),
                              start_unknown=sg["start_unknown"], joined_gaps=sg["joined"],
                              end_reason=sg["end_reason"])
                trip.points = [TripPoint(ts=o[0], lat=o[1], lon=o[2], speed=o[3], odo=o[4], frame_ts=o[8])
                               for o in seg]
                if sg["wait"] is not None:
                    wj, s_i, f_i = sg["wait"]
                    trip.waiting = {"start_ts": int(ts[ii[wj]]), "end_ts": int(ts[ii[s_i]]),
                                    "depart_ts": int(ts[ii[f_i]]), "n_pings": int(s_i - wj),
                                    "shape_candidates": list(sg["zone"])}
                    st["waits"].append((trip.waiting["end_ts"] - trip.waiting["start_ts"], int(s_i - wj)))
                trips.append(trip)
    elif len(alive) >= MIN_POINTS:
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
