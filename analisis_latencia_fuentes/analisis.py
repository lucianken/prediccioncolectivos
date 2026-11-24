"""
Analisis de la captura CABA vs CuandoSubo (OBA). Lee datos/captura_*.ndjson (el ultimo, o --archivo)
y escribe resultados.md (tablas) y resultados.json junto a este script.

Uso:  python analisis.py [--archivo datos/captura_XXXX.ndjson] [--sufijo _90min]  (escribe resultados<sufijo>.md/.json)
"""
import argparse, glob, json, math
from collections import defaultdict
from pathlib import Path
import numpy as np

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
SHAPES = RAIZ / "proyectoconsola" / "data" / "line_shapes"
V_DEFAULT = 4.0       # m/s si no hay velocidad estimable
V_MIN = 1.0           # por debajo de esto la velocidad media del coche no es confiable
MAX_PERP = 120.0      # m: descarta proyecciones lejos del shape
MAX_GAP_INTERP = 240  # s: maximo hueco entre fixes reales para interpolar la verdad
OUT = []


def p(*a):
    s = " ".join(str(x) for x in a)
    OUT.append(s)
    print(s)


def q(xs, nd=1):
    xs = np.asarray([x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))], float)
    if len(xs) == 0:
        return {"n": 0}
    return {"n": int(len(xs)), "p10": round(float(np.percentile(xs, 10)), nd), "p50": round(float(np.percentile(xs, 50)), nd),
            "p90": round(float(np.percentile(xs, 90)), nd), "min": round(float(xs.min()), nd), "max": round(float(xs.max()), nd)}


def qrow(name, d):
    if d["n"] == 0:
        return "| %s | 0 | - | - | - | - | - |" % name
    return "| %s | %d | %s | %s | %s | %s | %s |" % (name, d["n"], d["p10"], d["p50"], d["p90"], d["min"], d["max"])


HDR = "| métrica | n | p10 | p50 | p90 | min | max |\n|---|---|---|---|---|---|---|"


def hav(lat1, lon1, lat2, lon2):
    R = 6371000.0
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ---------------- shapes ----------------
LAT0 = -34.6
KX = 111320.0 * math.cos(math.radians(LAT0))
KY = 110574.0


def xy(lat, lon):
    return (lon + 58.4) * KX, (lat - LAT0) * KY


class Shape:
    def __init__(self, name, pts):
        a = np.array([xy(la, lo) for la, lo in pts])
        self.name = name
        self.A = a[:-1]
        self.B = a[1:]
        d = self.B - self.A
        self.L = np.hypot(d[:, 0], d[:, 1])
        self.cum = np.concatenate([[0], np.cumsum(self.L)])
        self.D = d

    def project(self, lat, lon):
        px, py = xy(lat, lon)
        P = np.array([px, py])
        L2 = np.maximum(self.L ** 2, 1e-9)
        t = np.clip(((P - self.A) * self.D).sum(1) / L2, 0, 1)
        C = self.A + self.D * t[:, None]
        dist = np.hypot(*(C - P).T)
        i = int(np.argmin(dist))
        return float(self.cum[i] + t[i] * self.L[i]), float(dist[i])

    def point(self, s):
        s = min(max(s, 0), self.cum[-1])
        i = int(np.searchsorted(self.cum, s, side="right") - 1)
        i = min(max(i, 0), len(self.L) - 1)
        t = (s - self.cum[i]) / max(self.L[i], 1e-9)
        return self.A[i] + self.D[i] * t


def load_shapes():
    out = {}
    for ln in ("39", "168"):
        d = json.loads((SHAPES / (ln + ".json")).read_text(encoding="utf8"))
        out[ln] = [Shape("%s|%s" % (r.get("shortName"), r["name"].split(":", 1)[-1].strip()), r["points"]) for r in d["ramales"]]
    return out


