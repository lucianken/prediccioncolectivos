"""Genera ASIGNACION_RECORRIDO.md a partir de resumen.json, eval_impacto.json, amb_worse.json, ejemplos.txt."""
import json
from pathlib import Path

import pandas as pd

H = Path(__file__).resolve().parent
r = json.load(open(H / "resumen.json"))
ev = json.load(open(H / "eval_impacto.json"))
aw = json.load(open(H / "amb_worse.json"))
T = pd.read_pickle(H / "_trips_all.pkl")
LINES = ["26", "39", "42", "92", "124", "151", "168", "50", "106", "107", "108", "132", "12", "15", "128"]
ALL = LINES + ["TODAS"]


def f(x, d=1):
    return f"{x:.{d}f}".replace(".", ",")


def p(x, d=1):
    return f(100 * x, d) + " %"


def n(x):
    return f"{int(x):,}".replace(",", ".")


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]
    out += ["| " + " | ".join(map(str, rw_)) + " |" for rw_ in rows]
    return "\n".join(out)


noise = r["noise"]; pg = r["pings"]; rw = r["rows"]; rt = r["rows_total"]; am = r["amb"]; fl = r["noise_frac_le"]
TOT = pg["TODAS"]
t1 = table(["Línea", "Pings", "> 150 m", "p50 (m)", "p90 (m)", "p95 (m)", "p99 (m)"],
           [[l, n(noise[l]["pings"]), p(noise[l]["frac_gt150"]), *[f(v) for v in noise[l]["pct_valid"]]] for l in ALL])
t1b = table(["Umbral (m)", "10", "15", "20", "30", "45", "60", "100"],
            [["% de pings válidos por debajo"] + [p(fl[k]) for k in ["10", "15", "20", "30", "45", "60", "100"]]])
t2 = table(["Línea", "Pings válidos", "45–150 m", "con otro shape ≥10 m más cerca", "de esos, el otro es el sentido opuesto", "Control: ≤45 m con otro ≥10 m más cerca"],
           [[l, n(pg[l]["valid"]), p(pg[l]["mid"] / pg[l]["valid"], 2), p(pg[l]["mid_oc"] / pg[l]["mid"]),
             p(pg[l]["mid_oc_opp"] / max(pg[l]["mid_oc"], 1), 0), p(pg[l]["low_oc"] / pg[l]["low"], 2)] for l in ALL])
t3 = table(["Línea", "Filas", "P en 45–150", "F en 45–150", "P o F en 45–150", "con otro más cerca", "Sucias (45–150 u otro más cerca)", "Limpias"],
           [[l, n(rw[l]["rows"]), p(rw[l]["mid_p"] / rw[l]["rows"], 2), p(rw[l]["mid_f"] / rw[l]["rows"], 2), p(rw[l]["mid_any"] / rw[l]["rows"], 2),
             p(rw[l]["mid_any_oc"] / max(rw[l]["mid_any"], 1)), p(rw[l]["dirty"] / rw[l]["rows"], 2), p(rw[l]["clean"] / rw[l]["rows"], 2)] for l in ALL])
t4 = table(["Línea", "Viajes", "Mediana perp. del viaje, p50", "dif. < 20 m", "dif. < 20 m y 2º es sentido opuesto", "2º es sentido opuesto", "Elegido > 20 m peor que otro", "Mediana perp. del viaje > 45 m"],
           [[l, n(am[l]["trips"]), f(am[l]["med1_p50"]) + " m", p(am[l]["frag20"]), p(am[l]["frag20_and_opp"]), p(am[l]["second_opp"]),
             p(aw[l]["worse20"], 2), p(aw[l]["med1_gt45"], 2)] for l in ALL])
t5 = table(["Línea", "Pares de pings válidos consecutivos", "Retroceso > 150 m", "Viajes con 1 o más retrocesos"],
           [[l, n(pg[l]["pairs"]), p(pg[l]["back150"] / pg[l]["pairs"], 3), p(pg[l]["back150_trips"] / pg[l]["trips"])] for l in ALL])
