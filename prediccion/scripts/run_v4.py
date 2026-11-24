"""
Lanzador reanudable de v4: modelo de producción con TODAS las líneas AMBA < 200 con shapes y datos suficientes.

Receta de producción sin cambios (geo2 / geo3, K=32, modelo por tramos `--loss l1 --stops-feature`, LR 2e-3, 12 épocas, OneCycle,
batch 1024, train desde 2026-07-20 hasta 2026-09-14, val 2026-09-15 -> 2026-10-14 con muestra del 40 %).

Etapas (todas idempotentes; si se corta, volver a ejecutar el mismo comando):
  0. keep_awake (`prediccion/scripts/keep_awake.py <pid del lanzador>`), verifica `keep_awake activo`; disco >= 60 GB
  1. build en data/ml/v4 (días 2026-07-20 -> 2026-10-14, todas las líneas candidatas), por bloques; reintenta días con error
  2. selección por volumen (>= MIN_TRIPS_DAY viajes con forma por día en promedio) -> data/ml/v4/selection.json, validation/summary.md
  3. ensamblado: data/ml/v4_sub (todas las seleccionadas = run 2, full) y data/ml/v4_ctrl (menos las 12 de control = run 1)
     + eval congelado nuevo data/ml/v4/eval (seen = todas las seleccionadas, val 2026-09-15 -> 10-14)
  4. run 2 (full, semilla 1) y run 1 (control, semilla 0), GPU (falla si el log no dice device=cuda)
  5. evaluación sobre el eval congelado de v3 (46 líneas habilitadas + control) y sobre el eval de v4 (líneas nuevas)
  6. comparación y garantía de no regresión -> data/ml/v4_sub/runs/no_regresion.md y decision.json
Última línea de runs/launcher.log: `listo: ...` o `ERROR ...`.

Lanzar con el Python 3.13 del sistema, desacoplado (Start-Process). `--smoke`: prueba chica en data/ml/v4_smoke.
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

SMOKE = "--smoke" in sys.argv
ML = Path("data/ml")
V4 = ML / ("v4_smoke" if SMOKE else "v4")
FULL = V4 / "full" if SMOKE else ML / "v4_sub"          # ensamblado con todas las líneas (run 2)
CTRL = V4 / "ctrl" if SMOKE else ML / "v4_ctrl"         # ensamblado sin las de control (run 1)
BASE = FULL / "runs"
V3 = ML / "v3"
V3_RUNS = ML / "v3_sub" / "runs" / "eval"
DATA_DIR = "//192.168.0.18/buffer/grabaciones"
SHAPES_DIR = Path("../proyectoconsola/data/line_shapes")
CONFIG = Path("../proyectoconsola/public/config/prediccion.json")
DAYS = "2026-09-14,2026-09-15,2026-09-16" if SMOKE else "2026-07-20:2026-10-14"
TRAIN_START = "2026-09-14" if SMOKE else "2026-07-20"
MIN_TRIPS_DAY = 12.0           # criterio de datos: viajes con forma por día (promedio sobre los días con datos) en el período
MIN_VAL_ROWS = 1000            # y filas de validación (días 2026-09-15 -> 10-14, sin muestrear)
NMIN = 100                     # n mínimo de filas de la banda 3-7 min para exigir el criterio por línea
CONTROL = ["1", "12", "15", "21", "64", "65", "68", "87", "100", "109", "128", "181"]
SMOKE_LINES = ["39", "26", "154", "60", "1", "12"]
RUN2 = ("full", 1)             # (nombre, semilla): candidato a producción
RUN1 = ("ctrl", 0)
MAIN = "3-7 min (principal)"
PROD_LABEL = "v3_l1_paradas_s1"     # path_v3_l1_s1 (producción); s0 como referencia de ruido entre semillas
N_PER_BUCKET = 300 if SMOKE else 40000
PY = [sys.executable, "-u", "-m"]
PYUTF = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    BASE.mkdir(parents=True, exist_ok=True)
    with open(BASE / "launcher.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def sh(cmd: list[str], logname: str, cpu_only: bool = False) -> int:
    env = dict(PYUTF)
    if cpu_only:
        env["CUDA_VISIBLE_DEVICES"] = ""
    (BASE / "logs").mkdir(parents=True, exist_ok=True)
    with open(BASE / "logs" / logname, "a", encoding="utf-8") as out:
        return subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT, env=env).returncode


def step(cmd: list[str], logname: str, cpu_only: bool = False) -> None:
    rc = sh(cmd, logname, cpu_only)
    if rc != 0:
        raise RuntimeError(f"{' '.join(cmd[3:5])} (rc={rc}); ver logs/{logname} y relanzar para reanudar")


# --------------------------------------------------------------------------------------------- líneas candidatas
def candidates() -> list[str]:
    """Líneas AMBA con número < 200 que figuran en LABEL_LINE_MAP (`lines`, solo AMBA) y tienen shapes en line_shapes."""
    if SMOKE:
        return SMOKE_LINES
    m = json.loads(Path("LABEL_LINE_MAP.json").read_text(encoding="utf-8"))["lines"]
    sh_ = {p.stem for p in SHAPES_DIR.glob("*.json") if p.stem.isdigit()}
    return sorted((l for l in m if l.isdigit() and int(l) < 200 and l in sh_), key=int)


def write_lines_file(lines: list[str]) -> Path:
    lf = V4 / "lines.json"
    d = {"train": lines, "heldout": [], "n_train": len(lines), "n_heldout": 0,
         "criteria": "todas las líneas AMBA < 200 con shapes en proyectoconsola/data/line_shapes y en LABEL_LINE_MAP (build); "
                     "la selección por volumen está en selection.json"}
    new = json.dumps(d, indent=1)
    if not lf.exists() or lf.read_text(encoding="utf-8") != new:
        V4.mkdir(parents=True, exist_ok=True)
        lf.write_text(new, encoding="utf-8")
    return lf


# --------------------------------------------------------------------------------------------- 0. entorno
def start_keep_awake() -> None:
    out = BASE / "keep_awake.out"
    BASE.mkdir(parents=True, exist_ok=True)
    out.write_text("", encoding="utf-8")
    subprocess.Popen([sys.executable, "-u", "prediccion/scripts/keep_awake.py", str(os.getpid())], stdout=open(out, "a"),
                     stderr=subprocess.STDOUT, creationflags=0x08000000)
    for _ in range(30):
        time.sleep(1)
        if "keep_awake activo" in out.read_text(encoding="utf-8", errors="ignore"):
            log(f"keep_awake activo (pid vigilado {os.getpid()})")
            return
    raise RuntimeError("keep_awake no confirmó 'keep_awake activo'")


def preflight() -> None:
    free = shutil.disk_usage(".").free / 1e9
    log(f"disco libre: {free:.0f} GB")
    if not SMOKE and free < 60:
        raise RuntimeError(f"disco libre {free:.0f} GB < 60 GB")
    import torch
    cuda = torch.cuda.is_available()
    log(f"python {sys.executable}; torch cuda disponible: {cuda}")
    if not SMOKE and not cuda:
        raise RuntimeError("CUDA no disponible: usar el Python 3.13 del sistema")


# --------------------------------------------------------------------------------------------- 1. build
def expected_days() -> list[str]:
    from prediccion.v2.build import available_days, parse_days
    return available_days(parse_days(DAYS), Path(DATA_DIR))


def day_blocks(days: list[str], n: int) -> list[list[str]]:
    return [days[i:i + n] for i in range(0, len(days), n)]


def pending_days(days: list[str], lines: list[str]) -> list[str]:
    from prediccion.v2.day import day_is_done, read_meta
    out = []
    for d in days:
        m = read_meta(V4, d)
        if not (m and day_is_done(m, sorted(lines), 32, False, "geo2", "geo3", "any", 1.0)):
            out.append(d)
    return out


def workers_now() -> int:
    if SMOKE:
        return 1
    try:
        import psutil
        return max(3, min(6, int(psutil.virtual_memory().available / 4.5e9)))
    except Exception:  # noqa: BLE001
        return 4


def build(lines: list[str], lf: Path) -> None:
    days = expected_days()
    t0 = time.time()
    for attempt in range(3):
        todo = pending_days(days, lines)
        if not todo:
            break
        log(f"build v4 intento {attempt + 1}: {len(todo)} días pendientes de {len(days)}")
        for i, blk in enumerate(day_blocks(todo, 4 if SMOKE else 24)):
            w = workers_now()
            log(f"build v4 bloque {i + 1} ({blk[0]} .. {blk[-1]}, {len(blk)} días): {w} workers")
            cmd = PY + ["prediccion.v2.build", "--lines-file", str(lf), "--lines", ",".join(lines), "--days", ",".join(blk),
                        "--pairs-per-trip", "32", "--workers", str(w), "--chunk-days", "3", "--segmentation", "geo2",
                        "--assign", "geo3", "--out-dir", str(V4), "--no-assemble", "--data-dir", DATA_DIR]
            sh(cmd, "build.log")     # rc != 0 por días con error: se reintentan en la vuelta siguiente
            log(f"build v4: {(time.time() - t0) / 60:.0f} min transcurridos")
    left = pending_days(days, lines)
    if left:
        raise RuntimeError(f"días sin construir tras 3 intentos: {left}")
    log(f"build v4 completo: {len(days)} días, {(time.time() - t0) / 60:.0f} min")


# --------------------------------------------------------------------------------------------- 2. selección
def select(lines: list[str]) -> list[str]:
    sel_path = V4 / "selection.json"
    if sel_path.exists():
        return json.loads(sel_path.read_text(encoding="utf-8"))["selected"]
    import pyarrow.parquet as pq
    acc = {ln: dict(trips=0, shaped=0, rows=0, su_rows=0, days=set(), val_rows=0) for ln in lines}
    ndays = 0
    for f in sorted((V4 / "daily").glob("*.trips.parquet")):
        day = f.name[:10]
        ndays += 1
        t = pq.read_table(f, columns=["line", "start_unknown", "n_rows"]).to_pandas()
        for ln, g in t.groupby("line"):
            a = acc.get(str(ln))
            if a is None:
                continue
            su = g["start_unknown"].astype(bool)
            a["trips"] += len(g)
            a["rows"] += int(g["n_rows"].sum())
            a["su_rows"] += int(g.loc[su, "n_rows"].sum())
            ok = g["n_rows"] > 0
            a["shaped"] += int(ok.sum())
            if ok.any():
                a["days"].add(day)
                if day >= "2026-09-15":
                    a["val_rows"] += int(g["n_rows"].sum())
    selected, excluded, rows = [], {}, []
    for ln in lines:
        a = acc[ln]
        nd = len(a["days"])
        tpd = a["shaped"] / nd if nd else 0.0
        reason = None
        if nd == 0 or a["rows"] == 0:
            reason = "sin filas"
        elif tpd < MIN_TRIPS_DAY:
            reason = f"{tpd:.1f} viajes con forma por día < {MIN_TRIPS_DAY:g}"
        elif a["val_rows"] < MIN_VAL_ROWS:
            reason = f"{a['val_rows']} filas de validación < {MIN_VAL_ROWS}"
        if reason:
            excluded[ln] = reason
        else:
            selected.append(ln)
        rows.append(f"| {ln} | {nd} | {a['trips']} | {a['shaped']} | {tpd:.1f} | {a['rows']} | {a['val_rows']} | "
                    f"{100 * a['su_rows'] / max(a['rows'], 1):.1f} | {'incluida' if not reason else 'excluida: ' + reason} |")
    (V4 / "validation").mkdir(parents=True, exist_ok=True)
    (V4 / "validation" / "summary.md").write_text(
        "\n".join([f"# Validación del build v4: {ndays} días", "",
                   f"Criterio de inclusión: >= {MIN_TRIPS_DAY:g} viajes con forma por día (promedio sobre días con datos) y >= {MIN_VAL_ROWS} "
                   f"filas de validación (2026-09-15 -> 10-14).", "",
                   "| línea | días con filas | viajes | viajes con forma | viajes con forma/día | filas | filas val | % filas start_unknown | decisión |",
                   "|---|---:|---:|---:|---:|---:|---:|---:|---|"] + rows) + "\n", encoding="utf-8")
    sel_path.write_text(json.dumps({"selected": selected, "excluded": excluded, "min_trips_day": MIN_TRIPS_DAY,
                                    "min_val_rows": MIN_VAL_ROWS, "candidates": lines}, indent=1, ensure_ascii=False), encoding="utf-8")
    log(f"selección: {len(selected)} líneas incluidas de {len(lines)}; excluidas: {excluded or 'ninguna'}")
    return selected


# --------------------------------------------------------------------------------------------- 3. ensamblado y eval
def assemble_all(selected: list[str]) -> None:
    ctrl_set = [c for c in CONTROL if c in selected]
    train_ctrl = [l for l in selected if l not in ctrl_set]
    lf_ctrl = V4 / "lines_ctrl.json"
    lf_ctrl.write_text(json.dumps({"train": train_ctrl, "heldout": ctrl_set}, indent=1), encoding="utf-8")
    lf_full = V4 / "lines.json"
    for dest, lf, only in ((FULL, lf_full, selected), (CTRL, lf_ctrl, train_ctrl)):
        if (dest / "assembled.json").exists():
            continue
        log(f"ensambla {dest} ({len(only)} líneas)")
        step(PY + ["prediccion.v2.assemble", "--v2-dir", str(V4), "--lines-file", str(lf), "--only-lines", ",".join(only),
                   "--dest", str(dest), "--train-start", TRAIN_START, "--val-sample-frac", "0.4"], f"assemble_{dest.name}.log")
        a = json.loads((dest / "assembled.json").read_text(encoding="utf-8"))
        log(f"{dest}: {a['rows_train']:,} filas train ({a['n_train_days']} días), {a['rows_val']:,} val ({a['n_val_days']} días)")
    if not (V4 / "eval" / "eval_seen.parquet").exists():
        log("congela el eval v4 (seen = líneas seleccionadas)")
        # make_eval usa train del lines-file como seen: archivo con solo las seleccionadas
        lf_sel = V4 / "lines_selected.json"
        lf_sel.write_text(json.dumps({"train": selected, "heldout": []}), encoding="utf-8")
        step(PY + ["prediccion.v2.make_eval", "--v2-dir", str(V4), "--lines-file", str(lf_sel), "--n-per-bucket", str(N_PER_BUCKET)],
             "make_eval.log")


# --------------------------------------------------------------------------------------------- 4. entrenamiento
def run_dir(name: str, seed: int) -> Path:
    return (FULL if name == "full" else CTRL) / "runs" / f"path_lr2e-3_s{seed}"


def train(name: str, seed: int) -> None:
    d = run_dir(name, seed)
    ml = FULL if name == "full" else CTRL
    lf = V4 / ("lines_selected.json" if name == "full" else "lines_ctrl.json")
    if (d / "path_eta_metrics.json").exists():
        log(f"saltea {name} s{seed}: ya terminó")
        return
    d.mkdir(parents=True, exist_ok=True)
    cmd = PY + ["prediccion.train_path", "--ml-dir", str(ml), "--out-dir", str(d), "--lines-file", str(lf),
                "--epochs", "1" if SMOKE else "12", "--batch-size", "1024", "--lr", "2e-3", "--seed", str(seed),
                "--loss", "l1", "--stops-feature", "--resume"]
    if SMOKE:
        cmd += ["--max-groups", "3", "--device", "cpu", "--workers", "0"]
    logf = BASE / "logs" / f"train_{name}_s{seed}.log"
    logf.parent.mkdir(parents=True, exist_ok=True)
    log(f"entrena {name} s{seed} -> {d}")
    t0 = time.time()
    env = dict(PYUTF)
    if SMOKE:
        env["CUDA_VISIBLE_DEVICES"] = ""
    with open(logf, "a", encoding="utf-8") as out:
        p = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, env=env)
        want = "device=cpu" if SMOKE else "device=cuda"
        checked = False
        while p.poll() is None:
            time.sleep(20)
            if not checked:
                txt = logf.read_text(encoding="utf-8", errors="ignore")
                if "device=" in txt:
                    checked = True
                    if want not in txt:
                        p.kill()
                        raise RuntimeError(f"entrenamiento {name} s{seed} sin {want}; ver {logf}")
                    log(f"{name} s{seed}: {want} confirmado")
        rc = p.returncode
    if rc != 0 or not (d / "path_eta_metrics.json").exists():
        raise RuntimeError(f"entrenando {name} s{seed} (rc={rc}); relanzar para reanudar")
    m = json.loads((d / "path_eta_metrics.json").read_text(encoding="utf-8"))
    log(f"terminó {name} s{seed} en {(time.time() - t0) / 60:.1f} min; val MAE {m['best_val_mae_s']:.1f}")


def evaluate(name: str, seed: int, which: str, v2dir: Path, tag: str) -> Path:
    out = BASE / "eval" / f"{name}_s{seed}_{tag}"
    f = sorted(out.glob(f"*_{which}_*.pred.npy"))
    if f:
        return f[-1]
    log(f"evalúa {name} s{seed} {which} en {v2dir}")
    cmd = PY + ["prediccion.eval", "--model", f"path:{run_dir(name, seed) / 'path_eta_best.pt'}", "--set", which,
                "--v2-dir", str(v2dir), "--out-dir", str(out), "--save-preds"]
    step(cmd, f"eval_{name}_s{seed}_{tag}_{which}.log", cpu_only=SMOKE)
    return sorted(out.glob(f"*_{which}_*.pred.npy"))[-1]


# --------------------------------------------------------------------------------------------- 6. comparación
def table(v2dir: Path, which: str):
    import pyarrow.parquet as pq
    t = pq.read_table(v2dir / "eval" / f"eval_{which}.parquet", columns=["line", "observed_eta_s"])
    return np.asarray(t["line"].to_pylist(), dtype=str), np.asarray(t["observed_eta_s"], dtype=np.float64)


def prod_pred(which: str, label: str = PROD_LABEL) -> np.ndarray:
    return np.load(sorted((V3_RUNS / label).glob(f"*_{which}_*.pred.npy"))[-1]).astype(np.float64)


def band(pred, true, mask=None) -> dict:
    from prediccion.eval import compute_eta_bands
    if mask is not None:
        pred, true = pred[mask], true[mask]
    return compute_eta_bands(pred, true)[MAIN]


def f1(x, nd=1):
    return "n/d" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"


def comparison(cand_seen: Path, cand_ctrl: Path | None, cand_v4: Path | None, v4_lines: list[str], runs_note: str) -> dict:
    """Garantía de no regresión (46 líneas habilitadas, eval congelado v3, banda 3-7 min) y habilitación de líneas nuevas."""
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    enabled = [e["line"] for e in cfg["enabledLines"]]
    line, true = table(V3, "seen")
    cand, prod = np.load(cand_seen).astype(np.float64), prod_pred("seen")
    prod0 = prod_pred("seen", "v3_l1_paradas_s0")
    if not (len(cand) == len(prod) == len(line)):
        raise RuntimeError(f"largos distintos: cand {len(cand)}, prod {len(prod)}, eval {len(line)}")
    m46 = np.isin(line, enabled)
    out = [f"# No regresión en las {len(enabled)} líneas habilitadas ({runs_note})", "",
           f"Eval congelado `data/ml/v3/eval/eval_seen.parquet` (mismas filas para ambos modelos), banda de ETA real {MAIN}. "
           f"Producción = `path_v3_l1_s1` (semilla 1); ruido de referencia = la semilla 0 de v3 contra la 1.", ""]
    bc, bp, b0 = band(cand, true, m46), band(prod, true, m46), band(prod0, true, m46)
    d_mae = bc["mae"] - bp["mae"]
    ok_global = d_mae <= 1.0
    out += ["## Global (46 líneas)", "", "| modelo | n | MAE (s) | P90 error abs. (s) | llega antes >60 s (%) | llega después >60 s (%) |", "|---|---:|---:|---:|---:|---:|"]
    for nm, b in (("candidato", bc), ("producción v3 s1", bp), ("v3 s0 (referencia de ruido)", b0)):
        out.append(f"| {nm} | {int(b['n'])} | {f1(b['mae'])} | {f1(b['p90'])} | {f1(b['pct_llega_antes_60s'])} | {f1(b['pct_llega_despues_60s'])} |")
    out += ["", f"Diferencia de MAE agregado (candidato menos producción): {d_mae:+.2f} s; criterio <= +1,0 s: {'CUMPLE' if ok_global else 'NO CUMPLE'}.", "",
            f"## Por línea (n mínimo {NMIN} filas de la banda para exigir el criterio de +5 s)", "",
            "| línea | n | MAE cand. | MAE prod. | dif. (s) | llega antes cand. % | llega antes prod. % | llega después cand. % | llega después prod. % | dif. v3 s0 vs s1 | criterio |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    bad, small = [], []
    per_line = {}
    for ln in enabled:
        m = line == ln
        if not m.any():
            out.append(f"| {ln} | 0 | | | | | | | | | sin filas en el eval |")
            small.append(ln)
            continue
        c, p, z = band(cand, true, m), band(prod, true, m), band(prod0, true, m)
        n = int(c["n"])
        dd = (c["mae"] - p["mae"]) if n else float("nan")
        per_line[ln] = dict(n=n, mae_cand=c["mae"], mae_prod=p["mae"], diff=dd)
        if n < NMIN:
            verdict = f"n < {NMIN}: informativo"
            small.append(ln)
        elif dd > 5.0:
            verdict = "FALLA (> +5 s)"
            bad.append(ln)
        else:
            verdict = "ok"
        out.append(f"| {ln} | {n} | {f1(c['mae'])} | {f1(p['mae'])} | {f1(dd)} | {f1(c['pct_llega_antes_60s'])} | {f1(p['pct_llega_antes_60s'])} | "
                   f"{f1(c['pct_llega_despues_60s'])} | {f1(p['pct_llega_despues_60s'])} | {f1(z['mae'] - p['mae'])} | {verdict} |")
    out += ["", f"Líneas con n < {NMIN} (no deciden): {', '.join(small) or 'ninguna'}. Líneas que fallan el criterio de +5 s: {', '.join(bad) or 'ninguna'}.", ""]
    # 61 y 88 (no habilitadas) y las otras del eval seen, informativo
    others = [l for l in sorted(set(line.tolist()), key=int) if l not in enabled]
    out += ["## Líneas del eval seen no habilitadas (informativo)", "", "| línea | n | MAE cand. | MAE prod. |", "|---|---:|---:|---:|"]
    for ln in others:
        m = line == ln
        c, p = band(cand, true, m), band(prod, true, m)
        out.append(f"| {ln} | {int(c['n'])} | {f1(c['mae'])} | {f1(p['mae'])} |")
    # heldout: líneas de control
    ctrl_summary = None
    if cand_ctrl is not None:
        lh, th = table(V3, "heldout")
        ch, ph = np.load(cand_ctrl).astype(np.float64), prod_pred("heldout")
        out += ["", "## Líneas de control (eval heldout de v3; para el candidato full ya no son desconocidas)", "",
                "| conjunto | n | MAE cand. | MAE prod. (v3 s1) | llega antes cand. % | llega antes prod. % |", "|---|---:|---:|---:|---:|---:|"]
        for nm, mm in (("las 12 de control", np.ones(len(lh), bool)), ("12, 15, 128", np.isin(lh, ["12", "15", "128"]))):
            c, p = band(ch, th, mm), band(ph, th, mm)
            out.append(f"| {nm} | {int(c['n'])} | {f1(c['mae'])} | {f1(p['mae'])} | {f1(c['pct_llega_antes_60s'])} | {f1(p['pct_llega_antes_60s'])} |")
        ctrl_summary = band(ch, th)["mae"]
    publish = ok_global and not bad
    decision = {"publish": publish, "global_mae_diff_s": d_mae, "global_ok": ok_global, "lines_failing_5s": bad, "lines_small_n": small,
                "mae_cand_46": bc["mae"], "mae_prod_46": bp["mae"], "per_line": per_line, "nmin": NMIN}
    # líneas nuevas: eval de v4, banda 3-7, seen del candidato full
    if cand_v4 is not None:
        l4, t4 = table(V4, "seen")
        p4 = np.load(cand_v4).astype(np.float64)
        med46 = float(np.median([band(p4, t4, l4 == ln)["mae"] for ln in enabled if (l4 == ln).sum() and band(p4, t4, l4 == ln)["n"] >= NMIN]))
        out += ["", "## Líneas nuevas (eval congelado de v4, seen, candidato full, banda 3-7 min)", "",
                f"Mediana del MAE de las líneas habilitadas actuales en este eval: {med46:.1f} s; umbral de habilitación 1,3 x mediana = {1.3 * med46:.1f} s, n >= {NMIN}.", "",
                "| línea | n | MAE (s) | llega antes >60 s % | llega después >60 s % | decisión |", "|---|---:|---:|---:|---:|---|"]
        new_en, new_no = [], {}
        for ln in sorted(set(v4_lines) - set(enabled), key=int):
            m = l4 == ln
            b = band(p4, t4, m)
            if ln in ("61", "88"):
                why = "no habilitada a propósito (decisión del usuario)"
            elif int(b["n"]) < NMIN:
                why = f"n = {int(b['n'])} < {NMIN}"
            elif b["mae"] > 1.3 * med46:
                why = f"MAE {b['mae']:.1f} s > 1,3 x mediana"
            else:
                why = None
            if why:
                new_no[ln] = why
            else:
                new_en.append(ln)
            out.append(f"| {ln} | {int(b['n'])} | {f1(b['mae'])} | {f1(b['pct_llega_antes_60s'])} | {f1(b['pct_llega_despues_60s'])} | {'habilitar' if not why else 'no: ' + why} |")
        decision.update({"median_mae_enabled_v4eval": med46, "new_enabled": new_en, "new_not_enabled": new_no})
    out += ["", f"## Decisión automática: {'PUBLICAR (criterios cumplidos)' if publish else 'NO PUBLICAR'}", ""]
    (BASE / "no_regresion.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    (BASE / "decision.json").write_text(json.dumps(decision, indent=1, ensure_ascii=False), encoding="utf-8")
    return decision


def main() -> int:
    BASE.mkdir(parents=True, exist_ok=True)
    log("inicio / reanudación del lanzador v4" + (" [smoke]" if SMOKE else ""))
    try:
        start_keep_awake()
        preflight()
        lines = candidates()
        lf = write_lines_file(lines)
        log(f"{len(lines)} líneas candidatas: {','.join(lines)}")
        build(lines, lf)
        selected = select(lines)
        assemble_all(selected)
        train(*RUN2)
        train(*RUN1)
        if SMOKE:
            evaluate("full", 1, "seen", V4, "v4")
            log("listo: smoke v4 (build, selección, ensamblado, entrenamiento, eval)")
            return 0
        full_seen = evaluate("full", 1, "seen", V3, "v3")
        full_ctrl = evaluate("full", 1, "heldout", V3, "v3")
        full_v4 = evaluate("full", 1, "seen", V4, "v4")
        evaluate("ctrl", 0, "seen", V3, "v3")
        evaluate("ctrl", 0, "heldout", V3, "v3")
        evaluate("ctrl", 0, "seen", V4, "v4")
        d = comparison(full_seen, full_ctrl, full_v4, selected, "run 2 full, semilla 1")
        log(f"decisión: publish={d['publish']} dif MAE global {d['global_mae_diff_s']:+.2f} s; fallan: {d['lines_failing_5s'] or 'ninguna'}")
    except Exception as e:  # noqa: BLE001
        log(f"ERROR {e}")
        return 1
    log("listo: v4 entrenado y evaluado (ver no_regresion.md y decision.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