# ---------------- carga ----------------
def cargar(path):
    recs = [json.loads(l) for l in open(path, encoding="utf8") if l.strip()]
    ntp = next((r for r in recs if r["src"] == "ntp"), {})
    off = ntp.get("offset_s", 0.0)  # remoto - local: tiempo_real = local + off
    return recs, ntp, off


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archivo")
    ap.add_argument("--sufijo", default="")
    a = ap.parse_args()
    path = a.archivo or sorted(glob.glob(str(AQUI / "datos" / "captura_*.ndjson")))[-1]
    recs, ntp, off = cargar(path)
    polls = [r for r in recs if r["src"] in ("caba", "oba") and "t_recv" in r]
    polls.sort(key=lambda r: r["t_recv"])
    J = {"archivo": Path(path).name, "ntp_offset_s": off}
    p("# Resultados automáticos (analisis.py)\n")
    p("Archivo: `%s`" % Path(path).name)
    p("Offset NTP (remoto - local): %+.4f s; muestras: %s. Todas las horas locales se corrigen como t_real = t_local + offset.\n" % (off, ntp.get("offsets_s")))

    # ---- 1) fixes únicos por id y fuente ----
    # fixes[src][id] = {ts: dict(lat,lon,recv,poll_idx,line)}
    fixes = {"caba": defaultdict(dict), "oba": defaultdict(dict)}
    first_poll = {}       # (src, agency) -> idx del primer poll
    seen_before = defaultdict(set)  # (src) -> ids vistos en polls previos (por poll)
    poll_count = defaultdict(int)
    first_ids = {}        # (src, id) -> idx de poll de primera aparicion
    for r in polls:
        if r.get("http_status") != 200 or not r.get("vehicles"):
            continue
        key = (r["src"], r.get("agency"))
        if key not in first_poll:
            first_poll[key] = poll_count[key]
        k = poll_count[key]
        poll_count[key] += 1
        for v in r["vehicles"]:
            ts = round(v["ts_gps"], 3)
            if (r["src"], v["id"]) not in first_ids:
                first_ids[(r["src"], v["id"])] = (key, k)
            d = fixes[r["src"]][v["id"]]
            if ts not in d:
                d[ts] = {"lat": v["lat"], "lon": v["lon"], "recv": r["t_recv"] + off, "key": key, "k": k,
                         "line": v["line"], "server": r.get("server_time")}
    n_ok = {k: v for k, v in poll_count.items()}
    p("## Polls válidos\n")
    for k, v in sorted(n_ok.items(), key=str):
        p("- %s agencia=%s: %d respuestas válidas" % (k[0], k[1], v))
    inc = [r for r in recs if r["src"] == "incidente"]
    fin = next((r for r in recs if r["src"] == "fin"), {})
    p("- Requests OBA en esta captura: %s; incidentes WAF/anomalías: %d (%s)\n" % (fin.get("n_oba_requests"), len(inc), [i.get("detalle") for i in inc]))
    sin_gps = set()
    for r in polls:
        if r["src"] == "oba":
            sin_gps.update(r.get("sin_gps", []))
    p("- Coches OBA sin GPS/location (descartados): %d\n" % len(sin_gps))

    line_of = {}
    for src in fixes:
        for i, d in fixes[src].items():
            line_of[i] = next(iter(d.values()))["line"]

    ids_caba, ids_oba = set(fixes["caba"]), set(fixes["oba"])
    ids_both = ids_caba & ids_oba
    t_start = min(r["t_recv"] for r in polls) + off
    p("## 1-2) Cruce de fixes (mismo id, |Δts| <= 1 s)\n")
    p("Coches distintos vistos: CABA %d, OBA %d, en ambas %d (solo CABA %d, solo OBA %d).\n" % (len(ids_caba), len(ids_oba), len(ids_both), len(ids_caba - ids_oba), len(ids_oba - ids_caba)))
    cross = {}
    dist_all = []
    match_tab = []
    for ln in ("39", "168", "todas"):
        m = oc = co = 0
        dists, dts = [], []
        un_dt = []
        for i in ids_both:
            if ln != "todas" and line_of.get(i) != ln:
                continue
            fc, fo = fixes["caba"][i], fixes["oba"][i]
            used = set()
            for ts, x in sorted(fo.items()):
                if ts < t_start - 0.0:
                    pass
                best = min(fc, key=lambda t: abs(t - ts), default=None)
                if best is not None and abs(best - ts) <= 1.0:
                    m += 1
                    used.add(best)
                    dists.append(hav(x["lat"], x["lon"], fc[best]["lat"], fc[best]["lon"]))
                    dts.append(ts - best)
                else:
                    oc += 1
                    if best is not None:
                        un_dt.append(ts - best)
            co += len([t for t in fc if t not in used])
        cross[ln] = {"coinciden": m, "solo_oba": oc, "solo_caba": co, "dist_m": q(dists, 2), "dts": q(dts, 2), "oba_sin_par_dt_al_caba_mas_cercano": q(un_dt, 1)}
        match_tab.append("| %s | %d | %d | %d |" % (ln, m, oc, co))
        if ln == "todas":
            dist_all = dists
    p("Fixes (coches presentes en ambas fuentes). Un fix cuenta como coincidente si el mismo id tiene ts_gps a ±1 s en la otra fuente.\n")
    p("| línea | coinciden | solo OBA | solo CABA |\n|---|---|---|---|")
    for l in match_tab:
        p(l)
    p("\nDistancia entre posiciones de fixes coincidentes (m) y Δts (OBA − CABA, s):\n")
    p(HDR)
    for ln in ("39", "168", "todas"):
        p(qrow("dist m (%s)" % ln, cross[ln]["dist_m"]))
        p(qrow("Δts s (%s)" % ln, cross[ln]["dts"]))
    p("\nFixes de OBA sin par en CABA: Δts al fix CABA más cercano del mismo coche (s):\n")
    p(HDR)
    for ln in ("39", "168", "todas"):
        p(qrow("OBA sin par (%s)" % ln, cross[ln]["oba_sin_par_dt_al_caba_mas_cercano"]))
    p("")
    J["cruce"] = cross

    # ---- 2b) cruce por posición (mismo fix con distinto timestamp) ----
    p("## 2b) Cruce por posición (mismo id, posición idéntica ≤ 2 m, sin importar ts_gps)\n")
    p("Sólo pares inequívocos: exactamente un fix CABA y un fix OBA del coche dentro de 2 m entre sí (se descartan coches detenidos con posiciones repetidas). "
      "Δts = ts_gps(CABA) − ts_gps(OBA) para el mismo punto. Δrecv = primera recepción CABA − primera recepción OBA (negativo: CABA lo mostró antes); "
      "sólo fixes aparecidos después del primer poll de ambas fuentes.\n")
    pos = {}
    for ln in ("39", "168", "todas"):
        dts_, drc, tot_o, mat = [], [], 0, 0
        for i in ids_both:
            if ln != "todas" and line_of.get(i) != ln:
                continue
            fc, fo = fixes["caba"][i], fixes["oba"][i]
            for ts, x in fo.items():
                tot_o += 1
                cand_c = [t for t, y in fc.items() if hav(x["lat"], x["lon"], y["lat"], y["lon"]) <= 2.0]
                cand_o = [t for t, y in fo.items() if hav(x["lat"], x["lon"], y["lat"], y["lon"]) <= 2.0]
                if len(cand_c) == 1 and len(cand_o) == 1:
                    mat += 1
                    tc = cand_c[0]
                    dts_.append(tc - ts)
                    yc = fc[tc]
                    ko, kc = first_ids[("oba", i)][1], first_ids[("caba", i)][1]
                    if x["k"] > first_poll[x["key"]] and x["k"] > ko and yc["k"] > first_poll[yc["key"]] and yc["k"] > kc:
                        drc.append(yc["recv"] - x["recv"])
        pos[ln] = {"fixes_oba": tot_o, "pares_inequivocos": mat, "dts_caba_menos_oba": q(dts_, 1), "drecv_caba_menos_oba": q(drc, 1)}
        p("- %s: %d fixes OBA de coches comunes; pares inequívocos por posición: %d" % (ln, tot_o, mat))
    p("")
    p(HDR)
    for ln in ("39", "168", "todas"):
        p(qrow("Δts CABA−OBA (s) [%s]" % ln, pos[ln]["dts_caba_menos_oba"]))
        p(qrow("Δrecv CABA−OBA (s) [%s]" % ln, pos[ln]["drecv_caba_menos_oba"]))
    J["cruce_posicion"] = pos
    p("")

    # ---- 3) retraso de publicación ----
    p("## 3) Retraso de publicación (primera recepción − ts_gps, corregido por NTP)\n")
    p("Resolución: CABA se consulta cada 15 s, OBA cada 30 s por agencia: el valor observado es cota superior del retraso real, con error de hasta +15 s (CABA) / +30 s (OBA). "
      "Sólo fixes de coches ya vistos antes y que aparecen después del primer poll válido de esa fuente/agencia.\n")
    p(HDR)
    delay = {}
    for src in ("caba", "oba"):
        for ln in ("39", "168", "todas"):
            xs = []
            for i, d in fixes[src].items():
                if ln != "todas" and line_of.get(i) != ln:
                    continue
                key0, k0 = first_ids[(src, i)]
                for ts, x in d.items():
                    if x["k"] > first_poll[x["key"]] and x["k"] > k0:
                        xs.append(x["recv"] - ts)
            delay[(src, ln)] = q(xs)
            p(qrow("%s %s" % (src.upper(), ln), delay[(src, ln)]))
    J["retraso_publicacion"] = {"%s_%s" % k: v for k, v in delay.items()}
    p("\nEdad del dato en cada respuesta (server_time − ts_gps, s; independiente del reloj local):\n")
    p(HDR)
    age = {}
    for src in ("caba", "oba"):
        for ln in ("39", "168", "todas"):
            xs = []
            for r in polls:
                if r["src"] != src or not r.get("vehicles") or r.get("server_time") is None:
                    continue
                for v in r["vehicles"]:
                    if ln == "todas" or v["line"] == ln:
                        xs.append(r["server_time"] - v["ts_gps"])
            age[(src, ln)] = q(xs)
            p(qrow("%s %s" % (src.upper(), ln), age[(src, ln)]))
    J["edad_dato"] = {"%s_%s" % k: v for k, v in age.items()}
    p("")

    # ---- 4) cadencia ----
    p("## 4) Cadencia: intervalo entre fixes consecutivos del mismo coche (s)\n")
    p("Medida con fixes observados; un poll más espaciado que la cadencia real (OBA cada 30 s) puede saltear fixes y sobreestimar el intervalo.\n")
    p(HDR)
    cad = {}
    for src in ("caba", "oba"):
        for ln in ("39", "168", "todas"):
            xs = []
            for i, d in fixes[src].items():
                if ln != "todas" and line_of.get(i) != ln:
                    continue
                ts = sorted(d)
                xs += [b - a_ for a_, b in zip(ts, ts[1:])]
            cad[(src, ln)] = q(xs)
            p(qrow("%s %s" % (src.upper(), ln), cad[(src, ln)]))
    J["cadencia"] = {"%s_%s" % k: v for k, v in cad.items()}
    # cadencia usando la union de fuentes
    xs = []
    for i in ids_both:
        ts = sorted(set(fixes["caba"][i]) | set(fixes["oba"][i]))
        xs += [b - a_ for a_, b in zip(ts, ts[1:]) if b - a_ > 1.0]
    p(qrow("unión CABA+OBA (fixes separados >1 s)", q(xs)))
    p("")

    # ---- 6) relojes ----
    p("## 6) Reloj de los servidores\n")
    p("OBA: currentTime − (t_recv + offset NTP). CABA: header.timestamp es la generación del feed (no un reloj en vivo): "
      "su diferencia con t_recv es la edad del feed; el reloj sale del header HTTP Date (resolución 1 s).\n")
    p(HDR)
    clk = {}
    for name, sel, fn in (
        ("OBA currentTime − t_real (s)", "oba", lambda r: r["server_time"] - (r["t_recv"] + off)),
        ("OBA HTTP Date − t_real (s)", "oba", None),
        ("CABA header.timestamp − t_real (s) [edad del feed, negativo]", "caba", lambda r: r["server_time"] - (r["t_recv"] + off)),
        ("CABA HTTP Date − t_real (s)", "caba", None),
    ):
        xs = []
        for r in polls:
            if r["src"] != sel or r.get("http_status") != 200:
                continue
            if fn is not None:
                if r.get("server_time") is None:
                    continue
                xs.append(fn(r))
            else:
                if not r.get("http_date"):
                    continue
                from email.utils import parsedate_to_datetime
                xs.append(parsedate_to_datetime(r["http_date"]).timestamp() - (r["t_recv"] + off))
        clk[name] = q(xs, 2)
        p(qrow(name, clk[name]))
    J["relojes"] = clk
    p("\nFixes con ts_gps en el futuro (reloj a bordo adelantado):\n")
    fut = {}
    for src in ("caba", "oba"):
        tot = n_srv = n_loc = 0
        mx = 0.0
        for r in polls:
            if r["src"] != src or not r.get("vehicles") or r.get("server_time") is None:
                continue
            for v in r["vehicles"]:
                tot += 1
                if v["ts_gps"] > r["server_time"] + 0.5:
                    n_srv += 1
                    mx = max(mx, v["ts_gps"] - r["server_time"])
                if v["ts_gps"] > r["t_recv"] + off + 1.0:
                    n_loc += 1
        fut[src] = {"observaciones": tot, "ts>server_time": n_srv, "max_s": round(mx, 1), "ts>t_real": n_loc}
        p("- %s: %d observaciones; ts_gps > server_time: %d (máx %.1f s); ts_gps > hora real local: %d" % (src.upper(), tot, n_srv, mx, n_loc))
    J["futuro"] = fut
    p("")

    # ---- 5) extrapolación de OBA ----
    p("## 5) Extrapolación de OBA (tripStatus.position vs GPS real)\n")
    shapes = load_shapes()
    # fixes reales de la union por coche
    union = defaultdict(dict)
    for src in ("caba", "oba"):
        for i, d in fixes[src].items():
            for ts, x in d.items():
                union[i].setdefault(ts, (x["lat"], x["lon"]))
    obs = []  # respuestas OBA con trip
    for r in polls:
        if r["src"] == "oba" and r.get("http_status") == 200:
            for v in r["vehicles"]:
                if v.get("has_trip") and v.get("pred_lat") is not None:
                    obs.append((r, v))
    # elegir shape por (id, trip)
    groups = defaultdict(list)
    for r, v in obs:
        groups[(v["id"], v["trip_id"])].append((r, v))
    shape_of = {}
    for (i, trip), lst in groups.items():
        ln = lst[0][1]["line"]
        t0 = min(v["ts_gps"] for _, v in lst)
        t1 = max(r["server_time"] for r, _ in lst)
        pts = [(ts, la, lo) for ts, (la, lo) in sorted(union[i].items()) if t0 - 1 <= ts <= t1 + 1]
        best, bs = None, 1e18
        for sh in shapes[ln]:
            proj = [sh.project(la, lo) for _, la, lo in pts]
            perps = [pp for _, pp in proj]
            sc = float(np.median(perps)) if perps else 1e9
            sv = [s for s, _ in proj]
            if len(sv) >= 2 and sv[-1] - sv[0] < -30:
                sc += 500
            if sc < bs:
                best, bs = sh, sc
        shape_of[(i, trip)] = (best, bs)
    # velocidad por coche (progreso medio sobre el shape elegido)
    vel = {}
    for (i, trip), (sh, sc) in shape_of.items():
        if sh is None:
            continue
        ts_s = sorted((ts, (x["lat"], x["lon"])) for ts, x in fixes["oba"].get(i, {}).items())
        pr = [(ts, sh.project(la, lo)[0]) for ts, (la, lo) in ts_s]
        if len(pr) >= 2 and pr[-1][0] > pr[0][0]:
            vv = (pr[-1][1] - pr[0][1]) / (pr[-1][0] - pr[0][0])
            # velocidad por tramos en movimiento
            seg = [(pr[k + 1][1] - pr[k][1]) / (pr[k + 1][0] - pr[k][0]) for k in range(len(pr) - 1) if pr[k + 1][0] - pr[k][0] > 5]
            seg = [x for x in seg if x > 0.5]
            vel[(i, trip)] = {"media": vv, "mov": float(np.median(seg)) if seg else None}
    rows = []
    desc = defaultdict(int)
    for r, v in obs:
        sh, sc = shape_of.get((v["id"], v["trip_id"]), (None, None))
        if sh is None:
            desc["sin shape"] += 1
            continue
        sg, pg = sh.project(v["lat"], v["lon"])
        sp, pp = sh.project(v["pred_lat"], v["pred_lon"])
        if pg > MAX_PERP or pp > MAX_PERP:
            desc["perp>%dm" % MAX_PERP] += 1
            continue
        vv = vel.get((v["id"], v["trip_id"]), {})
        vm = vv.get("media")
        if vm is not None and vm >= V_MIN:
            vs, vsrc = vm, "media"
        else:
            vs, vsrc = V_DEFAULT, "default"
        T = r["server_time"]
        age_ = T - v["ts_gps"]
        # verdad interpolada en T
        def verdad(base):
            fx_ = {ts: (x["lat"], x["lon"]) for ts, x in fixes[base].get(v["id"], {}).items()}
            tl = sorted(fx_)
            prev = [t for t in tl if t <= T]
            nxt = [t for t in tl if t > T]
            if prev and nxt:
                t_a, t_b = prev[-1], nxt[0]
                if t_b - t_a <= MAX_GAP_INTERP:
                    s_a = sh.project(*fx_[t_a])[0]
                    s_b = sh.project(*fx_[t_b])[0]
                    return s_a + (s_b - s_a) * (T - t_a) / (t_b - t_a)
            return None
        s_true = verdad("oba")
        s_true_c = verdad("caba")
        rows.append({"id": v["id"], "line": v["line"], "d_m": sp - sg, "vs": vs, "vsrc": vsrc, "age": age_, "sched": v.get("sched_dev"),
                     "err_pred": None if s_true is None else sp - s_true, "err_gps": None if s_true is None else sg - s_true,
                     "err_pred_c": None if s_true_c is None else sp - s_true_c, "err_gps_c": None if s_true_c is None else sg - s_true_c,
                     "dist_along": v.get("dist_along"), "pred_perp": pp})
    p("Respuestas OBA con trip y `position`: %d; usadas: %d; descartadas: %s." % (len(obs), len(rows), dict(desc)))
    p("Shape elegido por (coche, trip): el de menor mediana de distancia perpendicular de sus fixes reales (penalizando avance negativo). "
      "Velocidad del coche = progreso medio sobre el shape entre su primer y último fix real de la captura si es ≥ %.1f m/s; si no, %.1f m/s (por defecto, indicado en la columna de abajo).\n" % (V_MIN, V_DEFAULT))
    ext = {}
    p(HDR)
    for ln in ("39", "168", "todas"):
        R = [x for x in rows if ln == "todas" or x["line"] == ln]
        ext[ln] = {
            "delta_m": q([x["d_m"] for x in R]),
            "delta_s": q([x["d_m"] / x["vs"] for x in R]),
            "usa_vel_default": sum(1 for x in R if x["vsrc"] == "default"),
            "edad_s": q([x["age"] for x in R]),
            "sched_dev_s": q([x["sched"] for x in R if x["sched"] is not None]),
            "vel_implicita_m_s": q([x["d_m"] / x["age"] for x in R if x["age"] > 20], 2),
            "err_pred_m": q([x["err_pred"] for x in R if x["err_pred"] is not None]),
            "err_pred_s": q([x["err_pred"] / x["vs"] for x in R if x["err_pred"] is not None]),
            "err_gps_m": q([x["err_gps"] for x in R if x["err_gps"] is not None]),
            "err_gps_s": q([x["err_gps"] / x["vs"] for x in R if x["err_gps"] is not None]),
            "err_pred_m_baseCABA": q([x["err_pred_c"] for x in R if x["err_pred_c"] is not None]),
            "err_pred_s_baseCABA": q([x["err_pred_c"] / x["vs"] for x in R if x["err_pred_c"] is not None]),
            "err_gps_m_baseCABA": q([x["err_gps_c"] for x in R if x["err_gps_c"] is not None]),
        }
        e = [x for x in R if x["err_pred"] is not None]
        ext[ln]["pred_mejor_que_ultimo_gps"] = (sum(1 for x in e if abs(x["err_pred"]) < abs(x["err_gps"])), len(e))
        # correlacion sched_dev vs delta
        ss = [(x["sched"], x["d_m"]) for x in R if x["sched"] is not None]
        ext[ln]["corr_sched_delta"] = round(float(np.corrcoef(*zip(*ss))[0, 1]), 2) if len(ss) > 5 else None
        p(qrow("Δ pred−GPS (m) [%s]" % ln, ext[ln]["delta_m"]))
        p(qrow("Δ pred−GPS (s) [%s]" % ln, ext[ln]["delta_s"]))
        p(qrow("edad del GPS en la respuesta (s) [%s]" % ln, ext[ln]["edad_s"]))
        p(qrow("velocidad implícita Δm/edad (m/s) [%s]" % ln, ext[ln]["vel_implicita_m_s"]))
        p(qrow("scheduleDeviation (s) [%s]" % ln, ext[ln]["sched_dev_s"]))
        p(qrow("error pred vs GPS real a la misma hora (m) [%s]" % ln, ext[ln]["err_pred_m"]))
        p(qrow("error pred vs GPS real a la misma hora (s) [%s]" % ln, ext[ln]["err_pred_s"]))
        p(qrow("error del último GPS vs GPS real a la misma hora (m) [%s]" % ln, ext[ln]["err_gps_m"]))
        p(qrow("error del último GPS vs GPS real a la misma hora (s) [%s]" % ln, ext[ln]["err_gps_s"]))
        p(qrow("(base ts CABA) error pred vs real (m) [%s]" % ln, ext[ln]["err_pred_m_baseCABA"]))
        p(qrow("(base ts CABA) error pred vs real (s) [%s]" % ln, ext[ln]["err_pred_s_baseCABA"]))
        p(qrow("(base ts CABA) error del último GPS vs real (m) [%s]" % ln, ext[ln]["err_gps_m_baseCABA"]))
    p("\nPositivo = pred adelante (en el sentido de marcha) del GPS / de la posición real. La verdad a la hora `currentTime` se interpola en el shape entre el fix real anterior y el siguiente (fixes de OBA con su ts; variante: fixes de CABA con su ts, +29 s respecto de OBA); sólo si el hueco es ≤ %d s.\n" % MAX_GAP_INTERP)
    for ln in ("39", "168", "todas"):
        e = ext[ln]
        p("- %s: pred más cercana a la verdad que el último GPS en %d de %d respuestas; respuestas con velocidad por defecto: %d; correlación(scheduleDeviation, Δm) = %s" % (
            ln, e["pred_mejor_que_ultimo_gps"][0], e["pred_mejor_que_ultimo_gps"][1], e["usa_vel_default"], e["corr_sched_delta"]))
    J["extrapolacion"] = ext
    J["descartes_extrapolacion"] = dict(desc)
    (AQUI / ("resultados%s.md" % a.sufijo)).write_text("\n".join(OUT) + "\n", encoding="utf8")
    (AQUI / ("resultados%s.json" % a.sufijo)).write_text(json.dumps(J, ensure_ascii=False, indent=1, default=str), encoding="utf8")


if __name__ == "__main__":
    main()
