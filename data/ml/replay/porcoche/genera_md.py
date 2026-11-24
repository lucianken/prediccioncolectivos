"""Arma data/ml/replay/ERROR_POR_COCHE.md desde porcoche/resumen.json (salida de calcula.py). Uso: python genera_md.py"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = json.loads((HERE / "resumen.json").read_text(encoding="utf-8"))
T = R["tablas"]
P = R["proximo"]
G = {"seguro": "Viene", "puede_venir": "Puede venir", "provisional": "Sentido sin confirmar"}
BL = {"3-7": "3-7 min (banda principal)", "0-3": "0-3 min", "7-15": "7-15 min"}


def f(v, d=0):
    return "—" if v is None or v != v else f"{v:.{d}f}"


def row(label, k):
    v = T.get(k)
    if not v:
        return f"| {label} | 0 | — | — | — | — | — |"
    n = f"{v['n']:,}".replace(",", " ")
    if v["n_dias"] < 8:
        n += f" ({v['n_dias']} d)"
    return (f"| {label} | {n} | {f(v['mae'])} ± {f(v['mae_sd'])} | {f(v['p90'])} ± {f(v['p90_sd'])} | "
            f"{f(v['antes'],1)} ± {f(v['antes_sd'],1)} | {f(v['despues'],1)} ± {f(v['despues_sd'],1)} | {f(v['sesgo'])} ± {f(v['sesgo_sd'])} |")


def table(b):
    h = ("| corte | n coches | MAE (s) | P90 error abs. (s) | llega antes > 60 s % | llega después > 60 s % | sesgo (s; + = llega antes) |\n"
         "|---|---|---|---|---|---|---|")
    L = [h, row("**Todos los listados**", f"total|{b}")]
    L.append("| *Grupo de la app* | | | | | | |")
    for g, n in G.items():
        L.append(row(n, f"grupo:{g}|{b}"))
    L.append("| *Posición en la lista* | | | | | | |")
    L.append(row("1.º", f"pos:1.o|{b}"))
    L.append(row("2.º-5.º", f"pos:2.o-5.o|{b}"))
    L.append("| *Grupo × posición* | | | | | | |")
    for g, n in G.items():
        for p, pn in (("1.o", "1.º"), ("2.o-5.o", "2.º-5.º")):
            L.append(row(f"{n}, {pn}", f"grupo:{g}+pos:{p}|{b}"))
    L.append("| *Edad del ping en la consulta* | | | | | | |")
    for c in ("0-30", "30-60", "60-120", ">120"):
        L.append(row(f"{c} s", f"edad:{c}|{b}"))
    L.append("| *Pings de historial (en 15 min, incl. el actual)* | | | | | | |")
    for c, n in (("1", "1"), ("2", "2"), (">=3", "≥ 3")):
        L.append(row(n, f"pings:{c}|{b}"))
    return "\n".join(L)


rows = {x["cat"]: x for x in P["filas"]}


def comp(label, key_sub):
    xs = [x for x in P["filas"] if all(s in x["cat"] for s in key_sub)]
    return xs


def drow(label, xs):
    n = sum(x["n"] for x in xs)
    if not n:
        return f"| {label} | 0 | 0 | — | 0 | — | — | — |"
    w = 100 * n / P["n_con_anuncio"]
    mae = sum(x["mae"] * x["n"] for x in xs) / n
    ap = sum(x["aporte_s"] for x in xs)
    an = sum(x["antes"] * x["n"] for x in xs) / n
    de = sum(x["despues"] * x["n"] for x in xs) / n
    se = sum(x["sesgo"] * x["n"] for x in xs) / n
    return f"| {label} | {n} | {w:.1f} | {mae:.0f} | {ap:.1f} | {an:.1f} | {de:.1f} | {se:.0f} |" if n < 1000 else f"| {label} | {n // 1000} {n % 1000:03d} | {w:.1f} | {mae:.0f} | {ap:.1f} | {an:.1f} | {de:.1f} | {se:.0f} |"


A = comp("A", ["A. "])
B = [x for x in P["filas"] if x["cat"].startswith("B.")]
def sub(who, how):
    return [x for x in B if f"es {who};" in x["cat"] and how in x["cat"]]


dec = "\n".join([
    "| caso (banda real 3-7 min, instantes con anuncio) | n instantes | peso % | MAE (s) | aporte al MAE total (s) | llega antes > 60 s % | llega después > 60 s % | sesgo (s; + = llega antes) |",
    "|---|---|---|---|---|---|---|---|",
    drow("**A. el anunciado como 1.º es el primero en llegar** (error = su error por coche)", A),
    drow("B1. el primero en llegar es otro coche listado (2.º-5.º); el anunciado 1.º llega después", sub("listado 2.o-5.o", "llega despues")),
    drow("B2. ídem, y el anunciado 1.º ya había pasado (entre su último ping y t)", sub("listado 2.o-5.o", "ya paso")),
    drow("B3. ídem, y el anunciado 1.º es un bondi fantasma (no pasa en 40 min)", sub("listado 2.o-5.o", "fantasma")),
    drow("B4. el primero en llegar es un bondi no anunciado; el anunciado 1.º llega después", sub("bondi no anunciado", "llega despues")),
    drow("B5. ídem, y el anunciado 1.º ya había pasado", sub("bondi no anunciado", "ya paso")),
    drow("B6. ídem, y el anunciado 1.º es un bondi fantasma", sub("bondi no anunciado", "fantasma")),
    drow("B7. el anunciado 1.º es no verificable (hueco de GPS)", [x for x in B if "no verificable" in x["cat"]]),
    drow("**B. total (otro coche llega primero)**", B),
    drow("**Total con anuncio**", P["filas"]),
])

dd = "\n".join(f"| {x['day']} | {x['n']} | {x['mae']:.0f} | {x['pesoA']:.1f} | {x['maeA']:.0f} |" for x in P["por_dia"])
t37 = T["total|3-7"]

md = f"""# Error del ETA por coche en el replay (vara corregida, regla de sentido de racha final)

