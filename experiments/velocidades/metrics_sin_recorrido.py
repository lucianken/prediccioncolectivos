"""
Métricas de velocidad SIN usar los recorridos, con los tres estimadores de
distancia disponibles para cualquier línea del país:

  odo_qc   delta de odómetro, excluyendo las unidades con el odómetro roto
  odo      delta de odómetro crudo, sin filtrar nada
  hav      cuerda haversine entre posiciones consecutivas

Lee los parquets diarios que deja run_month.py.

Uso:
    python -m experiments.velocidades.metrics_sin_recorrido \
        --indir  experiments/velocidades/out_caba_202607 \
        --outdir experiments/velocidades/out_caba_202607
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

CAPS_KMH = [50, 40, 30, 25, 20]
EXCEED_GRID = list(range(0, 81, 2))

MIN_TRIP_KM = 5.0
MIN_TRIP_MIN = 15.0

# ── Definición de "odómetro roto" ───────────────────────────────────────────
# Se juzga por VEHÍCULO sobre todo el período, no por muestra: un odómetro sano
# lo es siempre y uno roto lo es siempre. La referencia es la cuerda haversine,
# que no necesita recorrido. La cuerda subestima el camino real ~6 %, así que un
# odómetro sano tiene ratio Δodo/cuerda apenas por encima de 1.
ODO_MIN_INTERVALOS = 100      # menos que esto: no alcanza para juzgar
ODO_RATIO_BANDA = (0.95, 1.30)
ODO_MAX_FRAC_CERO = 0.05      # % de intervalos con Δodo=0 habiéndose movido
ODO_MOVIO_M = 100.0           # "se movió" según la cuerda


def qc_odometro(iv: pd.DataFrame) -> pd.DataFrame:
    """
    Diagnóstico por vehículo del odómetro, sin usar recorridos.

    Un vehículo se considera ROTO si cumple alguna de estas dos:

      pegado — más del 5 % de sus intervalos tienen Δodo exactamente 0 mientras
               la cuerda dice que se movió más de 100 m. Un odómetro sano nunca
               hace eso; los rotos suelen estar pegados en 0 casi siempre.

      escala — la mediana de Δodo / cuerda cae fuera de [0,95 – 1,30]. El valor
               esperado de un odómetro sano es ~1,05: el camino real es un poco
               más largo que la recta. Por debajo de 0,95 cuenta de menos (la
               distancia recorrida no puede ser menor que la recta entre los
               extremos, salvo error de medición); por encima de 1,30 infla.

    Los vehículos con menos de 100 intervalos válidos quedan SIN JUZGAR y se
    excluyen del método filtrado — es preferible perder cobertura a colar una
    unidad rota por falta de evidencia.
    """
    s = iv[iv.ok_odo & iv.ok_hav & (iv.dist_hav_m > ODO_MOVIO_M)]
    q = s.groupby("vid").agg(
        line=("line", "first"),
        n=("dist_odo_m", "size"),
        frac_cero=("dist_odo_m", lambda x: float((x == 0).mean())),
    )
    q["ratio_med"] = (s.dist_odo_m / s.dist_hav_m).groupby(s.vid).median()

    q["pegado"] = q.frac_cero > ODO_MAX_FRAC_CERO
    q["escala"] = ~q.ratio_med.between(*ODO_RATIO_BANDA)
    q["juzgable"] = q.n >= ODO_MIN_INTERVALOS
    q["sano"] = q.juzgable & ~q.pegado & ~q.escala
    return q


def _prep(iv: pd.DataFrame, metodo: str, vids_sanos: set[str]) -> pd.DataFrame:
    """Devuelve los intervalos válidos para un método, con columna `dist_m`."""
    if metodo == "hav":
        s = iv[iv.ok_hav]
        dist = s.dist_hav_m
    elif metodo == "odo":
        s = iv[iv.ok_odo]
        dist = s.dist_odo_m
    elif metodo == "odo_qc":
        s = iv[iv.ok_odo & iv.vid.isin(vids_sanos)]
        dist = s.dist_odo_m
    elif metodo == "shape":
        s = iv[iv.ok_shape]
        dist = s.dist_shape_m
    else:
        raise ValueError(metodo)
    out = s[["line", "vid", "trip_key", "dt_s", "speed_api_ms", "hour", "is_weekday"]].copy()
    out["dist_m"] = dist.to_numpy()
    return out


def resumen(s: pd.DataFrame) -> dict:
    """Velocidad comercial y exposición para un subconjunto ya preparado."""
    T = float(s.dt_s.sum())
    D = float(s.dist_m.sum())
    v_spot = s.speed_api_ms * 3.6
    return {
        "n_intervalos": int(len(s)),
        "n_vehiculos": int(s.vid.nunique()),
        "horas": round(T / 3600, 1),
        "km": round(D / 1000, 1),
        "v_comercial_kmh": round(D / T * 3.6, 2),
        "pct_muestras_frenado": round(100 * float(s.dt_s[v_spot == 0].sum()) / T, 1),
        "pct_tiempo_sobre_30_spot": round(100 * float(s.dt_s[v_spot > 30].sum()) / T, 2),
        "pct_tiempo_sobre_30_medio": round(
            100 * float(s.dt_s[s.dist_m / s.dt_s * 3.6 > 30].sum()) / T, 2
        ),
    }


def exceedance(s: pd.DataFrame) -> pd.DataFrame:
    T = float(s.dt_s.sum())
    v_spot = (s.speed_api_ms * 3.6).to_numpy()
    v_int = (s.dist_m / s.dt_s * 3.6).to_numpy()
    dt = s.dt_s.to_numpy()
    return pd.DataFrame(
        [
            {
                "v_kmh": v,
                "pct_tiempo_spot": 100 * dt[v_spot > v].sum() / T,
                "pct_tiempo_medio": 100 * dt[v_int > v].sum() / T,
            }
            for v in EXCEED_GRID
        ]
    ).round(3)


def counterfactual(s: pd.DataFrame) -> pd.DataFrame:
    """Cota superior del costo de un tope. Ver README §2 para la interpretación."""
    T = float(s.dt_s.sum())
    v_spot = (s.speed_api_ms * 3.6).to_numpy()
    v_int = (s.dist_m / s.dt_s * 3.6).to_numpy()
    dt = s.dt_s.to_numpy()
    dist = s.dist_m.to_numpy()
    rows = []
    for cap in CAPS_KMH:
        m = v_int > cap
        extra_lo = (dist[m] / (cap / 3.6) - dt[m]).sum()
        m2 = v_spot > cap
        extra_hi = (dt[m2] * (v_spot[m2] / cap - 1)).sum()
        rows.append(
            {
                "cap_kmh": cap,
                "pct_tiempo_sobre_cap_spot": round(100 * dt[m2].sum() / T, 2),
                "sobrecosto_bajo_pct": round(100 * extra_lo / T, 2),
                "sobrecosto_alto_pct": round(100 * extra_hi / T, 2),
            }
        )
    return pd.DataFrame(rows)


def por_linea(s: pd.DataFrame, cobertura: pd.Series | None = None) -> pd.DataFrame:
    g = s.groupby("line")
    r = pd.DataFrame(
        {
            "km": g.dist_m.sum() / 1000,
            "horas": g.dt_s.sum() / 3600,
            "v_comercial_kmh": g.dist_m.sum() / g.dt_s.sum() * 3.6,
            "n_vehiculos": g.vid.nunique(),
        }
    )
    sobre30 = s[s.speed_api_ms * 3.6 > 30].groupby("line").dt_s.sum()
    r["pct_tiempo_sobre_30"] = (100 * sobre30 / g.dt_s.sum()).fillna(0)
    if cobertura is not None:
        # Con poca cobertura de trip_id el resultado se apoya en una fracción
        # chica de la operación de esa línea: marcarlo, no corregirlo.
        r["pct_con_trip_id"] = cobertura.reindex(r.index)
        r["confianza"] = np.where(r.pct_con_trip_id < 50, "baja", "ok")
    return r.round(2).sort_values("v_comercial_kmh")


def por_viaje(s: pd.DataFrame) -> pd.DataFrame:
    t = s.groupby("trip_key").agg(
        line=("line", "first"),
        km=("dist_m", lambda x: x.sum() / 1000),
        minutos=("dt_s", lambda x: x.sum() / 60),
    )
    t["v_comercial_kmh"] = t.km / (t.minutos / 60)
    return t[(t.km >= MIN_TRIP_KM) & (t.minutos >= MIN_TRIP_MIN)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", type=Path, required=True)
    ap.add_argument("--outdir", type=Path, required=True)
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    files = sorted(args.indir.glob("iv_*.parquet"))
    cols = [
        "line", "vid", "trip_key", "date", "dt_s", "dist_hav_m", "dist_odo_m",
        "dist_shape_m", "ok_hav", "ok_odo", "ok_shape", "speed_api_ms",
        "hour", "is_weekday",
    ]
    iv = pd.concat([pd.read_parquet(f, columns=cols) for f in files], ignore_index=True)
    print(f"{len(iv):,} intervalos de {len(files)} días")

    cov_path = args.indir / "trip_id_coverage.csv"
    cobertura = None
    if cov_path.exists():
        cobertura = pd.read_csv(cov_path, dtype={"line": str}).set_index("line").pct_con_trip_id

    # Líneas que quedaron sin muestra utilizable: el operador no publica viajes,
    # así que el filtro de trip_id las borra enteras. Es un límite de cobertura
    # del dato, no un resultado. No se las mide sin el filtro: sin trip_id no se
    # puede separar el servicio de las horas paradas en cabecera o garage.
    presentes = set(iv.line.unique())
    from experiments.velocidades.lineas_caba import LINEAS_CABA
    sin_datos = [l for l in LINEAS_CABA if l not in presentes or (iv.line == l).sum() < 1000]
    if sin_datos:
        iv = iv[~iv.line.isin(sin_datos)]
        print(f"Líneas sin trip_id utilizable, excluidas: {sin_datos}")

    q = qc_odometro(iv)
    sanos = set(q.index[q.sano])
    q.to_csv(args.outdir / "odometro_qc.csv")

    res: dict = {
        "cobertura": {
            "dias": len(files),
            "lineas": int(iv.line.nunique()),
            "lineas_caba_sin_trip_id": sin_datos,
            "lineas_confianza_baja_trip_id_bajo_50pct": (
                sorted(cobertura.index[cobertura < 50].intersection(presentes), key=int)
                if cobertura is not None else None
            ),
            "vehiculos": int(iv.vid.nunique()),
            "viajes": int(iv.trip_key.nunique()),
            "intervalos": int(len(iv)),
        },
        "odometro_qc": {
            "vehiculos_con_datos": int(len(q)),
            "sin_evidencia_suficiente": int((~q.juzgable).sum()),
            "rotos_pegado_en_cero": int((q.juzgable & q.pegado).sum()),
            "rotos_escala": int((q.juzgable & ~q.pegado & q.escala).sum()),
            "sanos": int(q.sano.sum()),
            "pct_sanos_sobre_juzgables": round(
                100 * float(q.sano.sum()) / max(int(q.juzgable.sum()), 1), 1
            ),
            "ratio_mediano_sanos": round(float(q.ratio_med[q.sano].median()), 4),
        },
        "metodos": {},
    }

    for metodo in ("odo_qc", "hav", "odo"):
        s = _prep(iv, metodo, sanos)
        v = por_viaje(s)
        res["metodos"][metodo] = {
            **resumen(s),
            "n_viajes_completos": int(len(v)),
            "v_comercial_mediana_viaje_kmh": round(float(v.v_comercial_kmh.median()), 2),
            "contrafactico": json.loads(counterfactual(s).to_json(orient="records")),
        }
        exceedance(s).to_csv(args.outdir / f"excedencia_{metodo}.csv", index=False)
        por_linea(s, cobertura).to_csv(args.outdir / f"por_linea_{metodo}.csv")

    # Validación: en las 4 líneas con shape, contrastar contra la proyección.
    val = iv[iv.ok_shape]
    if len(val):
        res["validacion_con_shape"] = {
            "lineas": sorted(val.line.unique().tolist()),
            "v_comercial_shape": round(
                float(val.dist_shape_m.sum() / val.dt_s.sum() * 3.6), 2
            ),
        }
        for metodo in ("odo_qc", "hav", "odo"):
            sub = _prep(val, metodo, sanos)
            # mismos intervalos para los dos estimadores
            ref = val.loc[val.index.isin(sub.index), "dist_shape_m"].sum()
            res["validacion_con_shape"][metodo] = {
                "v_comercial": round(float(sub.dist_m.sum() / sub.dt_s.sum() * 3.6), 2),
                "sesgo_vs_shape_pct": round(100 * (float(sub.dist_m.sum()) / float(ref) - 1), 2),
                "cobertura_intervalos_pct": round(100 * len(sub) / len(val), 1),
            }

    with open(args.outdir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
