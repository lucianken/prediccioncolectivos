"""
Lanzador reanudable de v3: escalado del modelo por tramos a 60 líneas (ARQUITECTURA.md §6 y §10).

Líneas: las 60 de data/ml/v2/lines.json (decisión del usuario; ver NEW_LINES). Train = 48 líneas (las 12 de producción + 36),
control = 12 líneas (1, 12, 15, 21, 64, 65, 68, 87, 100, 109, 128, 181) fuera de train.

Etapas, todas idempotentes (si algo se corta, volver a ejecutar el mismo comando):
  1. build en data/ml/v3 por bloques de 14 días (segmentación geo2, asignación geo3, K=32, 2026-03-28:2026-10-14); reanuda por día
  2. validación rápida (viajes, filas, % start_unknown por línea) -> data/ml/v3/validation/summary.md; falla si una línea no tiene filas
  3. ensamblado data/ml/v3_sub (48 líneas, train desde 2026-07-20, 40 % de la val) y eval congelado data/ml/v3/eval
  4. modelo por tramos `--loss l1 --stops-feature`, LR 2e-3, 12 épocas, OneCycle, batch 1024, semillas 0 y 1
     -> data/ml/v3_sub/runs/
  5. evaluación en data/ml/v3/eval (seen y heldout) de esos dos y, en el mismo eval, de v2c L1 (producción, path_v2c_l1_s1 es
     la semilla 1) y v2c L1 con paradas, estos sobre las 12 líneas que conocen (seen) y sobre las 3 de control (12, 15, 128) cuyos shapes tienen en su tabla (las otras 9 son desconocidas para ellos);
     tablas por bandas de ETA real (principal 3-7 min) y por línea en runs/comparacion.md
Línea final de runs/launcher.log: `listo: v3 entrenado y evaluado` o `ERROR ...`.

RESTRICCIÓN DE RECURSOS (el usuario usa la PC hasta GATE, 19:00 hora local del 2026-11-14; sobrescribible con BONDI_GATE=ISO):
  - antes de GATE: build con 2 workers, prioridad BelowNormal (--low-priority), ensamblado/eval-set en BelowNormal con
    OMP_NUM_THREADS=2; NO se usa la GPU: el entrenamiento y la evaluación esperan a GATE (chequeo antes de cada uno).
  - desde GATE: sin tope. El build, que corre por bloques de días, decide workers y prioridad en cada bloque: pasa a
    min(6, RAM libre / 3 GB) workers y prioridad normal; el entrenamiento usa la GPU completa.

Lanzar desacoplado (las tareas de fondo mueren a las 2 h):
  Start-Process python -ArgumentList "-u","-m","prediccion.scripts.run_v3" -WindowStyle Hidden -RedirectStandardOutput <log>
`--smoke`: prueba de punta a punta con 2 días y las 60 líneas en data/ml/v3_smoke (build, validación, ensamblado, eval
congelado chico, 1 época sobre 3 row groups en CPU, evaluación y tablas); no usa GPU.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

from prediccion.scripts import run_v2b as R

SMOKE = R.SMOKE
V3 = Path("data/ml/v3_smoke") if SMOKE else Path("data/ml/v3")
SUB = V3 / "sub" if SMOKE else Path("data/ml/v3_sub")
BASE = SUB / "runs"
R.ML, R.V2B, R.BASE = SUB, V3, BASE

DATA_DIR = "//192.168.0.18/buffer/grabaciones"
DAYS = ("2026-03-28", "2026-10-14")
SMOKE_DAYS = "2026-08-12,2026-09-16"

OLD12 = "26,39,42,92,124,151,168,50,106,107,108,132".split(",")
# Lista decidida por el usuario (2026-11-14): las 60 líneas de data/ml/v2/lines.json tal cual, sin filtro de calidad adicional
# (48 de `train`, que incluye 7, 76, 84, 115, y 12 de `heldout` como control), más la 132 por estar en producción (ya está
# en las 48). Total: 48 de train y 12 de control. Las 12 de producción (OLD12) son las que conocen los modelos v2c.
KNOWN_CTRL = ["12", "15", "128"]   # de control, con shapes en la tabla de los modelos v2c (las otras 9 no: predict_path las descarta)
CONTROL = ["1", "12", "15", "21", "64", "65", "68", "87", "100", "109", "128", "181"]
NEW_LINES = [x for x in ["4", "7", "9", "20", "25", "26", "28", "29", "33", "34", "39", "41", "42", "44", "46", "47", "50", "61", "62", "74", "76", "84", "85", "88", "92", "98", "102", "106", "107", "108", "110", "113", "114", "115", "118", "123", "124", "127", "132", "143", "151", "168", "169", "180", "184", "188", "194", "197"] if x not in OLD12]
TRAIN = OLD12 + NEW_LINES   # 48 (la 132 está en OLD12)
ALL = TRAIN + CONTROL
SEEDS = (0, 1)
N_PER_BUCKET = 200 if SMOKE else 15000

GATE = datetime.fromisoformat(os.environ.get("BONDI_GATE", "2026-11-14T19:00:00"))
BELOW_NORMAL = 0x00004000
MAIN = "3-7 min (principal)"
KEEP_AWAKE = Path(os.environ.get("TEMP", ".")) / "keep_awake_bondi24.ps1"

OLD_MODELS = [("v2c_l1", lambda s: Path("data/ml/v2c_sub/runs") / f"path_lr2e-3_s{s}"),
              ("v2c_l1_paradas", lambda s: Path("data/ml/v2c_sub/runs_stops") / f"path_lr2e-3_s{s}")]
NEW_LABEL = "v3_l1_paradas"
REFS = (("v2c_l1", 1),) if SMOKE else tuple((lb, s) for lb, _ in OLD_MODELS for s in SEEDS)


def restricted() -> bool:
    return datetime.now() < GATE


def log(msg: str) -> None:
    R.log(msg)


def sh(cmd: list[str], logfile: Path, cpu_only: bool = False) -> int:
    """Corre un comando con prioridad BelowNormal y 2 hilos mientras rija la restricción horaria."""
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    flags = 0
    if restricted():
        flags = BELOW_NORMAL
        env["OMP_NUM_THREADS"] = "2"
    if cpu_only:
        env["CUDA_VISIBLE_DEVICES"] = ""
    logfile.parent.mkdir(parents=True, exist_ok=True)
    with open(logfile, "a", encoding="utf-8") as out:
        return subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT, env=env, creationflags=flags).returncode


def step(cmd: list[str], logname: str, cpu_only: bool = False) -> None:
    rc = sh(cmd, BASE / "logs" / logname, cpu_only)
    if rc != 0:
        raise RuntimeError(f"{' '.join(cmd[3:5])} (rc={rc}); ver logs/{logname} y relanzar para reanudar")


def wait_gate(what: str) -> None:
    """La GPU y el entrenamiento no se usan hasta GATE (smoke: no usa GPU, no espera)."""
    if SMOKE or not restricted():
        return
    log(f"espera {GATE:%H:%M} para {what} (restricción de recursos)")
    while restricted():
        time.sleep(30)
    log(f"pasó {GATE:%H:%M}: sigue con {what}")


def blocks() -> list[str]:
    a, b = (date.fromisoformat(x) for x in DAYS)
    out = []
    while a <= b:
        e = min(a + timedelta(days=13), b)
        out.append(f"{a}:{e}")
        a = e + timedelta(days=1)
    return out


def workers_now() -> int:
    if restricted():
        return 2
    try:
        import psutil
        return max(3, min(6, int(psutil.virtual_memory().available / 3e9)))
    except Exception:  # noqa: BLE001
        return 4


PY = [sys.executable, "-u", "-m"]
ALL_S = ",".join(ALL)


def write_lines_file() -> None:
    lf = V3 / "lines.json"
    d = {"train": TRAIN, "heldout": CONTROL, "n_train": len(TRAIN), "n_heldout": len(CONTROL), "new_lines": NEW_LINES,
         "criteria": "lista de 60 líneas decidida por el usuario (data/ml/v2/lines.json: 48 train + 12 heldout), +132 por estar en producción (ya está en las 48)"}
    new = json.dumps(d, indent=1, ensure_ascii=False)
    if not lf.exists() or lf.read_text(encoding="utf-8") != new:
        V3.mkdir(parents=True, exist_ok=True)
        lf.write_text(new, encoding="utf-8")


def build() -> None:
    days = [SMOKE_DAYS] if SMOKE else blocks()
    t0 = time.time()
    for i, b in enumerate(days):
        w, low = workers_now(), restricted()
        log(f"build v3 bloque {i + 1}/{len(days)} ({b}): {w} workers{', prioridad baja' if low else ''}")
        cmd = PY + ["prediccion.v2.build", "--lines-file", str(V3 / "lines.json"), "--lines", ALL_S, "--days", b,
                    "--pairs-per-trip", "32", "--workers", str(w), "--segmentation", "geo2", "--assign", "geo3",
                    "--out-dir", str(V3), "--no-assemble", "--data-dir", DATA_DIR]
        if low:
            cmd.append("--low-priority")
        step(cmd, "build.log")
        log(f"build v3: {i + 1}/{len(days)} bloques, {(time.time() - t0) / 60:.0f} min")


def validate() -> None:
    """Viajes, filas y % start_unknown por línea sobre los daily del build; falla si una línea no tiene filas."""
    import pyarrow.parquet as pq
    acc = {ln: [0, 0, 0, 0, set()] for ln in ALL}      # viajes, viajes su, filas, filas su, días
    ndays = 0
    for f in sorted((V3 / "daily").glob("*.trips.parquet")):
        day = f.name[:10]
        meta = json.loads((V3 / "daily" / f"{day}.meta.json").read_text(encoding="utf-8"))
        if not set(ALL) <= set(meta.get("lines", [])):
            raise RuntimeError(f"día {day} sin todas las líneas en meta.json; relanzar para reanudar")
        ndays += 1
        t = pq.read_table(f, columns=["line", "start_unknown", "n_rows"]).to_pandas()
        for ln, g in t.groupby("line"):
            a = acc.get(str(ln))
            if a is None:
                continue
            su = g["start_unknown"].astype(bool)
            a[0] += len(g); a[1] += int(su.sum()); a[2] += int(g["n_rows"].sum()); a[3] += int(g.loc[su, "n_rows"].sum())
            if g["n_rows"].sum() > 0:
                a[4].add(day)
    rows = ["# Validación del build v3", "",
            f"{ndays} días construidos. `start_unknown` por viaje y por filas. Referencia v2c (15 líneas): 15,4 % de viajes y 15,4 % de filas.", "",
            "| línea | grupo | días con filas | viajes | filas | % viajes start_unknown | % filas start_unknown |",
            "|---|---|---:|---:|---:|---:|---:|"]
    bad, warn = [], []
    for ln in ALL:
        v, vs, r, rs, ds = acc[ln][0], acc[ln][1], acc[ln][2], acc[ln][3], acc[ln][4]
        grp = "control" if ln in CONTROL else ("train vieja" if ln in OLD12 else "train nueva")
        pv, pr = (100 * vs / v if v else float("nan")), (100 * rs / r if r else float("nan"))
        rows.append(f"| {ln} | {grp} | {len(ds)} | {v} | {r} | {pv:.1f} | {pr:.1f} |")
        if r == 0:
            bad.append(ln)
        elif pr > 35:
            warn.append(f"{ln} ({pr:.0f} %)")
    tv, tr = sum(a[0] for a in acc.values()), sum(a[2] for a in acc.values())
    rows += ["", f"Total: {tv} viajes, {tr} filas; filas start_unknown {100 * sum(a[3] for a in acc.values()) / max(tr, 1):.1f} %."]
    if warn:
        rows.append(f"Aviso: start_unknown > 35 % de las filas en {', '.join(warn)}.")
    (V3 / "validation").mkdir(parents=True, exist_ok=True)
    (V3 / "validation" / "summary.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    log(f"validación: {tv} viajes, {tr} filas, sin filas: {bad or 'ninguna'}; start_unknown alto: {warn or 'ninguna'}")
    if bad:
        raise RuntimeError(f"líneas sin filas tras el build: {bad}")


def assemble_and_eval_set() -> None:
    lf = V3 / "lines.json"
    if not (SUB / "assembled.json").exists():
        log("ensambla v3_sub")
        step(PY + ["prediccion.v2.assemble", "--v2-dir", str(V3), "--lines-file", str(lf), "--only-lines", ",".join(TRAIN),
                   "--dest", str(SUB), "--train-start", "2026-07-20", "--val-sample-frac", "0.4"], "assemble.log")
    if not (V3 / "eval" / "eval_seen.parquet").exists():
        log("congela el eval v3")
        step(PY + ["prediccion.v2.make_eval", "--v2-dir", str(V3), "--lines-file", str(lf),
                   "--n-per-bucket", str(N_PER_BUCKET)], "make_eval.log")
    a = json.loads((SUB / "assembled.json").read_text(encoding="utf-8"))
    log(f"v3_sub: {a['rows_train']:,} filas train, {a['rows_val']:,} val (v2c_sub: 9.376.572 / 1.911.415; "
        f"tiempo por época esperado ~{a['rows_train'] / 9376572:.1f}x el de v2c)")


def train() -> None:
    for s in SEEDS:
        d = R.run_dir("path", "2e-3", s)
        if R.metrics_path("path", d).exists():
            log(f"saltea {d.name}: ya terminó")
            continue
        wait_gate(f"entrenar {d.name}")
        d.mkdir(parents=True, exist_ok=True)
        log(f"entrena {d.name}")
        t0 = time.time()
        extra = ["--loss", "l1", "--stops-feature"] + (["--device", "cpu", "--workers", "0"] if SMOKE else [])
        rc = sh(R.train_cmd("path", "2e-3", s) + extra, BASE / "logs" / f"{d.name}.log", cpu_only=SMOKE)
        if rc != 0 or not R.metrics_path("path", d).exists():
            raise RuntimeError(f"entrenando {d.name} (rc={rc}); relanzar el lanzador para reanudar")
        log(f"terminó {d.name} en {(time.time() - t0) / 60:.1f} min; val MAE {R.val_mae('path', d):.1f}")


def ckpt_of(label: str, s: int) -> Path:
    if label == NEW_LABEL:
        return R.best_ckpt("path", R.run_dir("path", "2e-3", s))
    return R.best_ckpt("path", dict(OLD_MODELS)[label](s))


def evaluate(label: str, s: int) -> None:
    """seen y heldout en data/ml/v3/eval con predicciones por fila. Los v2c, solo sobre las 12 líneas que conocen en seen."""
    old = label != NEW_LABEL
    for which in ("seen", "heldout"):
        name = f"{label}_s{s}"
        out = BASE / "eval" / name
        if list(out.glob(f"*_{which}_*.json")) and list(out.glob(f"*_{which}_*.pred.npy")):
            continue
        wait_gate(f"evaluar {name} {which}")
        cmd = PY[:3] + ["prediccion.eval", "--model", f"path:{ckpt_of(label, s)}", "--set", which, "--v2-dir", str(V3),
                        "--out-dir", str(out), "--save-preds"]
        if old:
            cmd += ["--lines", ",".join(OLD12 if which == "seen" else KNOWN_CTRL), "--tag", "known"]
        log(f"evalúa {name} {which}")
        rc = sh(cmd, BASE / "logs" / f"eval_{name}_{which}.log", cpu_only=SMOKE)
        if rc != 0:
            raise RuntimeError(f"evaluando {name} {which} (rc={rc})")


def load_preds(label: str, s: int, which: str, tbl: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(línea, ETA real, predicción) de las filas sobre las que se evaluó el modelo en `which`."""
    f = sorted((BASE / "eval" / f"{label}_s{s}").glob(f"*_{which}_*.pred.npy"))[-1]
    pred = np.load(f).astype(np.float64)
    line, true = tbl[which]
    if label != NEW_LABEL:
        m = np.isin(line, OLD12 if which == "seen" else KNOWN_CTRL)
        line, true = line[m], true[m]
    if len(pred) != len(line):
        raise RuntimeError(f"{f}: {len(pred)} predicciones contra {len(line)} filas del eval")
    return line, true, pred


