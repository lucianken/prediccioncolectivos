"""Tablas markdown de HISTORIAL_COCHE_ADELANTE.md a partir de resumen.json (historial_ca_report)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
r = json.load(open(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data/ml/replay/histca/resumen.json", encoding="utf-8"))
VARS = ["w20", "w60", "wdia", "wviaje"]
NAMES = {"w20": "20 min (servicio hoy)", "w60": "60 min", "wdia": "día completo, función de la app", "wviaje": "día completo por viaje (≈ entrenamiento)"}
ROWS = [("MAE próximo coche, 3–7 min (s)", "mae_prox", 2), ("próximo coche llega antes > 60 s %", "antes_prox", 2),
        ("próximo coche llega después > 60 s %", "desp_prox", 2), ("bondi fantasma %", "fantasma", 2), ("bondi no anunciado %", "no_anunciado", 2),
        ("MAE por coche, 3–7 min (s)", "mae_coche", 2), ("coche llega antes > 60 s %", "antes_coche", 2),
        ("coche llega después > 60 s %", "desp_coche", 2), ("last_bus_found = 0 %, coches de la banda", "lbf0_coche", 1),
        ("last_bus_found = 0 %, todos los listados", "lbf0_all", 1)]


def ci(g, var, m, d):
    b = r["boot"].get(f"{g}|{var}|{m}")
    if not b or b[0] != b[0]:
        return "—"
    return f"{b[0]:+.{d}f} [{b[1]:+.{d}f}, {b[2]:+.{d}f}]"


def table(g):
    out = ["| métrica | " + " | ".join(NAMES[v] for v in VARS) + " | Δ 60 min vs 20 [IC95] | Δ día-app vs 20 [IC95] | Δ día-viaje vs 20 [IC95] |", "|---|" + "---|" * (len(VARS) + 3)]
    for name, m, d in ROWS:
        vals = [r["pooled"].get(f"{g}|{v}", {}).get(m) for v in VARS]
        out.append(f"| {name} | " + " | ".join("—" if x is None else f"{x:.{d}f}" for x in vals) + " | " + " | ".join(ci(g, v, m, d) for v in VARS[1:]) + " |")
    p = r["pooled"].get(f"{g}|w20", {})
    out.append(f"\nn: próximo coche en banda {p.get('n_prox')}, coches en banda {p.get('n_coche')}, coches listados con last_bus_found definido {p.get('n_all')}.")
    return "\n".join(out)


print("## TODAS\n" + table("todas"))
for g in ["alta (<= 5 min)", "media (5-8 min)", "baja (8-12 min)", "muy baja (> 12 min)"]:
    print(f"\n## {g} ({r['n_lines_group'].get(g)} líneas)\n" + table(g))
print("\n## por línea (todos los días): intervalo, MAE próximo w20 → w60 → viaje, lbf0 w20 → w60 → viaje")
for ln in r["lines"]:
    t = lambda v, m: r["lines_tab"][f"{ln}|{v}"][m]  # noqa: E731
    print(f"| {ln} | {r['hw'][ln]:.1f} | {r['glab'][ln]} | {t('w20','mae_prox'):.0f} → {t('w60','mae_prox'):.0f} → {t('wviaje','mae_prox'):.0f} | "
          f"{t('w20','lbf0_all'):.1f} → {t('w60','lbf0_all'):.1f} → {t('wviaje','lbf0_all'):.1f} |")
