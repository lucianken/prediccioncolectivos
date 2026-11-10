"""
Métricas de velocidad y contrafáctico de límite de velocidad.

Escribe un JSON con todos los números del informe + CSVs auxiliares.

Uso:
    python -m experiments.velocidades.metrics \
        --intervals experiments/velocidades/out/intervals.parquet \
        --outdir    experiments/velocidades/out
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

CAPS_KMH = [50, 40, 30, 25, 20]
EXCEED_GRID = list(range(0, 81, 2))

# Un viaje se considera completo/analizable si lo vimos de punta a punta.
MIN_TRIP_KM = 5.0
MIN_TRIP_MIN = 15.0

# Ratio odo/shape aceptable para considerar sano el odómetro de una unidad.
ODO_OK_RANGE = (0.90, 1.10)
ODO_MIN_SAMPLES = 100


def qc_odometer(iv: pd.DataFrame) -> pd.DataFrame:
    """
    El odómetro de la API es exacto en la mayoría de las unidades y está roto
    (pegado en 0, o contando de a saltos) en unas pocas. Devuelve el resumen
    por vehículo para poder filtrar y para reportar la tasa de unidades sanas.
    """
    s = iv[iv.ok_shape & iv.ok_odo & (iv.dist_shape_m > 200)]
    q = s.groupby("vid").agg(
        n=("dist_odo_m", "size"),
        ratio_med=("dist_odo_m", "median"),
        shape_med=("dist_shape_m", "median"),
        frac_cero=("dist_odo_m", lambda x: float((x == 0).mean())),
    )
    r = s.assign(r=s.dist_odo_m / s.dist_shape_m).groupby("vid").r.median()
    q["ratio_med"] = r
    q = q[q.n >= ODO_MIN_SAMPLES]
    q["sano"] = q.ratio_med.between(*ODO_OK_RANGE) & (q.frac_cero < 0.05)
    return q


def distance_method_comparison(iv: pd.DataFrame, odo_ok_vids: set[str]) -> dict:
    """Compara los tres estimadores de distancia sobre los mismos intervalos."""
    s = iv[iv.ok_shape & iv.ok_hav].copy()
    out = {}
    for name, col, mask in [
        ("haversine", "dist_hav_m", s.index),
        ("odometro_crudo", "dist_odo_m", s.index[s.ok_odo]),
        ("odometro_qc", "dist_odo_m", s.index[s.ok_odo & s.vid.isin(odo_ok_vids)]),
    ]:
        sub = s.loc[mask]
        tot_m = float(sub[col].sum())
        tot_ref = float(sub.dist_shape_m.sum())
        r = (sub[col] / sub.dist_shape_m)[sub.dist_shape_m > 100]
        out[name] = {
            "n_intervalos": int(len(sub)),
            "km_metodo": round(tot_m / 1000, 1),
            "km_shape_mismos_intervalos": round(tot_ref / 1000, 1),
            "sesgo_agregado_pct": round(100 * (tot_m / tot_ref - 1), 2),
            "ratio_p10": round(float(np.nanpercentile(r, 10)), 3),
            "ratio_mediana": round(float(np.nanmedian(r)), 3),
            "ratio_p90": round(float(np.nanpercentile(r, 90)), 3),
        }
    return out


def commercial_speed(iv: pd.DataFrame, dist_col: str, ok_col: str) -> pd.DataFrame:
    """
    Velocidad comercial = distancia total / tiempo total, incluyendo detenciones.
    Es el número que le importa al pasajero y el que se compara contra el límite.
    Se calcula como cociente de sumas (no promedio de velocidades) para que cada
    segundo pese igual.
    """
    s = iv[iv[ok_col]]
    g = s.groupby(["line", "is_weekday"])
    r = g.apply(
        lambda d: pd.Series(
            {
                "km": d[dist_col].sum() / 1000,
                "horas": d.dt_s.sum() / 3600,
                "v_comercial_kmh": d[dist_col].sum() / d.dt_s.sum() * 3.6,
                # Probabilidad de encontrar al bondi frenado en un instante
                # cualquiera. Ojo: NO es "% del tiempo detenido en paradas":
                # en esos mismos minutos el vehículo igual promedia ~12 km/h.
                "pct_muestras_frenado": 100
                * d.dt_s[d.speed_api_ms == 0].sum()
                / d.dt_s.sum(),
                "v_sin_frenadas_kmh": (
                    d[dist_col][d.speed_api_ms > 0].sum()
                    / d.dt_s[d.speed_api_ms > 0].sum()
                    * 3.6
                ),
                "n_intervalos": len(d),
            }
        ),
        include_groups=False,
    )
    return r.round(2)


def by_hour(iv: pd.DataFrame, dist_col: str, ok_col: str) -> pd.DataFrame:
    s = iv[iv[ok_col] & iv.is_weekday]
    g = s.groupby(["line", "hour"])
    return (
        g.apply(
            lambda d: pd.Series(
                {
                    "v_comercial_kmh": d[dist_col].sum() / d.dt_s.sum() * 3.6,
                    "pct_muestras_frenado": 100
                    * d.dt_s[d.speed_api_ms == 0].sum()
                    / d.dt_s.sum(),
                    "n": len(d),
                }
            ),
            include_groups=False,
        )
        .round(2)
        .reset_index()
    )


def spot_calibration(iv: pd.DataFrame) -> float:
    """
    Factor por el que la media de la lectura puntual queda por debajo de la
    velocidad que implica el desplazamiento observado (~1.11).

    NO se aplica por defecto. El desvío no parece un error de escala sino un
    exceso de ceros: en los minutos con lectura puntual 0 el bondi igual
    promedió ~12 km/h, o sea que el 0 es un instante de frenada dentro de un
    minuto en movimiento, no un minuto detenido. Si el sesgo vive en los ceros,
    multiplicar toda la distribución inflaría la cola alta sin fundamento.
    Se reporta como sensibilidad.
    """
    s = iv[iv.ok_shape]
    v_desp = s.dist_shape_m.sum() / s.dt_s.sum()
    v_spot = np.average(s.speed_api_ms, weights=s.dt_s)
    return float(v_desp / v_spot)


def exceedance(iv: pd.DataFrame, calib: float) -> pd.DataFrame:
    """
    Para cada umbral V: qué fracción del tiempo y de la distancia transcurre por
    encima de V, medida con dos instrumentos.

      spot  — lectura puntual de la API, calibrada. Muestreo uniforme en el
              tiempo ⇒ la fracción de muestras por encima de V estima sin sesgo
              la fracción de tiempo por encima de V. Capta los picos.
      medio — velocidad media del intervalo de ~60 s. Amortigua los picos, así
              que da una cota inferior de la exposición.
    """
    s = iv[iv.ok_shape].copy()
    s["v_spot"] = s.speed_api_ms * 3.6 * calib
    s["v_int"] = s.dist_shape_m / s.dt_s * 3.6
    rows = []
    T = s.dt_s.sum()
    D = s.dist_shape_m.sum()
    for v in EXCEED_GRID:
        m_spot = s.v_spot > v
        m_int = s.v_int > v
        rows.append(
            {
                "v_kmh": v,
                "pct_tiempo_spot": 100 * s.dt_s[m_spot].sum() / T,
                "pct_dist_spot": 100 * (s.v_spot * s.dt_s / 3.6)[m_spot].sum()
                / (s.v_spot * s.dt_s / 3.6).sum(),
                "pct_tiempo_medio": 100 * s.dt_s[m_int].sum() / T,
                "pct_dist_medio": 100 * s.dist_shape_m[m_int].sum() / D,
            }
        )
    return pd.DataFrame(rows).round(3)


def counterfactual(iv: pd.DataFrame, calib: float) -> pd.DataFrame:
    """
    Cuánto tiempo extra costaría un tope de velocidad Vcap, en el escenario más
    pesimista posible: se supone que TODO el exceso por encima del tope se paga
    íntegro, sin ninguna compensación (ni menos congestión, ni mejor
    coordinación semafórica, ni cambio de demanda). Es una cota superior del
    costo, no una predicción.

    Dos estimadores que acotan el resultado por arriba y por abajo:

      BAJO  — con la velocidad media del intervalo (~60 s). Si el bondi promedió
              25 km/h en el minuto, un tope de 30 no le hace nada, aunque haya
              tocado 45 durante 10 segundos. Subestima.
      ALTO  — con la lectura puntual calibrada, suponiendo que esa velocidad se
              sostuvo el intervalo entero. Sobreestima por construcción.

    El costo real está entre los dos.
    """
    s = iv[iv.ok_shape].copy()
    s["v_spot"] = s.speed_api_ms * 3.6 * calib
    s["v_int"] = s.dist_shape_m / s.dt_s * 3.6

    T_total = s.dt_s.sum()
    rows = []
    for cap in CAPS_KMH:
        # BAJO: el intervalo entero viajó a v_int; si v_int > cap, se estira.
        m = s.v_int > cap
        extra_lo = (s.dist_shape_m[m] / (cap / 3.6) - s.dt_s[m]).sum()

        # ALTO: el intervalo entero viajó a v_spot sostenida.
        m2 = s.v_spot > cap
        extra_hi = (s.dt_s[m2] * (s.v_spot[m2] / cap - 1)).sum()

        rows.append(
            {
                "cap_kmh": cap,
                "pct_tiempo_sobre_cap_spot": round(100 * s.dt_s[m2].sum() / T_total, 2),
                "pct_tiempo_sobre_cap_medio": round(100 * s.dt_s[m].sum() / T_total, 2),
                "sobrecosto_bajo_pct": round(100 * extra_lo / T_total, 2),
                "sobrecosto_alto_pct": round(100 * extra_hi / T_total, 2),
            }
        )
    return pd.DataFrame(rows)


def per_trip(iv: pd.DataFrame, calib: float) -> pd.DataFrame:
    """Un viaje por fila: velocidad comercial, pico alcanzado y costo del tope."""
    s = iv[iv.ok_shape].copy()
    s["v_spot"] = s.speed_api_ms * 3.6 * calib
    s["v_int"] = s.dist_shape_m / s.dt_s * 3.6

    aggs = {
        "line": ("line", "first"),
        "date": ("date", "first"),
        "is_weekday": ("is_weekday", "first"),
        "hour": ("hour", "min"),
        "km": ("dist_shape_m", lambda x: x.sum() / 1000),
        "min": ("dt_s", lambda x: x.sum() / 60),
        "v_max_spot": ("v_spot", "max"),
        "v_max_int": ("v_int", "max"),
        "n": ("dt_s", "size"),
    }
    t = s.groupby("trip_key").agg(**aggs)
    t["v_comercial_kmh"] = t.km / (t["min"] / 60)

    for cap in CAPS_KMH:
        m = s.v_int > cap
        extra = (
            (s.dist_shape_m[m] / (cap / 3.6) - s.dt_s[m])
            .groupby(s.trip_key[m])
            .sum()
        )
        t[f"extra_s_cap{cap}_bajo"] = extra.reindex(t.index).fillna(0)

        m2 = s.v_spot > cap
        extra2 = (
            (s.dt_s[m2] * (s.v_spot[m2] / cap - 1)).groupby(s.trip_key[m2]).sum()
        )
        t[f"extra_s_cap{cap}_alto"] = extra2.reindex(t.index).fillna(0)

    t["completo"] = (t.km >= MIN_TRIP_KM) & (t["min"] >= MIN_TRIP_MIN)
    return t


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--intervals", type=Path, required=True)
    ap.add_argument("--outdir", type=Path, required=True)
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    iv = pd.read_parquet(args.intervals)
    # Baseline sin calibrar (ver spot_calibration): el estimador ALTO ya es
    # generoso por suponer la velocidad puntual sostenida un minuto entero.
    calib = 1.0
    calib_sens = spot_calibration(iv)

    odo_q = qc_odometer(iv)
    odo_ok = set(odo_q.index[odo_q.sano])

    res: dict = {
        "cobertura": {
            "dias": sorted(iv.date.unique().tolist()),
            "lineas": sorted(iv.line.unique().tolist()),
            "vehiculos": int(iv.vid.nunique()),
            "viajes": int(iv.trip_key.nunique()),
            "intervalos": int(len(iv)),
            "horas_bondi": round(float(iv.dt_s.sum() / 3600), 1),
            "km_recorridos": round(float(iv.dist_shape_m[iv.ok_shape].sum() / 1000), 1),
        },
        "odometro_qc": {
            "vehiculos_evaluados": int(len(odo_q)),
            "pct_unidades_sanas": round(100 * float(odo_q.sano.mean()), 1),
            "ratio_mediana_unidades_sanas": round(
                float(odo_q.ratio_med[odo_q.sano].median()), 4
            ),
        },
        "comparacion_distancias": distance_method_comparison(iv, odo_ok),
        "factor_calibracion_spot_no_aplicado": round(calib_sens, 4),
    }

    com = commercial_speed(iv, "dist_shape_m", "ok_shape")
    com_hav = commercial_speed(iv, "dist_hav_m", "ok_hav")
    res["velocidad_comercial_shape"] = json.loads(
        com.reset_index().to_json(orient="records")
    )
    res["velocidad_comercial_haversine"] = json.loads(
        com_hav.reset_index().to_json(orient="records")
    )

    exc = exceedance(iv, calib)
    cf = counterfactual(iv, calib)
    trips = per_trip(iv, calib)
    tc = trips[trips.completo]

    res["excedencia"] = json.loads(exc.to_json(orient="records"))
    res["contrafactico_global"] = json.loads(cf.to_json(orient="records"))

    # Sensibilidad: qué pasa si el desvío de la lectura puntual fuera de escala
    # y no de exceso de ceros. Cota superior de la cota superior.
    res["contrafactico_sensibilidad_spot_calibrado"] = json.loads(
        counterfactual(iv, calib_sens).to_json(orient="records")
    )

    # Excedencia por línea, y para la 42 excluyendo Cantilo/Lugones, donde un
    # límite urbano de 30 no aplicaría.
    por_linea = {}
    for line in sorted(iv.line.unique()):
        sub = iv[iv.line == line]
        por_linea[line] = json.loads(exceedance(sub, calib).to_json(orient="records"))
    sub42 = iv[(iv.line == "42") & ~iv.autopista]
    por_linea["42_sin_autopista"] = json.loads(
        exceedance(sub42, calib).to_json(orient="records")
    )
    res["excedencia_por_linea"] = por_linea

    res["contrafactico_por_viaje"] = {
        "n_viajes_completos": int(len(tc)),
        "duracion_mediana_min": round(float(tc["min"].median()), 1),
        "largo_mediano_km": round(float(tc.km.median()), 1),
        "v_comercial_mediana_kmh": round(float(tc.v_comercial_kmh.median()), 2),
        "por_cap": [
            {
                "cap_kmh": cap,
                "extra_s_mediana_bajo": round(float(tc[f"extra_s_cap{cap}_bajo"].median()), 1),
                "extra_s_media_bajo": round(float(tc[f"extra_s_cap{cap}_bajo"].mean()), 1),
                "extra_s_media_alto": round(float(tc[f"extra_s_cap{cap}_alto"].mean()), 1),
                "extra_pct_media_alto": round(
                    float(100 * tc[f"extra_s_cap{cap}_alto"].mean() / (tc["min"].mean() * 60)), 2
                ),
                "pct_viajes_sin_efecto_bajo": round(
                    float(100 * (tc[f"extra_s_cap{cap}_bajo"] < 1).mean()), 1
                ),
            }
            for cap in CAPS_KMH
        ],
    }

    # La 42 usa Cantilo/Lugones, donde el límite urbano no aplicaría.
    a42 = iv[(iv.line == "42") & iv.ok_shape]
    res["linea_42_autopista"] = {
        "pct_tiempo_en_autopista": round(
            100 * float(a42.dt_s[a42.autopista].sum() / a42.dt_s.sum()), 2
        ),
        "v_comercial_con_autopista": round(
            float(a42.dist_shape_m.sum() / a42.dt_s.sum() * 3.6), 2
        ),
        "v_comercial_sin_autopista": round(
            float(
                a42.dist_shape_m[~a42.autopista].sum()
                / a42.dt_s[~a42.autopista].sum()
                * 3.6
            ),
            2,
        ),
    }

    exc.to_csv(args.outdir / "excedencia.csv", index=False)
    cf.to_csv(args.outdir / "contrafactico.csv", index=False)
    by_hour(iv, "dist_shape_m", "ok_shape").to_csv(args.outdir / "por_hora.csv", index=False)
    trips.to_csv(args.outdir / "viajes.csv")
    odo_q.to_csv(args.outdir / "odometro_qc.csv")

    with open(args.outdir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
