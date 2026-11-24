"""Arma data/ml/replay/v4prod/DESCOMPOSICION.md desde descomposicion_lineas.csv (salida de descomposicion.py).
Uso (desde prediccion colectivos/): python data/ml/replay/porcoche/descomposicion_md.py"""
import json, re, sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT / "data/ml/replay/v4prod"
PROY = ROOT.parent / "proyectoconsola"
CASES = ["a", "b", "c", "d", "e", "f"]


def model_mae():
    """MAE de la vara del modelo (banda 3-7 min): 46 lineas de eval v3 congelado (no_regresion.md, candidato v4),
    72 nuevas de eval v4 congelado (no_regresion.md), 8 habilitadas tarde + 164 de v4_eval_ext/resultados.csv (columnas mae, n)."""
    txt = (ROOT / "data/ml/v4_sub/runs/no_regresion.md").read_text(encoding="utf-8")
    out = {}
    sec = None
    for ln in txt.splitlines():
        if ln.startswith("## "):
            sec = "46" if ln.startswith("## Por l") else ("72" if ln.startswith("## Líneas nuevas") else None)
            continue
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if sec == "46" and re.fullmatch(r"\d+", c[0]) and len(c) >= 11:
            out[c[0]] = (float(c[2]), int(c[1]), "eval v3 (46)")
        elif sec == "72" and re.fullmatch(r"\d+", c[0]) and len(c) == 6 and c[5] == "habilitar":
            out[c[0]] = (float(c[2]), int(c[1]), "eval v4 (72)")
    ext = pd.read_csv(ROOT / "data/ml/v4_eval_ext/resultados.csv")
    for r in ext.itertuples():
        out[str(r.line)] = (float(r.mae), int(r.n), "eval ext (v4_eval_ext)")
    return out


def shapes():
    out = {}
    for p in (PROY / "data/line_shapes").glob("*.json"):
        if p.stem == "index":
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        rs = d["ramales"]
        names = {r["shortName"] for r in rs}   # ramal = shortName (cada uno con ida y vuelta = 2 shapes)
        out[p.stem] = (len(rs), len(names))
    return out


def f(x, d=0):
    return "—" if x is None or x != x else f"{x:.{d}f}"


def spearman(x, y):
    x, y = pd.Series(x), pd.Series(y)
    ok = x.notna() & y.notna()
    r = float(x[ok].rank().corr(y[ok].rank()))
    n = int(ok.sum())
    try:
        from scipy.stats import spearmanr
        p = float(spearmanr(x[ok], y[ok])[1])
    except Exception:
        p = float("nan")
    return r, p, n


df = pd.read_csv(OUT / "descomposicion_lineas.csv", dtype={"line": str})
enabled = [e["line"] for e in json.loads((PROY / "public/config/prediccion.json").read_text(encoding="utf-8"))["enabledLines"]]
MM, SH = model_mae(), shapes()
tab = pd.read_pickle(OUT / "resumen.pkl")["rows4"]

df["mae_prox"] = df.sum_abs / df.n_con
df["mae_coche"] = df.sum_coche / df.n_coche
df["sin_pct"] = 100 * df.n_sin / (df.n_con + df.n_sin)
df["mae_modelo"] = df.line.map(lambda l: MM.get(l, (np.nan,))[0])
df["n_modelo"] = df.line.map(lambda l: MM.get(l, (np.nan, np.nan))[1])
df["fuente"] = df.line.map(lambda l: MM.get(l, (0, 0, "—"))[2])
df["shapes"] = df.line.map(lambda l: SH.get(l, (np.nan, np.nan))[0])
df["ramales"] = df.line.map(lambda l: SH.get(l, (np.nan, np.nan))[1])
df["tab_mae"] = df.line.map(lambda l: tab.get(l, {}).get("mae", np.nan))
df["tab_n"] = df.line.map(lambda l: tab.get(l, {}).get("n", np.nan))
for c in CASES:
    df[f"ap_{c}"] = df[f"abs_{c}"] / df.n_con          # aporte en s al MAE de la linea (suman mae_prox)
    df[f"pc_{c}"] = 100 * df[f"n_{c}"] / df.n_con
    df[f"mae_{c}"] = df[f"abs_{c}"] / df[f"n_{c}"].replace(0, np.nan)
