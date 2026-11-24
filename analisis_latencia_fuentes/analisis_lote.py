"""
Estampado por lote de CABA: Δts del mismo punto, firmas de lote y prueba de plausibilidad de velocidades.
Corre sobre cualquier captura (datos/captura_*.ndjson, la última por defecto).

Uso:  python analisis_lote.py [--archivo datos/captura_XXXX.ndjson] [--sufijo _90min]
Escribe resultados_lote<sufijo>.md y resultados_lote<sufijo>.json.
La parte de retraso de publicación y extrapolación de OBA está en analisis.py (mismo --archivo/--sufijo).
"""
import argparse, glob, json, math
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
from analisis import Shape, load_shapes, hav, q, qrow, HDR, cargar

AQUI = Path(__file__).resolve().parent
OUT = []
BLOQUE = 900          # s: bloques de 15 min
MAX_PERP = 120.0
V_IMPOSIBLE = 25.0    # m/s
MOV_MIN_M = 20.0      # m: intervalo "en movimiento"


def p(*a):
    s = " ".join(str(x) for x in a)
    OUT.append(s)
    print(s)


def pct(n, d):
    return "%.1f %%" % (100.0 * n / d) if d else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archivo")
    ap.add_argument("--sufijo", default="")
    a = ap.parse_args()
    path = a.archivo or sorted(glob.glob(str(AQUI / "datos" / "captura_*.ndjson")))[-1]
    recs, ntp, off = cargar(path)
    polls = sorted([r for r in recs if r["src"] in ("caba", "oba") and r.get("http_status") == 200 and r.get("vehicles")],
                   key=lambda r: r["t_recv"])
    J = {"archivo": Path(path).name}
    t0 = polls[0]["t_recv"] + off
    t1 = polls[-1]["t_recv"] + off
    fin = next((r for r in recs if r["src"] == "fin"), {})
    p("# Estampado por lote, Δts y plausibilidad (analisis_lote.py)\n")
    p("Archivo: `%s`. Primer poll %s, último %s (hora local, corregida por NTP %+.3f s). Duración %.1f min. Requests OBA: %s; incidentes: %s.\n" % (
        Path(path).name, __import__("datetime").datetime.fromtimestamp(t0).strftime("%Y-%m-%d %H:%M:%S"),
        __import__("datetime").datetime.fromtimestamp(t1).strftime("%H:%M:%S"), off, (t1 - t0) / 60, fin.get("n_oba_requests"), fin.get("n_waf")))
    J["inicio"], J["fin"], J["oba_requests"], J["waf"] = t0, t1, fin.get("n_oba_requests"), fin.get("n_waf")

    # fixes únicos por fuente/coche
    fixes = {"caba": defaultdict(dict), "oba": defaultdict(dict)}
    line_of = {}
    for r in polls:
        for v in r["vehicles"]:
            ts = round(v["ts_gps"], 3)
            line_of.setdefault(v["id"], v["line"])
            fixes[r["src"]][v["id"]].setdefault(ts, {"lat": v["lat"], "lon": v["lon"], "speed": v.get("speed")})
    ids_both = set(fixes["caba"]) & set(fixes["oba"])

    # ---------- b) firmas de lote ----------
    p("## b) Firmas de lote\n")
    p("### Por respuesta (ts distintos vs coches)\n")
    p("| fuente | respuestas | coches/resp p50 | ts distintos/resp p10 / p50 / p90 | distintos / coches p50 | mayor grupo con mismo ts (% de la respuesta) p50 / p90 | coches con dato de ≤ 120 s de edad p50 | ts distintos entre esos p50 |\n|---|---|---|---|---|---|---|---|")
    firm = {}
    for src in ("caba", "oba"):
        n, nd, ratio, top, nf, ndf = [], [], [], [], [], []
        for r in polls:
            if r["src"] != src:
                continue
            ts = [round(v["ts_gps"], 3) for v in r["vehicles"]]
            c = Counter(ts)
            n.append(len(ts)); nd.append(len(c)); ratio.append(len(c) / len(ts)); top.append(c.most_common(1)[0][1] / len(ts))
            fr = [t for t in ts if (r['server_time'] - t) <= 120]
            nf.append(len(fr)); ndf.append(len(set(fr)))
        f = {"respuestas": len(n), "coches_p50": float(np.median(n)), "distintos": q(nd, 0), "ratio_p50": round(float(np.median(ratio)), 3),
             "mayor_grupo_p50": round(float(np.median(top)), 3), "mayor_grupo_p90": round(float(np.percentile(top, 90)), 3),
             "frescos_p50": float(np.median(nf)), "distintos_frescos_p50": float(np.median(ndf))}
        firm[src] = f
        p("| %s | %d | %g | %g / %g / %g | %.3f | %.0f %% / %.0f %% | %g | %g |" % (
            src.upper(), f["respuestas"], f["coches_p50"], f["distintos"]["p10"], f["distintos"]["p50"], f["distintos"]["p90"], f["ratio_p50"],
            100 * f["mayor_grupo_p50"], 100 * f["mayor_grupo_p90"], f["frescos_p50"], f["distintos_frescos_p50"]))
    p("")
    p("### Sobre puntos únicos (coche, ts) por fuente\n")
    p("| fuente | puntos únicos | con milisegundos | pares (sobre ts enteros) | pares (sobre floor de todos) | en segundos 40-59 del minuto |\n|---|---|---|---|---|---|")
    mods = {}
    for src in ("caba", "oba"):
        allts = [ts for d in fixes[src].values() for ts in d]
        n = len(allts)
        ms = sum(1 for t in allts if abs(t - round(t)) > 1e-6)
        ent = [int(round(t)) for t in allts if abs(t - round(t)) <= 1e-6]
        par_e = sum(1 for t in ent if t % 2 == 0)
        par_f = sum(1 for t in allts if int(math.floor(t)) % 2 == 0)
        in40 = sum(1 for t in allts if int(math.floor(t)) % 60 >= 40)
        m60 = Counter(int(math.floor(t)) % 60 for t in allts)
        mods[src] = m60
        p("| %s | %d | %s | %s | %s | %s |" % (src.upper(), n, pct(ms, n), pct(par_e, len(ent)), pct(par_f, n), pct(in40, n)))
        firm[src].update({"puntos": n, "con_ms": ms, "pares_enteros": [par_e, len(ent)], "pares_floor": [par_f, n], "seg40_59": [in40, n],
                          "top_segundos": [(k, v) for k, v in m60.most_common(10)]})
    p("")
    p("Reparto por segundo del minuto (ts mod 60), % por franja de 10 s (uniforme = 16.7 %):\n")
    p("| fuente | 0-9 | 10-19 | 20-29 | 30-39 | 40-49 | 50-59 | top 6 segundos (% c/u; uniforme 1.7 %) |\n|---|---|---|---|---|---|---|---|")
    for src in ("caba", "oba"):
        m60 = mods[src]
        tot = sum(m60.values())
        fr = [sum(m60[s] for s in range(b, b + 10)) for b in range(0, 60, 10)]
        top = ", ".join("%d: %.1f" % (k, 100 * v / tot) for k, v in m60.most_common(6))
        p("| %s | %s | %s |" % (src.upper(), " | ".join("%.1f" % (100 * x / tot) for x in fr), top))
    p("")
    J["firmas_lote"] = firm
    p("Evolución de la firma por bloque de 10 min (según hora de primera recepción del punto; pares / milisegundos / segundos 40-59, sobre puntos únicos):\n")
    p("| bloque (min) | CABA n | CABA pares | CABA ms | CABA 40-59 | OBA n | OBA pares | OBA ms | OBA 40-59 |\n|---|---|---|---|---|---|---|---|---|")
    por = {"caba": defaultdict(list), "oba": defaultdict(list)}
    for r in polls:
        pass
    visto = {"caba": set(), "oba": set()}
    for r in polls:
        for v in r["vehicles"]:
            k_ = (v["id"], round(v["ts_gps"], 3))
            if k_ not in visto[r["src"]]:
                visto[r["src"]].add(k_)
                por[r["src"]][int((r["t_recv"] + off - t0) // 600)].append(v["ts_gps"])
    J["firma_por_bloque"] = {}
    for b in range(int((t1 - t0) // 600) + 1):
        cols = []
        for src in ("caba", "oba"):
            L = por[src].get(b, [])
            if not L:
                cols += ["0", "-", "-", "-"]
                continue
            fl = [int(math.floor(t)) for t in L]
            cols += [str(len(L)), pct(sum(1 for f in fl if f % 2 == 0), len(L)), pct(sum(1 for t in L if abs(t - round(t)) > 1e-6), len(L)), pct(sum(1 for f in fl if f % 60 >= 40), len(L))]
        J["firma_por_bloque"][b] = cols
        p("| %d-%d | %s |" % (b * 10, (b + 1) * 10, " | ".join(cols)))
    p("")

    # ---------- a) Δts mismo punto ----------
    p("## a) ts_CABA − ts_OBA para el mismo punto\n")
    p("Match por id y posición ≤ 2 m, sólo pares inequívocos (un solo fix CABA y un solo fix OBA del coche dentro de 2 m entre sí; se excluyen coches detenidos con posiciones repetidas). "
      "Bloques de 15 min contados desde el primer poll, según el ts de OBA del punto.\n")
    matched = defaultdict(list)   # id -> [(to, tc, lat, lon)]
    for i in ids_both:
        fc, fo = fixes["caba"][i], fixes["oba"][i]
        for to, x in fo.items():
            cc = [t for t, y in fc.items() if hav(x["lat"], x["lon"], y["lat"], y["lon"]) <= 2.0]
            co = [t for t, y in fo.items() if hav(x["lat"], x["lon"], y["lat"], y["lon"]) <= 2.0]
            if len(cc) == 1 and len(co) == 1:
                matched[i].append((to, cc[0], x["lat"], x["lon"]))
    pairs = [(line_of[i], to, tc - to) for i, L in matched.items() for to, tc, _, _ in L]
    tot_oba = sum(len(fixes["oba"][i]) for i in ids_both)
    p("Pares inequívocos: %d de %d fixes OBA de coches comunes (%s).\n" % (len(pairs), tot_oba, pct(len(pairs), tot_oba)))
    J["delta_ts"] = {"pares": len(pairs), "fixes_oba_comunes": tot_oba}
    p(HDR)
    for ln in ("39", "168", "todas"):
        xs = [d for l, _, d in pairs if ln == "todas" or l == ln]
        J["delta_ts"][ln] = q(xs, 1)
        p(qrow("Δts s [%s]" % ln, J["delta_ts"][ln]))
    p("\nPor bloque de 15 min (n, p10 / p50 / p90 en s):\n")
    nb = int((t1 - t0) // BLOQUE) + 1
    p("| bloque | " + " | ".join("39" if k == 0 else "168" for k in range(2)) + " | ambas |\n|---|---|---|---|")
    J["delta_ts"]["bloques"] = []
    for b in range(nb):
        row, jr = [], {"bloque": b}
        for ln in ("39", "168", "todas"):
            xs = [d for l, to, d in pairs if (ln == "todas" or l == ln) and int((to - t0) // BLOQUE) == b]
            s = q(xs, 1)
            jr[ln] = s
            row.append("n=%d, %s / %s / %s" % (s["n"], s.get("p10", "-"), s.get("p50", "-"), s.get("p90", "-")) if s["n"] else "n=0")
        J["delta_ts"]["bloques"].append(jr)
        p("| %d (min %d-%d) | %s |" % (b, b * 15, min((b + 1) * 15, int((t1 - t0) // 60)), " | ".join(row)))
    p("\nPor bloque de 5 min (ambas líneas; hora local de inicio según ts de OBA; Δts ≥ 20 s = régimen desfasado):\n")
    p("| inicio | n | p10 / p50 / p90 | % con Δts ≥ 20 s |\n|---|---|---|---|")
    J["delta_ts"]["bloques5"] = []
    for b in range(int((t1 - t0) // 300) + 1):
        xs = [d for _, to, d in pairs if int((to - t0) // 300) == b]
        if xs:
            s5 = q(xs, 1)
            hh = __import__("datetime").datetime.fromtimestamp(t0 + b * 300).strftime("%H:%M")
            fr = sum(1 for x in xs if x >= 20)
            J["delta_ts"]["bloques5"].append({"inicio": hh, **s5, "n_desfasado": fr})
            p("| %s | %d | %s / %s / %s | %s |" % (hh, s5["n"], s5["p10"], s5["p50"], s5["p90"], pct(fr, len(xs))))
    p("\nHistograma por valor (Δts redondeado al segundo; sólo valores con ≥ 2 % de los pares):\n")
    for ln in ("39", "168", "todas"):
        xs = [int(round(d)) for l, _, d in pairs if ln == "todas" or l == ln]
        if not xs:
            continue
        c = Counter(xs)
        n = len(xs)
        w1 = sum(v for k, v in c.items() if 27 <= k <= 31)
        w2 = sum(v for k, v in c.items() if 55 <= k <= 61)
        top = ", ".join("%d s: %d (%.1f %%)" % (k, v, 100 * v / n) for k, v in sorted(c.items(), key=lambda kv: -kv[1]) if v / n >= 0.02)
        p("- %s (n=%d): %s. En 27-31 s: %s; en 55-61 s: %s; fuera de ambas ventanas: %s." % (
            ln, n, top, pct(w1, n), pct(w2, n), pct(n - w1 - w2, n)))
        J["delta_ts"].setdefault("hist", {})[ln] = {"n": n, "en_27_31": w1, "en_55_61": w2, "otros": n - w1 - w2, "top": c.most_common(12)}
    p("")

    # ---------- a2) retraso de publicación por régimen ----------
    p("### a2) Retraso de publicación (primera recepción − ts) y reparto de segundos por régimen\n")
    corte = None
    bl = J["delta_ts"]["bloques5"]
    for k in range(len(bl)):
        if all(b["n_desfasado"] / b["n"] < 0.5 for b in bl[k:]) and any(b["n_desfasado"] / b["n"] >= 0.5 for b in bl[:k]):
            hh, mm = bl[k]["inicio"].split(":")
            d0 = __import__("datetime").datetime.fromtimestamp(t0).replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            corte = d0.timestamp()
            break
    J["corte_regimen"] = corte
    if corte is None:
        p("No hay cambio de régimen en esta captura (Δts ≥ 20 s no pasa de mayoría a minoría).\n")
    else:
        p("Corte automático: primer bloque de 5 min a partir del cual < 50 %% de los pares tiene Δts ≥ 20 s y no vuelve: %s (hora local). A = antes del corte, B = desde el corte. Retraso: sólo fixes de coches ya vistos antes en esa fuente, aparecidos después del primer poll; cota superior con error de hasta +15 s (CABA) / +30 s (OBA) por la resolución de poll.\n" % (
            __import__("datetime").datetime.fromtimestamp(corte).strftime("%H:%M")))
        vistos_id, vistos_fix = set(), set()
        dly = defaultdict(list)
        mod = defaultdict(Counter)
        for r in polls:
            ph = "A" if r["t_recv"] + off < corte else "B"
            for v in r["vehicles"]:
                kf = (r["src"], v["id"], round(v["ts_gps"], 3))
                if kf in vistos_fix:
                    continue
                vistos_fix.add(kf)
                mod[(r["src"], ph)][int(math.floor(v["ts_gps"])) % 60] += 1
                if (r["src"], v["id"]) in vistos_id:
                    dly[(r["src"], ph)].append(r["t_recv"] + off - v["ts_gps"])
            for v in r["vehicles"]:
                vistos_id.add((r["src"], v["id"]))
        p(HDR)
        J["retraso_por_regimen"] = {}
        for src in ("caba", "oba"):
            for ph in ("A", "B"):
                s_ = q(dly[(src, ph)], 1)
                J["retraso_por_regimen"]["%s_%s" % (src, ph)] = s_
                p(qrow("retraso %s %s" % (src.upper(), ph), s_))
        p("\nSegundos del minuto (ts mod 60) más frecuentes por régimen (% de puntos únicos):\n")
        for src in ("caba", "oba"):
            for ph in ("A", "B"):
                m_ = mod[(src, ph)]
                tt = sum(m_.values())
                p("- %s %s (n=%d): %s; en 40-59: %s" % (src.upper(), ph, tt, ", ".join("%d: %.1f" % (k, 100 * v / tt) for k, v in m_.most_common(6)),
                                                       pct(sum(v for k, v in m_.items() if k >= 40), tt)))
                J.setdefault("mod60_por_regimen", {})["%s_%s" % (src, ph)] = m_.most_common(8)
        p("")

    # ---------- c) plausibilidad de velocidades ----------
    p("## c) Prueba de plausibilidad: velocidades entre fixes consecutivos con cada base de tiempo\n")
    shapes = load_shapes()

    def shape_for(i, pts):
        best, bs = None, 1e18
        for sh in shapes[line_of[i]]:
            perps = [sh.project(la, lo)[1] for la, lo in pts[::max(1, len(pts) // 25)]]
            sc = float(np.median(perps))
            if sc < bs:
                best, bs = sh, sc
        return best

    def dist(sh, a_, b_):
        if sh is not None:
            sa, pa = sh.project(*a_)
            sb, pb = sh.project(*b_)
            if pa <= MAX_PERP and pb <= MAX_PERP:
                return abs(sb - sa), True
        return hav(a_[0], a_[1], b_[0], b_[1]), False

    def resumen(nombre, ints):
        """ints: lista por coche de [(dist, dt, v_rep)] en orden temporal."""
        v_all = [d / dt for L in ints for d, dt, _ in L if dt > 0]
        n = len(v_all)
        imp = sum(1 for v in v_all if v > V_IMPOSIBLE)
        # ceros raros: intervalo ~sin movimiento (<1 m) entre dos intervalos en movimiento (>3 m/s)
        zr = z_tot = 0
        jit = []
        mov = []
        for L in ints:
            vs = [d / dt if dt > 0 else float("nan") for d, dt, _ in L]
            for k in range(1, len(L) - 1):
                if vs[k - 1] > 3 and vs[k + 1] > 3:
                    z_tot += 1
                    if L[k][0] < 1.0:
                        zr += 1
            for k in range(1, len(L)):
                if L[k][0] >= MOV_MIN_M and L[k - 1][0] >= MOV_MIN_M:
                    jit.append(abs(math.log(vs[k] / vs[k - 1])))
            mov += [v for (d, dt, _), v in zip(L, vs) if d >= MOV_MIN_M]
        mov = np.asarray(mov)
        mad = float(np.median(np.abs(mov - np.median(mov)))) * 1.4826 if len(mov) else float("nan")
        cvr = mad / float(np.median(mov)) if len(mov) else float("nan")
        rel = []
        for L in ints:
            for d, dt, vr in L:
                if vr is not None and vr > 3 and dt > 0 and d >= MOV_MIN_M:
                    rel.append(abs(d / dt - vr) / vr)
        r = {"intervalos": n, "imposibles": imp, "ceros_raros": [zr, z_tot], "mov": int(len(mov)), "mediana_v_mov": round(float(np.median(mov)), 2) if len(mov) else None,
             "CV_robusto": round(cvr, 3), "jitter_mediano_|Δln v|": round(float(np.median(jit)), 3) if jit else None, "n_jitter": len(jit),
             "err_rel_vs_speed_reportada_p50": round(float(np.median(rel)), 3) if rel else None, "n_rel": len(rel),
             "dt": q([dt for L in ints for _, dt, _ in L], 1)}
        p("| %s | %d | %d (%s) | %d / %d | %d | %s | %s | %s | %s |" % (
            nombre, n, imp, pct(imp, n), zr, z_tot, len(mov), r["mediana_v_mov"], r["CV_robusto"], r["jitter_mediano_|Δln v|"], r["err_rel_vs_speed_reportada_p50"]))
        return r

    cab = "| base | intervalos | v > %d m/s | ceros raros (n / candidatos) | intervalos en movimiento (≥ %d m) | v mediana mov. (m/s) | CV robusto (MAD/mediana) | jitter: mediana de \\|Δln v\\| entre intervalos en movimiento consecutivos | error relativo mediano contra `speed` reportada por CABA (v>3 m/s) |\n|---|---|---|---|---|---|---|---|---|" % (V_IMPOSIBLE, MOV_MIN_M)
    p("### c1) Mismos puntos, distinta base de tiempo (control: la distancia es idéntica, sólo cambia el reloj)\n")
    p("Puntos emparejados por posición (sección a), consecutivos por ts de OBA. Régimen \"desfasado\": ts_CABA − ts_OBA ≥ 20 s en ambos extremos del intervalo; \"alineado\": < 20 s en ambos (ver sección a: el desfase no es constante en el tiempo). Distancia sobre el shape si ambos puntos proyectan (≤ 120 m), si no haversine.\n")
    J["plausibilidad"] = {}

    def c1(nombre, acepta):
        ints_o, ints_c = [], []
        n_hav = n_sh = 0
        gan_c = gan_o = 0
        for i, L in matched.items():
            L = sorted(L)
            if len(L) < 2:
                continue
            sh = shape_for(i, [(x[2], x[3]) for x in L])
            io, ic = [], []
            for k in range(1, len(L)):
                if not acepta(L[k - 1], L[k]):
                    continue
                d, ok = dist(sh, (L[k - 1][2], L[k - 1][3]), (L[k][2], L[k][3]))
                n_sh += ok
                n_hav += (not ok)
                vr = fixes["caba"][i][L[k][1]].get("speed")
                vr0 = fixes["caba"][i][L[k - 1][1]].get("speed")
                vrep = None if vr is None or vr0 is None else (vr + vr0) / 2
                if vrep is not None and vrep > 3 and d >= MOV_MIN_M:
                    eo = abs(d / (L[k][0] - L[k - 1][0]) - vrep)
                    ec = abs(d / (L[k][1] - L[k - 1][1]) - vrep)
                    gan_c += ec < eo
                    gan_o += eo < ec
                io.append((d, L[k][0] - L[k - 1][0], vrep))
                ic.append((d, L[k][1] - L[k - 1][1], vrep))
            ints_o.append(io)
            ints_c.append(ic)
        p("**%s**\n" % nombre)
        p(cab)
        res = {"dist_shape": n_sh, "dist_haversine": n_hav, "gana_caba_vs_speed": gan_c, "gana_oba_vs_speed": gan_o}
        res["oba"] = resumen("ts OBA", ints_o)
        res["caba"] = resumen("ts CABA", ints_c)
        p("\nIntervalos con distancia sobre el shape: %d; por haversine: %d. Coches con intervalos: %d." % (n_sh, n_hav, sum(1 for x in ints_o if x)))
        p("Intervalos con `speed` reportada > 3 m/s y movimiento ≥ %d m: la base CABA queda más cerca de la `speed` reportada en %d, la base OBA en %d (empates excluidos)." % (MOV_MIN_M, gan_c, gan_o))
        dto = np.array([dt for L in ints_o for _, dt, _ in L])
        dtc = np.array([dt for L in ints_c for _, dt, _ in L])
        if len(dto):
            p("Intervalo de tiempo entre puntos consecutivos (p10 / p50 / p90): OBA %s; CABA %s.\n" % (
                " / ".join("%.1f" % np.percentile(dto, x) for x in (10, 50, 90)), " / ".join("%.1f" % np.percentile(dtc, x) for x in (10, 50, 90))))
        J["plausibilidad"][nombre] = res

    c1("c1-todos", lambda x, y: True)
    c1("c1-desfasado", lambda x, y: (x[1] - x[0]) >= 20 and (y[1] - y[0]) >= 20)
    c1("c1-alineado", lambda x, y: (x[1] - x[0]) < 20 and (y[1] - y[0]) < 20)
    p("### c2) Todos los fixes de cada fuente (con su propio ts)\n")
    p(cab)
    for src in ("oba", "caba"):
        ints = []
        for i, d in fixes[src].items():
            ts = sorted(d)
            if len(ts) < 3:
                continue
            pts = [(d[t]["lat"], d[t]["lon"]) for t in ts]
            sh = shape_for(i, pts)
            L = []
            for k in range(1, len(ts)):
                dd, _ = dist(sh, pts[k - 1], pts[k])
                vr = d[ts[k]].get("speed")
                vr0 = d[ts[k - 1]].get("speed")
                L.append((dd, ts[k] - ts[k - 1], None if (vr is None or vr0 is None or src == "oba") else (vr + vr0) / 2))
            ints.append(L)
        J["plausibilidad"]["c2_" + src] = resumen("%s (todos los fixes)" % src.upper(), ints)
    p("\n`speed` reportada sólo existe en CABA; en OBA la columna queda vacía. Un CV robusto o jitter menores indican velocidades más estables con esa base de tiempo; esto no prueba cuál reloj coincide con el tiempo real, sólo cuál es más coherente con un movimiento regular.\n")

    Path(AQUI / ("resultados_lote%s.md" % a.sufijo)).write_text("\n".join(OUT) + "\n", encoding="utf8")
    Path(AQUI / ("resultados_lote%s.json" % a.sufijo)).write_text(json.dumps(J, ensure_ascii=False, indent=1, default=str), encoding="utf8")


if __name__ == "__main__":
    main()
