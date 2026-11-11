"""
Lista final de líneas v2 (segunda tanda, decisiones del usuario) -> data/ml/v2/lines.json

Parte de la primera propuesta (data/ml/v2/lines_first_pass.json, hecha con segmentación por trip_id) y aplica:
  - las 27 líneas de CABA (experiments/velocidades/lineas_caba.py) quedan todas en el dataset;
  - se saca la 56 de train; en el control sale la 91 y entra la 65;
  - las 9 de CABA que pasaron el filtro y no estaban elegidas se reparten 5 train / 4 control;
  - las de CABA excluidas antes (sin trip_id / recorrido OSM parcial) van a train;
  - 124 y 151 se quedan en train.
Las métricas salen de la segmentación geométrica (data/ml/v2/line_metrics.json) y se comparan con las de la
primera tanda (line_metrics_old_segmentation.json).

  python -m prediccion.v2.lines_final
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from prediccion.v2.select_lines import CURRENT_LINES, _centroid, summarize
from prediccion.v2.shapes import DEFAULT_LINE_SHAPES_DIR, DEFAULT_V2_DIR, LineShapes

CABA_FILE = Path(__file__).resolve().parents[2] / "experiments" / "velocidades" / "lineas_caba.py"
DROP_FROM_TRAIN = {"56": "decisión del usuario: se saca de train"}
CONTROL_KEEP = ["1", "15", "21", "87", "100", "128", "181"]
CONTROL_SWAP_IN = {"65": "control (CABA): decisión del usuario; antes excluida por 'recorrido incompleto'"}
CONTROL_SWAP_OUT = {"91": "decisión del usuario: sale del control"}
_PARCIAL = "CABA con recorrido OSM parcial (10-20 % de pings a >150 m): se acepta perder esos puntos"
_SIN_TID = "CABA sin trip_id: ya no es motivo de exclusión (segmentación geométrica)"
FORCE_TRAIN_CABA = {"4": _SIN_TID, "25": _SIN_TID, "84": _SIN_TID,
                    "102": "CABA con trip_id parcial: ya no es motivo de exclusión (segmentación geométrica)",
                    "7": _PARCIAL, "44": _PARCIAL, "76": _PARCIAL, "115": _PARCIAL}
KEEP_TRAIN_FLAGGED = {"124": "actual, se mantiene por decisión del usuario",
                      "151": "actual, se mantiene por decisión del usuario"}
# Las 9 quedan todas en la zona "centro" por centroide, así que la zona no discrimina; se balancea por posición
# dentro de CABA, empresa (el control suma 4 empresas ausentes de train) y volumen. 108 y 109 son vecinas casi
# idénticas: una a cada lado. La 61 (~190 viajes/día) rinde más como dato de train que como control.
NINE_SPLIT = {
    "68": ("control", "norte de CABA (lat -34,575), empresa 39 ausente de train; ~1078 viajes/día"),
    "109": ("control", "oeste (lon -58,451), empresa 24 ausente de train; vecina de la 108 (train)"),
    "12": ("control", "microcentro-este, empresa 704 ausente de train; ~1006 viajes/día"),
    "64": ("control", "este (lon -58,396), empresa 41 ausente de train; ~590 viajes/día"),
    "34": ("train", "oeste-centro, empresa 36 ya presente en train; ~1057 viajes/día"),
    "61": ("train", "solo ~190 viajes/día: más útil como dato de train que como control"),
    "108": ("train", "vecina de la 109 (control); empresa 715"),
    "118": ("train", "este (lon -58,408), empresa 42; ~935 viajes/día"),
    "132": ("train", "centro-este, empresa 12; ~1093 viajes/día"),
}
FOCUS = ["7", "44", "65", "76", "115", "151"]


def caba_lines() -> list[str]:
    import importlib.util
    spec = importlib.util.spec_from_file_location("lineas_caba", CABA_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod.LINEAS_CABA)


def build(metrics_path: Path, old_metrics_path: Path, first_pass_path: Path, out_path: Path, shapes_dir) -> dict:
    first = json.loads(Path(first_pass_path).read_text(encoding="utf-8"))
    new = summarize(json.loads(Path(metrics_path).read_text(encoding="utf-8")))
    old = summarize(json.loads(Path(old_metrics_path).read_text(encoding="utf-8")))
    shapes = LineShapes(shapes_dir)
    caba = caba_lines()

    reasons: dict[str, str] = {}
    train = [l for l in first["train"] if l not in DROP_FROM_TRAIN]
    for l in train:
        reasons[l] = "actual" if l in CURRENT_LINES else "elegida por calidad y variedad geográfica (primera tanda)"
    reasons.update(KEEP_TRAIN_FLAGGED)
    for l, why in FORCE_TRAIN_CABA.items():
        train.append(l)
        reasons[l] = "train: " + why
    control = list(CONTROL_KEEP)
    for l in control:
        reasons[l] = "control (primera tanda)"
    for l, why in CONTROL_SWAP_IN.items():
        control.append(l)
        reasons[l] = why
    for l, (where, why) in NINE_SPLIT.items():
        (train if where == "train" else control).append(l)
        reasons[l] = f"{where} (CABA, pasó el filtro y no estaba elegida): {why}"
    train = sorted(set(train), key=int)
    control = sorted(set(control), key=int)
    assert not set(train) & set(control)

    def row(l):
        n, o = new[l], old.get(l)
        return {
            "split": "train" if l in train else "control", "caba": l in caba, "reason": reasons[l],
            "agencies": n["agencies"][:3], "centroid": [round(c, 4) for c in _centroid(shapes, l)],
            "trips_weekday": round(n["trips_weekday"]), "median_perp_m": round(n["median_perp_m"], 2),
            "frac_within_150_trips": round(n["frac_within_150"], 3),
            "frac_within_150_moving": round(n["frac_within_150_moving"], 3),
            "depot_frac": round(n["depot_frac"], 3),
            "frac_trips_perp_le_50": round(n["frac_trips_perp_le_50"], 3),
            "trip_id_cov_solo_informativo": round(n["trip_id_cov"], 2),
            "antes_segmentacion_trip_id": None if not o else {
                "trips_weekday": round(o["trips_weekday"]), "frac_within_150": round(o["frac_within_150"], 3),
                "frac_trips_perp_le_50": round(o["frac_trips_perp_le_50"], 3)},
        }

    metrics = {l: row(l) for l in train + control}
    depot_study = {l: {"antes": metrics[l]["antes_segmentacion_trip_id"],
                       "despues": {k: metrics[l][k] for k in ("frac_within_150_trips", "frac_within_150_moving",
                                                              "depot_frac", "frac_trips_perp_le_50", "trips_weekday")}}
                   for l in FOCUS}
    suspect = [l for l in train + control
               if metrics[l]["frac_within_150_moving"] < 0.93 or metrics[l]["frac_trips_perp_le_50"] < 0.90]
    out = {
        "train": train, "heldout": control, "n_train": len(train), "n_heldout": len(control),
        "caba_lines": caba, "caba_missing_from_dataset": [l for l in caba if l not in train + control],
        "criteria": {
            "segmentation": "geométrica (v2/segmenter.py): no usa trip_id, start_time ni route_id",
            "sample_days": ["2026-08-18", "2026-09-17", "2026-08-22"],
            "metric_definitions": {
                "frac_within_150_trips": "% de pings dentro de viajes segmentados a <=150 m del mejor recorrido",
                "frac_within_150_moving": "% de pings que no son de depósito (quietos y lejos de todo recorrido) a <=150 m de algún recorrido",
                "depot_frac": "% de pings descartados como depósito/garage/playa",
                "frac_trips_perp_le_50": "% de viajes geométricos con error perp. mediano <=50 m",
                "antes_segmentacion_trip_id": "métricas de la primera tanda (5 días, segmentación por trip_id, todos los pings, incluye depósito)"},
            "recorrido_incompleto": "El 10-20 % de pings fuera de 150 m de 7, 44, 65, 76, 115 y 151 era depósito/garage y "
                "traslados (los coches comparten depósito y se pasan unidades entre líneas), no un ramal faltante en OSM. "
                "Con pings en movimiento y viajes segmentados el ajuste sube a 0,91-0,98 (ver depot_study). "
                "Solo las de suspect_recorrido_con_pings_en_movimiento siguen por debajo de 0,93/0,90 y son candidatas a ramal faltante.",
            "nine_caba_split": {l: {"split": w, "why": y} for l, (w, y) in NINE_SPLIT.items()},
        },
        "depot_study": depot_study,
        "suspect_recorrido_con_pings_en_movimiento": suspect,
        "metrics": metrics,
        "dropped": {**DROP_FROM_TRAIN, **CONTROL_SWAP_OUT},
        "not_in_dataset_first_pass": {k: v for k, v in first.get("excluded", {}).items()
                                      if k.split(" ")[0] not in train + control},
    }
    Path(out_path).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metrics", type=Path, default=DEFAULT_V2_DIR / "line_metrics.json")
    ap.add_argument("--old-metrics", type=Path, default=DEFAULT_V2_DIR / "line_metrics_old_segmentation.json")
    ap.add_argument("--first-pass", type=Path, default=DEFAULT_V2_DIR / "lines_first_pass.json")
    ap.add_argument("--out", type=Path, default=DEFAULT_V2_DIR / "lines.json")
    ap.add_argument("--shapes-dir", type=Path, default=DEFAULT_LINE_SHAPES_DIR)
    a = ap.parse_args()
    o = build(a.metrics, a.old_metrics, a.first_pass, a.out, a.shapes_dir)
    print("train", o["n_train"], o["train"])
    print("control", o["n_heldout"], o["heldout"])
    print("CABA faltantes:", o["caba_missing_from_dataset"], "| sospechosas:", o["suspect_recorrido_con_pings_en_movimiento"])


if __name__ == "__main__":
    main()
