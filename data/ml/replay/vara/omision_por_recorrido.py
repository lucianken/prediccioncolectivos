"""Omisión (<= 10 min, vara corregida sin geometría) partida por si el recorrido EX POST del coche en el instante del paso tiene la
parada en su lista (`ramales[].stops`, shape en st.serving) o no. Si no la tiene, el coche no para ahí pero la verdad lo cuenta
como paso cuando va compatible con un shape que sí la sirve (tronco compartido): paso sobrecontado, no omisión.
Uso: python omision_por_recorrido.py RUN_DIR OUT_TXT [workers]  (RUN_DIR con variantes base, cs, ramal: run_cs_sg)"""
import sys, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from prediccion.replay import core, run as RUN  # noqa: E402
from prediccion.replay.pinned import path_reference as PR  # noqa: E402

MODEL = str(ROOT / "data/ml/export/path_v3_l1_s1")
SHAPES = str(ROOT.parent / "proyectoconsola/data/line_shapes")
DATA = "//192.168.0.18/buffer/grabaciones"
LMAP = str(ROOT / "LABEL_LINE_MAP.json")


def do_day(a):
    day, run_dir = a
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        pass
    run_dir = Path(run_dir)
    lines = sorted({p.name.split("_")[1].split(".")[0] for p in run_dir.glob(f"{day}_*.veh.parquet")})
    bundle = PR.load_bundle(MODEL)
    per_line = RUN.load_day(day, set(lines), DATA, LMAP, SHAPES, with_trips=True)
    out = []
    for ln in lines:
        veh = pd.read_parquet(run_dir / f"{day}_{ln}.veh.parquet")
        v = veh[(veh.tp2_s <= 600) & veh.visible].copy()
        stops = {s.id: s for s in core.prepare_stops(bundle, ln, SHAPES, 40)}
        vs = per_line.get(ln, {})
        cache = {}
        res = []
        for r in v.itertuples():
            ve = vs.get(r.vehicle)
            sid = ve.true_shape(float(r.t) + float(r.tp2_s)) if ve is not None else None
            res.append(-1 if sid is None else int(sid in stops[r.stop_id].serving))
        v["sirve"] = res
        out.append(v[["variant", "line", "day", "listed", "sirve"]])
    return pd.concat(out)


if __name__ == "__main__":
    run_dir, outp = sys.argv[1], sys.argv[2]
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    days = sorted({p.name[:10] for p in Path(run_dir).glob("*.veh.parquet")})
    days = [d for d in days if d != "2026-10-04"]    # los 6 días de FILTRO_RAMAL_CS.md
    with ProcessPoolExecutor(w) as ex:
        df = pd.concat(list(ex.map(do_day, [(d, run_dir) for d in days])))
    lines_out = []
    k = df[df.sirve >= 0]
    lines_out.append(f"pasos con recorrido ex post conocido: {len(k)} de {len(df)} (variante base: {int((k.variant=='base').sum())} de {int((df.variant=='base').sum())})")
    b = k[k.variant == "base"]
    lines_out.append(f"de ellos (base), el recorrido real tiene la parada en su lista: {100*b.sirve.mean():.1f} %")
    for var in ("base", "cs", "ramal"):
        x = k[k.variant == var]
        s, n = x[x.sirve == 1], x[x.sirve == 0]
        lines_out.append(f"{var} omision todos {100*(~x.listed).mean():.1f} | recorrido real con la parada en su lista {100*(~s.listed).mean():.1f} (n={len(s)}) | sin la parada en su lista {100*(~n.listed).mean():.1f} (n={len(n)})")
    b = k[k.variant == "base"]
    for ln in sorted(b.line.unique(), key=int):
        res = []
        for var in ("base", "cs", "ramal"):
            x = k[(k.variant == var) & (k.line == ln)]
            s = x[x.sirve == 1]
            res.append(f"{100*(~s.listed).mean():.1f}")
        x = b[b.line == ln]
        lines_out.append(f"{ln} omision (recorrido real con la parada) base/cs/oraculo: {' / '.join(res)}  pct sin la parada en su lista: {100*(x.sirve==0).mean():.1f}")
    Path(outp).write_text("\n".join(lines_out) + "\n", encoding="utf-8")
    print("\n".join(lines_out))
