#!/usr/bin/env python3
"""
Estadísticas del grabador de posiciones.

Uso:
  python stats.py               # resumen del estado actual
  python stats.py --detail      # incluye desglose por día
"""

import argparse
import gzip
import json
import os
import glob
from datetime import datetime, timezone, timedelta
from pathlib import Path

_default_data_dir = "/mnt/buffer/grabaciones" if os.path.isdir("/mnt/buffer/grabaciones") else "/data"
DATA_DIR = os.environ.get("DATA_DIR", _default_data_dir)
TZ_BA = timezone(timedelta(hours=-3))


def fmt_mb(b):
    return f"{b/1e6:.1f} MB"

def fmt_gb(b):
    return f"{b/1e9:.2f} GB"

def human_delta(seconds):
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds/60)}m"
    return f"{seconds/3600:.1f}h"


def analyze_file(path, full=False):
    """
    Lee un .ndjson.gz y retorna estadísticas.
    full=False: solo cuenta KF/deltas/gaps con búsqueda de substring (rápido).
    full=True:  parsea JSON completo para vehículos, bytes, timestamps (lento).
    """
    keyframes = 0
    deltas = 0
    gaps = 0

    if not full:
        with gzip.open(path, "rt") as f:
            for line in f:
                if '"gap": true' in line or '"gap":true' in line:
                    gaps += 1
                elif '"keyframe": true' in line or '"keyframe":true' in line:
                    keyframes += 1
                elif line.strip():
                    deltas += 1
        return {
            "keyframes": keyframes,
            "deltas": deltas,
            "gaps": gaps,
            "total_cycles": keyframes + deltas,
            "kf_bytes": 0, "delta_bytes": 0,
            "avg_kf_veh": 0, "avg_delta_upd": 0,
            "duration_s": 0, "first_ts": None, "last_ts": None,
        }

    kf_bytes = 0
    delta_bytes = 0
    vehicles_per_kf = []
    vehicles_per_delta = []
    last_ts = None
    first_ts = None

    with gzip.open(path, "rt") as f:
        for line in f:
            n = len(line)
            try:
                frame = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = frame.get("t", 0)
            if first_ts is None:
                first_ts = t
            last_ts = t
            if frame.get("gap"):
                gaps += 1
            elif frame.get("keyframe"):
                keyframes += 1
                kf_bytes += n
                vehicles_per_kf.append(len(frame.get("new", [])))
            else:
                deltas += 1
                delta_bytes += n
                vehicles_per_delta.append(len(frame.get("upd", [])) + len(frame.get("new", [])))

    duration_s = (last_ts - first_ts) if first_ts and last_ts else 0
    avg_kf_veh = int(sum(vehicles_per_kf) / len(vehicles_per_kf)) if vehicles_per_kf else 0
    avg_delta_upd = int(sum(vehicles_per_delta) / len(vehicles_per_delta)) if vehicles_per_delta else 0

    return {
        "keyframes": keyframes,
        "deltas": deltas,
        "gaps": gaps,
        "kf_bytes": kf_bytes,
        "delta_bytes": delta_bytes,
        "total_cycles": keyframes + deltas,
        "duration_s": duration_s,
        "avg_kf_veh": avg_kf_veh,
        "avg_delta_upd": avg_delta_upd,
        "first_ts": first_ts,
        "last_ts": last_ts,
    }


def check_container():
    """Verifica si el health file fue tocado recientemente."""
    health = Path(DATA_DIR) / "health"
    if not health.exists():
        return "DESCONOCIDO (no hay health file)"
    age = datetime.now().timestamp() - health.stat().st_mtime
    if age < 120:
        return f"OK (hace {human_delta(age)})"
    return f"ALERTA — health no actualizado hace {human_delta(age)}"


