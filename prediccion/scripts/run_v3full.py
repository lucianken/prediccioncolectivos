"""
Lanzador reanudable de v3full: mismo modelo v3, pero con TODO el período de train (desde el primer día construido, 2026-03-28,
hasta 2026-09-14) en vez de solo 2026-07-20 -> 2026-09-14. Un solo cambio respecto de v3: `--train-start`.

Todo lo demás idéntico a run_v3: 48 líneas de train (data/ml/v3/lines.json), val 2026-09-15 -> 10-14 con --val-sample-frac 0.4,
eval congelado data/ml/v3/eval, modelo por tramos `--loss l1 --stops-feature`, LR 2e-3, 12 épocas, batch 1024, semilla 0.
NO reconstruye el build (usa data/ml/v3/daily tal cual) ni toca data/ml/v3_sub (solo lee sus predicciones de eval y assembled.json).

Etapas (idempotentes; si se corta, volver a ejecutar el mismo comando):
  0. keep_awake: el lanzador arranca `prediccion/scripts/keep_awake.py <su pid>` y verifica que imprimió `keep_awake activo`
  1. ensamblado en data/ml/v3full_sub (train desde 2026-03-28)
  2. entrenamiento v3full_s0 en data/ml/v3full_sub/runs (GPU; falla si el log no dice device=cuda)
  3. evaluación (seen y heldout, data/ml/v3/eval) y comparación contra v3 (predicciones ya guardadas en data/ml/v3_sub/runs/eval)
     -> data/ml/v3full_sub/runs/comparacion.md
Línea final de runs/launcher.log: `listo: ...` o `ERROR ...`.

Lanzar con el Python 3.13 del sistema (el `python` de PowerShell es el .venv con torch CPU) y desacoplado:
  $PY = "C:\\Users\\LK\\AppData\\Local\\Programs\\Python\\Python313\\python.exe"
  Start-Process $PY -ArgumentList "-u","-m","prediccion.scripts.run_v3full" -WindowStyle Hidden -PassThru -RedirectStandardOutput <out> -RedirectStandardError <err>
`--smoke`: prueba de punta a punta chica en data/ml/v3full_smoke (ensamblado de pocos días, 1 época sobre 3 row groups en CPU,
evaluación sobre el eval congelado real y comparación); no usa GPU.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from prediccion.scripts import run_v2b as R
from prediccion.scripts import run_v3 as V

SMOKE = R.SMOKE
V3 = Path("data/ml/v3")                       # build y eval congelado reales (solo lectura)
DEST = Path("data/ml/v3full_smoke") if SMOKE else Path("data/ml/v3full_sub")
BASE = DEST / "runs"
V3_RUNS = Path("data/ml/v3_sub/runs")         # predicciones v3 ya evaluadas (solo lectura)
TRAIN_START = "2026-09-12" if SMOKE else "2026-03-28"
LABEL, V3_LABEL, SEED = "v3full_l1_paradas", "v3_l1_paradas", 0
MAIN = V.MAIN

# Reusa las funciones de run_v2b / run_v3 apuntando a este destino (run_v3 hace lo mismo con v3_sub).
R.ML, R.V2B, R.BASE = DEST, V3, BASE
V.V3, V.SUB, V.BASE = V3, DEST, BASE
log = R.log


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


def assemble() -> None:
    lf = V3 / "lines.json"
    if not (DEST / "assembled.json").exists():
        log(f"ensambla {DEST.name} (train desde {TRAIN_START})")
        cmd = V.PY + ["prediccion.v2.assemble", "--v2-dir", str(V3), "--lines-file", str(lf), "--only-lines", ",".join(V.TRAIN),
                      "--dest", str(DEST), "--train-start", TRAIN_START, "--val-sample-frac", "0.4"]
        if SMOKE:
            cmd += ["--val-end", "2026-09-16"]
        V.step(cmd, "assemble.log")
    a = json.loads((DEST / "assembled.json").read_text(encoding="utf-8"))
    log(f"{DEST.name}: {a['rows_train']:,} filas train ({a['n_train_days']} días, {a['train_days']}), "
        f"{a['rows_val']:,} val ({a['n_val_days']} días, {a['val_days']}) (v3_sub: 30.979.763 / 6.619.478)")


def train() -> Path:
    d = R.run_dir("path", "2e-3", SEED)
    if R.metrics_path("path", d).exists():
        log(f"saltea {d.name}: ya terminó")
        return d
    d.mkdir(parents=True, exist_ok=True)
    log(f"entrena {d.name}")
    t0 = time.time()
    extra = ["--loss", "l1", "--stops-feature"] + (["--device", "cpu", "--workers", "0"] if SMOKE else [])
    logname = d.name + ".log"
    rc = V.sh(R.train_cmd("path", "2e-3", SEED) + extra, BASE / "logs" / logname, cpu_only=SMOKE)
    if rc != 0 or not R.metrics_path("path", d).exists():
        raise RuntimeError(f"entrenando {d.name} (rc={rc}); relanzar el lanzador para reanudar")
    log(f"terminó {d.name} en {(time.time() - t0) / 60:.1f} min; val MAE {R.val_mae('path', d):.1f}")
    return d


def check_cuda(d: Path) -> None:
    txt = (BASE / "logs" / f"{d.name}.log").read_text(encoding="utf-8", errors="replace")
    if "device=cuda" not in txt:
        raise RuntimeError(f"el log de entrenamiento no dice device=cuda ({d.name}.log)")


def evaluate(d: Path) -> None:
    for which in ("seen", "heldout"):
        out = BASE / "eval" / f"{LABEL}_s{SEED}"
        if list(out.glob(f"*_{which}_*.json")) and list(out.glob(f"*_{which}_*.pred.npy")):
            continue
        log(f"evalúa {LABEL}_s{SEED} {which}")
        cmd = V.PY[:3] + ["prediccion.eval", "--model", f"path:{R.best_ckpt('path', d)}", "--set", which, "--v2-dir", str(V3),
                          "--out-dir", str(out), "--save-preds"]
        rc = V.sh(cmd, BASE / "logs" / f"eval_{LABEL}_s{SEED}_{which}.log", cpu_only=SMOKE)
        if rc != 0:
            raise RuntimeError(f"evaluando {LABEL} {which} (rc={rc})")


def comparison() -> None:
    import pyarrow.parquet as pq
    from prediccion.eval import compute_eta_bands, _stats
    tbl = {}
    for which in ("seen", "heldout"):
        t = pq.read_table(V3 / "eval" / f"eval_{which}.parquet", columns=["line", "observed_eta_s"])
        tbl[which] = (np.asarray(t["line"].to_pylist(), dtype=str), np.asarray(t["observed_eta_s"], dtype=np.float64))

    def load(runs: Path, label: str, s: int, which: str):
        f = sorted((runs / "eval" / f"{label}_s{s}").glob(f"*_{which}_*.pred.npy"))[-1]
        pred = np.load(f).astype(np.float64)
        line, true = tbl[which]
        if len(pred) != len(line):
            raise RuntimeError(f"{f}: {len(pred)} predicciones contra {len(line)} filas del eval")
        return line, true, pred

    cache = {(LABEL, 0, w): load(BASE, LABEL, 0, w) for w in ("seen", "heldout")}
    for s in V.SEEDS:
        for w in ("seen", "heldout"):
            cache[(V3_LABEL, s, w)] = load(V3_RUNS, V3_LABEL, s, w)
    # modelos: (nombre, [(label, seed)]) ; media = promedio de celdas de las semillas
    models = [("v3full_s0", [(LABEL, 0)]), ("v3_s0", [(V3_LABEL, 0)]), ("v3_media_s0_s1", [(V3_LABEL, 0), (V3_LABEL, 1)])]
    keys = [("mae", "MAE (s)"), ("p90", "P90 error abs. (s)"), ("pct_llega_antes_60s", "llega antes >60 s (%)"),
            ("pct_llega_despues_60s", "llega después >60 s (%)"), ("espera_extra_media_s", "espera extra media (s)")]

    def bands(lb, s, which, lines):
        line, true, pred = cache[(lb, s, which)]
        m = np.isin(line, lines) if lines is not None else np.ones(len(line), bool)
        return compute_eta_bands(pred[m], true[m])

    def val(name, which, lines, band, k):
        v = [bands(lb, s, which, lines)[band][k] for lb, s in dict(models)[name]]
        return float(np.mean([np.nan if x is None else x for x in v]))

    def gmae(name, which, ln):
        v = []
        for lb, s in dict(models)[name]:
            line, true, pred = cache[(lb, s, which)]
            m = line == ln
            v.append(_stats(pred[m], true[m])["mae"])
        return float(np.mean(v))

    KC, TRAIN, NEW, CONTROL, OLD12 = V.KNOWN_CTRL, V.TRAIN, V.NEW_LINES, V.CONTROL, V.OLD12
    scopes = [("seen, 12 líneas de producción", "seen", OLD12),
              (f"seen, {len(NEW)} líneas nuevas", "seen", NEW),
              (f"seen, las {len(TRAIN)} líneas de train", "seen", TRAIN),
              (f"heldout, las {len(KC)} de control con shapes conocidos por v2c ({', '.join(KC)}; ninguna en train)", "heldout", KC),
              (f"heldout, las {len(CONTROL)} de control (ninguna en train)", "heldout", CONTROL)]
    a_full = json.loads((DEST / "assembled.json").read_text(encoding="utf-8"))
    a_v3 = json.loads(Path("data/ml/v3_sub/assembled.json").read_text(encoding="utf-8"))
    out = ["# Comparación v3full (train desde 2026-03-28) contra v3 (train desde 2026-07-20) sobre el eval de v3", "",
           f"Único cambio: `--train-start` ({a_full['train_days'][0]} contra {a_v3['train_days'][0]}; ambos hasta 2026-09-14). "
           f"Filas train: v3full {a_full['rows_train']:,} ({a_full['n_train_days']} días), v3 {a_v3['rows_train']:,} ({a_v3['n_train_days']} días); "
           f"val idéntica ({a_full['rows_val']:,} contra {a_v3['rows_val']:,} filas). Eval `data/ml/v3/eval` (asignación geo3). "
           "`v3full_s0`: semilla 0 de este run; `v3_s0`: semilla 0 de v3; `v3_media_s0_s1`: media de las semillas 0 y 1 de v3 "
           "(la diferencia entre semillas de v3 fue <= 0,4 s en la banda principal). "
           f"Banda principal: {MAIN}. Diferencia = v3full_s0 menos v3_s0 (negativa = v3full mejor).", ""]
    for title, which, lines in scopes:
        n = bands(LABEL, 0, which, lines)[MAIN]["n"]
        out += [f"## {title}: ETA real {MAIN} (n = {int(n)})", "", "| modelo | " + " | ".join(h for _, h in keys) + " |",
                "|---|" + "---:|" * len(keys)]
        for nm, _ in models:
            out.append(f"| {nm} | " + " | ".join(f"{val(nm, which, lines, MAIN, k):.1f}" for k, _ in keys) + " |")
        out.append("| diferencia (v3full_s0 − v3_s0) | " + " | ".join(
            f"{val('v3full_s0', which, lines, MAIN, k) - val('v3_s0', which, lines, MAIN, k):+.1f}" for k, _ in keys) + " |")
        bl = [b for b in bands(LABEL, 0, which, lines) if b != MAIN]
        out += ["", f"MAE (s) por banda de ETA real, {title}:", "", "| modelo | " + " | ".join(bl) + " |", "|---|" + "---:|" * len(bl)]
        for nm, _ in models:
            out.append(f"| {nm} | " + " | ".join(f"{val(nm, which, lines, b, 'mae'):.1f}" for b in bl) + " |")
        out.append("")

    def per_line(title, which, lines, note):
        rows = [f"## {title}", "", note, "",
                "| línea | grupo | n train v3full | n train v3 | n banda | v3full_s0 MAE banda | v3_s0 MAE banda | v3_media MAE banda | dif. (full − s0) | "
                "v3full llega antes % | v3_s0 llega antes % | v3full MAE global | v3_s0 MAE global |",
                "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for ln in lines:
            grp = "control" if ln in CONTROL else ("vieja" if ln in OLD12 else "nueva")
            nf, n3 = a_full["rows_train_by_line"].get(ln, 0), a_v3["rows_train_by_line"].get(ln, 0)
            b = bands(LABEL, 0, which, [ln])[MAIN]
            f = lambda nm, k: val(nm, which, [ln], MAIN, k)  # noqa: E731
            rows.append(f"| {ln} | {grp} | {nf if grp != 'control' else '-'} | {n3 if grp != 'control' else '-'} | {int(b['n'])} | "
                        f"{f('v3full_s0', 'mae'):.1f} | {f('v3_s0', 'mae'):.1f} | {f('v3_media_s0_s1', 'mae'):.1f} | "
                        f"{f('v3full_s0', 'mae') - f('v3_s0', 'mae'):+.1f} | {f('v3full_s0', 'pct_llega_antes_60s'):.1f} | "
                        f"{f('v3_s0', 'pct_llega_antes_60s'):.1f} | {gmae('v3full_s0', which, ln):.1f} | {gmae('v3_s0', which, ln):.1f} |")
        return rows + [""]

    out += per_line("Desglose por línea (seen)", "seen", TRAIN,
                    f"MAE en la banda {MAIN}, % llega antes >60 s y MAE global (todas las bandas). n train = filas de train de la línea en cada ensamblado "
                    "(control: sin train). Ordenar por n train v3 para ver el efecto en líneas con poca muestra.")
    out += per_line("Desglose por línea (heldout, control)", "heldout", CONTROL,
                    f"Líneas de control, fuera de train en ambos modelos; MAE en la banda {MAIN}.")
    (BASE / "comparacion.md").write_text("\n".join(out), encoding="utf-8")


def preflight() -> None:
    free = shutil.disk_usage(".").free / 1e9
    log(f"disco libre: {free:.0f} GB")
    if not SMOKE and free < 40:
        raise RuntimeError(f"disco libre {free:.0f} GB < 40 GB; liberar espacio y relanzar")


def main() -> int:
    (BASE / "logs").mkdir(parents=True, exist_ok=True)
    (BASE / "eval").mkdir(parents=True, exist_ok=True)
    log("inicio / reanudación del lanzador v3full" + (" [smoke]" if SMOKE else "") + f" (python {sys.executable})")
    try:
        ka = start_keep_awake()
        preflight()
        assemble()
        d = train()
        check_cuda(d) if not SMOKE else None
        evaluate(d)
        comparison()
        ka.terminate()
    except Exception as e:  # noqa: BLE001
        log(f"ERROR {e}")
        return 1
    log("listo: v3full entrenado y evaluado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