Medido el 2026-11-16 sobre resultados ya existentes del replay (sin volver a predecir ni entrenar). Código: `data/ml/replay/porcoche/calcula.py` (cálculo) y `genera_md.py` (este documento); salidas intermedias en `data/ml/replay/porcoche/` (`filas.parquet`, `instantes.parquet`, `resumen.json`).

## Datos y verdad

- Crudos: `data/ml/replay/vara/run_base_sg` (9 días) + `run_cs_sg` (3-oct, variante `base`), modelo `path_v3_l1_s1`, regla de sentido `trailing_run`, 12 líneas, 40 paradas por línea, instantes cada 10 min de 6 a 23 h; los 10 días de `VARA_CORREGIDA.md` (15-20 sep., 3, 4, 6, 8 oct.). Lo duplicado cuenta una vez. Los crudos traen todo lo pedido salvo la edad del ping y la cantidad de pings de historial: se leen de los pings grabados (solo timestamps), con la regla de `core.evaluate_line` (último ping ≤ t; historial = pings en [t − 15 min, t] incluido el actual).
- **Verdad: la actual (`tp2_s`), que cuenta como paso a coches cuyo recorrido real no tiene la parada (≈ 4 % de los pasos ≤ 10 min, ver `VARA_CORREGIDA.md`).** Otro agente está cambiando la verdad (paso solo si el recorrido ex post del coche tiene la parada): re-correr `python data/ml/replay/porcoche/calcula.py --runs <crudos nuevos> ` y `python data/ml/replay/porcoche/genera_md.py` (las cifras de este documento cambian; ver Re-corrida). Con la verdad actual la reproducción del replay es exacta: 130 159 instantes en la banda 3-7 min, MAE próximo coche {P['mae_total']:.1f} s, llega antes {P['antes']:.1f} %, llega después {P['despues']:.1f} % (iguales a `VARA_CORREGIDA.md`).
- **Error por coche** = ETA anunciado (`eta0_s`, hora común) − tiempo real hasta SU propio paso firme (`tp2_s`). Positivo = el coche llega antes de lo anunciado; negativo = llega después. Se evalúa cada (parada, t, coche listado entre los 5 mostrados) que cruza la parada en ≤ 40 min con paso firme: {R['n_filas_listadas_con_paso']} coches. Excluye los listados sin paso firme (bondi fantasma, ya pasó, no verificable).
- **Banda** = tiempo real hasta el paso del propio coche (0-3, 3-7, 7-15 min). Condicionar por el tiempo real produce sesgo por selección (en la banda cercana el ETA tiende a ser tardío y en la lejana temprano): el sesgo por banda no es un sesgo del modelo.
- **Posición** = orden de pantalla (Viene por ETA, luego Puede venir y Sentido sin confirmar por ETA). **Dispersión**: cada celda es la media de los días ± desvío día a día (días con ≥ 20 coches en la celda; entre paréntesis, cuántos días cuando son menos de 8); P90 = percentil 90 del error absoluto, media de los días.
{{}}

