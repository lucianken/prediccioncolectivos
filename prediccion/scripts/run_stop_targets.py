"""
Lanzador reanudable del experimento "T en paradas reales" (ARQUITECTURA.md §11 ítem 4b, resultado en §7).

Pregunta: entrenar con puntos objetivo T en paradas reales (en vez de puntos cualquiera del camino), ¿mejora la predicción de
llegada a paradas? Un solo cambio contra la base `v2c_l1_paradas` (data/ml/v2c_sub/runs_stops: 12 líneas, L1 + --stops-feature,
LR 2e-3, 12 épocas, OneCycle, batch 1024, geo3, semillas 0 y 1, días 2026-07-20 .. 2026-10-14): mismos viajes, misma receta, pero
los pares (P, T) se arman con T en paradas del recorrido (v2/stop_targets.py; `--targets stops`, solo paradas: la medición del
smoke dio ~99 % de los pares de la base, no hace falta mezclar).

Etapas, todas idempotentes (si algo se corta, volver a ejecutar el mismo comando):
  0. keep_awake: arranca `prediccion/scripts/keep_awake.py <su pid>` y verifica `keep_awake activo`
  1. ESPERA a GATE (2026-11-17 00:00 hora local; BONDI_GATE=ISO la sobrescribe). Antes de GATE no corre nada pesado.
  2. build en data/ml/v2c_stops (15 líneas, días 2026-07-20:2026-10-14, bloques de 14 días, geo2 + geo3, K=32, --targets stops,
     4 workers = mitad de los 8 núcleos, prioridad baja). Se siembran los carry de data/ml/v2c para que cada día tenga el mismo
     estado previo que la base (los viajes salen idénticos; se verifica contra los trips.parquet de v2c).
  3. ensamblado data/ml/v2c_stops_sub (12 líneas, train desde 2026-07-20, 40 % de la val) y eval CONGELADO de T en paradas
     data/ml/v2c_stops/eval (7.500 filas por bucket de ETA; días de val 2026-09-15 .. 2026-10-14, disjuntos del train)
  4. entrenamiento `--loss l1 --stops-feature`, semillas 0 y 1 -> data/ml/v2c_stops_sub/runs; el log debe decir device=cuda
  5. evaluación de nuevo y base (data/ml/v2c_sub/runs_stops) en las dos varas: (1) eval de paradas (data/ml/v2c_stops/eval) y
     (2) eval de siempre, T cualquiera (data/ml/v2c/eval); seen (12 líneas) y heldout (12, 15, 128)
  6. runs/comparacion.md (banda 3-7 min: MAE, P90, % llega antes / después > 60 s; media de semillas, por semilla, por línea;
     veredicto contra la diferencia entre semillas) y sección en ARQUITECTURA.md §7
Línea final de runs/launcher.log: `listo: T en paradas entrenado y evaluado` o `ERROR ...`.

Lanzar con el Python 3.13 del sistema y desacoplado:
  $PY = "C:\\Users\\LK\\AppData\\Local\\Programs\\Python\\Python313\\python.exe"
  Start-Process $PY -ArgumentList "-u","-m","prediccion.scripts.run_stop_targets" -WindowStyle Hidden -PassThru -RedirectStandardOutput <out> -RedirectStandardError <err>
`--smoke`: punta a punta chico (2 días, CPU, 1 época sobre 3 row groups) en data/ml/v2c_stops_smoke; no espera GATE ni toca ARQUITECTURA.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from prediccion.scripts import run_v2b as R

SMOKE = R.SMOKE
if SMOKE:
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
V2C = Path("data/ml/v2c")
V2C_SUB = Path("data/ml/v2c_sub")
VS = Path("data/ml/v2c_stops_smoke") if SMOKE else Path("data/ml/v2c_stops")
SUBS = VS / "sub" if SMOKE else Path("data/ml/v2c_stops_sub")
BASE = SUBS / "runs"
R.ML, R.V2B, R.BASE = SUBS, VS, BASE
log = R.log

LINES_12 = "26,39,42,92,124,151,168,50,106,107,108,132"
LINES_15 = LINES_12 + ",12,15,128"
DATA_DIR = "//192.168.0.18/buffer/grabaciones"
DAYS = ("2026-07-20", "2026-10-14")
SMOKE_DAYS = "2026-08-12,2026-09-16"
SEEDS = (0, 1)
GATE = datetime.fromisoformat(os.environ.get("BONDI_GATE", "2026-11-17T00:00:00"))
BUILD_WORKERS = 4
MAIN = "3-7 min (principal)"
BANDS = ["0-2 min", "2-4 min", "4-6 min", "6-8 min", "8-10 min", "10-15 min", "15-20 min", MAIN]
KEYS = [("mae", "MAE (s)"), ("p90", "P90 error abs. (s)"), ("pct_llega_antes_60s", "llega antes >60 s (%)"),
        ("pct_llega_despues_60s", "llega después >60 s (%)"), ("espera_extra_media_s", "espera extra media (s)")]
L_BASE, L_NEW = "v2c_l1_paradas", "v2c_l1_paradas_T"
BASE_RUNS = V2C_SUB / "runs_stops"
VARAS = {"paradas": VS, "cualquiera": V2C}      # vara 1: eval congelado de T en paradas; vara 2: la de siempre
ARQ = Path("ARQUITECTURA.md")
ARQ_HEAD = "### T en paradas reales (2026-11-17)"
PY = [sys.executable, "-u", "-m"]


def start_keep_awake() -> subprocess.Popen:
    out = BASE / "keep_awake.out"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("", encoding="utf-8")
    p = subprocess.Popen([sys.executable, "-u", "prediccion/scripts/keep_awake.py", str(os.getpid())],
                         stdout=open(out, "a", encoding="utf-8"), stderr=subprocess.STDOUT)
    for _ in range(50):
        if "keep_awake activo" in out.read_text(encoding="utf-8"):
            log(f"keep_awake activo (pid {p.pid}, vigila al lanzador {os.getpid()})")
            return p
        if p.poll() is not None:
            break
        time.sleep(0.2)
    raise RuntimeError(f"keep_awake no imprimió 'keep_awake activo' (ver {out})")


def wait_gate(what: str) -> None:
    if SMOKE or datetime.now() >= GATE:
        return
    log(f"espera {GATE:%Y-%m-%d %H:%M} para {what} (restricción horaria: nada pesado antes)")
    while datetime.now() < GATE:
        time.sleep(30)
    log(f"pasó {GATE:%H:%M}: sigue con {what}")


def step(cmd: list[str], logname: str) -> None:
    rc = R.sh(cmd, BASE / "logs" / logname)
    if rc != 0:
        raise RuntimeError(f"{' '.join(cmd[3:5])} (rc={rc}); ver logs/{logname} y relanzar para reanudar")


def blocks() -> list[str]:
    from datetime import date, timedelta
    a, b = (date.fromisoformat(x) for x in DAYS)
    out = []
    while a <= b:
        e = min(a + timedelta(days=13), b)
        out.append(f"{a}:{e}")
        a = e + timedelta(days=1)
    return out


def workers_now() -> int:
    if SMOKE:
        return 2
    try:
        import psutil
        return max(2, min(BUILD_WORKERS, int(psutil.virtual_memory().available / 3e9)))
    except Exception:  # noqa: BLE001
        return 3


def seed_carries() -> None:
    """Copia los carry de v2c (estado previo de cada día) para que los viajes y la caché de pasajes sean los de la base."""
    (VS / "daily").mkdir(parents=True, exist_ok=True)
    n = 0
    for f in (V2C / "daily").glob("*.carry.json"):
        d = f.name[:10]
        if d < "2026-07-19":
            continue
        dst = VS / "daily" / f.name
        if not dst.exists():
            shutil.copy2(f, dst)
            n += 1
    log(f"carry sembrados desde v2c: {n}")


def build() -> None:
    (VS).mkdir(parents=True, exist_ok=True)
    lf = VS / "lines.json"
    if not lf.exists():
        shutil.copy2(V2C / "lines.json", lf)
    if not SMOKE:
        seed_carries()
    days = [SMOKE_DAYS] if SMOKE else blocks()
    t0 = time.time()
    for i, b in enumerate(days):
        w = workers_now()
        log(f"build T en paradas bloque {i + 1}/{len(days)} ({b}): {w} workers, prioridad baja")
        step(PY + ["prediccion.v2.build", "--lines-file", str(lf), "--lines", LINES_15, "--days", b, "--pairs-per-trip", "32",
                   "--workers", str(w), "--segmentation", "geo2", "--assign", "geo3", "--targets", "stops",
                   "--low-priority", "--chunk-days", "1" if SMOKE else "7", "--out-dir", str(VS), "--no-assemble",
                   "--data-dir", DATA_DIR], "build.log")
        log(f"build: {i + 1}/{len(days)} bloques, {(time.time() - t0) / 60:.0f} min")


def validate() -> None:
    """Todos los días con meta targets=stops; viajes idénticos a v2c; filas contra v2c (misma línea, mismos días)."""
    import pyarrow.parquet as pq
    rows_new, rows_old, mism, noise, ndays = {}, {}, [], [], 0
    trips_old = trips_diff = rows_diff = 0
    for f in sorted((VS / "daily").glob("*.meta.json")):
        d = f.name[:10]
        m = json.loads(f.read_text(encoding="utf-8"))
        if m.get("targets") != "stops" or not set(LINES_15.split(",")) <= set(m["lines"]):
            raise RuntimeError(f"día {d} sin targets=stops / sin las 15 líneas; relanzar para reanudar")
        ndays += 1
        mo = json.loads((V2C / "daily" / f"{d}.meta.json").read_text(encoding="utf-8"))
        cols = ["vehicle_id", "start_ts", "shape_id", "n_rows"]
        tn = pq.read_table(VS / "daily" / f"{d}.trips.parquet", columns=cols).to_pandas()
        to = pq.read_table(V2C / "daily" / f"{d}.trips.parquet", columns=cols).to_pandas()
        mg = to.merge(tn, on=["vehicle_id", "start_ts"], how="outer", suffixes=("_o", "_n"), indicator=True)
        lo, ro, bo = mg[mg._merge == "left_only"], mg[mg._merge == "right_only"], mg[mg._merge == "both"]
        nd = len(lo) + len(ro) + int((bo.shape_id_o != bo.shape_id_n).sum())
        trips_old += len(to)
        trips_diff += nd
        rows_diff += int(lo.n_rows_o.sum() + ro.n_rows_n.sum())
        if nd:
            mism.append(d)
        for ln, v in m["per_line"].items():
            rows_new[ln] = rows_new.get(ln, 0) + v["rows"]
            rows_old[ln] = rows_old.get(ln, 0) + mo["per_line"][ln]["rows"]
        if m.get("stop_noise_abs_s"):
            noise.append(m["stop_noise_abs_s"])
    tn_, to_ = sum(rows_new.values()), sum(rows_old.values())
    nz = sum(x["n"] for x in noise)
    p50 = sum(x["p50"] * x["n"] for x in noise) / max(nz, 1)
    p90 = sum(x["p90"] * x["n"] for x in noise) / max(nz, 1)
    out = ["# Validación del build T en paradas", "",
           f"{ndays} días construidos. Filas totales (15 líneas): {tn_:,} contra {to_:,} de v2c ({100 * tn_ / max(to_, 1):.1f} %). "
           f"Días con viajes distintos de v2c: {mism or 'ninguno'}.",
           f"Ruido de interpolar la hora (error absoluto de predecir un ping desde sus dos vecinos, span <= 120 s; promedio ponderado por día): "
           f"P50 {p50:.1f} s, P90 {p90:.1f} s ({nz:,} ternas).", "",
           "| línea | filas T en paradas | filas v2c | % |", "|---|---:|---:|---:|"]
    for ln in sorted(rows_new, key=int):
        out.append(f"| {ln} | {rows_new[ln]:,} | {rows_old[ln]:,} | {100 * rows_new[ln] / max(rows_old[ln], 1):.1f} |")
    (VS / "validation").mkdir(parents=True, exist_ok=True)
    (VS / "validation" / "summary.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    log(f"validación: filas {tn_:,} / {to_:,} v2c ({100 * tn_ / max(to_, 1):.1f} %); ruido interpolación P50 {p50:.0f} s P90 {p90:.0f} s; "
        f"días con viajes distintos: {mism or 'ninguno'}")
    pt, pr = 100 * trips_diff / max(trips_old, 1), 100 * rows_diff / max(to_, 1)
    log(f"viajes distintos de v2c: {trips_diff:,} de {trips_old:,} ({pt:.2f} %), filas afectadas {rows_diff:,} ({pr:.2f} %) en {len(mism)} días "
        "(causa: carry_in False en el primer día de cada bloque de v2c + deriva del asignador; ver validation/diagnostico_viajes.md)")
    if pt > 0.5 or pr > 0.5:
        raise RuntimeError(f"viajes distintos de v2c: {pt:.2f} % de viajes, {pr:.2f} % de filas (> 0,5 %)")


def assemble_and_eval_set() -> None:
    lf = VS / "lines.json"
    if not (SUBS / "assembled.json").exists():
        log("ensambla v2c_stops_sub")
        step(PY + ["prediccion.v2.assemble", "--v2-dir", str(VS), "--lines-file", str(lf), "--only-lines", LINES_12,
                   "--dest", str(SUBS), "--train-start", "2026-07-20", "--val-sample-frac", "0.4"], "assemble.log")
    if not (VS / "eval" / "eval_seen.parquet").exists():
        log("congela el eval de T en paradas")
        step(PY + ["prediccion.v2.make_eval", "--v2-dir", str(VS), "--lines-file", str(lf),
                   "--n-per-bucket", "200" if SMOKE else "7500"], "make_eval.log")
    a = json.loads((SUBS / "assembled.json").read_text(encoding="utf-8"))
    b = json.loads((V2C_SUB / "assembled.json").read_text(encoding="utf-8"))
    log(f"pares: train {a['rows_train']:,} (base {b['rows_train']:,}, {100 * a['rows_train'] / b['rows_train']:.1f} %), "
        f"val {a['rows_val']:,} (base {b['rows_val']:,})")


def train(seed: int) -> None:
    d = R.run_dir("path", "2e-3", seed)
    if R.metrics_path("path", d).exists():
        log(f"saltea {d.name}: ya terminó")
        return
    wait_gate(f"entrenar {d.name}")
    d.mkdir(parents=True, exist_ok=True)
    lg = BASE / "logs" / f"{d.name}.log"
    lg.parent.mkdir(parents=True, exist_ok=True)
    cmd = R.train_cmd("path", "2e-3", seed) + ["--loss", "l1", "--stops-feature"]
    if SMOKE:
        cmd += ["--device", "cpu", "--workers", "0"]
    log(f"entrena {d.name}")
    t0 = time.time()
    with open(lg, "a", encoding="utf-8") as out:
        p = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT,
                             env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        checked = SMOKE
        while p.poll() is None:
            time.sleep(5)
            if not checked:
                txt = lg.read_text(encoding="utf-8", errors="replace")
                if "device=" in txt:
                    checked = True
                    if "device=cuda" not in txt:
                        p.kill()
                        raise RuntimeError(f"el entrenamiento no arrancó en CUDA ({lg.name}); usar el Python 3.13 del sistema")
                    log(f"{d.name}: device=cuda verificado")
    if p.returncode != 0 or not R.metrics_path("path", d).exists():
        raise RuntimeError(f"entrenando {d.name} (rc={p.returncode}); relanzar el lanzador para reanudar")
    log(f"terminó {d.name} en {(time.time() - t0) / 60:.1f} min; val MAE {R.val_mae('path', d):.1f}")


def ckpt(label: str, s: int) -> Path:
    return R.best_ckpt("path", (BASE_RUNS if label == L_BASE else BASE) / f"path_lr2e-3_s{s}")


def evaluate(label: str, s: int, vara: str) -> None:
    for which in ("seen", "heldout"):
        name = f"{label}_s{s}"
        out = BASE / "eval" / vara / name
        if list(out.glob(f"*_{which}_*.json")) and list(out.glob(f"*_{which}_*.pred.npy")):
            continue
        log(f"evalúa {name} {which} (vara {vara})")
        rc = R.sh(PY[:3] + ["prediccion.eval", "--model", f"path:{ckpt(label, s)}", "--set", which, "--v2-dir", str(VARAS[vara]),
                            "--out-dir", str(out), "--save-preds"], BASE / "logs" / f"eval_{vara}_{name}_{which}.log")
        if rc != 0:
            raise RuntimeError(f"evaluando {name} {which} {vara} (rc={rc})")


def comparison() -> dict:
    import pyarrow.parquet as pq
    from prediccion.eval import compute_eta_bands
    res: dict = {}
    out = ["# T en paradas reales contra la base `v2c_l1_paradas`", "",
           f"`{L_BASE}`: base (`data/ml/v2c_sub/runs_stops`, T cualquiera del camino); `{L_NEW}`: misma receta con T solo en paradas "
           "(`data/ml/v2c_stops_sub/runs`). Semillas 0 y 1; cada celda es la media de las semillas salvo donde se aclara. Llega antes = "
           "pred - real > 60 s (el coche llega antes de lo anunciado); llega después = real - pred > 60 s; espera extra = media de "
           f"(real - pred) cuando llega después. Banda principal: ETA real {MAIN}. Veredicto contra la diferencia entre semillas "
           "(|MAE s0 - MAE s1|, la mayor de las dos familias). Vara 1 = eval congelado de T en paradas (`data/ml/v2c_stops/eval`); "
           "vara 2 = la de siempre, T cualquiera (`data/ml/v2c/eval`).", ""]
    for vara, vdir in VARAS.items():
        title = "vara 1: eval de T en paradas" if vara == "paradas" else "vara 2: eval de siempre (T cualquiera)"
        for which in ("seen", "heldout"):
            t = pq.read_table(vdir / "eval" / f"eval_{which}.parquet", columns=["line", "observed_eta_s"])
            line = np.asarray(t["line"].to_pylist(), dtype=str)
            true = np.asarray(t["observed_eta_s"], dtype=np.float64)
            preds = {lb: [np.load(sorted((BASE / "eval" / vara / f"{lb}_s{s}").glob(f"*_{which}_*.pred.npy"))[-1]).astype(np.float64)
                          for s in SEEDS] for lb in (L_BASE, L_NEW)}
            for lb in preds:
                for p in preds[lb]:
                    if len(p) != len(line):
                        raise RuntimeError(f"{vara} {lb} {which}: {len(p)} predicciones contra {len(line)} filas del eval")

            def bd(lb, i, m=None):
                m = np.ones(len(line), bool) if m is None else m
                return compute_eta_bands(preds[lb][i][m], true[m])

            def avg(lb, band, k, m=None):
                v = [bd(lb, i, m)[band][k] for i in range(len(SEEDS))]
                return float(np.mean([np.nan if x is None else x for x in v]))

            n = int(bd(L_BASE, 0)[MAIN]["n"])
            out += [f"## {title}, {which}: ETA real {MAIN} (n = {n}, eval de {len(line)} filas)", "",
                    "| modelo | " + " | ".join(h for _, h in KEYS) + " |", "|---|" + "---:|" * len(KEYS)]
            for lb in (L_BASE, L_NEW):
                out.append(f"| {lb} | " + " | ".join(f"{avg(lb, MAIN, k):.1f}" for k, _ in KEYS) + " |")
            out += ["", "Por semilla:", "", "| modelo | MAE s0 / s1 (s) | diferencia entre semillas (s) | llega antes s0 / s1 (%) | llega después s0 / s1 (%) |",
                    "|---|---|---:|---|---|"]
            mae, gap = {}, {}
            for lb in (L_BASE, L_NEW):
                b = [bd(lb, i)[MAIN] for i in range(len(SEEDS))]
                mae[lb], gap[lb] = float(np.mean([x["mae"] for x in b])), abs(b[0]["mae"] - b[1]["mae"])
                out.append(f"| {lb} | {b[0]['mae']:.1f} / {b[1]['mae']:.1f} | {gap[lb]:.1f} | "
                           f"{b[0]['pct_llega_antes_60s']:.1f} / {b[1]['pct_llega_antes_60s']:.1f} | "
                           f"{b[0]['pct_llega_despues_60s']:.1f} / {b[1]['pct_llega_despues_60s']:.1f} |")
            gain, thr = mae[L_BASE] - mae[L_NEW], max(gap.values())
            a_b, a_n = avg(L_BASE, MAIN, "pct_llega_antes_60s"), avg(L_NEW, MAIN, "pct_llega_antes_60s")
            res[(vara, which)] = dict(base=mae[L_BASE], new=mae[L_NEW], gain=gain, thr=thr, antes_base=a_b, antes_new=a_n,
                                      desp_base=avg(L_BASE, MAIN, "pct_llega_despues_60s"), desp_new=avg(L_NEW, MAIN, "pct_llega_despues_60s"),
                                      p90_base=avg(L_BASE, MAIN, "p90"), p90_new=avg(L_NEW, MAIN, "p90"), n=n)
            out += ["", f"MAE (s) por banda de ETA real:", "", "| banda | n | base | nuevo | diferencia (nuevo - base) |", "|---|---:|---:|---:|---:|"]
            for band in [MAIN] + [b for b in BANDS if b != MAIN]:
                out.append(f"| {band} | {int(bd(L_BASE, 0)[band]['n'])} | {avg(L_BASE, band, 'mae'):.1f} | {avg(L_NEW, band, 'mae'):.1f} | "
                           f"{avg(L_NEW, band, 'mae') - avg(L_BASE, band, 'mae'):+.1f} |")
            mm = (true >= 180.0) & (true < 420.0)
            out += ["", f"Por línea, banda {MAIN}:", "",
                    "| línea | n | MAE base | MAE nuevo | diferencia | llega antes base / nuevo (%) | llega después base / nuevo (%) |",
                    "|---|---:|---:|---:|---:|---|---|"]
            for ln in sorted(set(line.tolist()), key=int):
                m = (line == ln) & mm
                if m.sum() == 0:
                    continue
                out.append(f"| {ln} | {int(m.sum())} | {avg(L_BASE, MAIN, 'mae', m):.1f} | {avg(L_NEW, MAIN, 'mae', m):.1f} | "
                           f"{avg(L_NEW, MAIN, 'mae', m) - avg(L_BASE, MAIN, 'mae', m):+.1f} | "
                           f"{avg(L_BASE, MAIN, 'pct_llega_antes_60s', m):.1f} / {avg(L_NEW, MAIN, 'pct_llega_antes_60s', m):.1f} | "
                           f"{avg(L_BASE, MAIN, 'pct_llega_despues_60s', m):.1f} / {avg(L_NEW, MAIN, 'pct_llega_despues_60s', m):.1f} |")
            out.append("")
    out += ["## Veredicto", ""]
    for (vara, which), r in res.items():
        if vara == "paradas":
            v = "MEJORA" if r["gain"] > r["thr"] else ("EMPEORA" if -r["gain"] > r["thr"] else "sin diferencia clara")
            out.append(f"- vara 1 (paradas), {which}: MAE {r['base']:.1f} -> {r['new']:.1f} s ({r['gain']:+.1f} s de mejora) contra "
                       f"diferencia entre semillas {r['thr']:.1f} s -> {v}; llega antes {r['antes_base']:.1f} -> {r['antes_new']:.1f} %.")
        else:
            d = -r["gain"]
            v = "EMPEORA fuera de paradas" if d > r["thr"] else ("mejora" if -d > r["thr"] else "no empeora (dentro de la diferencia entre semillas)")
            out.append(f"- vara 2 (T cualquiera), {which}: MAE {r['base']:.1f} -> {r['new']:.1f} s ({d:+.1f} s) contra diferencia entre "
                       f"semillas {r['thr']:.1f} s -> {v}; llega antes {r['antes_base']:.1f} -> {r['antes_new']:.1f} %.")
    (BASE / "comparacion.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    return res


def write_arquitectura(res: dict) -> None:
    # ARQUITECTURA.md lo edita el orquestador a mano (pedido del usuario 2026-11-16); el lanzador no lo toca.
    log("ARQUITECTURA.md no se modifica: resultado en comparacion.md")
    return
    a = json.loads((SUBS / "assembled.json").read_text(encoding="utf-8"))
    b = json.loads((V2C_SUB / "assembled.json").read_text(encoding="utf-8"))
    val = (VS / "validation" / "summary.md").read_text(encoding="utf-8").splitlines()
    noise = next((ln for ln in val if ln.startswith("Ruido")), "")
    rows = ["| Vara | Conjunto | base MAE (llega antes) | T en paradas MAE (llega antes) | mejora | diferencia entre semillas |", "|---|---|---|---|---|---|"]
    for (vara, which), r in res.items():
        nm = "1: T en paradas" if vara == "paradas" else "2: T cualquiera"
        cj = "seen (12 líneas)" if which == "seen" else "heldout (12, 15, 128)"
        rows.append(f"| {nm} | {cj} | {r['base']:.1f} s ({r['antes_base']:.1f} %) | {r['new']:.1f} s ({r['antes_new']:.1f} %) | "
                    f"{r['gain']:+.1f} s | {r['thr']:.1f} s |")
    p1 = [r for (v, _), r in res.items() if v == "paradas"]
    p2 = [r for (v, _), r in res.items() if v == "cualquiera"]
    mejora = all(r["gain"] > r["thr"] for r in p1)
    parcial = any(r["gain"] > r["thr"] for r in p1)
    peor = any(-r["gain"] > r["thr"] for r in p2)
    lectura = ("T en paradas " + ("mejora la predicción de llegada a paradas en seen y heldout" if mejora else
               ("mejora la llegada a paradas solo en uno de los conjuntos" if parcial else "no mejora la llegada a paradas por encima de la diferencia entre semillas"))
               + "; " + ("fuera de paradas (T cualquiera) empeora." if peor else "fuera de paradas (T cualquiera) no empeora por encima de la diferencia entre semillas."))
    sec = f"""
{ARQ_HEAD}

