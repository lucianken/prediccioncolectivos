"""
Prueba de equivalencia de nivel 2 de la mudanza de reglas a `red` (F1.5, bondi/docs/specs/red-reglas.md, "Pruebas").

Mismas corridas con el código anterior (tag `pre-red`) y con `red` importado, sobre un día fijo; las salidas tienen que
ser idénticas, sin tolerancia.

  corre    --codigo <árbol de prediccion colectivos> --salida <dir> --insumos <dir> [--prior-dir <dir>]
  compara  --antes <dir> --despues <dir> --out resultado.json

`--insumos` congela las entradas para los dos lados: `line_shapes/` (copia de proyectoconsola/data/line_shapes),
`LABEL_LINE_MAP.json` y `modelo/` (export vigente, path_v4_l1_s1_r20261126). El replay lee el map del árbol
(ROOT/LABEL_LINE_MAP.json, no configurable): es el mismo archivo versionado en los dos lados.

Corridas (cada una en un proceso aparte, cwd = --codigo):
  v2_geo3        pipeline v2, segmentación geo2, asignación geo3 (ejerce compat_masks)
  v2_legacy      pipeline v2, segmentación geo2, asignación legacy
  v2_geo3_stops  pipeline v2, geo2 + geo3 con objetivos en paradas (ejerce red.stops)
  replay         replay con variantes base, sentido, ramal y prior_token_ii
  fixture        gen_path_parity_fixture (seed 7) sobre el mismo export
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

DIA = "2026-09-15"
LINEAS = "26,39,42,168"
GRABACIONES = "Z:/grabaciones"
VARIANTES = "base,sentido,ramal,prior_token_ii"
SEED = 7
# Claves que cambian entre corridas sin que cambie el resultado (tiempo de pared) o que solo existen después de la mudanza
# (versión de `red` registrada en el meta).
VOLATILES = {"elapsed_s", "red_version"}
# Clave que agrega el superset de path_reference (R4): solo en el lado nuevo del fixture; se cuenta aparte.
SUPERSET = {"eta0_s"}


def corridas(salida: Path, ins: Path, prior_dir: str) -> dict[str, list[str]]:
    v2 = ["-m", "prediccion.v2.build", "--days", DIA, "--lines", LINEAS, "--segmentation", "geo2",
          "--data-dir", GRABACIONES, "--shapes-dir", str(ins / "line_shapes"), "--label-map", str(ins / "LABEL_LINE_MAP.json"),
          "--workers", "1", "--no-assemble"]
    return {
        "v2_geo3": v2 + ["--assign", "geo3", "--out-dir", str(salida / "v2_geo3")],
        "v2_legacy": v2 + ["--assign", "legacy", "--out-dir", str(salida / "v2_legacy")],
        "v2_geo3_stops": v2 + ["--assign", "geo3", "--targets", "stops", "--out-dir", str(salida / "v2_geo3_stops")],
        "replay": ["-m", "prediccion.replay.run", "--model", str(ins / "modelo"), "--days", DIA, "--lines", LINEAS,
                   "--variants", VARIANTES, "--out", str(salida / "replay"), "--data-dir", GRABACIONES,
                   "--shapes-dir", str(ins / "line_shapes"), "--prior-dir", prior_dir, "--workers", "1"],
        "fixture": ["-m", "prediccion.scripts.gen_path_parity_fixture", "--export", str(ins / "modelo"),
                    "--out", str(salida / "fixture.json"), "--seed", str(SEED)],
    }


def cmd_corre(a) -> int:
    codigo, salida, ins = Path(a.codigo).resolve(), Path(a.salida).resolve(), Path(a.insumos).resolve()
    salida.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONPATH": str(codigo), "PYTHONHASHSEED": "0"}
    tiempos = {}
    for nombre, args in corridas(salida, ins, a.prior_dir).items():
        if a.solo and nombre not in a.solo.split(","):
            continue
        t0 = time.time()
        print(f"== {nombre}: {' '.join(args)}", flush=True)
        with open(salida / f"{nombre}.log", "w", encoding="utf-8") as log:
            r = subprocess.run([sys.executable, *args], cwd=codigo, env=env, stdout=log, stderr=subprocess.STDOUT)
        tiempos[nombre] = round(time.time() - t0, 1)
        print(f"   {nombre}: código {r.returncode}, {tiempos[nombre]} s", flush=True)
        if r.returncode != 0:
            print(f"ERROR en {nombre}; ver {salida / (nombre + '.log')}", flush=True)
            return 1
    (salida / "tiempos.json").write_text(json.dumps(tiempos, indent=1), encoding="utf-8")
    return 0


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _sin(o, claves):
    if isinstance(o, dict):
        return {k: _sin(v, claves) for k, v in o.items() if k not in claves}
    if isinstance(o, list):
        return [_sin(v, claves) for v in o]
    return o


def _cuenta_claves(o, claves) -> int:
    if isinstance(o, dict):
        return sum(k in claves for k in o) + sum(_cuenta_claves(v, claves) for v in o.values())
    if isinstance(o, list):
        return sum(_cuenta_claves(v, claves) for v in o)
    return 0


def cmd_compara(a) -> int:
    import pandas as pd
    from pandas.testing import assert_frame_equal

    A, B = Path(a.antes), Path(a.despues)
    res = {"dia": DIA, "lineas": LINEAS, "variantes": VARIANTES, "parquets": {}, "json": {}, "diferencias": []}
    pa = sorted(p.relative_to(A).as_posix() for p in A.rglob("*.parquet"))
    pb = sorted(p.relative_to(B).as_posix() for p in B.rglob("*.parquet"))
    if pa != pb:
        res["diferencias"].append({"archivos_parquet": {"solo_antes": sorted(set(pa) - set(pb)),
                                                        "solo_despues": sorted(set(pb) - set(pa))}})
    for rel in sorted(set(pa) & set(pb)):
        da, db = pd.read_parquet(A / rel), pd.read_parquet(B / rel)
        item = {"filas": len(da), "columnas": len(da.columns), "sha256_antes": _sha(A / rel), "sha256_despues": _sha(B / rel)}
        try:
            assert_frame_equal(da, db, check_exact=True)
            item["igual"] = True
        except AssertionError as e:
            item["igual"] = False
            res["diferencias"].append({rel: str(e)[:2000]})
        res["parquets"][rel] = item
    ja = sorted(p.relative_to(A).as_posix() for p in A.rglob("*.json") if p.name != "tiempos.json")
    jb = sorted(p.relative_to(B).as_posix() for p in B.rglob("*.json") if p.name != "tiempos.json")
    if ja != jb:
        res["diferencias"].append({"archivos_json": {"solo_antes": sorted(set(ja) - set(jb)), "solo_despues": sorted(set(jb) - set(ja))}})
    for rel in sorted(set(ja) & set(jb)):
        oa = json.loads((A / rel).read_text(encoding="utf-8"))
        ob = json.loads((B / rel).read_text(encoding="utf-8"))
        item = {}
        if rel == "fixture.json":
            item["casos"] = len(oa.get("cases", oa)) if isinstance(oa, dict) else len(oa)
            item["claves_superset_antes"] = _cuenta_claves(oa, SUPERSET)
            item["claves_superset_despues"] = _cuenta_claves(ob, SUPERSET)
            igual = _sin(oa, SUPERSET | VOLATILES) == _sin(ob, SUPERSET | VOLATILES)
        else:
            igual = _sin(oa, VOLATILES) == _sin(ob, VOLATILES)
            if rel.endswith("manifest.json") or rel.endswith(".meta.json"):
                item["assign_params"] = [d.get("assign_params") for d in ([oa] if "assign_params" in oa else [])]
        item["igual"] = igual
        if not igual:
            res["diferencias"].append({rel: "json distinto"})
        res["json"][rel] = item
    for lado, d in (("antes", A), ("despues", B)):
        t = d / "tiempos.json"
        res[f"tiempos_{lado}_s"] = json.loads(t.read_text(encoding="utf-8")) if t.exists() else None
    res["n_parquets"] = len(res["parquets"])
    res["n_filas"] = sum(v["filas"] for v in res["parquets"].values())
    res["n_parquets_byte_identicos"] = sum(v["sha256_antes"] == v["sha256_despues"] for v in res["parquets"].values())
    res["veredicto"] = "IGUAL" if not res["diferencias"] else "DISTINTO"
    Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{res['veredicto']}: {res['n_parquets']} parquets ({res['n_filas']:,} filas; "
          f"{res['n_parquets_byte_identicos']} idénticos byte a byte), {len(res['json'])} json, "
          f"{len(res['diferencias'])} diferencias", flush=True)
    return 0 if not res["diferencias"] else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("corre")
    c.add_argument("--codigo", required=True)
    c.add_argument("--salida", required=True)
    c.add_argument("--insumos", required=True)
    c.add_argument("--prior-dir", required=True, help="P_eventos.parquet y meta.json del prior causal (variante prior_*)")
    c.add_argument("--solo", default="", help="subconjunto de corridas (coma)")
    k = sp.add_parser("compara")
    k.add_argument("--antes", required=True)
    k.add_argument("--despues", required=True)
    k.add_argument("--out", required=True)
    a = ap.parse_args()
    return cmd_corre(a) if a.cmd == "corre" else cmd_compara(a)


if __name__ == "__main__":
    sys.exit(main())
