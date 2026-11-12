"""Muestreo de K pares (P, F) por viaje, estratificado por distancia (§4.2)."""

from __future__ import annotations

import zlib

import numpy as np

MIN_DIST_M = 100.0
# Buckets: [100,500) [500,1000) [1000,2000) [2000,5000) [5000,inf)
DIST_EDGES_M = (MIN_DIST_M, 500.0, 1000.0, 2000.0, 5000.0)
N_BUCKETS = len(DIST_EDGES_M)


def trip_seed(date: str, vehicle_id: str, start_ts: int) -> int:
    """Semilla determinística por viaje (independiente del orden de procesamiento)."""
    return zlib.crc32(f"{date}|{vehicle_id}|{int(start_ts)}".encode())


def _allocate(counts: list[int], k: int) -> list[int]:
    """Reparte k entre buckets de forma pareja; un bucket con menos candidatos cede el resto."""
    alloc = [0] * len(counts)
    remaining = k
    active = [i for i, c in enumerate(counts) if c > 0]
    while remaining > 0 and active:
        share = max(1, remaining // len(active))
        nxt = []
        for i in active:
            take = min(share, counts[i] - alloc[i], remaining)
            alloc[i] += take
            remaining -= take
            if alloc[i] < counts[i]:
                nxt.append(i)
            if remaining == 0:
                break
        active = nxt
    return alloc


def sample_pairs(
    dists: np.ndarray,
    ts: np.ndarray,
    k: int,
    seed: int,
    seg: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Elige hasta k pares (i, j), i<j, con dist[j]-dist[i] >= 100 m y ts[j] > ts[i].

    Estratificado por distancia restante en 5 buckets (100-500 m, 0,5-1, 1-2, 2-5, 5+ km):
    cada bucket aporta ~k/5; si uno tiene menos candidatos, el resto se reparte entre los demás.
    Si hay k candidatos o menos se devuelven todos. Determinístico dado (dists, ts, k, seed).
    seg (opcional, un id por punto): P y F tienen que tener el mismo id (mismo tramo continuo; un hueco de datos
    que no se unió separa tramos). Con seg=None el comportamiento es el de siempre.
    """
    n = len(dists)
    if n < 2 or k <= 0:
        return np.empty(0, np.int64), np.empty(0, np.int64)
    ii, jj = np.triu_indices(n, 1)
    d = dists[jj] - dists[ii]
    ok = (d >= MIN_DIST_M) & (ts[jj] > ts[ii])
    if seg is not None:
        ok &= seg[jj] == seg[ii]
    ii, jj, d = ii[ok], jj[ok], d[ok]
    m = len(ii)
    if m == 0:
        return np.empty(0, np.int64), np.empty(0, np.int64)
    if m <= k:
        return ii.astype(np.int64), jj.astype(np.int64)

    bucket = np.searchsorted(np.asarray(DIST_EDGES_M[1:]), d, side="right")  # 0..4
    members = [np.flatnonzero(bucket == b) for b in range(N_BUCKETS)]
    alloc = _allocate([len(x) for x in members], k)
    rng = np.random.default_rng(seed)
    chosen = []
    for b in range(N_BUCKETS):
        if alloc[b] > 0:
            chosen.append(rng.choice(members[b], size=alloc[b], replace=False))
    sel = np.sort(np.concatenate(chosen))
    return ii[sel].astype(np.int64), jj[sel].astype(np.int64)