df["cociente"] = df.mae_prox / df.mae_modelo
df["cociente_coche"] = df.mae_coche / df.mae_modelo
df["ap_cd"] = df.ap_c + df.ap_d
df["ap_cde"] = df.ap_c + df.ap_d + df.ap_e
assert np.allclose(sum(df[f"ap_{c}"] for c in CASES), df.mae_prox)
chk_mae = float((df.mae_prox - df.tab_mae).abs().max())
chk_n = int((df.n_inst_banda != df.tab_n).sum())
# tablas.md: n banda = instantes en banda (con y sin anuncio, sin excluidos)

E = df[df.line.isin(enabled)].copy()
X = df[df.line == "164"].copy()
assert len(E) == 126, len(E)
assert E.mae_modelo.notna().all(), E[E.mae_modelo.isna()].line.tolist()


def agg(d):
    n = d.n_con.sum()
    r = {"lineas": len(d), "n_inst": int(d.n_inst_banda.sum()), "n_con": int(n), "sin_pct": 100 * d.n_sin.sum() / d.n_inst_banda.sum(),
         "mae_prox": d.sum_abs.sum() / n, "mae_coche": d.sum_coche.sum() / d.n_coche.sum(), "n_coche": int(d.n_coche.sum()),
         "mae_modelo": (d.mae_modelo * d.n_con).sum() / n, "mae_modelo_n": (d.mae_modelo * d.n_modelo).sum() / d.n_modelo.sum(), "n_modelo": int(d.n_modelo.sum())}
    for c in CASES:
        r[f"pc_{c}"] = 100 * d[f"n_{c}"].sum() / n
        r[f"mae_{c}"] = d[f"abs_{c}"].sum() / max(d[f"n_{c}"].sum(), 1)
        r[f"ap_{c}"] = d[f"abs_{c}"].sum() / n
        r[f"n_{c}"] = int(d[f"n_{c}"].sum())
    r["antes"] = 100 * d.sum_antes.sum() / n
    r["despues"] = 100 * d.sum_despues.sum() / n
    return r


A = agg(E)
A_nm = agg(E)
mm_simple = float(E.mae_modelo.mean())
mm_mediana = float(E.mae_modelo.median())

# ---- tabla agregada
NC = {"a": "(a) el 1.º anunciado es el primero en llegar",
      "b": "(b) el 1.º anunciado ya había pasado entre su último ping y t (otro coche llega primero)",
      "c": "(c) el 1.º anunciado es bondi fantasma (otro coche llega primero)",
      "d": "(d) el 1.º anunciado llega después; otro coche listado (2.º-5.º) llega primero",
      "e": "(e) el 1.º anunciado llega después; llega primero un bondi no anunciado",
      "f": "(f) el 1.º anunciado es no verificable (hueco de GPS)"}


def agg_table(a, extra=""):
    L = ["| caso (banda real 3-7 min, instantes con anuncio) | n instantes | % de instantes | MAE (s) | aporte al MAE (s) |", "|---|---:|---:|---:|---:|"]
    for c in CASES:
        L.append(f"| {NC[c]} | {a[f'n_{c}']:,} | {a[f'pc_{c}']:.1f} | {a[f'mae_{c}']:.0f} | {a[f'ap_{c}']:.1f} |".replace(",", " "))
    L.append(f"| **Total con anuncio** | {a['n_con']:,} | 100 | {a['mae_prox']:.1f} | {a['mae_prox']:.1f} |".replace(",", " "))
    return "\n".join(L)


# ---- tabla por linea
S = E.sort_values("mae_prox", ascending=False)