Un solo cambio contra la base `v2c_l1_paradas` (12 líneas de producción, L1 + `--stops-feature`, LR 2e-3, 12 épocas, geo3, semillas 0 y 1, días 2026-07-20 a 2026-10-14, `data/ml/v2c_sub/runs_stops`): los puntos objetivo T de cada par (P, T) se muestrean solo en paradas del recorrido en vez de en pings cualquiera del camino. Datos: `data/ml/v2c_stops` (build) y `data/ml/v2c_stops_sub` (train), `prediccion/v2/stop_targets.py`, lanzador `prediccion/scripts/run_stop_targets.py`, comparación completa en `data/ml/v2c_stops_sub/runs/comparacion.md`.

- **T:** solo las paradas de la lista del propio recorrido (`ramales[].stops` de la relación OSM de ese shape); NO se agregan paradas de otros recorridos por geometría (una parada que no figura en un ramal es una que ese ramal no sirve); distancia = proyección de `models/stops.py` (la de la app). Paradas a < 10 m entre sí cuentan una. Una parada a < 50 m del final se cruza al llegar a 50 m del final.
- **Etiqueta:** hora de paso por la parada, interpolada linealmente en la distancia entre los dos pings válidos consecutivos que la encierran (mismo tramo continuo, <= 10 min entre ellos, sin saltos de GPS: avance <= 25 m/s x dt + 50 m). P a >= 100 m de la parada y anterior al cruce. {noise.replace('Ruido de interpolar', 'Ruido de interpolar')}
- **Muestreo:** solo paradas, K = 32 pares por viaje estratificados por distancia restante (igual que la base). Viajes idénticos a los de v2c (mismo segmentador, asignación geo3 y estado previo por día). Pares de train: {a['rows_train']:,} contra {b['rows_train']:,} de la base ({100 * a['rows_train'] / b['rows_train']:.1f} %); val {a['rows_val']:,} contra {b['rows_val']:,}. No hizo falta mezclar con T cualquiera.
- **Eval:** vara 1 = eval congelado de T en paradas (`data/ml/v2c_stops/eval`, días de val 2026-09-15 a 2026-10-14, 7.500 filas por bucket de ETA); vara 2 = la de siempre (`data/ml/v2c/eval`). Banda de ETA real 3-7 min. Mismo eval para los dos modelos.

