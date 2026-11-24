"""Tablas de CONSISTENCIA_ETA.md a partir de data/ml/replay/consistencia/run/*.parquet.
python -m prediccion.replay.report_consistencia RUN_DIR OUT_MD"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

BANDS = [(0, 120, "0-2"), (120, 180, "2-3"), (180, 300, "3-5"), (300, 420, "5-7"), (420, 600, "7-10"), (600, 1200, "10-20"),
         (1200, 2400, "20-40")]
FOCUS = (180, 420)
TOL = 60.0


def load(run):
    dfs = [pd.read_parquet(p) for p in sorted(Path(run).glob("*.parquet"))]
    df = pd.concat([x for x in dfs if len(x)], ignore_index=True)
    df["past"] = df.past.astype(bool)
    df["unv"] = df.unv.astype(bool)
    return df


def build_steps(df):
    """Secuencias = rachas de consultas consecutivas (60 s) en que el coche está listado en la parada, hasta su paso."""
    df = df[~df.past].sort_values(["line", "day", "stop", "veh", "t"]).reset_index(drop=True)
    key = df.line + "|" + df.day + "|" + df.stop.astype(str) + "|" + df.veh.astype(str)
    newrun = (key != key.shift()) | (df.t.diff() != 60)
    df["seq"] = newrun.cumsum()
    df["pass_abs"] = df.t + df.tp2_s
    # un coche listado tras pasar (tp2 deja de existir): cortar en el primer paso conocido de la racha
    first_pass = df.groupby("seq").pass_abs.transform("min")
    df = df[~(df.t >= first_pass)].copy()
    g = df.groupby("seq")
    nxt = g.shift(-1)
    ok = nxt.t.notna()
    st = pd.DataFrame({
        "line": df.line[ok], "day": df.day[ok], "seq": df.seq[ok], "eta0": df.eta0_s[ok], "eta1": nxt.eta0_s[ok],
        "tp2": df.tp2_s[ok], "new_ping": (nxt.ping_ts[ok] != df.ping_ts[ok]), "group": df.group[ok],
        "group1": nxt.group[ok],
    })
    st["d"] = st.eta1 - st.eta0          # ideal: -60
    st["exc"] = st.d + 60.0               # exceso sobre el reloj
    st["err"] = st.tp2 - st.eta0          # <0: llega antes de lo anunciado
    st["band"] = pd.cut(st.eta0, [b[0] for b in BANDS] + [BANDS[-1][1]], labels=[b[2] for b in BANDS], right=False)
    # tamaño de secuencias
    last = g.tail(1)
    seqs = pd.DataFrame({"seq": last.seq, "line": last.line, "day": last.day, "eta_last": last.eta0_s, "tp2_last": last.tp2_s})
    seqs["err_last"] = seqs.tp2_last - seqs.eta_last
    return df, st, seqs


def pct(x):
    return float(100 * np.mean(x)) if len(x) else np.nan


def f1(x):
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.1f}"


def md(rows, header):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def band_table(st):
    rows = []
    sets = [(b[2], st[st.band == b[2]]) for b in BANDS] + [("3-7 (foco)", st[(st.eta0 >= FOCUS[0]) & (st.eta0 < FOCUS[1])]),
                                                           ("todas", st)]
    for name, s in sets:
        if not len(s):
            continue
        q = s.d.quantile([.05, .25, .5, .75, .95]).round(0).astype(int).tolist()
        rows.append([name, len(s), *q, f1(s.d.mean()), f1(pct(s.d > 0)), f1(pct(s.d > 30)), f1(pct(s.d > 60)), f1(pct(s.d > 120)),
                     f1(pct(s.d < -120))])
    return md(rows, ["banda ETA (min)", "pasos", "Δ P5", "P25", "P50", "P75", "P95", "Δ medio", "sube >0 %", ">30 s %", ">60 s %",
                     ">120 s %", "baja >60 s más que el reloj %"])


def ping_table(st):
    rows = []
    for name, s0 in (("3-7 (foco)", st[(st.eta0 >= FOCUS[0]) & (st.eta0 < FOCUS[1])]), ("todas", st)):
        for lab, s in (("ping nuevo", s0[s0.new_ping]), ("sin ping nuevo", s0[~s0.new_ping])):
            if not len(s):
                continue
            a = s.exc.abs()
            rows.append([name, lab, len(s), f1(s.d.median()), f1(a.median()), f1(a.quantile(.9)), f1(pct(s.d > 0)), f1(pct(s.d > 60)),
                         f1(pct(s.d < -120))])
    return md(rows, ["banda", "paso", "pasos", "Δ mediana", "|Δ+60| mediana", "|Δ+60| P90", "sube >0 %", "sube >60 s %",
                     "baja >60 s más que el reloj %"])


def outcome_table(st):
    s0 = st[(st.eta0 >= FOCUS[0]) & (st.eta0 < FOCUS[1]) & st.tp2.notna()]
    cls = pd.cut(s0.d, [-1e9, -120, 0, 60, 1e9], labels=["baja >60 s más que el reloj (Δ < -120)", "baja normal (-120 a 0)",
                                                          "sube 0-60 s", "sube > 60 s"], right=False)
    rows = []
    for c in cls.cat.categories:
        s = s0[cls == c]
        if len(s):
            rows.append([c, len(s), f1(pct(s.err < -TOL)), f1(pct(s.err > TOL)), f1(s.err.median()), f1(s.err.abs().mean())])
    rows.append(["todos los pasos", len(s0), f1(pct(s0.err < -TOL)), f1(pct(s0.err > TOL)), f1(s0.err.median()), f1(s0.err.abs().mean())])
    return md(rows, ["paso (anuncio 3-7 min, paso real conocido)", "n", "llega antes >60 s %", "llega después >60 s %", "error mediano (s)",
                     "MAE (s)"])


def seq_table(st, seqs):
    rows = []
    s0 = st[(st.eta0 >= FOCUS[0]) & (st.eta0 < FOCUS[1])]
    for name, s in (("3-7 (pasos en la banda)", s0), ("todas las bandas", st)):
        a = s.groupby("seq").agg(rise60=("d", lambda x: (x > 60).any()), rise0=("d", lambda x: (x > 0).any()), n=("d", "size"),
                                 fast=("d", lambda x: (x < -120).any()))
        r = a.join(seqs.set_index("seq")[["err_last"]], how="left")
        k = r.err_last.notna()
        rows.append([name, len(a), f1(a.n.mean()), f1(pct(a.rise0)), f1(pct(a.rise60)), f1(pct(a.fast)),
                     f1(pct(r[k & r.rise60].err_last > TOL)) if (k & r.rise60).any() else "—",
                     f1(pct(r[k & ~r.rise60].err_last > TOL)) if (k & ~r.rise60).any() else "—",
                     f1(pct(r[k & a.fast].err_last < -TOL)) if (k & a.fast).any() else "—",
                     f1(pct(r[k & ~a.fast].err_last < -TOL)) if (k & ~a.fast).any() else "—"])
    return md(rows, ["secuencias con ≥1 paso en", "n sec.", "pasos por sec.", "con ≥1 subida >0 %", "con ≥1 subida >60 s %",
                     "con ≥1 baja >60 s más que el reloj %", "con subida: termina llega después >60 s %",
                     "sin subida: termina llega después >60 s %", "con baja rápida: termina llega antes >60 s %",
                     "sin baja rápida: termina llega antes >60 s %"])


def group_table(st, col):
    s0 = st[(st.eta0 >= FOCUS[0]) & (st.eta0 < FOCUS[1])]
    rows = []
    for k, s in s0.groupby(col):
        rows.append([k, len(s), f1(s.d.median()), f1(s.d.quantile(.05)), f1(s.d.quantile(.95)), f1(pct(s.d > 0)), f1(pct(s.d > 60)),
                     f1(pct(s.d > 120)), f1(pct(s.d < -120)), f1(pct(s.new_ping))])
    return rows


def main():
    run, out = sys.argv[1], sys.argv[2]
    df = load(run)
    df0, st, seqs = build_steps(df)
    foc = st[(st.eta0 >= FOCUS[0]) & (st.eta0 < FOCUS[1])]
    hdr = ["", "pasos 3-7", "Δ mediana", "Δ P5", "Δ P95", "sube >0 %", "sube >60 s %", "sube >120 s %", "baja >60 s más %", "con ping nuevo %"]
    lines_rows = group_table(st, "line")
    days_rows = group_table(st, "day")
    dayspread = foc.groupby("day").apply(lambda s: pct(s.d > 60))
    dayspread0 = foc.groupby("day").apply(lambda s: pct(s.d > 0))
    linespread = foc.groupby("line").apply(lambda s: pct(s.d > 60))
    grp = group_table(st, "group")
    txt = []
    txt.append("## Resumen del dataset\n")
    txt.append(f"Filas (listados por consulta): {len(df)}; días {df.day.nunique()}, líneas {df.line.nunique()}, paradas distintas "
               f"{df.groupby('line').stop.nunique().sum()}, pares (parada, coche) {df.groupby(['line','day','stop','veh']).ngroups}, "
               f"secuencias (rachas de consultas consecutivas) {seqs.seq.nunique()}, pasos entre consultas {len(st)} (3-7 min: {len(foc)}).\n")
    txt.append("## Δanuncio entre consultas consecutivas (60 s), por banda de ETA anunciado\n")
    txt.append("Δ = ETA anunciado en t+60 s − ETA anunciado en t, en segundos (ideal −60). «Sube» = Δ > 0.\n")
    txt.append(band_table(st) + "\n")
    txt.append("## Pasos con ping nuevo del coche contra sin ping nuevo\n")
    txt.append(ping_table(st) + "\n")
    txt.append("## Secuencias (coche, parada)\n")
    txt.append(seq_table(st, seqs) + "\n")
    txt.append("## Relación con el resultado (pasos con anuncio 3-7 min)\n")
    txt.append(outcome_table(st) + "\n")
    txt.append("## Por línea (anuncio 3-7 min)\n")
    txt.append(md(lines_rows, ["línea"] + hdr[1:]) + "\n")
    txt.append(f"Sube >60 s % entre líneas: mín {linespread.min():.1f}, mediana {linespread.median():.1f}, máx {linespread.max():.1f}.\n")
    txt.append("## Por día (anuncio 3-7 min)\n")
    txt.append(md(days_rows, ["día"] + hdr[1:]) + "\n")
    txt.append(f"Sube >0 % entre días: media {dayspread0.mean():.1f}, desvío {dayspread0.std():.1f}, mín {dayspread0.min():.1f}, máx {dayspread0.max():.1f}. "
               f"Sube >60 s %: media {dayspread.mean():.1f}, desvío {dayspread.std():.1f}, mín {dayspread.min():.1f}, máx {dayspread.max():.1f}.\n")
    txt.append("## Por grupo mostrado al inicio del paso (anuncio 3-7 min)\n")
    txt.append(md(grp, ["grupo"] + hdr[1:]) + "\n")
    Path(out).write_text("\n".join(txt), encoding="utf-8")
    print("\n".join(txt))


if __name__ == "__main__":
    main()
