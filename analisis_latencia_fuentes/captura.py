"""
Captura simultanea CABA (vehiclePositions, protobuf) + CuandoSubo (OBA vehicles-for-agency)
para las lineas 39 (agencia 56) y 168 (agencia 80). Escribe NDJSON crudo en datos/.

Uso:
  python captura.py                       # 10 min, tick 15 s
  python captura.py --minutes 10 --tick 15
  python captura.py --prueba              # 1 tick (1 CABA + 1 OBA 56), archivo prueba_*.ndjson

Reglas WAF de OBA: requests secuenciales, max 1 cada 15 s, sin redirects; respuesta
no-200/no-JSON -> pausa 120 s; segunda vez -> se aborta la captura OBA (CABA sigue).
Las credenciales se leen de proyectoconsola/.env.local y nunca se escriben.
"""
import argparse, json, re, subprocess, sys, time
from datetime import datetime, date
from pathlib import Path
import requests
from google.transit import gtfs_realtime_pb2

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
ENV = RAIZ / "proyectoconsola" / ".env.local"
LABEL_MAP = RAIZ / "proyectoconsola" / "LABEL_LINE_MAP.json"
CABA_URL = "https://apitransporte.buenosaires.gob.ar/colectivos/vehiclePositions"
OBA_URL = "https://cuandosubo.sube.gob.ar/onebusaway-api-webapp/api/where/vehicles-for-agency/{ag}.json"
AGENCY_LINE = {"56": "39", "80": "168"}
OBA_MIN_GAP = 15.0
WAF_PAUSE = 120.0


def leer_env():
    env = {}
    for ln in ENV.read_text(encoding="utf8").splitlines():
        if "=" in ln and not ln.lstrip().startswith("#"):
            k, v = ln.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENVV = leer_env()
SECRETOS = [v for v in ENVV.values() if v]


def redact(s):
    s = str(s)
    for x in SECRETOS:
        s = s.replace(x, "<REDACTED>")
    return s


def suffix_map():
    d = json.loads(LABEL_MAP.read_text(encoding="utf8"))
    hoy = date.today().isoformat()
    out = {}
    for ln in ("39", "168"):
        for s in d["lines"][ln]["suffixes"]:
            if (s.get("from") or "0000") <= hoy and (s.get("to") is None or hoy <= s["to"]):
                out[s["suffix"]] = ln
    return out