S = r["sim"]; b, s = S["base"], S["s45"]
rs = lambda d, k: n(d["reasons"].get(k, 0))
chg = lambda a, c: ("+" if c >= a else "") + f(100 * (c - a) / a, 0) + " %"
t6 = table(["", "FIT_M = 150 (v2b)", "FIT_M = 45", "Cambio"],
           [["Viajes", n(b["trips"]), n(s["trips"]), chg(b["trips"], s["trips"])],
            ["Pings válidos", n(b["valid_pings"]), n(s["valid_pings"]), chg(b["valid_pings"], s["valid_pings"])]]
           + [[f"Cortes por «{k}» ({lab})", rs(b, k), rs(s, k), chg(b["reasons"][k], s["reasons"][k])] for k, lab in
              [("reverse", "inversión de sentido sostenida"), ("off", "salida del recorrido, p. ej. cambio de ramal"), ("gap", "hueco > 5 min no unido"),
               ("end", "llegada al final"), ("stop", "detenido en cabecera o final"), ("data_end", "fin de datos")]]
           + [["start_unknown (% de viajes)", p(b["start_unknown"]), p(s["start_unknown"]), f(100 * (s["start_unknown"] - b["start_unknown"]), 1) + " pp"],
              ["start_unknown (% de pings válidos)", p(b["start_unknown_w"]), p(s["start_unknown_w"]), f(100 * (s["start_unknown_w"] - b["start_unknown_w"]), 1) + " pp"],
              ["Viajes consecutivos del mismo coche (hueco ≤ 5 min): sentido opuesto del mismo ramal", n(b["transitions"]["opposite"]), n(s["transitions"]["opposite"]), chg(b["transitions"]["opposite"], s["transitions"]["opposite"])],
              ["idem: otro ramal", n(b["transitions"]["other_ramal"]), n(s["transitions"]["other_ramal"]), chg(b["transitions"]["other_ramal"], s["transitions"]["other_ramal"])],
              ["idem: mismo recorrido", n(b["transitions"]["same"]), n(s["transitions"]["same"]), chg(b["transitions"]["same"], s["transitions"]["same"])]])


def evrows(w):
    out = []
    for band, lab in [("global", "Global"), ("3-7min", "ETA real 3–7 min")]:
        x = ev[w][band]
        for k, nm in [("limpia", "Limpias"), ("contaminada", "Contaminadas"), ("todas_matched", "Todas")]:
            v = x[k]
            out.append([lab, nm, n(v["n"]), p(v["frac"]), f(v["mae"]), f(v["p90"]), f(v["bias"]), p(v["late60"], 0), p(v["early60"], 0)])
    return table(["Banda", "Grupo", "n", "% filas", "MAE (s)", "p90 error abs (s)", "Sesgo (s)", "Predice tarde >60 s", "Predice temprano >60 s"], out)


NM = {"limpia": "limpia", "perp45_150": "45–150 m", "otro_mas_cerca": "≤45 m y otro más cerca", "perp45_150+otro": "45–150 m y otro más cerca"}


def evgrp(w):
    out = []
    for band, lab in [("global", "Global"), ("3-7min", "3–7 min")]:
        for g, v in ev[w][band]["grp"].items():
            out.append([lab, NM[g], n(v["n"]), f(v["mae"]) if v["mae"] else "-"])
    return table(["Banda", "Grupo", "n", "MAE (s)"], out)


def evperp(w):
    out = []
    for band, lab in [("global", "Global"), ("3-7min", "3–7 min")]:
        out += [[lab, k + " m", n(v["n"]), f(v["mae"])] for k, v in ev[w][band]["por_perp_max"].items()]
    return table(["Banda", "max(perp P, perp F)", "n", "MAE (s)"], out)