## Resultado principal: banda de tiempo real 3-7 min

{table("3-7")}

Lectura:
1. **Error por coche en 3-7 min: MAE {t37['mae']:.0f} ± {t37['mae_sd']:.0f} s** (P90 {t37['p90']:.0f} s; llega antes > 60 s {t37['antes']:.1f} %, llega después > 60 s {t37['despues']:.1f} %, sesgo {t37['sesgo']:.0f} s). Es igual a la vara del modelo (~55 s).
2. El coche anunciado como 1.º tiene mejor error que el resto (MAE {T['pos:1.o|3-7']['mae']:.0f} contra {T['pos:2.o-5.o|3-7']['mae']:.0f} s), pero su sesgo es de signo contrario: llega después de lo anunciado (más que antes). Los 2.º-5.º llegan más seguido antes de lo anunciado.
3. Por grupo: Viene {T['grupo:seguro|3-7']['mae']:.0f} s, Puede venir {T['grupo:puede_venir|3-7']['mae']:.0f} s, Sentido sin confirmar {T['grupo:provisional|3-7']['mae']:.0f} s (este último, 0,8 % de los coches de la banda). El grupo importa poco para el error del coche que sí llega; importa para si llega (bondi fantasma, ver `VARA_CORREGIDA.md`).
4. Por edad del ping: 0-30 s {T['edad:0-30|3-7']['mae']:.0f} s, 30-60 s {T['edad:30-60|3-7']['mae']:.0f} s, 60-120 s {T['edad:60-120|3-7']['mae']:.0f} s, > 120 s {T['edad:>120|3-7']['mae']:.0f} s. Con ping fresco (≤ 30 s, 75 % de los coches) el error ya es ~53 s: la edad del ping no explica la diferencia con la vara. Los pings > 120 s (3,7 % de los coches) casi duplican el error y llegan después de lo anunciado (sesgo negativo).
5. Por historial: ≥ 3 pings {T['pings:>=3|3-7']['mae']:.0f} s (99,3 % de los coches), 2 pings {T['pings:2|3-7']['mae']:.0f} s, 1 ping {T['pings:1|3-7']['mae']:.0f} s: pocos casos, error mayor, sin peso en el agregado.

## Bandas 0-3 y 7-15 min

### 0-3 min

{table("0-3")}

### 7-15 min

{table("7-15")}

El error crece con el horizonte (35 → 56 → 90 s de MAE por coche). En 7-15 min el sesgo es negativo (llega después) por selección de banda, más fuerte en el 1.º de la lista.

## Descomposición del MAE «próximo coche» (banda 3-7 min)

Instante = (parada, t) con el próximo paso real (`real_next2_s`) en 3-7 min, sin los instantes excluidos por paso previo no verificable ({P['n_excl_unv']} de {P['n_instantes_banda']}); {P['n_con_anuncio']} con anuncio (sin aviso firme: {P['sin_anuncio_pct']:.1f} %, fuera del MAE; es un problema de la app, no del modelo). Error del instante = ETA anunciado del 1.º de la lista (`ann0_any_s`) − tiempo real al primer coche en llegar (cualquiera, listado o no). Verificación: `ann0_any_s` coincide con el `eta0_s` del 1.º de la lista en {100*R['check_ann0_igual_eta0_primero']:.1f} % de los instantes (el resto, empates de ETA).

{dec}

Por día (el peso de A y su MAE):