def line_table(d):
    h = ("| línea | ramales (shapes) | n inst. | sin anuncio % | MAE modelo (s) | MAE por coche replay (s) | MAE próximo coche (s) | cociente próx./modelo | "
         "a (s) | b (s) | c (s) | d (s) | e (s) | f (s) |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    L = [h]
    for r in d.itertuples():
        L.append(f"| {r.line} | {f(r.ramales)} ({f(r.shapes)}) | {r.n_con} | {r.sin_pct:.1f} | {r.mae_modelo:.1f} | {r.mae_coche:.0f} | {r.mae_prox:.0f} | {r.cociente:.1f} | "
                 f"{r.ap_a:.0f} | {r.ap_b:.0f} | {r.ap_c:.0f} | {r.ap_d:.0f} | {r.ap_e:.0f} | {r.ap_f:.1f} |")
    return "\n".join(L)


# ---- correlaciones
corr = {}
for nm, y in (("aporte c+d", E.ap_cd), ("aporte c+d+e", E.ap_cde), ("cociente próx./modelo", E.cociente), ("cociente coche/modelo", E.cociente_coche),
              ("MAE próximo coche", E.mae_prox)):
    corr[(nm, "ramales")] = spearman(E.ramales, y)
    corr[(nm, "shapes")] = spearman(E.shapes, y)
ct = ["| variable | Spearman con ramales | p | Spearman con shapes | p |", "|---|---:|---:|---:|---:|"]
for nm in ("aporte c+d", "aporte c+d+e", "cociente próx./modelo", "cociente coche/modelo", "MAE próximo coche"):
    r1, p1, n = corr[(nm, "ramales")]; r2, p2, _ = corr[(nm, "shapes")]
    ct.append(f"| {nm} | {r1:+.2f} | {p1:.1e} | {r2:+.2f} | {p2:.1e} |")
# por cantidad de ramales
E["grp"] = pd.cut(E.shapes, [0, 2, 4, 6, 100], labels=["1-2 shapes", "3-4", "5-6", ">= 7"])
gt = ["| shapes de la línea | líneas | MAE modelo (s) | MAE por coche (s) | MAE próximo coche (s) | cociente | aporte c+d (s) | aporte a (s) |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
for g, d in E.groupby("grp", observed=True):
    a = agg(d)
    gt.append(f"| {g} | {len(d)} | {a['mae_modelo']:.1f} | {a['mae_coche']:.0f} | {a['mae_prox']:.0f} | {a['mae_prox']/a['mae_modelo']:.1f} | {a['ap_c']+a['ap_d']:.0f} | {a['ap_a']:.0f} |")

# ---- fantasma causas (12 lineas)
cz = pd.read_csv(OUT / "descomposicion_fantasma_causas12.csv")
cz_tab = ["| causa (clasificación de `FALSAS_ALARMAS.md`) | n instantes (c) | % de (c) | aporte al MAE de esas 12 líneas (s) |", "|---|---:|---:|---:|"]
for r in cz.itertuples():
    cz_tab.append(f"| {r.cause} | {r.n} | {r.peso_pct:.1f} | {r.aporte_s_por_instante_con_anuncio:.2f} |")

# ---- linea 164
x = X.iloc[0]
l164 = (f"Línea 164 (no habilitada; {int(x.n_con)} instantes con anuncio): ramales {f(x.ramales)} ({f(x.shapes)} shapes), MAE modelo {x.mae_modelo:.1f} s "
        f"(n {int(x.n_modelo)}, {x.fuente}), MAE por coche replay {x.mae_coche:.0f} s, MAE próximo coche {x.mae_prox:.0f} s, cociente {x.cociente:.1f}; "
        f"aportes a {x.ap_a:.0f} / b {x.ap_b:.0f} / c {x.ap_c:.0f} / d {x.ap_d:.0f} / e {x.ap_e:.0f} / f {x.ap_f:.1f} s; sin anuncio {x.sin_pct:.1f} %.")

top = S.head(25)
w = S.sort_values("cociente", ascending=False).head(5)
r_cd = corr[("aporte c+d", "ramales")]; r_q = corr[("cociente próx./modelo", "ramales")]
lectura = f"""1. El MAE del próximo coche anunciado de las 126 líneas habilitadas es {A['mae_prox']:.0f} s (n {A['n_con']:,} instantes con anuncio) contra {A['mae_modelo']:.0f} s de la vara del modelo (ponderada por instantes; {A['mae_modelo_n']:.0f} s ponderada por n de eval): cociente {A['mae_prox']/A['mae_modelo']:.1f}. El MAE por coche del replay es {A['mae_coche']:.0f} s (cociente {A['mae_coche']/A['mae_modelo']:.1f}); el error de cada coche listado casi coincide con la vara, la diferencia está en qué coche se anuncia primero.
2. Cuando el 1.º anunciado es el primero en llegar (a) hay {A['pc_a']:.0f} % de los instantes, con MAE {A['mae_a']:.0f} s y aporte {A['ap_a']:.0f} s. El otro {100-A['pc_a']:.0f} % de los instantes aporta {A['mae_prox']-A['ap_a']:.0f} s ({100*(A['mae_prox']-A['ap_a'])/A['mae_prox']:.0f} % del MAE).
3. Bondi fantasma como 1.º (c): {A['pc_c']:.1f} % de los instantes, MAE {A['mae_c']:.0f} s, aporte {A['ap_c']:.0f} s. El 1.º ya había pasado (b): {A['pc_b']:.1f} %, aporte {A['ap_b']:.0f} s. Otro listado llega primero (d): {A['pc_d']:.1f} %, aporte {A['ap_d']:.0f} s. Bondi no anunciado llega primero con el 1.º llegando después (e): {A['pc_e']:.1f} %, aporte {A['ap_e']:.0f} s. No verificable (f): {A['pc_f']:.1f} %, aporte {A['ap_f']:.1f} s. Sin anuncio: {A['sin_pct']:.1f} % de los instantes (fuera del MAE).
4. Diferencia con `ERROR_POR_COCHE.md`: allá B5 y B6 (1.º ya pasado o fantasma con bondi no anunciado primero) se cuentan también en la fila del bondi no anunciado; acá cada instante cae en un solo caso, por el estado del 1.º anunciado, y los aportes suman el MAE.
5. Por línea el MAE del próximo coche va de {S.mae_prox.min():.0f} a {S.mae_prox.max():.0f} s (mediana {S.mae_prox.median():.0f} s) y el cociente próximo/modelo de {S.cociente.min():.1f} a {S.cociente.max():.1f} (mediana {S.cociente.median():.1f}). Las 5 líneas de mayor cociente: {', '.join(f'{r.line} ({r.cociente:.1f})' for r in w.itertuples())}. En {int((E.mae_prox > 2*E.mae_modelo).sum())} de 126 líneas el MAE del próximo coche supera al doble de la vara. En las 25 peores líneas los aportes de b-e suman {(top.ap_b+top.ap_c+top.ap_d+top.ap_e).mean():.0f} s en promedio contra {top.ap_a.mean():.0f} s de a (cociente por coche/modelo de esas líneas: {top.mae_coche.mean()/top.mae_modelo.mean():.2f}).
6. Cantidad de ramales: Spearman con el aporte de (c)+(d) = {r_cd[0]:+.2f} (p {r_cd[1]:.1e}), con el cociente próximo/modelo = {r_q[0]:+.2f} (p {r_q[1]:.1e}), n = {r_cd[2]}. Con la cantidad de shapes: {corr[('aporte c+d','shapes')][0]:+.2f} y {corr[('cociente próx./modelo','shapes')][0]:+.2f}. Ver la tabla por cantidad de shapes.
7. Causas de bondi fantasma: solo hay clasificación (`falsas/clasif.parquet`) para las 12 líneas viejas con el run de v3 de la vara anterior; se cruzó por (día, línea, parada, t, coche) con el 1.º anunciado de v4. Para las otras 114 líneas hace falta el diagnóstico de `falsas_diag.py` (viaje ex post de cada coche; corrida de ~3 h por 12 líneas), por eso se omite. Cruce de las 12: ver tabla.
"""

md = f"""# Descomposición del error del próximo coche anunciado por línea (replay v4, banda de ETA real 3-7 min)

Medido el 2026-11-22 sobre los crudos de `data/ml/replay/v4prod/v4/` (modelo `path_v4_l1_s1`, 10 días, 40 paradas por línea, instantes cada 10 min de 6 a 23 h). Sin volver a predecir. Código: `data/ml/replay/porcoche/descomposicion.py` (cálculo; salidas `descomposicion_lineas.csv`, `descomposicion_fantasma_causas12.csv`) y `data/ml/replay/porcoche/descomposicion_md.py` (este documento). Reusa la lógica de `porcoche/calcula.py` sin modificarlo.

## Definiciones

- **Líneas:** las 126 de `proyectoconsola/public/config/prediccion.json`; la 164 (no habilitada) aparte.
- **MAE modelo (vara vigente, banda de ETA real 3-7 min):** 46 líneas, eval congelado de v3, modelo v4 candidato (`data/ml/v4_sub/runs/no_regresion.md`, tabla por línea); 72 líneas nuevas, eval congelado de v4 (mismo archivo); 8 habilitadas tarde (49, 97, 119, 153, 154, 163, 185, 193) y la 164, `data/ml/v4_eval_ext/resultados.csv` (columnas `mae`, `n`, eval extendido de 25 días). n pequeños en varias nuevas (57-700 filas): el MAE de la vara tiene ruido de ±5 s por línea.
- **MAE por coche replay:** ETA anunciado (`eta0_s`) − tiempo real hasta SU propio paso (`tp2_s`) de cada coche listado con paso firme en 3-7 min; MAE pooled.
- **MAE próximo coche:** ETA anunciado del 1.º de la lista − tiempo real al primer coche en llegar (cualquiera, listado o no), instantes con el próximo paso real en 3-7 min, sin los de paso previo no verificable, solo con anuncio. Coincide con `tablas.md` (diferencia máxima por línea {chk_mae:.1e} s; n de instantes de la banda distinto en {chk_n} líneas de {len(df)}).
- **Casos** (excluyentes, por el estado del 1.º anunciado; el aporte en s es la suma de |error| del caso dividida por todos los instantes con anuncio de la línea, y los seis suman el MAE): (a) el 1.º anunciado es el primero en llegar; (b) el 1.º ya había pasado entre su último ping y t; (c) el 1.º es bondi fantasma (no pasa en 40 min); (d) el 1.º llega después y otro coche listado (2.º-5.º) llega primero; (e) el 1.º llega después y llega primero un bondi no anunciado; (f) el 1.º es no verificable (hueco de GPS; no pedido, queda para que sumen). En b y c el primero en llegar puede ser listado o bondi no anunciado.
- Llega antes / después de lo anunciado: error = anunciado − real; > 0 llega antes, < 0 llega después. Sin anuncio = instantes sin ningún ETA anunciado (no es el «sin aviso firme» de `tablas.md`, que es «viene» vacío); fuera del MAE.

## Tabla agregada (126 líneas, ponderada por instantes)

MAE modelo ponderado por instantes de la línea ({A['mae_modelo']:.1f} s; ponderado por n de cada eval {A['mae_modelo_n']:.1f} s, n {A['n_modelo']:,}; media simple de líneas {mm_simple:.1f}, mediana {mm_mediana:.1f}). MAE por coche replay {A['mae_coche']:.1f} s (n {A['n_coche']:,} coches). MAE próximo coche {A['mae_prox']:.1f} s; llega antes > 60 s {A['antes']:.1f} %, llega después > 60 s {A['despues']:.1f} %; sin anuncio {A['sin_pct']:.1f} % de {A['n_inst']:,} instantes de la banda. Cociente próximo coche / modelo {A['mae_prox']/A['mae_modelo']:.2f}; por coche / modelo {A['mae_coche']/A['mae_modelo']:.2f}.

{agg_table(A)}

## Cantidad de ramales y error

{chr(10).join(ct)}

{chr(10).join(gt)}

## Bondi fantasma: causa (12 líneas con clasificación)

{chr(10).join(cz_tab)}

## Tabla por línea (ordenada por MAE del próximo coche, descendente)

Columnas a-f: aporte en s al MAE de la línea. n inst. = instantes con anuncio. Ramales (shapes): recorridos distintos y shapes de `proyectoconsola/data/line_shapes`.

{line_table(S)}

## Línea 164 (aparte)

{l164}

## Lectura

{lectura}"""
(OUT / "DESCOMPOSICION.md").write_text(md.replace("{chr(10)}", "\n"), encoding="utf-8")
json.dump({"agregado": A, "corr": {f"{k[0]}|{k[1]}": v for k, v in corr.items()}}, open(OUT / "descomposicion_agregado.json", "w"), indent=1, default=float)
print("ok", chk_mae, chk_n)
