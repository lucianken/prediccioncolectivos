"""Genera DENTRO_2MIN.md desde dentro_2min.json / dentro_2min_lineas.csv (salida de dentro_2min.py)."""
import json
from pathlib import Path
import pandas as pd
OUT = Path(__file__).resolve().parents[1] / "v4prod"
s = json.load(open(OUT / "dentro_2min.json")); R = pd.read_csv(OUT / "dentro_2min_lineas.csv", dtype={"line": str})
g = s["global"]; L = []
w = L.append
w("# Primer arribo anunciado dentro de ±2 min del primer paso real; caso (d) de la descomposición (replay v4)\n")
w("Medido el 2026-11-27 sobre los crudos de `data/ml/replay/v4prod/v4/` (modelo `path_v4_l1_s1`, 126 líneas habilitadas, 10 días, 40 paradas por línea, instantes cada 10 min, vara corregida). Sin volver a predecir. Código: `prediccion/replay/metrics.py` (`within_tol`), `data/ml/replay/porcoche/dentro_2min.py` (cálculo) y `dentro_2min_md.py` (este documento). Salidas: `dentro_2min.json`, `dentro_2min_lineas.csv`.\n")
w("## Definición\n")
w("- Instante = (línea, día, parada, t). Verdad = primer paso firme de cualquier coche que sirve la parada (`real_next2_s`), la misma de `next_bus(corrected=True)`; sin los instantes con paso previo no verificable. Banda = ETA real al primer paso en 3–7 min (180–420 s) o en 0–15 min.")
w("- Anunciado = primer arribo de la lista (`ann0_any_s`: 1.º de «viene» y, si no hay, 1.º de «puede venir» o provisional; hora común). «Dentro de ±tol» = |anunciado − real| ≤ tol.")
w("- Dos denominadores: **con anuncio** (como el MAE; los instantes sin ningún anuncio quedan fuera) y **total** (el instante sin anuncio cuenta como falla). Por defecto se cita «con anuncio».")
w("- Grupo por cantidad de shapes del export de v4 (= `backup_line_shapes_2026-11-26`; los `line_shapes` actuales cambiaron en la 132 y la 47 y no se usan).\n")
w("## Global y por cantidad de shapes\n")
w("| banda | grupo | líneas | instantes | ±60 s | ±120 s | ±180 s | ±120 s (total) |"); w("|---|---|---:|---:|---:|---:|---:|---:|")
for b in g:
    v = g[b]; w(f"| {b} | **todas** | {v['lineas']} | {v['n_con']:,} | {v['60_con']:.1f} % | **{v['120_con']:.1f} %** | {v['180_con']:.1f} % | {v['120_total']:.1f} % |")
    for k, v in s["grupo"][b].items():
        w(f"| {b} | {k} shapes | {v['lineas']} | {v['n_con']:,} | {v['60_con']:.1f} % | {v['120_con']:.1f} % | {v['180_con']:.1f} % | {v['120_total']:.1f} % |")
w("\nInstantes = con anuncio. Ponderado por instantes.\n")
c = s["casos"]
w("## Error por caso de la descomposición (banda 3–7 min)\n")
w("|caso| n | % | MAE (s) | mediana error abs. (s) | p75 | p90 | < 60 s | < 120 s | < 180 s |"); w("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
nm = {"a": "(a) el 1.º es el primero en llegar", "b": "(b) el 1.º ya había pasado", "c": "(c) el 1.º es bondi fantasma", "d": "(d) otro coche listado llega primero", "e": "(e) llega primero un coche no anunciado", "f": "(f) no verificable"}
for k, v in c.items():
    w(f"| {nm[k]} | {v['n']:,} | {v['pct']:.1f} | {v['mae']:.0f} | {v['med']:.0f} | {v['p75']:.0f} | {v['p90']:.0f} | {v['lt60']:.1f} % | {v['lt120']:.1f} % | {v['lt180']:.1f} % |")
d = s["d_resumen"]
w("\n## Caso (d): amontonados contra inversiones\n")
w("Separación = paso real del 1.º anunciado − paso real del primero que llega (≥ 0). Error propio = ETA anunciado del 1.º − paso real de ese mismo coche.\n")
w("| separación | n | % de (d) | % con error abs. < 120 s | mediana error abs. (s) | mediana error propio (s) |"); w("|---|---:|---:|---:|---:|---:|")
for k, v in s["d_sep"].items():
    w(f"| {k} | {v['n']:,} | {v['pct']:.1f} | {v['lt120']:.1f} % | {v['abs_med']:.0f} | {v['own_med']:.0f} |")
w(f"\n- (d) = {d['n']:,} instantes. |error| < 120 s en el **{d['err_lt120']:.1f} %**.")
w(f"- **Amontonados con error chico** (separación ≤ 120 s y |error| < 120 s): **{d['amontonado_err_chico']:.1f} %** de (d). Separación ≤ 120 s en total: {d['sep_le120']:.1f} % (de ellos con |error| ≥ 120 s: {d['sep_le120_err_grande']:.1f} % de (d), error propio del coche anunciado).")
w(f"- **Inversiones grandes** (el 1.º anunciado pasa más de 2 min después del primero real): {d['inversion_sep_gt120']:.1f} % de (d); más de 5 min: {d['inversion_sep_gt300']:.1f} %. Mediana de separación en (d): {d['sep_med']:.0f} s.")
w(f"- Error propio del coche anunciado: mediana {d['own_abs_med']:.0f} s, < 60 s en {d['own_lt60']:.1f} %.")
a = c["a"]
w(f"\nReferencia (a): el 1.º anunciado es el primero en llegar (separación 0 por definición); |error| mediano {a['med']:.0f} s, < 60 s en {a['lt60']:.1f} %, < 120 s en {a['lt120']:.1f} %, p90 {a['p90']:.0f} s. Lo que separa (d) de (a) en el piso del error: en (d) el 70 % ya está dentro de 2 min, pero el 18 % de (d) son inversiones de más de 10 min.\n")
w("## Por línea (banda 3–7 min, con anuncio)\n")
x = R[R.banda == "3-7 min"].merge(R[R.banda == "0-15 min"][["line", "dentro_120_con_pct"]], on="line", suffixes=("", "_015")).sort_values("dentro_120_con_pct")
w("| línea | shapes | instantes | ±60 s | ±120 s | ±180 s | ±120 s (0–15 min) |"); w("|---|---:|---:|---:|---:|---:|---:|")
for r in x.itertuples():
    w(f"| {r.line} | {int(r.shapes)} | {r.n_con:,} | {r.dentro_60_con_pct:.1f} | {r.dentro_120_con_pct:.1f} | {r.dentro_180_con_pct:.1f} | {r.dentro_120_con_pct_015:.1f} |")
w("\nOrdenada de menor a mayor ±120 s.\n")
w("## Salvedades\n")
w("- Mismos instantes y paradas muestreadas (40 por línea) que la descomposición; los porcentajes por línea con pocos instantes son ruidosos.")
w("- «Dentro de ±2 min» mide el anuncio del 1.º de la lista contra el primer paso real, no el error de ETA por coche (~54 s): incluye los casos (b)–(e), donde el anunciado es otro coche.")
w("- En (d), «amontonado» es una clasificación por separación entre pasos reales (≤ 120 s); no distingue si los coches van físicamente juntos o si el modelo los ordenó mal por poco.")
open(OUT / "DENTRO_2MIN.md", "w", encoding="utf8").write("\n".join(L) + "\n")
