"""
Lanzador reanudable del experimento "Tránsito actual por tramo" (ARQUITECTURA.md §11, ítem 1): modelo por tramos con la
entrada nueva `--traffic-feature` (velocidad / coches / quietos de la celda de cada tramo, ventanas completas previas a
ts_p; contrato en `prediccion/v2/traffic/feature.py`). Un solo cambio contra la base `v2c_l1_paradas`.

Base: data/ml/v2c_sub/runs_stops (L1 + --stops-feature, LR 2e-3, 12 épocas, OneCycle, batch 1024, semillas 0 y 1).
Nuevo: lo mismo + `--traffic-feature`, semillas 0 y 1 -> data/ml/v2c_sub/runs_traffic/path_lr2e-3_s{0,1}.
Eval: el mismo de la base, data/ml/v2c/eval (seen = 12 líneas de train; heldout = 12, 15, 128).

Etapas, todas idempotentes (si algo se corta, volver a ejecutar el mismo comando):
  0. keep_awake: el lanzador arranca `prediccion/scripts/keep_awake.py <su pid>` y verifica `keep_awake activo`
  1. tabla densa de tránsito data/ml/v2c_sub/traffic_dense.npz (si falta; desde data/ml/v2/traffic/daily) y chequeo de cobertura
  2. ESPERA a que termine la corrida de GPU de v3full (última línea de data/ml/v3full_sub/runs/launcher.log = `listo: ...` o
     `ERROR ...`) y a que la GPU esté libre (memoria usada < GPU_FREE_MB). No toca ningún proceso ajeno.
  3. entrenamiento de las dos semillas; el log tiene que decir device=cuda (si no, aborta)
  4. evaluación (seen y heldout) de nuevo y base con predicciones por fila, cobertura de tránsito de las filas de eval
  5. runs_traffic/comparacion.md: banda 3-7 min (MAE, P90, % llega antes / después >60 s, % de tramos con dato), MAE por
     banda de ETA, seen y heldout, media de semillas y por semilla, desglose por línea
Línea final de runs_traffic/launcher.log: `listo: tránsito entrenado y evaluado` o `ERROR ...`.

Lanzar con el Python 3.13 del sistema y desacoplado:
  $PY = "C:\\Users\\LK\\AppData\\Local\\Programs\\Python\\Python313\\python.exe"
  Start-Process $PY -ArgumentList "-u","-m","prediccion.scripts.run_traffic" -WindowStyle Hidden -PassThru -RedirectStandardOutput <out> -RedirectStandardError <err>
`--smoke`: prueba chica de punta a punta (1 row group, 1 época, CPU, 1 worker) en data/ml/v2c_sub/runs_traffic_smoke; no espera la GPU.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from prediccion.scripts import run_v2b as R
from prediccion.scripts.run_v2c import BANDS, KEYS, MAIN, SEEDS, SUB, V2C

SMOKE = R.SMOKE
if SMOKE:
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
R.ML, R.V2B = SUB, V2C
R.BASE = SUB / ("runs_traffic_smoke" if SMOKE else "runs_traffic")
BASE = R.BASE
TABLE = SUB / "traffic_dense.npz"
GATE_LOG = Path("data/ml/v3full_sub/runs/launcher.log")      # corrida de GPU en curso (otro agente): no se toca
GPU_FREE_MB = 2500                                           # memoria de GPU usada máxima para arrancar (la base del escritorio ronda 0,8 GB)
BASE_RUNS = SUB / "runs_stops"
L_BASE, L_NEW = "v2c_l1_paradas", "v2c_l1_paradas_traffic"
log = R.log


# ── 0. keep_awake ────────────────────────────────────────────────────────────

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


# ── 1. tabla ─────────────────────────────────────────────────────────────────

def ensure_table() -> None:
    if TABLE.exists():
        log(f"tabla de tránsito presente: {TABLE}")
        return
    log("arma la tabla densa de tránsito")
    rc = R.sh([sys.executable, "-u", "-m", "prediccion.v2.traffic.feature", "--out", str(TABLE),
               "--lines-file", str(V2C / "lines.json")], BASE / "logs" / "traffic_table.log")
    if rc != 0:
        raise RuntimeError("armando la tabla de tránsito; ver logs/traffic_table.log")


# ── 2. espera de la GPU ──────────────────────────────────────────────────────

def gate_state() -> tuple[bool, str]:
    """(libre, motivo). Libre = el log de v3full terminó (`listo:` / `ERROR`) y la memoria de GPU usada es baja."""
    if GATE_LOG.exists():
        lines = [ln for ln in GATE_LOG.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
        last = lines[-1] if lines else ""
        if " listo:" not in last and " ERROR" not in last:
            return False, f"v3full sigue: {last[:90]}"
    try:
        used = int(subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                  capture_output=True, text=True, timeout=30).stdout.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        return True, "nvidia-smi no disponible"
    if used > GPU_FREE_MB:
        return False, f"GPU ocupada ({used} MiB usados)"
    return True, f"GPU libre ({used} MiB usados)"


def wait_gpu() -> None:
    if SMOKE:
        return
    t_log = 0.0
    while True:
        free, why = gate_state()
        if free:
            log(f"sigue: {why}")
            return
        if time.time() - t_log > 900:
            log(f"espera la GPU: {why}")
            t_log = time.time()
        time.sleep(60)


# ── 3. entrenamiento ─────────────────────────────────────────────────────────

def train_cmd(seed: int) -> list[str]:
    cmd = R.train_cmd("path", "2e-3", seed) + ["--loss", "l1", "--stops-feature", "--traffic-feature",
                                               "--traffic-table", str(TABLE)]
    if SMOKE:
        cmd[cmd.index("--max-groups") + 1] = "1"
        cmd += ["--device", "cpu", "--workers", "1"]
    return cmd


def train(seed: int) -> None:
    d = R.run_dir("path", "2e-3", seed)
    if R.metrics_path("path", d).exists():
        log(f"saltea {d.name}: ya terminó")
        return
    d.mkdir(parents=True, exist_ok=True)
    wait_gpu()
    lg = BASE / "logs" / f"{d.name}.log"
    lg.parent.mkdir(parents=True, exist_ok=True)
    log(f"entrena {d.name}")
    t0 = time.time()
    with open(lg, "a", encoding="utf-8") as out:
        p = subprocess.Popen(train_cmd(seed), stdout=out, stderr=subprocess.STDOUT,
                             env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        checked = SMOKE
        while p.poll() is None:
            time.sleep(5)
            if not checked:
                txt = lg.read_text(encoding="utf-8", errors="replace")
                if "device=" in txt:           # la línea de arranque del trainer: aborta si no es CUDA (falló el 2026-11-14)
                    checked = True
                    if "device=cuda" not in txt:
                        p.kill()
                        raise RuntimeError(f"el entrenamiento no arrancó en CUDA ({lg.name}); usar el Python 3.13 del sistema")
                    log(f"{d.name}: device=cuda verificado")
    if p.returncode != 0 or not R.metrics_path("path", d).exists():
        raise RuntimeError(f"entrenando {d.name} (rc={p.returncode}); relanzar el lanzador para reanudar")
    log(f"terminó {d.name} en {(time.time() - t0) / 60:.1f} min; val MAE {R.val_mae('path', d):.1f}")


# ── 4. evaluación y cobertura ────────────────────────────────────────────────

def ckpt(label: str, s: int) -> Path:
    return R.best_ckpt("path", (BASE_RUNS if label == L_BASE else BASE) / f"path_lr2e-3_s{s}")


def evaluate(label: str, s: int) -> None:
    for which in ("seen", "heldout"):
        name = f"{label}_s{s}"
        out = BASE / "eval" / name
        if list(out.glob(f"*_{which}_*.json")) and list(out.glob(f"*_{which}_*.pred.npy")):
            continue
        log(f"evalúa {name} {which}")
        rc = R.sh([sys.executable, "-u", "-m", "prediccion.eval", "--model", f"path:{ckpt(label, s)}", "--set", which,
                   "--v2-dir", str(V2C), "--out-dir", str(out), "--save-preds"], BASE / "logs" / f"eval_{name}_{which}.log")
        if rc != 0:
            raise RuntimeError(f"evaluando {name} {which} (rc={rc})")


def eval_table(which: str):
    import pyarrow.parquet as pq
    t = pq.read_table(V2C / "eval" / f"eval_{which}.parquet", columns=["line", "observed_eta_s"])
    return np.asarray(t["line"].to_pylist(), dtype=str), np.asarray(t["observed_eta_s"], dtype=np.float64)


def coverage(which: str) -> dict:
    """Cobertura por fila del eval (no depende de la semilla: solo de la tabla y del camino); se cachea en runs_traffic/."""
    f = BASE / f"coverage_{which}.npz"
    if f.exists():
        z = np.load(f)
        return {k: z[k] for k in z.files}
    from prediccion.models.path_eta import path_traffic_coverage
    n = len(eval_table(which)[1])
    cov = path_traffic_coverage(V2C / "eval" / f"eval_{which}.parquet", ckpt(L_NEW, SEEDS[0]), n)
    np.savez(f, **cov)
    return cov


# ── 5. comparación ───────────────────────────────────────────────────────────

def pct_data(cov: dict, m, key: str = "con_dato") -> float:
    return float(100.0 * cov[key][m].sum() / max(cov["n_seg"][m].sum(), 1))


def comparison() -> None:
    from prediccion.eval import ETA_BANDS_MIN, MAIN_BAND_MIN, compute_eta_bands
    labels = (L_BASE, L_NEW)
    out = ["# Tránsito actual por tramo contra la base `v2c_l1_paradas`, mismo eval (`data/ml/v2c/eval`)", "",
           f"`{L_BASE}`: modelo por tramos L1 + `--stops-feature` (`data/ml/v2c_sub/runs_stops`); `{L_NEW}`: igual + "
           "`--traffic-feature` (`data/ml/v2c_sub/runs_traffic`). Un solo cambio; semillas 0 y 1; cada celda es la media "
           "de las semillas salvo donde se aclara. Llega antes / después = % de filas con error > 60 s (llega antes = pred - "
           "real > 60 s); espera extra = media de (real - pred) cuando llega después. "
           f"Banda principal: {MAIN}. **% tramos con dato** = tramos de 250 m del camino P->T cuya celda tiene algún coche de la "
           "flota en las 2 ventanas completas previas a ts_p (= la información real que ve el modelo; el resto entra como máscara); "
           "**% con velocidad** = además con algún coche en movimiento. Se calcula sobre las filas de la banda (tramos "
           "acumulados, no promedio de promedios) y es igual para base y nuevo (la base no usa tránsito).", ""]
    verdict = []
    for which in ("seen", "heldout"):
        line, true = eval_table(which)
        cov = coverage(which)
        preds = {lb: [np.load(sorted((BASE / "eval" / f"{lb}_s{s}").glob(f"*_{which}_*.pred.npy"))[-1]).astype(np.float64)
                      for s in SEEDS] for lb in labels}
        for lb in labels:
            for p in preds[lb]:
                if len(p) != len(line):
                    raise RuntimeError(f"{lb} {which}: {len(p)} predicciones contra {len(line)} filas del eval")

        def bands(lb, i, m=None):
            m = np.ones(len(line), bool) if m is None else m
            return compute_eta_bands(preds[lb][i][m], true[m])

        def avg(lb, band, k, m=None):
            v = [bands(lb, i, m)[band][k] for i in range(len(SEEDS))]
            return float(np.mean([np.nan if x is None else x for x in v]))

        def bmask(band):
            lo, hi = MAIN_BAND_MIN if band == MAIN else next((a, b) for a, b in ETA_BANDS_MIN if f"{a}-{b} min" == band)
            return (true >= lo * 60.0) & (true < hi * 60.0)

        mm = bmask(MAIN)
        out += [f"## {which}: ETA real {MAIN} (n = {int(mm.sum())})", "",
                "| modelo | " + " | ".join(h for _, h in KEYS) + " | % tramos con dato | % con velocidad |",
                "|---|" + "---:|" * (len(KEYS) + 2)]
        for lb in labels:
            out.append(f"| {lb} | " + " | ".join(f"{avg(lb, MAIN, k):.1f}" for k, _ in KEYS)
                       + f" | {pct_data(cov, mm):.1f} | {pct_data(cov, mm, 'con_velocidad'):.1f} |")
        out += ["", f"### {which}: semillas 0 / 1 en {MAIN}", "",
                "| modelo | MAE s0 / s1 (s) | diferencia entre semillas (s) | llega antes s0 / s1 (%) | llega después s0 / s1 (%) |",
                "|---|---|---:|---|---|"]
        mae, gap = {}, {}
        for lb in labels:
            b = [bands(lb, i)[MAIN] for i in range(len(SEEDS))]
            mae[lb], gap[lb] = float(np.mean([x["mae"] for x in b])), abs(b[0]["mae"] - b[1]["mae"])
            out.append(f"| {lb} | {b[0]['mae']:.1f} / {b[1]['mae']:.1f} | {gap[lb]:.1f} | "
                       f"{b[0]['pct_llega_antes_60s']:.1f} / {b[1]['pct_llega_antes_60s']:.1f} | "
                       f"{b[0]['pct_llega_despues_60s']:.1f} / {b[1]['pct_llega_despues_60s']:.1f} |")
        gain, thr = mae[L_BASE] - mae[L_NEW], max(gap.values())
        verdict.append((which, gain, thr))
        out += ["", f"Mejora del MAE medio en {MAIN}: {gain:+.1f} s (diferencia entre semillas: {thr:.1f} s, la mayor de las dos "
                    f"familias) -> {'supera' if gain > thr else 'no supera'} el criterio.", "",
                f"### {which}: MAE (s) por banda de ETA real y % de tramos con dato", "",
                "| banda | n | " + f"{L_BASE} MAE | {L_NEW} MAE | diferencia | llega antes base / nuevo (%) | % tramos con dato |",
                "|---|---:|---:|---:|---:|---|---:|"]
        for band in [MAIN] + [b for b in BANDS if b != MAIN]:
            bm = bmask(band)
            a, b = avg(L_BASE, band, "mae"), avg(L_NEW, band, "mae")
            out.append(f"| {band} | {int(bm.sum())} | {a:.1f} | {b:.1f} | {b - a:+.1f} | "
                       f"{avg(L_BASE, band, 'pct_llega_antes_60s'):.1f} / {avg(L_NEW, band, 'pct_llega_antes_60s'):.1f} | "
                       f"{pct_data(cov, bm):.1f} |")
        out += ["", f"### {which}: desglose por línea, banda {MAIN}", "",
                f"| línea | n | MAE {L_BASE} | MAE {L_NEW} | diferencia | llega antes base / nuevo (%) | llega después base / nuevo (%) "
                "| % tramos con dato |", "|---|---:|---:|---:|---:|---|---|---:|"]
        for ln in sorted(set(line.tolist()), key=lambda x: (len(x), x)):
            m = (line == ln) & mm
            if m.sum() == 0:
                continue
            a, b = avg(L_BASE, MAIN, "mae", m), avg(L_NEW, MAIN, "mae", m)
            out.append(f"| {ln} | {int(m.sum())} | {a:.1f} | {b:.1f} | {b - a:+.1f} | "
                       f"{avg(L_BASE, MAIN, 'pct_llega_antes_60s', m):.1f} / {avg(L_NEW, MAIN, 'pct_llega_antes_60s', m):.1f} | "
                       f"{avg(L_BASE, MAIN, 'pct_llega_despues_60s', m):.1f} / {avg(L_NEW, MAIN, 'pct_llega_despues_60s', m):.1f} | "
                       f"{pct_data(cov, m):.1f} |")
        out.append("")
    out += ["## Veredicto", ""] + [f"- {w}: mejora {g:+.1f} s contra diferencia entre semillas {t:.1f} s -> "
                                   f"{'SUPERA' if g > t else 'no supera'}" for w, g, t in verdict]
    (BASE / "comparacion.md").write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    (BASE / "logs").mkdir(parents=True, exist_ok=True)
    (BASE / "eval").mkdir(parents=True, exist_ok=True)
    log("inicio / reanudación del lanzador tránsito" + (" [smoke]" if SMOKE else "") + f" (python {sys.executable})")
    ka = None
    try:
        ka = start_keep_awake()
        ensure_table()
        for s in SEEDS:
            train(s)
        for lb in (L_NEW, L_BASE):
            for s in SEEDS:
                evaluate(lb, s)
        comparison()
    except Exception as e:  # noqa: BLE001
        log(f"ERROR {e}")
        return 1
    finally:
        if ka is not None:
            ka.terminate()
    log("listo: tránsito entrenado y evaluado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