| día | instantes | MAE próximo coche (s) | peso de A % | MAE de A (s) |
|---|---|---|---|---|
{dd}

Lectura:
1. **Cuando el anunciado como 1.º es el que llega primero (75 % de los instantes) el MAE es ~50 s, igual a su error por coche** (49,5 s; en 3-7 min por coche, 1.º de la lista: {T['pos:1.o|3-7']['mae']:.0f} s). Aporta 37 s de los 99 s.
2. **El otro 25 % de los instantes aporta 62 s (63 % del MAE)** con error de 110-410 s por instante. No es error de ETA de un coche: el ETA anunciado corresponde a otro coche que llega más tarde, ya pasó o no existe. Pesos: el anunciado 1.º ya pasó entre su último ping y t, mientras otro coche llega primero (B2 + B5: 7,0 % de los instantes, 19,4 s); el anunciado 1.º es un bondi fantasma (B3 + B6: 4,7 %, 18,7 s); otro coche listado llega primero y el 1.º llega después (B1: 10,0 %, 11,4 s); el primero en llegar es un bondi no anunciado (B4 + B5 + B6: 4,7 %, 17,0 s; B5 y B6 ya están contados en las dos líneas anteriores).
3. En B1 (mismo conjunto de coches, orden de llegada distinto) el MAE es 114 s: son errores de orden entre coches con ETA parecido; el error del anunciado contra su propio paso es de 176 s en esos casos, por lo que el modelo tampoco acierta a ese coche, no solo el orden.

## Conclusión

- **El modelo no es peor en producción.** El error por coche en el replay en 3-7 min es **{t37['mae']:.0f} s** (media de días ± {t37['mae_sd']:.0f}), contra ~55 s de la vara del modelo; con ping fresco ≤ 30 s, 53 s. El 1.º de la lista tiene 52 s.
- **La diferencia (~99 s contra ~55 s) viene de qué coche se anuncia como próximo**, no del ETA de cada coche: en 75 % de los instantes el 1.º anunciado es el primero en llegar y el MAE es ~50 s. En el 25 % restante otro coche llega primero (el anunciado ya pasó, es un bondi fantasma, llega después que otro coche listado, o el primero es un bondi no anunciado) y esos instantes aportan 62 de los 99 s.
- Diferencias de muestra que quedan entre la vara del modelo y el replay (no cuantificadas por separado, excepto la edad del ping): la vara mide filas con ETA real 3-7 min sobre puntos cualquiera (un coche en un punto del trayecto, ping fresco, historial completo) y el replay mide coches listados en 40 paradas por línea, cada 10 min, con la regla de lista (≤ 5 coches, grupos), pings de hasta 10 min de antigüedad, historial de 15 min recortado y paradas y horarios distintos; el replay además condiciona por el paso real firme del propio coche (verdad con la limitación de coches cuyo recorrido no tiene la parada, ≈ 4 % de los pasos). Los coches con 1-2 pings (0,7 %) y con ping > 120 s (3,7 %) tienen error 70-110 s pero no mueven el agregado.
- El «próximo coche» tiene un error propio de selección que el error por coche no ve: coches ya pasados (ping viejo), bondi fantasma y orden equivocado de llegada. Eso es lo que hay que atacar para bajar el ~99 s, no el ETA por coche.

## Re-corrida con la verdad nueva

`python data/ml/replay/porcoche/calcula.py --runs data/ml/replay/vara/run_base_xp [--days ...]` y luego `python data/ml/replay/porcoche/genera_md.py` (regenera este archivo; los textos de «Lectura» y «Conclusión» que citan números fijos hay que revisarlos a mano). Con la verdad nueva se espera: menos coches con paso firme (los pasos de coches cuyo recorrido no tiene la parada dejan de ser verdad), con lo cual algunos coches que hoy cuentan como «llega» pasarían a ser bondi fantasma y, en el cálculo por coche, salen de la muestra (el error por coche se mide solo sobre coches que cruzan). Las filas `run_base_xp` del cálculo actual no se usaron.
"""
(HERE.parent / "ERROR_POR_COCHE.md").write_text(md.replace("{}", ""), encoding="utf-8")
print("ok")