def gain(w, band):
    x = ev[w][band]
    return p(1 - x["limpia"]["mae"] / x["todas_matched"]["mae"])


EJ = [json.loads(l) for l in (H / "ejemplos.txt").read_text(encoding="utf-8").strip().splitlines() if l.startswith("{")]
by = {(e["tipo"], e["linea"], e["vid"]): e for e in EJ}


def ej(t, ln, vid, desc):
    e = by[(t, ln, vid)]
    return f"| {ln} | {e['label']} | {e['dia']} {e['hora_local']} | {e['lat']}, {e['lon']} | {desc} |"


HEAD = "| Línea | Coche (label) | Día y hora local | Lat, lon | Qué pasó |\n|---|---|---|---|---|"
ex_A = "\n".join([HEAD,
    ej("A", "151", "97385", "Viaje de 70 pings: 21 de 66 válidos a 45–150 m del recorrido 19481774 (en 20 hay otro más cerca; medianas 14,0 m contra 12,7 m del 4020922): ramales casi superpuestos."),
    ej("A", "39", "77665", "25 de 71 pings válidos a 45–150 m del 382202 (39A), todos con el 382208 (39B) más cerca; medianas 7,1 y 11,6 m."),
    ej("A", "92", "26763", "22 de 60 pings a 45–150 m del 6750274, todos con otro recorrido más cerca (medianas 6,4 y 22,2 m). El viaje termina por salida del recorrido."),
    ej("A", "108", "95302", "26 de 77 pings a 45–150 m del 4240252, todos con el sentido opuesto (4237146) más cerca; medianas 4,4 y 19,3 m. Termina detenido.")])
ex_B = "\n".join([HEAD,
    ej("B", "108", "95455", "Viaje de 21 pings. Mediana 8,4 m al recorrido elegido (4240252) y 10,2 m al sentido opuesto (4237146): la geometría no decide; decide el avance hacia adelante (≥ 60 %)."),
    ej("B", "168", "20020", "36 pings; medianas 3,0 m (4681272) y 7,1 m (5188890, sentido opuesto). Misma situación.")])
ex_C = "\n".join([HEAD,
    ej("C", "128", "82838", "Se eligió el 374958 con mediana de 101 m (167 de 176 pings a 45–150 m); el 374959, sentido opuesto, tenía 5,0 m. El coche circula por una calle y el recorrido elegido pasa por la paralela."),
    ej("C", "42", "77694", "Elegido 3464448, mediana 104 m; el sentido opuesto (3464362) tenía 3,6 m. Termina por inversión de sentido."),
    ej("C", "106", "79281", "Elegido 3663267, mediana 143 m; el sentido opuesto (3008238) tenía 19,0 m. Termina por salida del recorrido.")])
ex_D = "\n".join([HEAD,
    ej("D", "42", "90844", "Viaje de 245 pings con solo 33 válidos (mediana 159 m al elegido): 22 retrocesos > 150 m; la proyección salta entre tramos."),
    ej("D", "92", "27269", "61 pings, 57 válidos, mediana 6,0 m: 18 retrocesos > 150 m aun con buen ajuste; la proyección pasa a otro pasaje del recorrido.")])
ex_E = "\n".join([HEAD,
    ej("E", "12", "97980", "Con 150 m: un viaje (370813, termina por inversión). Con 45 m: el tramo se reparte en dos viajes que se cortan en este ping (19336740 y luego 370813)."),
    ej("E", "151", "97464", "Con 150 m: un viaje que termina por inversión (19481774). Con 45 m: corte por hueco no unido y un viaje nuevo (4020850) que arranca después."),
    ej("E", "26", "78148", "Con 150 m: un viaje hasta fin de datos (23555). Con 45 m: se parte en este ping, entre 23305 y 23555."),
    ej("E", "151", "97016", "Con 150 m: un viaje (4020850). Con 45 m: salida del recorrido y se parte entre 19481774 y 19481773.")])