{chr(10).join(rows)}

**Lectura:** {lectura} Ver `comparacion.md` para llega después, P90, bandas y desglose por línea. No se midió con el replay de producto.
"""
    txt = ARQ.read_text(encoding="utf-8")
    if ARQ_HEAD in txt:
        return
    marker = "\n## 8. "
    i = txt.index(marker)
    ARQ.write_text(txt[:i].rstrip("\n") + "\n" + sec + txt[i:], encoding="utf-8")


def main() -> int:
    (BASE / "logs").mkdir(parents=True, exist_ok=True)
    (BASE / "eval").mkdir(parents=True, exist_ok=True)
    log("inicio / reanudación del lanzador T en paradas" + (" [smoke]" if SMOKE else "") + f" (python {sys.executable})")
    ka = None
    try:
        ka = start_keep_awake()
        wait_gate("el build pesado")
        build()
        validate()
        assemble_and_eval_set()
        for s in SEEDS:
            train(s)
        for vara in VARAS:
            for lb in (L_NEW, L_BASE):
                for s in SEEDS:
                    evaluate(lb, s, vara)
        res = comparison()
        if not SMOKE:
            write_arquitectura(res)
    except Exception as e:  # noqa: BLE001
        log(f"ERROR {e}")
        return 1
    finally:
        if ka is not None:
            ka.terminate()
    log("listo: T en paradas entrenado y evaluado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