def comparison() -> None:
    import pyarrow.parquet as pq
    from prediccion.eval import compute_eta_bands, _stats
    tbl = {}
    for which in ("seen", "heldout"):
        t = pq.read_table(V3 / "eval" / f"eval_{which}.parquet", columns=["line", "observed_eta_s"])
        tbl[which] = (np.asarray(t["line"].to_pylist(), dtype=str), np.asarray(t["observed_eta_s"], dtype=np.float64))
    models = [(NEW_LABEL, s) for s in SEEDS] + list(REFS)
    cache = {(lb, s, w): load_preds(lb, s, w, tbl) for lb, s in models for w in ("seen", "heldout")}
    keys = [("mae", "MAE (s)"), ("p90", "P90 error abs. (s)"), ("pct_llega_antes_60s", "llega antes >60 s (%)"),
            ("pct_llega_despues_60s", "llega después >60 s (%)"), ("espera_extra_media_s", "espera extra media (s)")]

    def bands(lb, s, which, lines):
        line, true, pred = cache[(lb, s, which)]
        m = np.isin(line, lines) if lines is not None else np.ones(len(line), bool)
        return compute_eta_bands(pred[m], true[m])

    def mean_over_seeds(lb, which, lines, band, k):
        seeds = [s for l2, s in models if l2 == lb]
        v = [bands(lb, s, which, lines)[band][k] for s in seeds]
        return float(np.mean([np.nan if x is None else x for x in v]))

    labels = [NEW_LABEL] + [lb for lb, _ in OLD_MODELS]
    scopes = [("seen, 12 líneas de producción (las que conocen todos los modelos)", "seen", OLD12, labels),
              (f"seen, {len(NEW_LINES)} líneas nuevas (no en producción; solo v3)", "seen", NEW_LINES, [NEW_LABEL]),
              (f"seen, las {len(TRAIN)} líneas de train (solo v3)", "seen", TRAIN, [NEW_LABEL]),
              (f"heldout, las {len(KNOWN_CTRL)} de control con shapes conocidos por v2c ({', '.join(KNOWN_CTRL)}; ninguna en train de ningún modelo)", "heldout", KNOWN_CTRL, labels),
              (f"heldout, las {len(CONTROL)} de control (solo v3; ninguna en train)", "heldout", CONTROL, [NEW_LABEL])]
    ref_note = ("`v2c_l1`: modelo por tramos L1 sin paradas entrenado sobre v2c (12 líneas; su semilla 1 es `path_v2c_l1_s1`, "
                "el de producción); `v2c_l1_paradas`: igual con `--stops-feature` (`data/ml/v2c_sub/runs_stops`); "
                f"`{NEW_LABEL}`: este escalado (v3_sub, {len(TRAIN)} líneas). Cada celda es la media de las semillas 0 y 1. "
                f"Banda principal: {MAIN}.")
    out = ["# Comparación sobre el eval de v3, modelo por tramos con pérdida L1", "",
           f"Eval `data/ml/v3/eval` ({N_PER_BUCKET} filas por bucket de ETA y por conjunto, asignación geo3). " + ref_note, ""]
    for title, which, lines, labs in scopes:
        labs = [lb for lb in labs if any(l2 == lb for l2, _ in models)]
        n = bands(labs[0], models[[l2 for l2, _ in models].index(labs[0])][1], which, lines)[MAIN]["n"]
        out += [f"## {title}: ETA real {MAIN} (n = {int(n)})", "", "| modelo | " + " | ".join(h for _, h in keys) + " |",
                "|---|" + "---:|" * len(keys)]
        for lb in labs:
            out.append(f"| {lb} | " + " | ".join(f"{mean_over_seeds(lb, which, lines, MAIN, k):.1f}" for k, _ in keys) + " |")
        out += ["", f"MAE (s) por banda de ETA real, {title}:", "",
                "| modelo | " + " | ".join(b for b in bands(labs[0], models[0][1], which, lines) if b != MAIN) + " |",
                "|---|" + "---:|" * (len(bands(labs[0], models[0][1], which, lines)) - 1)]
        for lb in labs:
            out.append(f"| {lb} | " + " | ".join(f"{mean_over_seeds(lb, which, lines, b, 'mae'):.1f}"
                                                 for b in bands(labs[0], models[0][1], which, lines) if b != MAIN) + " |")
        out += ["", f"Semillas 0 / 1 en {MAIN} (MAE s; llega antes %):", ""]
        for lb in labs:
            ss = [s for l2, s in models if l2 == lb]
            cells = [bands(lb, s, which, lines)[MAIN] for s in ss]
            out.append(f"- {lb}: " + " ; ".join(f"s{s} {c['mae'] or float('nan'):.1f} s ({c['pct_llega_antes_60s'] or float('nan'):.1f} %)" for s, c in zip(ss, cells)))
        out.append("")
    # desglose por línea sobre seen
    out += ["## Desglose por línea (seen)", "",
            f"MAE y % llega antes >60 s en la banda {MAIN}, y MAE global (todas las bandas), media de semillas. Las columnas v2c "
            "solo existen para las 12 líneas viejas. n = filas de la banda.", "",
            f"| línea | grupo | n banda | {NEW_LABEL} MAE banda | llega antes % | MAE global | v2c_l1 MAE banda | v2c_l1_paradas MAE banda |",
            "|---|---|---:|---:|---:|---:|---:|---:|"]
    for ln in TRAIN:
        grp = "vieja" if ln in OLD12 else "nueva"
        b = [bands(NEW_LABEL, s, "seen", [ln]) for s in SEEDS]
        glob = np.mean([_stats(cache[(NEW_LABEL, s, "seen")][2][cache[(NEW_LABEL, s, "seen")][0] == ln],
                               cache[(NEW_LABEL, s, "seen")][1][cache[(NEW_LABEL, s, "seen")][0] == ln])["mae"] for s in SEEDS])
        nn = lambda k: np.mean([np.nan if x[MAIN][k] is None else x[MAIN][k] for x in b])  # noqa: E731
        row = [f"{nn('mae'):.1f}", f"{nn('pct_llega_antes_60s'):.1f}", f"{glob:.1f}"]
        for lb, _ in OLD_MODELS:
            row.append(f"{mean_over_seeds(lb, 'seen', [ln], MAIN, 'mae'):.1f}" if ln in OLD12 else "")
        out.append(f"| {ln} | {grp} | {int(b[0][MAIN]['n'])} | " + " | ".join(row) + " |")
    out.append("")
    (BASE / "comparacion.md").write_text("\n".join(out), encoding="utf-8")