doc = f"""# Asignación de recorrido en v2b: ¿cuánto error de datos hay con el criterio de 150 m?

Diagnóstico de solo lectura sobre `data/ml/v2b` (15 líneas, {r['n_days']} días, {r['first']} a {r['last']}). No se entrenó nada ni se tocó el pipeline ni `data/ml/v2*`. Todo lo generado está en `data/ml/v2b/diag/asignacion/`.

## 0. Método

- Se releyó el NDJSON crudo de los {r['n_days']} días y se volvió a segmentar con el segmentador v2b (`geo2`) con el mismo carry del build (`data/ml/v2b/daily/*.carry.json`). Reproduce exactamente los viajes del build (comprobado: misma cantidad de viajes por línea y en total en el día de prueba). Total: {n(r['trips_n'])} viajes y {n(TOT['pings'])} pings.
- Por viaje se proyecta cada ping sobre **todos** los recorridos de la línea (`ShapeIndex.project_many`) y se toma el recorrido asignado por `geometry_for_trip` (el del build).
- «Otro shape más cerca» = algún otro recorrido de la línea con perp menor que el asignado **en más de 10 m**. Con comparación estricta (cualquier diferencia) el control en ≤45 m da ~11 %, porque ramales que comparten tronco empatan por ruido; por eso el margen de 10 m. Los valores estrictos están en `resumen.json`.
- «Sentido opuesto del mismo ramal» se deduce del nombre del recorrido (`A → B` contra `B → A`); no se usa route_id, trip_id ni start_time.
- Filas de entrenamiento: se leyeron los parquet diarios y se emparejó cada fila (P y F) con su ping por (recorrido, ts, distancia a lo largo). Se emparejaron {n(rw['TODAS']['rows'])} de {n(rt['TODAS'])} filas (99,99 %).
- Punto 5: simulación con `FIT_M = 45` en {len(r['sim_days'])} días de muestra (1 de cada 5 más 4 días hábiles de la validación del segmentador), sin escribir en v2b.
- Punto 6: modelo `path_lr2e-3_s0`, evaluado con `prediccion.eval --save-preds` con salida en `eval/`. Las filas de eval se emparejan con las filas de entrenamiento de los días de validación (por recorrido, ts_p y dist_along).
- Ping «válido» = perp ≤ 150 m al recorrido asignado (la máscara de v2b). Los percentiles salen de histogramas de 0,5 m.

## 1. Ruido GPS real (perp al recorrido asignado ex post)

Percentiles sobre los pings válidos (≤ 150 m); la columna «> 150 m» es la fracción de pings de viaje fuera de la máscara.

{t1}

Fracción de los pings válidos por debajo de cada umbral:

{t1b}

Lectura: la mitad de los pings cae a ≤ 3,5 m del recorrido y el 95 % a ≤ 14,5 m. Entre 15 y 45 m queda un 3,0 % y entre 45 y 150 m un 1,6 % de los pings válidos. El p99 (73 m) ya no es ruido de GPS sino desvíos reales, calles paralelas y tramos fuera de recorrido. Por línea el p95 va de 10,5 m (107) a 22 m (151) y 19 m (42).

**Umbral físico razonable: 45 m** (98,4 % de los pings válidos, unas 3 veces el p95). Con 30 m se retiene 97,8 %; con 20 m, 96,9 %. Entre 45 y 100 m no hay ruido de GPS sino otra calle o un desvío, y una cuadra porteña (100–130 m) cae dentro de 150 m.

## 2. Filas contaminadas (perp 45–150 m)

Pings válidos (total {n(TOT['valid'])}): {p(TOT['mid']/TOT['valid'],2)} están a 45–150 m. En {p(TOT['mid_oc']/TOT['mid'])} de ellos otro recorrido de la línea está ≥ 10 m más cerca (comparación estricta: {p(TOT['mid_oc_strict']/TOT['mid'])}) y en {p(TOT['mid_oc_opp']/TOT['mid_oc'],0)} de esos el más cercano es el sentido opuesto del mismo ramal (el resto, otro ramal). Control: dentro de ≤ 45 m el «otro más cerca» ocurre en {p(TOT['low_oc']/TOT['low'],2)} de los pings.

{t2}

Filas de entrenamiento (par P, F; {n(rw['TODAS']['rows'])} emparejadas): P o F a 45–150 m en {p(rw['TODAS']['mid_any']/rw['TODAS']['rows'],2)}; de esas, {p(rw['TODAS']['mid_any_oc']/rw['TODAS']['mid_any'])} con otro recorrido más cerca. **Sucias** (45–150 m en P o F, o algún otro recorrido ≥ 10 m más cerca en P o F): **{p(rw['TODAS']['dirty']/rw['TODAS']['rows'],2)}**.

{t3}

Las peores líneas son 92, 151 y 42 (5,6–6,9 % de filas sucias); las mejores, 128, 106, 26 y 168 (2,0–2,5 %).

## 3. Ambigüedad de la asignación del viaje

Diferencia = (mediana de perp del mejor otro recorrido) menos (mediana de perp del elegido), sobre todos los pings del viaje. Sobre {n(r['trips_n'])} viajes.

{t4}

- «dif. < 20 m» es muy alto ({p(am['TODAS']['frag20'],1)}) pero **no es error por sí mismo**: son ramales que comparten casi todo el trazado (39, 12, 132, 42, 151, 168 y 15 pasan del 98 %), y la elección arbitraria entre ellos ya estaba aceptada en ARQUITECTURA §4.1 (ruido de normalización, no de etiqueta).
- Lo que sí importa es que el segundo mejor sea el **sentido opuesto del mismo ramal**: {p(am['TODAS']['second_opp'],1)} de los viajes (100 % en 26, 124, 128, que tienen solo ida y vuelta; 79 % en 106). Con diferencia < 20 m: **{p(am['TODAS']['frag20_and_opp'],1)}** de los viajes, concentrado en 108 ({p(am['108']['frag20_and_opp'],0)}), 50 ({p(am['50']['frag20_and_opp'],0)}) y 92 ({p(am['92']['frag20_and_opp'],0)}). Ahí la perp no decide el sentido: lo decide `_forward_fraction ≥ 0,6` (avance hacia adelante).
- **Elegido claramente peor que otro (> 20 m)**: {p(aw['TODAS']['worse20'],2)} de los viajes ({n(len(T[(T.med2-T.med1)<-20]))}), {p(aw['TODAS']['worse20_and_second_opp'],0)} de ellos con el mejor alternativo en sentido opuesto: el coche circula por una calle y el recorrido que cumple la regla de avance es el de la calle paralela. Son {p(aw['TODAS']['worse20_valid_pings'],2)} de los pings válidos. Viajes con mediana de perp > 45 m: {p(aw['TODAS']['med1_gt45'],2)} (92: {p(aw['92']['med1_gt45'],1)}, 42: {p(aw['42']['med1_gt45'],1)}, 107: {p(aw['107']['med1_gt45'],1)}).

## 4. Proyección en el sentido equivocado (retroceso de la distancia a lo largo > 150 m)

Entre pings válidos consecutivos del mismo viaje. Total: {n(TOT['back150'])} retrocesos en {n(TOT['pairs'])} pares (**{p(TOT['back150']/TOT['pairs'],3)}**). Pero {p(TOT['back150_trips']/TOT['trips'])} de los viajes tienen al menos uno, y esos viajes reúnen 10,7 % de los pings válidos.

{t5}

Concentrado en 15 ({p(pg['15']['back150_trips']/pg['15']['trips'],0)} de los viajes), 42 ({p(pg['42']['back150_trips']/pg['42']['trips'],0)}), 124 ({p(pg['124']['back150_trips']/pg['124']['trips'],0)}) y 92 ({p(pg['92']['back150_trips']/pg['92']['trips'],0)}). No se verificó la causa; es consistente con recorridos con bucles o tramos que pasan dos veces por la misma calle (la proyección salta a otro pasaje), pero hay que mirarlo en el mapa (§7, tipo D). A nivel de filas el efecto queda acotado por las reglas del par (`dist[F] − dist[P] ≥ 100 m`, `ts[F] > ts[P]`); no se midió por separado.

## 5. Segmentador con FIT_M = 45 m en vez de 150 m

Simulación en {len(r['sim_days'])} días (mismos NDJSON y mismo carry; `FIT_M` cambiado solo en memoria). `start_unknown` se calcula con la máscara perp ≤ FIT_M de cada caso (45 o 150 m) y el umbral de 1 km.

{t6}

Entre las dos segmentaciones, {n(S['split_150_into_multiple_45'])} viajes de 150 m ({p(S['split_150_into_multiple_45']/b['trips'],1)}) quedan partidos en 2 o más de 45 m y {n(S['merge_multiple_150_into_one_45'])} viajes de 45 m reúnen 2 o más de 150 m (solapamiento ≥ 60 s).

Lectura: con 45 m **desaparece el {f(100*(1-s['reasons']['reverse']/b['reasons']['reverse']),0)} % de los cortes por inversión de sentido**, aparecen **{f(s['reasons']['off']/b['reasons']['off'],1)} veces más** cortes por salida del recorrido y el doble de huecos no unidos (con 45 m más huecos y excursiones no cumplen «vuelve a ≤ FIT_M»). El número de viajes casi no cambia ({chg(b['trips'], s['trips'])}), pero se cortan en otro lugar; `start_unknown` sube {f(100*(s['start_unknown']-b['start_unknown']),1)} pp (viajes) y {f(100*(s['start_unknown_w']-b['start_unknown_w']),1)} pp (pings). Los pasos entre viajes consecutivos de un mismo coche (inversión de sentido, cambio de ramal) casi no cambian ({chg(b['transitions']['opposite'], s['transitions']['opposite'])} y {chg(b['transitions']['other_ramal'], s['transitions']['other_ramal'])}); lo que cambia es en qué ping se corta y con qué causa. Bajar FIT_M **del segmentador** a 45 m no mejora los datos y los fragmenta más; conviene separar el umbral de segmentación del de asignación y validez.

## 6. Impacto en la evaluación (modelo por tramos `path_lr2e-3_s0`)

MAE global del modelo: seen {f(ev['seen']['global']['todas_matched']['mae'],2)} s (coincide con ARQUITECTURA: 102,7), heldout {f(ev['heldout']['global']['todas_matched']['mae'],2)} s. Limpia = P y F con perp ≤ 45 m y ningún otro recorrido ≥ 10 m más cerca. Se emparejaron {n(ev['seen']['global']['matched'])} de 30.000 filas (seen) y {n(ev['heldout']['global']['matched'])} de 30.000 (heldout). Sesgo = predicción menos ETA real (negativo = predice antes de lo real, el coche llega más tarde).

**seen**

{evrows('seen')}

**heldout**

{evrows('heldout')}

MAE por grupo de contaminación, seen:

{evgrp('seen')}

heldout:

{evgrp('heldout')}

MAE por perp máxima del par, para ver si el error crece con la distancia al recorrido. seen:

{evperp('seen')}

heldout:

{evperp('heldout')}

Lectura: las filas sucias tienen **aproximadamente el doble de error** (global: seen 208 s contra 98 s; heldout 402 contra 198; banda 3–7 min: 85 contra 53 s en seen y 158 contra 79 s en heldout). El error crece de forma monótona con la perp (banda 3–7 min, seen: 52 s a ≤ 10 m, 71 s a 20–45 m, 94 s a 75–150 m). Pero son solo {p(1-ev['seen']['global']['limpia']['frac'],1)} (seen) y {p(1-ev['heldout']['global']['limpia']['frac'],1)} (heldout) de las filas: sacarlas bajaría el MAE global {gain('seen','global')} (seen) y {gain('heldout','global')} (heldout), y en la banda 3–7 min {gain('seen','3-7min')} y {gain('heldout','3-7min')}. Advertencia: no se puede separar «etiqueta ruidosa» de «situación difícil»; las filas lejos del recorrido son también las de desvíos, cabeceras y cruces, donde el modelo yerra más aunque el recorrido fuera el correcto.

## 7. Ejemplos para mirar en el mapa

Hora local = UTC−3; el día es el del archivo de grabación. Lat/lon es la posición del ping indicado (en A y D el primer ping con el problema; en B, C y E el primer ping del viaje o del corte). Coche = `label` de la API (`<n>-<sufijo>`).

**A. Pings a 45–150 m con otro recorrido más cerca (calle paralela u otro ramal)**

{ex_A}

**B. Asignación frágil: el sentido opuesto del mismo ramal tiene casi la misma perp**

{ex_B}

**C. Recorrido elegido peor que el opuesto (sentido equivocado a nivel de viaje)**

{ex_C}

**D. Retroceso de la distancia a lo largo > 150 m**

{ex_D}

**E. Segmentador: con 150 m un viaje, con 45 m un corte en este punto**

{ex_E}

## 8. Conclusión

1. **¿Error de datos relevante en el entrenamiento? No en volumen.** El 96,2 % de las filas es limpia (ruido GPS real: p50 3,5 m, p95 14,5 m); el 3,8 % está sucia (2,9 % con P o F a 45–150 m, de las cuales 45 % con otro recorrido más cerca, 59 % de ellos el sentido opuesto), y el recorrido elegido es claramente peor que otro en 0,12 % de los viajes. La asignación ex post con el viaje completo es mucho más limpia que el criterio en vivo de 150 m.
2. **Umbral: 45 m** para validez de un ping o fila (98,4 % de los pings válidos; 30 m da 97,8 %), y que el sentido salga del avance sostenido y no de la perp: en 5,9 % de los viajes la perp no distingue ida de vuelta (108, 50, 92). En producción 150 m no sirve porque caben dos calles.
3. **Impacto en el modelo:** las filas sucias tienen el doble de MAE (3–7 min: 85 contra 53 s en seen), pero al ser 4 % de la evaluación, limpiarlas mejora el MAE solo 2–5 %; no se puede separar etiqueta ruidosa de situación difícil.
4. **Segmentador:** FIT_M = 45 m no sirve (−42 % de cortes por inversión, 3 veces más por salida del recorrido, +0,9 pp de `start_unknown`); mantener 150 m ahí y usar 45 m solo en la máscara de filas y en la asignación.
5. **¿Reconstruir v2b con umbral menor? No por esto:** la ganancia esperada es de hasta 5 % del MAE. Si se reconstruye por otra razón, usar máscara de filas de 45 m (segmentador en 150 m) y revisar los retrocesos de 15, 42, 124 y 92 (8,7 % de los viajes en total). El problema de producción (asignación en vivo sin ver el viaje completo) no se mide acá y es el que hay que arreglar en `inference`.

## Archivos

- `diag_asignacion.py` (diagnóstico por día, escribe `_days/*.pkl`), `analizar.py` (agregación, `resumen.json`), `eval_impacto.py` (`eval_impacto.json`), `ejemplos.py` (`ejemplos.txt`), `informe.py` (genera este documento).
- `eval/` (predicciones y métricas del modelo en seen y heldout), `_days/*.rows.parquet` (filas de los días de validación con perp y banderas).
"""
(H / "ASIGNACION_RECORRIDO.md").write_text(doc, encoding="utf-8")
print(len(doc))