def ntp():
    res = {"src": "ntp", "t_local": time.time(), "raw": [], "offsets_s": []}
    try:
        r = subprocess.run(["w32tm", "/stripchart", "/computer:time.windows.com", "/samples:3", "/dataonly"],
                           capture_output=True, text=True, timeout=60)
        for ln in r.stdout.splitlines():
            res["raw"].append(ln)
            m = re.search(r",\s*([+-]\d+\.\d+)s", ln)
            if m:
                res["offsets_s"].append(float(m.group(1)))
        res["note"] = "w32tm stripchart: offset = reloj remoto menos reloj local (positivo = local atrasado)"
    except Exception as e:
        res["error"] = redact(e)
    if res["offsets_s"]:
        xs = sorted(res["offsets_s"])
        res["offset_s"] = xs[len(xs) // 2]
    return res


def get_caba(sess, smap, oba_ids):
    t_send = time.time()
    rec = {"src": "caba", "t_send": t_send, "url": CABA_URL + "?client_id=<REDACTED>&client_secret=<REDACTED>"}
    try:
        r = sess.get(CABA_URL, params={"client_id": ENVV["BA_API_CLIENT_ID"], "client_secret": ENVV["BA_API_CLIENT_SECRET"]},
                     timeout=30, allow_redirects=False)
        rec["t_recv"] = time.time()
        rec["http_status"] = r.status_code
        rec["http_date"] = r.headers.get("Date")
        if r.status_code != 200:
            rec["vehicles"] = []
            return rec
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(r.content)
        rec["server_time"] = feed.header.timestamp
        rec["n_total"] = len(feed.entity)
        vs = []
        for e in feed.entity:
            if not e.HasField("vehicle"):
                continue
            v = e.vehicle
            label = v.vehicle.label or ""
            vid = v.vehicle.id
            suf = label.rsplit("-", 1)[-1] if "-" in label else ""
            linea = smap.get(suf)
            if linea is None:
                linea = oba_ids.get(vid)
            if linea is None:
                continue
            vs.append({"id": vid, "label": label, "line": linea, "ts_gps": v.timestamp,
                       "lat": round(v.position.latitude, 6), "lon": round(v.position.longitude, 6),
                       "speed": round(v.position.speed, 2)})
        rec["vehicles"] = vs
    except Exception as e:
        rec["t_recv"] = time.time()
        rec["error"] = redact(e)
        rec["vehicles"] = []
    return rec


def get_oba(sess, ag):
    """Devuelve (rec, ok). ok=False si respuesta anomala (posible WAF)."""
    t_send = time.time()
    rec = {"src": "oba", "agency": ag, "t_send": t_send,
           "url": OBA_URL.format(ag=ag) + "?key=<REDACTED>"}
    try:
        r = sess.get(OBA_URL.format(ag=ag), params={"key": ENVV["CUANDOSUBO_API_KEY"]},
                     timeout=30, allow_redirects=False)
        rec["t_recv"] = time.time()
        rec["http_status"] = r.status_code
        rec["http_date"] = r.headers.get("Date")
        j = None
        if r.status_code == 200:
            try:
                j = r.json()
            except Exception:
                j = None
        if j is None or "data" not in j:
            rec["vehicles"] = []
            rec["anomalia"] = "status=%s content-type=%s" % (r.status_code, r.headers.get("Content-Type"))
            return rec, False
        rec["server_time"] = j["currentTime"] / 1000.0
        vs = []
        for it in j["data"]["list"]:
            vid = it["vehicleId"].split("_", 1)[-1]
            ts = it.get("tripStatus")
            if not it.get("location") or not it.get("lastUpdateTime"):
                rec.setdefault("sin_gps", []).append(vid)
                continue
            d = {"id": vid, "label": (ts or {}).get("vehicleLabel", ""), "line": AGENCY_LINE[ag],
                 "ts_gps": it["lastUpdateTime"] / 1000.0,
                 "lat": it["location"]["lat"], "lon": it["location"]["lon"],
                 "trip_id": it.get("tripId", ""), "has_trip": bool(ts)}
            if ts:
                p = ts.get("position") or {}
                d.update(pred_lat=p.get("lat"), pred_lon=p.get("lon"),
                         dist_along=ts.get("distanceAlongTrip"), total_dist=ts.get("totalDistanceAlongTrip"),
                         sched_dev=ts.get("scheduleDeviation"), predicted=ts.get("predicted"))
            vs.append(d)
        rec["vehicles"] = vs
        return rec, True
    except Exception as e:
        rec["t_recv"] = time.time()
        rec["error"] = redact(e)
        rec["vehicles"] = []
        rec["error_parseo"] = True
        try:
            rec["raw_head"] = redact(r.text[:3000])
        except Exception:
            pass
        return rec, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--tick", type=float, default=15)
    ap.add_argument("--prueba", action="store_true")
    ap.add_argument("--max-oba", type=int, default=45)
    a = ap.parse_args()
    if a.tick < OBA_MIN_GAP:
        sys.exit("tick < 15 s no permitido (WAF de OBA)")
    smap = suffix_map()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = AQUI / "datos" / (("prueba_" if a.prueba else "captura_") + stamp + ".ndjson")
    sess = requests.Session()
    sess.headers["User-Agent"] = "latencia-fuentes/1.0"
    n_ticks = 1 if a.prueba else int(a.minutes * 60 / a.tick)
    agencias = ["56"] if a.prueba else ["56", "80"]
    oba_ids, n_oba, wafs, oba_abort = {}, 0, 0, False
    last_oba = 0.0
    f = out.open("a", encoding="utf8")

    def w(rec):
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()

    w({"src": "meta", "t_local": time.time(), "tick": a.tick, "minutes": a.minutes, "suffix_map": smap,
       "prueba": a.prueba})
    if not a.prueba:
        w(ntp())
    t0 = time.time()
    for i in range(n_ticks):
        espera = t0 + i * a.tick - time.time()
        if espera > 0:
            time.sleep(espera)
        rc = get_caba(sess, smap, oba_ids)
        w(rc)
        print("[%d/%d] caba status=%s n=%d" % (i + 1, n_ticks, rc.get("http_status"), len(rc["vehicles"])), flush=True)
        if not oba_abort and n_oba < a.max_oba:
            gap = time.time() - last_oba
            if gap < OBA_MIN_GAP:
                time.sleep(OBA_MIN_GAP - gap)
            ag = agencias[i % len(agencias)]
            ro, ok = get_oba(sess, ag)
            last_oba = time.time()
            n_oba += 1
            w(ro)
            print("[%d/%d] oba %s status=%s n=%d ok=%s (req oba=%d)" % (i + 1, n_ticks, ag, ro.get("http_status"), len(ro["vehicles"]), ok, n_oba), flush=True)
            if ok:
                for v in ro["vehicles"]:
                    oba_ids[v["id"]] = v["line"]
            else:
                wafs += 1
                w({"src": "incidente", "t_local": time.time(), "agency": ag,
                   "detalle": ro.get("anomalia") or ro.get("error"), "n_waf": wafs})
                if wafs >= 2:
                    oba_abort = True
                    print("OBA abortado tras segunda anomalia", flush=True)
                else:
                    print("Anomalia OBA: pausa 120 s", flush=True)
                    if a.prueba:
                        continue
                    time.sleep(WAF_PAUSE)
    w({"src": "fin", "t_local": time.time(), "n_oba_requests": n_oba, "n_waf": wafs, "oba_abortado": oba_abort})
    f.close()
    print("Listo: %s; requests OBA=%d; anomalias=%d" % (out.name, n_oba, wafs))


if __name__ == "__main__":
    main()