def check_state():
    """Lee state.json y retorna info del último ciclo persistido."""
    state_path = Path(DATA_DIR) / "state.json"
    if not state_path.exists():
        return None, None
    try:
        with open(state_path) as f:
            state = json.load(f)
        age = datetime.now().timestamp() - state_path.stat().st_mtime
        vehicles = state.get("vehicles", state)
        return len(vehicles), age
    except Exception:
        return None, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--detail", action="store_true", help="Desglose por día")
    args = parser.parse_args()

    files = sorted(glob.glob(os.path.join(DATA_DIR, "*.ndjson.gz")))
    if not files:
        print(f"No hay archivos .ndjson.gz en {DATA_DIR}")
        return

    now_ba = datetime.now(TZ_BA)
    today_str = now_ba.strftime("%Y-%m-%d")

    print("=" * 60)
    print(f"  GRABADOR DE POSICIONES — {now_ba.strftime('%Y-%m-%d %H:%M')} (BA)")
    print("=" * 60)

    # Estado del container
    print(f"\n[CONTAINER]")
    print(f"  Health:     {check_container()}")
    state_veh, state_age = check_state()
    if state_veh is not None:
        print(f"  State:      {state_veh} vehículos, actualizado hace {human_delta(state_age)}")

    # Espacio en disco
    try:
        stat = os.statvfs(DATA_DIR)
        free_gb = stat.f_bavail * stat.f_frsize / 1e9
        total_gb = stat.f_blocks * stat.f_frsize / 1e9
        print(f"\n[DISCO]")
        print(f"  Libre:      {free_gb:.1f} GB de {total_gb:.0f} GB ({free_gb/total_gb*100:.0f}% libre)")
    except Exception:
        pass

    # Archivos
    sizes = [os.path.getsize(f) for f in files]
    dates = [Path(f).stem.replace(".ndjson", "") for f in files]

    # Excluir primer día si tiene menos de 50 MB (arranque parcial)
    complete_files = [(f, s, d) for f, s, d in zip(files, sizes, dates) if s > 50e6]
    partial_note = len(files) - len(complete_files)

    total_bytes = sum(sizes)
    days_complete = len(complete_files)
    avg_bytes = sum(s for _, s, _ in complete_files) / days_complete if days_complete else 0

    print(f"\n[ALMACENAMIENTO]")
    print(f"  Días grabados:    {len(files)}" + (f"  ({partial_note} parcial excluido del promedio)" if partial_note else ""))
    print(f"  Total:            {fmt_mb(total_bytes)}  ({fmt_gb(total_bytes)})")
    print(f"  Promedio/día:     {fmt_mb(avg_bytes)}  (días completos)")
    print(f"  Proyección/mes:   {fmt_mb(avg_bytes*30)}  ({fmt_gb(avg_bytes*30)})")
    print(f"  Proyección/año:   {fmt_gb(avg_bytes*365)}")
    if sizes:
        min_i = sizes.index(min(sizes))
        max_i = sizes.index(max(sizes))
        print(f"  Mínimo/día:       {fmt_mb(sizes[min_i])}  ({dates[min_i]})")
        print(f"  Máximo/día:       {fmt_mb(sizes[max_i])}  ({dates[max_i]})")

    # Analizar el día de hoy
    today_file = next((f for f, d in zip(files, dates) if d == today_str), None)
    if today_file:
        print(f"\n[HOY — {today_str}]")
        st = analyze_file(today_file, full=True)
        file_mb = os.path.getsize(today_file) / 1e6
        raw_mb = (st["kf_bytes"] + st["delta_bytes"]) / 1e6
        ratio = raw_mb / file_mb if file_mb else 0
        pct_done = st["duration_s"] / 86400 * 100 if st["duration_s"] else 0
        print(f"  Ciclos:           {st['total_cycles']}  ({st['keyframes']} KF + {st['deltas']} deltas)")
        print(f"  Duración grabada: {human_delta(st['duration_s'])}  ({pct_done:.0f}% del día)")
        print(f"  Vehículos/KF:     ~{st['avg_kf_veh']}")
        print(f"  Updates/delta:    ~{st['avg_delta_upd']}")
        print(f"  Tamaño actual:    {file_mb:.1f} MB  (raw descomp: {raw_mb:.0f} MB, ratio {ratio:.1f}x)")
        if st["gaps"]:
            print(f"  Gaps:             {st['gaps']}")
        if pct_done > 0:
            projected_today = file_mb / (pct_done / 100)
            print(f"  Proyectado hoy:   {projected_today:.0f} MB")

    # Desglose por día
    if args.detail:
        print(f"\n[DESGLOSE POR DÍA]")
        print(f"  {'Fecha':<14} {'Tamaño':>10} {'Ciclos':>8} {'KF':>6} {'Deltas':>8} {'Gaps':>6}")
        print(f"  {'-'*14} {'-'*10} {'-'*8} {'-'*6} {'-'*8} {'-'*6}")
        for fpath, fsize, fdate in zip(files, sizes, dates):
            try:
                st = analyze_file(fpath, full=False)
                gap_str = str(st["gaps"]) if st["gaps"] else "-"
                print(f"  {fdate:<14} {fmt_mb(fsize):>10} {st['total_cycles']:>8} {st['keyframes']:>6} {st['deltas']:>8} {gap_str:>6}")
            except Exception as e:
                print(f"  {fdate:<14} {fmt_mb(fsize):>10}   (error: {e})")

    print()


if __name__ == "__main__":
    main()