def preflight() -> None:
    free = shutil.disk_usage(".").free / 1e9
    log(f"disco libre: {free:.0f} GB")
    if not SMOKE and free < 12:
        raise RuntimeError(f"disco libre {free:.0f} GB < 12 GB; liberar espacio y relanzar")
    log(f"líneas: {len(TRAIN)} train ({len(OLD12)} viejas + {len(NEW_LINES)} nuevas: {','.join(NEW_LINES)}), control {','.join(CONTROL)}; "
        f"restricción de recursos hasta {GATE:%Y-%m-%d %H:%M} ({'activa' if restricted() else 'vencida'})")
    write_lines_file()


def main() -> int:
    (BASE / "logs").mkdir(parents=True, exist_ok=True)
    (BASE / "eval").mkdir(parents=True, exist_ok=True)
    log("inicio / reanudación del lanzador v3" + (" [smoke]" if SMOKE else ""))
    try:
        preflight()
        build()
        validate()
        assemble_and_eval_set()
        train()
        for lb, s in [(NEW_LABEL, s) for s in SEEDS] + list(REFS):
            evaluate(lb, s)
        comparison()
    except Exception as e:  # noqa: BLE001
        log(f"ERROR {e}")
        return 1
    log("listo: v3 entrenado y evaluado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
