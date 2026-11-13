"""
Vara de medir única (ARQUITECTURA.md §5).

  python -m prediccion.eval --model a0               --set seen
  python -m prediccion.eval --model a0c:7            --set heldout
  python -m prediccion.eval --model a1:data/ml/v2/models/a1_v123.pkl --set seen
  python -m prediccion.eval --model a3:data/ml/v2/models/eta_a3_best.pt --set heldout
  (opcional: --lines 39 para filtrar líneas, --sdn <json> para fijar las medianas de schedule_dev)

Modelos:
  a0          naive: dist_remaining / max(speed_mps en P, v_floor)  (v_floor = 3 m/s)
  a0c[:v]     naive de velocidad constante (default 7 m/s, el "naive" histórico de 672 s)
  a1:<pkl>    A1Baseline; se consulta con la posición REAL de P (dist_along_m), no con 0 como evaluate_a1
  path:<pt>   PathETAModel (modelo por tramos, models/path_eta.py)
  a3:<pt>     A3ETAModel (checkpoint .pt del trainer). Sin flota (el v2 no la trae). d_model se infiere
              del checkpoint. schedule_dev_norm sale de --sdn (default: <ml_dir del checkpoint>/schedule_dev_medians.json,
              o el del v2 evaluado si no existe).

Escribe data/ml/v2/eval/<modelo>_<set>_<YYYYMMDD>.json y .md con métricas por bucket de ETA real y de
distancia: n, MAE, P50, P90 (del error absoluto), sesgo (pred - real; + = sobreestima) y % de
subestimaciones > 60 s (el usuario pierde el colectivo). El MAE global se informa pero no decide.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

from prediccion.v2.shapes import DEFAULT_V2_DIR

ETA_BUCKETS_S = [("0-5 min", 0.0, 300.0), ("5-10 min", 300.0, 600.0), ("10-20 min", 600.0, 1200.0),
                 ("20+ min", 1200.0, math.inf)]
DIST_BUCKETS_M = [("<500 m", 0.0, 500.0), ("0,5-2 km", 500.0, 2000.0), ("2-5 km", 2000.0, 5000.0),
                  ("5+ km", 5000.0, math.inf)]
UNDER_THRESHOLD_S = 60.0
# Distancia más fina (diagnóstico distancia/línea): 0-0,5, 0,5-1, 1-2, 2-3, 3-5, 5-8, 8-12, 12+ km
DIST_FINE_M = [("0-0,5 km", 0.0, 500.0), ("0,5-1 km", 500.0, 1000.0), ("1-2 km", 1000.0, 2000.0),
               ("2-3 km", 2000.0, 3000.0), ("3-5 km", 3000.0, 5000.0), ("5-8 km", 5000.0, 8000.0),
               ("8-12 km", 8000.0, 12000.0), ("12+ km", 12000.0, math.inf)]
# Desglose por fase del viaje (solo reporte; no cambia los números de la vara)
START_TIME_S = 300.0      # P en los primeros 5 min del viaje (time_since_start)...
START_DIST_M = 1000.0     # ...o a menos de 1 km del inicio del shape
STOPPED_MPS = 0.5         # P detenido: velocidad < 0,5 m/s
A0_V_FLOOR_MPS = 3.0


# ── métricas (puras) ─────────────────────────────────────────────────────────

def _stats(pred: np.ndarray, true: np.ndarray) -> dict:
    n = len(pred)
    if n == 0:
        return {"n": 0, "mae": None, "p50": None, "p90": None, "bias": None, "pct_under_60s": None,
                "pct_over_60s": None}
    err = pred - true                      # + = sobreestima
    ae = np.abs(err)
    return {
        "n": int(n),
        "mae": float(ae.mean()),
        "p50": float(np.percentile(ae, 50)),
        "p90": float(np.percentile(ae, 90)),
        "bias": float(err.mean()),
        "pct_under_60s": float(100.0 * np.mean((true - pred) > UNDER_THRESHOLD_S)),
        # sobreestima: pred - real > 60 s (el colectivo llega antes de lo predicho)
        "pct_over_60s": float(100.0 * np.mean((pred - true) > UNDER_THRESHOLD_S)),
    }


def compute_metrics(pred, true, dist, line=None) -> dict:
    """
    pred, true: ETA predicho / real en segundos; dist: distancia restante en metros.
    Retorna {"global": {...}, "by_eta": {label: {...}}, "by_dist": {label: {...}}}.
    Los buckets son [lo, hi): un ETA real de exactamente 300 s cae en 5-10 min.
    """
    pred = np.asarray(pred, dtype=np.float64)
    true = np.asarray(true, dtype=np.float64)
    dist = np.asarray(dist, dtype=np.float64)
    out = {"global": _stats(pred, true), "by_eta": {}, "by_dist": {}}
    for label, lo, hi in ETA_BUCKETS_S:
        m = (true >= lo) & (true < hi)
        out["by_eta"][label] = _stats(pred[m], true[m])
    for label, lo, hi in DIST_BUCKETS_M:
        m = (dist >= lo) & (dist < hi)
        out["by_dist"][label] = _stats(pred[m], true[m])
    out["by_dist_fine"] = {}
    for label, lo, hi in DIST_FINE_M:
        m = (dist >= lo) & (dist < hi)
        out["by_dist_fine"][label] = _stats(pred[m], true[m])
    if line is not None:
        line = np.asarray(line).astype(str)
        out["by_line"] = {}
        for ln in sorted(set(line.tolist()), key=lambda x: (len(x), x)):
            m = line == ln
            out["by_line"][ln] = _stats(pred[m], true[m])
    return out


def phase_masks(time_since_start, dist_along_m, speed_mps) -> tuple[np.ndarray, np.ndarray]:
    """(inicio_de_viaje, detenido) como máscaras booleanas por fila de eval."""
    tss = np.nan_to_num(np.asarray(time_since_start, dtype=np.float64), nan=np.inf)
    start = (tss < START_TIME_S) | (np.asarray(dist_along_m, dtype=np.float64) < START_DIST_M)
    stopped = np.asarray(speed_mps, dtype=np.float64) < STOPPED_MPS
    return start, stopped


def compute_phase_breakdown(pred, true, start, stopped) -> dict:
    """
    Error por fase del viaje: (a) inicio de viaje vs resto, (b) P detenido vs en movimiento, el cruce de ambos y
    el global SIN las filas de inicio de viaje (cuánto baja el error medio si se las excluye).
    """
    pred = np.asarray(pred, dtype=np.float64)
    true = np.asarray(true, dtype=np.float64)
    start = np.asarray(start, dtype=bool)
    stopped = np.asarray(stopped, dtype=bool)
    sel = {
        "inicio de viaje": start, "resto del viaje": ~start,
        "P detenido": stopped, "P en movimiento": ~stopped,
        "inicio y detenido": start & stopped, "inicio y en movimiento": start & ~stopped,
        "resto y detenido": ~start & stopped, "resto y en movimiento": ~start & ~stopped,
        "global": np.ones(len(pred), bool), "global sin inicio de viaje": ~start,
    }
    return {k: _stats(pred[m], true[m]) for k, m in sel.items()}


def compute_start_unknown_breakdown(pred, true, start_unknown) -> dict:
    """Error según si el inicio del viaje es conocido (v2b: start_unknown / time_since_start NaN) o no."""
    pred = np.asarray(pred, dtype=np.float64)
    true = np.asarray(true, dtype=np.float64)
    su = np.asarray(start_unknown, dtype=bool)
    return {"inicio desconocido": _stats(pred[su], true[su]), "inicio conocido": _stats(pred[~su], true[~su])}


def start_unknown_to_markdown(d: dict) -> str:
    rows = ["**Por inicio del viaje conocido / desconocido** (v2b: `start_unknown`)", "",
            "| inicio | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) | sobreest. >60 s (%) |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for label, s_ in d.items():
        rows.append(f"| {label} | {s_['n']} | {_fmt(s_['mae'])} | {_fmt(s_['p50'])} | {_fmt(s_['p90'])} | "
                    f"{_fmt(s_['bias'])} | {_fmt(s_['pct_under_60s'])} | {_fmt(s_.get('pct_over_60s'))} |")
    return "\n".join(rows) + "\n"


def phase_to_markdown(phase: dict) -> str:
    hdr = "| fase | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) | sobreest. >60 s (%) |"
    rows = ["**Por fase del viaje** (inicio = primeros 5 min o <1 km del inicio del shape; detenido = <0,5 m/s)", "",
            hdr, "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for label, s_ in phase.items():
        rows.append(f"| {label} | {s_['n']} | {_fmt(s_['mae'])} | {_fmt(s_['p50'])} | {_fmt(s_['p90'])} | "
                    f"{_fmt(s_['bias'])} | {_fmt(s_['pct_under_60s'])} | {_fmt(s_.get('pct_over_60s'))} |")
    return "\n".join(rows) + "\n"


def _fmt(v, nd=1):
    return "-" if v is None else f"{v:.{nd}f}"


def metrics_to_markdown(title: str, metrics: dict) -> str:
    lines = [f"### {title}", ""]
    hdr = "| bucket | n | MAE (s) | P50 (s) | P90 (s) | sesgo (s) | subest. >60 s (%) | sobreest. >60 s (%) |"
    sep = "|---|---:|---:|---:|---:|---:|---:|---:|"

    def block(name, d):
        rows = [f"**{name}**", "", hdr, sep]
        for label, s in d.items():
            rows.append(f"| {label} | {s['n']} | {_fmt(s['mae'])} | {_fmt(s['p50'])} | {_fmt(s['p90'])} | "
                        f"{_fmt(s['bias'])} | {_fmt(s['pct_under_60s'])} | {_fmt(s.get('pct_over_60s'))} |")
        return rows + [""]

    g = metrics["global"]
    lines += block("Global (informativo, no decide)", {"global": g})
    lines += block("Por ETA real", metrics["by_eta"])
    lines += block("Por distancia restante", metrics["by_dist"])
    if "by_dist_fine" in metrics:
        lines += block("Por distancia restante (fina)", metrics["by_dist_fine"])
    if "by_line" in metrics:
        lines += block("Por línea", metrics["by_line"])
    return "\n".join(lines)


# ── predictores ──────────────────────────────────────────────────────────────

def predict_a0(df, v_floor: float = A0_V_FLOOR_MPS) -> np.ndarray:
    v = np.maximum(df["speed_mps"].to_numpy(np.float64), v_floor)
    return df["dist_remaining_m"].to_numpy(np.float64) / v


def predict_a0_const(df, v: float = 7.0) -> np.ndarray:
    return df["dist_remaining_m"].to_numpy(np.float64) / v


def _hours(df) -> np.ndarray:
    hs = df["hour_sin"].to_numpy(np.float64)
    hc = df["hour_cos"].to_numpy(np.float64)
    return np.round(np.arctan2(hs, hc) * 24.0 / (2 * math.pi)).astype(int) % 24


def predict_a1(df, model) -> np.ndarray:
    hours = _hours(df)
    dows = df["dow"].to_numpy().astype(int)
    rid = df["ramal_id"].tolist()
    d0 = df["dist_along_m"].to_numpy(np.float64)
    d1 = d0 + df["dist_remaining_m"].to_numpy(np.float64)
    out = np.empty(len(df), dtype=np.float64)
    for i in range(len(df)):
        out[i] = model.predict_direct(rid[i], float(d0[i]), float(d1[i]), int(hours[i]), int(dows[i]))[0]
    return out


def predict_a3(parquet_path: Path, ckpt_path: Path, shape_lengths: dict, sdn_path: Path | None,
               n_expected: int, batch_size: int = 4096, device: str | None = None) -> np.ndarray:
    """
    Corre A3ETAModel sobre el eval parquet (usa ETADataset, así la normalización es idéntica a la del
    entrenamiento). El eval parquet viene prefiltrado con el mismo filtro que ETADataset, de modo que las
    filas salen en el mismo orden y en la misma cantidad; se verifica.
    """
    import torch
    from torch.utils.data import DataLoader
    from prediccion.models.a3_eta import A3ETAModel
    from prediccion.models.eta_dataset import ETADataset, collate_identity

    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    sd = ckpt["model_state_dict"] if isinstance(ckpt, dict) and "model_state_dict" in ckpt else ckpt
    d_model = int(sd["trajectory_enc.input_proj.weight"].shape[0])
    city_grid = "city_grid.embed.weight" in sd          # E1c: se infiere del checkpoint
    # v2b: la entrada start_unknown agrega 1 a la primera capa del MLP; se infiere del checkpoint (los viejos no la tienen)
    base_in = A3ETAModel(d_model=d_model, city_grid=city_grid).mlp[0].in_features
    start_unknown = int(sd["mlp.0.weight"].shape[1]) == base_in + 1
    model = A3ETAModel(d_model=d_model, city_grid=city_grid, start_unknown=start_unknown)
    model.load_state_dict(sd)
    model.to(device).eval()

    ds = ETADataset(parquet_path, shape_lengths=shape_lengths, shuffle=False, yield_batch_size=batch_size,
                    use_fleet=False, schedule_dev_medians=str(sdn_path) if sdn_path else None,
                    use_geo=city_grid)
    loader = DataLoader(ds, batch_size=1, shuffle=False, collate_fn=collate_identity, num_workers=0)
    preds = []
    with torch.no_grad():
        for b in loader:
            g = lambda k: b[k].to(device)  # noqa: E731
            p = model(g("trajectory"), g("trajectory_mask"), g("fleet"), g("fleet_mask"), g("hour_sin"),
                      g("hour_cos"), g("dow"), g("dist_remaining_norm"), g("time_since_start"), g("ts_age_s"),
                      g("has_active_bus"), g("schedule_dev_norm"), g("time_since_last_bus_s"),
                      g("last_bus_found"), g("geo") if city_grid else None,
                      g("start_unknown") if start_unknown else None)
            preds.append(p.squeeze(-1).cpu().numpy())
    pred = np.concatenate(preds).astype(np.float64) if preds else np.empty(0)
    if len(pred) != n_expected:
        raise RuntimeError(f"A3 predijo {len(pred)} filas pero el eval tiene {n_expected}: el parquet de eval "
                           "contiene filas que ETADataset descarta (regenerar con make_eval --force).")
    return pred


# ── CLI ──────────────────────────────────────────────────────────────────────

def load_eval_df(path: Path):
    import pyarrow.parquet as pq
    cols = ["line", "ramal_id", "dist_along_m", "dist_remaining_m", "speed_mps", "hour_sin", "hour_cos", "dow",
            "observed_eta_s", "time_since_start"]
    if "start_unknown" in pq.ParquetFile(str(path)).schema_arrow.names:      # v2b
        cols = cols + ["start_unknown"]
    return pq.read_table(path, columns=cols).to_pandas()


def _model_name(spec: str) -> str:
    kind, _, arg = spec.partition(":")
    if kind in ("a1", "a3", "path"):
        return f"{kind}_{Path(arg).stem}"
    return kind if not arg else f"{kind}{arg}"


def run_eval(model_spec: str, which: str, v2_dir: Path, lines: list[str] | None = None,
             sdn: Path | None = None, out_dir: Path | None = None, eval_path: Path | None = None,
             v_floor: float = A0_V_FLOOR_MPS, tag: str | None = None, save_preds: bool = False) -> dict:
    v2_dir = Path(v2_dir)
    path = eval_path or (v2_dir / "eval" / f"eval_{which}.parquet")
    out_dir = Path(out_dir or v2_dir / "eval")
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_filtered = None
    if lines:
        # subconjunto por línea: parquet temporal, así todos los modelos (incluido a3) ven las mismas filas
        import pyarrow as pa
        import pyarrow.compute as pc
        import pyarrow.parquet as pq
        t = pq.read_table(path)
        t = t.filter(pc.is_in(t["line"], value_set=pa.array([str(x) for x in lines])))
        tmp_filtered = out_dir / f"_tmp_eval_{which}_{'-'.join(lines)}.parquet"
        pq.write_table(t, str(tmp_filtered), row_group_size=100_000)
        path = tmp_filtered
    df = load_eval_df(path)
    keep = np.ones(len(df), bool)
    kind, _, arg = model_spec.partition(":")
    t0 = time.time()
    sub_path = path

    if kind == "a0":
        pred = predict_a0(df, v_floor)
    elif kind == "a0c":
        pred = predict_a0_const(df, float(arg) if arg else 7.0)
    elif kind == "a1":
        from prediccion.models.a1_baseline import A1Baseline
        pred = predict_a1(df, A1Baseline.load(arg))
    elif kind == "path":
        from prediccion.models.path_eta import predict_path
        pred = predict_path(path, Path(arg), len(df))
    elif kind == "a3":
        lengths_p = v2_dir / "shape_lengths.json"
        with open(lengths_p, encoding="utf-8") as f:
            lengths = json.load(f)
        # medianas de schedule_dev con las que se entrenó el checkpoint: <ml_dir>/schedule_dev_medians.json
        # (ckpt en <ml_dir>/models/*.pt); si no están, las del v2 evaluado
        sibling = Path(arg).resolve().parent.parent / "schedule_dev_medians.json"
        sdn_path = sdn or (sibling if sibling.exists() else v2_dir / "schedule_dev_medians.json")
        pred = predict_a3(path, Path(arg), lengths, sdn_path if Path(sdn_path).exists() else None, len(df))
    else:
        raise SystemExit(f"modelo desconocido: {model_spec} (a0 | a0c[:v] | a1:<pkl> | a3:<pt> | path:<pt>)")

    true = df["observed_eta_s"].to_numpy(np.float64)
    dist = df["dist_remaining_m"].to_numpy(np.float64)
    m = compute_metrics(pred[keep], true[keep], dist[keep], df["line"].to_numpy()[keep])
    start, stopped = phase_masks(df["time_since_start"], df["dist_along_m"], df["speed_mps"])
    result_phase = compute_phase_breakdown(pred[keep], true[keep], start[keep], stopped[keep])
    su_mask = np.isnan(df["time_since_start"].to_numpy(np.float64))
    if "start_unknown" in df:
        su_mask = su_mask | df["start_unknown"].to_numpy().astype(bool)
    result_su = compute_start_unknown_breakdown(pred[keep], true[keep], su_mask[keep]) if su_mask.any() or "start_unknown" in df else None
    result = {"model": model_spec, "set": which, "eval_file": str(sub_path), "lines": lines,
              "n": int(keep.sum()), "elapsed_s": round(time.time() - t0, 1),
              "date": time.strftime("%Y-%m-%d"), "metrics": m, "phase": result_phase,
              "by_start_unknown": result_su}
    if tmp_filtered is not None:
        tmp_filtered.unlink(missing_ok=True)
    result["eval_file"] = str(eval_path or (v2_dir / "eval" / f"eval_{which}.parquet"))
    stem = f"{_model_name(model_spec)}_{which}_{time.strftime('%Y%m%d')}" + ((("_" + tag) if tag else "_L" + "-".join(lines)) if lines else "")
    with open(out_dir / f"{stem}.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)
    md = metrics_to_markdown(f"{model_spec} sobre eval_{which} (n={result['n']})", m)
    md = md + "\n\n" + phase_to_markdown(result_phase)
    if result_su is not None:
        md = md + "\n" + start_unknown_to_markdown(result_su)
    (out_dir / f"{stem}.md").write_text(md + "\n", encoding="utf-8")
    if save_preds:   # predicciones por fila (mismo orden que el parquet de eval) para diagnósticos posteriores
        np.save(out_dir / f"{stem}.pred.npy", pred.astype(np.float32))
    result["json_path"] = str(out_dir / f"{stem}.json")
    result["markdown"] = md
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--set", dest="which", choices=["seen", "heldout"], required=True)
    ap.add_argument("--v2-dir", type=Path, default=DEFAULT_V2_DIR)
    ap.add_argument("--lines", default=None, help="filtrar líneas (coma), p.ej. 39")
    ap.add_argument("--tag", default=None, help="sufijo del archivo de salida cuando se usa --lines (default: _L<lineas>)")
    ap.add_argument("--out-dir", type=Path, default=None, help="directorio de salida (default: <v2-dir>/eval)")
    ap.add_argument("--sdn", type=Path, default=None, help="schedule_dev_medians.json a usar con a3")
    ap.add_argument("--save-preds", action="store_true", help="guarda <stem>.pred.npy con la predicción por fila")
    ap.add_argument("--v-floor", type=float, default=A0_V_FLOOR_MPS)
    a = ap.parse_args(argv)
    r = run_eval(a.model, a.which, a.v2_dir, a.lines.split(",") if a.lines else None, a.sdn, out_dir=a.out_dir, v_floor=a.v_floor, tag=a.tag, save_preds=a.save_preds)
    print(r["markdown"])
    print(f"\n-> {r['json_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
