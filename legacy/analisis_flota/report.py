"""
report.py — Lee fleet_db.json y genera fleet_report.html con Plotly.js.

Dos umbrales normativos:
  CABA: 10 años duros (Ley 2.148 + Res. 70, 139, 170/SECT/25)
  Nacional: 13 años efectivos (Ley 24.449 + Decreto 123/09 + Res. 10/2024)
"""

import json
from collections import defaultdict
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
FLEET_DB_PATH = SCRIPT_DIR / "fleet_db.json"
OUTPUT_PATH = SCRIPT_DIR / "fleet_report.html"

# Referencia: junio 2026
# >10 años = fabricado en 2015 o antes  (2026 - 10 - 1 = 2015)
# >13 años = fabricado en 2012 o antes  (2026 - 13 - 1 = 2012)
CUTOFF_10 = 2015
CUTOFF_13 = 2012

MIN_VEHICLES = 10
TODAY = date.today().strftime("%d/%m/%Y")

CABA_LINES = {
    "4", "7", "12", "25", "26", "34", "39", "42", "44", "47",
    "50", "61", "62", "64", "65", "68", "76", "84", "102", "106",
    "107", "108", "109", "115", "118", "132", "151",
}


def load_db() -> dict:
    with open(FLEET_DB_PATH, encoding="utf-8") as f:
        return json.load(f)


def compute_stats(db: dict) -> tuple[list[dict], list[dict]]:
    by_line: dict[str, dict] = defaultdict(lambda: {
        "years": [], "plates": [], "agency": "", "line": ""
    })
    for plate, v in db.items():
        line = v["line"]
        by_line[line]["line"] = line
        by_line[line]["agency"] = v.get("agency", "")
        by_line[line]["years"].append(v["est_year"])
        by_line[line]["plates"].append({"plate": plate, "year": v["est_year"]})

    included, excluded = [], []
    for line, data in by_line.items():
        years = data["years"]
        n = len(years)
        n_old10 = sum(1 for y in years if y <= CUTOFF_10)
        n_old13 = sum(1 for y in years if y <= CUTOFF_13)
        pct_old10 = round(n_old10 / n * 100, 1) if n else 0
        pct_old13 = round(n_old13 / n * 100, 1) if n else 0
        avg_year = round(sum(years) / n, 1) if n else 0
        entry = {
            "line": line,
            "agency": data["agency"],
            "n_total": n,
            "n_old10": n_old10,
            "n_old13": n_old13,
            "pct_old": pct_old10,   # alias principal para ranking
            "pct_old10": pct_old10,
            "pct_old13": pct_old13,
            "avg_year": avg_year,
            "newest": max(years) if years else 0,
            "oldest": min(years) if years else 0,
            "plates": sorted(data["plates"], key=lambda x: x["year"]),
        }
        if n >= MIN_VEHICLES:
            included.append(entry)
        else:
            excluded.append(entry)

    included.sort(key=lambda x: (-x["pct_old10"], x["avg_year"]))
    for i, s in enumerate(included):
        s["rank"] = i + 1
    excluded.sort(key=lambda x: int(x["line"]) if x["line"].isdigit() else 9999)
    return included, excluded


def bar_color(pct: float) -> str:
    if pct >= 50:
        return "#c0392b"
    if pct >= 20:
        return "#e67e22"
    return "#27ae60"


def year_color(y: int) -> str:
    if y <= CUTOFF_13:
        return "#7b241c"   # rojo oscuro: fuera de norma incluso con prórroga nacional
    if y <= CUTOFF_10:
        return "#e67e22"   # naranja: fuera de norma CABA, dentro de prórroga nacional
    return "#2980b9"        # azul: dentro de norma


def generate_html(db: dict, stats: list[dict], excluded: list[dict]) -> str:
    total_vehicles = len(db)
    total_lines = len(stats)
    total_in_stats = sum(s["n_total"] for s in stats)
    total_old10 = sum(s["n_old10"] for s in stats)
    total_old13 = sum(s["n_old13"] for s in stats)
    pct_old10_global = round(total_old10 / total_in_stats * 100, 1) if total_in_stats else 0
    pct_old13_global = round(total_old13 / total_in_stats * 100, 1) if total_in_stats else 0

    # CABA stats (límite duro: 10 años)
    caba_stats = [s for s in stats if s["line"] in CABA_LINES]
    caba_total = sum(s["n_total"] for s in caba_stats)
    caba_old10 = sum(s["n_old10"] for s in caba_stats)
    caba_old13 = sum(s["n_old13"] for s in caba_stats)
    caba_pct10 = round(caba_old10 / caba_total * 100, 1) if caba_total else 0
    caba_pct13 = round(caba_old13 / caba_total * 100, 1) if caba_total else 0

    # Histograma global
    all_years = [v["est_year"] for v in db.values()]
    year_counts: dict[int, int] = defaultdict(int)
    for y in all_years:
        year_counts[y] += 1
    hist_years = sorted(year_counts.keys())
    hist_counts = [year_counts[y] for y in hist_years]
    hist_colors = [year_color(y) for y in hist_years]

    # Ranking chart
    lines_labels = [f"Línea {s['line']}" for s in stats]
    pct_old_vals = [s["pct_old10"] for s in stats]
    bar_colors_list = [bar_color(p) for p in pct_old_vals]

    # CABA chart (ordenado por pct desc)
    caba_sorted = sorted(caba_stats, key=lambda x: x["pct_old10"])
    caba_labels = [f"Línea {s['line']}" for s in caba_sorted]
    caba_vals = [s["pct_old10"] for s in caba_sorted]
    caba_bar_colors = [bar_color(p) for p in caba_vals]

    worst5 = stats[:5]
    best5 = sorted(stats, key=lambda x: -x["avg_year"])[:5]
    stats_by_line_num = sorted(stats, key=lambda x: int(x["line"]) if x["line"].isdigit() else 9999)

    def card(s, color):
        caba_tag = ' <span style="font-size:0.6rem;background:#4a90c4;color:#fff;padding:1px 5px;border-radius:6px;vertical-align:middle">CABA</span>' if s["line"] in CABA_LINES else ""
        return f"""
        <div class="card" style="border-left:4px solid {color}">
          <div class="card-rank">#{s['rank']}</div>
          <div class="card-line">Línea {s['line']}{caba_tag}</div>
          <div class="card-pct" style="color:{color}">{s['pct_old10']}%</div>
          <div class="card-sub">{s['n_old10']} / {s['n_total']} &gt; 10 años</div>
          <div class="card-agency">{s['agency'][:40]}</div>
        </div>"""

    def card_best(s):
        caba_tag = ' <span style="font-size:0.6rem;background:#4a90c4;color:#fff;padding:1px 5px;border-radius:6px;vertical-align:middle">CABA</span>' if s["line"] in CABA_LINES else ""
        return f"""
        <div class="card" style="border-left:4px solid #27ae60">
          <div class="card-rank">año prom</div>
          <div class="card-line">Línea {s['line']}{caba_tag}</div>
          <div class="card-pct" style="color:#27ae60">{s['avg_year']}</div>
          <div class="card-sub">{s['pct_old10']}% &gt;10a · {s['n_total']} vehículos</div>
          <div class="card-agency">{s['agency'][:40]}</div>
        </div>"""

    worst_cards = "\n".join(card(s, "#c0392b") for s in worst5)
    best_cards = "\n".join(card_best(s) for s in best5)

    table_rows = ""
    for s in stats:
        color = bar_color(s["pct_old10"])
        badge10 = f"background:{color};color:#fff;padding:2px 8px;border-radius:10px;font-weight:700;font-size:0.82rem;"
        c13 = "#c0392b" if s["pct_old13"] > 0 else "#27ae60"
        badge13 = f"background:{c13};color:#fff;padding:2px 8px;border-radius:10px;font-weight:700;font-size:0.82rem;"
        caba_badge = ' <span style="background:#4a90c4;color:#fff;padding:1px 5px;border-radius:6px;font-size:0.68rem;font-weight:600;vertical-align:middle">CABA</span>' if s["line"] in CABA_LINES else ""
        table_rows += f"""
        <tr>
          <td>{s['rank']}</td>
          <td><strong>Línea {s['line']}</strong>{caba_badge}</td>
          <td class="agency-cell">{s['agency']}</td>
          <td>{s['n_total']}</td>
          <td><span style="{badge10}">{s['pct_old10']}%</span></td>
          <td><span style="{badge13}">{s['pct_old13']}%</span></td>
          <td>{s['avg_year']}</td>
          <td>{s['oldest']}</td>
          <td>{s['newest']}</td>
        </tr>"""

    detail_sections = ""
    for s in stats_by_line_num:
        plate_rows = ""
        for p in s["plates"]:
            yc = year_color(p["year"])
            fw = "700" if p["year"] <= CUTOFF_10 else "400"
            flag = " &#9679;" if p["year"] <= CUTOFF_13 else (" &#9675;" if p["year"] <= CUTOFF_10 else "")
            plate_rows += f'<tr><td style="font-family:monospace">{p["plate"]}</td><td style="color:{yc};font-weight:{fw}">{p["year"]}{flag}</td></tr>'
        bc = bar_color(s["pct_old10"])
        caba_tag = ' <span style="background:#4a90c4;color:#fff;padding:1px 5px;border-radius:6px;font-size:0.7rem">CABA</span>' if s["line"] in CABA_LINES else ""
        detail_sections += f"""
        <details class="line-detail">
          <summary>
            <strong>Línea {s['line']}</strong>{caba_tag}
            <span class="pct-badge" style="background:{bc}">{s['pct_old10']}% &gt;10a</span>
            {"<span class='pct-badge' style='background:#7b241c'>" + str(s['pct_old13']) + "% &gt;13a</span>" if s['pct_old13'] > 0 else ""}
            <span style="color:#666;font-size:0.82rem">{s['n_total']} vehículos</span>
            <span class="agency-name">{s['agency'][:50]}</span>
          </summary>
          <table class="plate-table">
            <thead><tr><th>Patente</th><th>Año est.</th></tr></thead>
            <tbody>{plate_rows}</tbody>
          </table>
        </details>"""

    plotly_ranking = json.dumps({"x": pct_old_vals, "y": lines_labels, "colors": bar_colors_list})
    plotly_hist = json.dumps({"x": hist_years, "y": hist_counts, "colors": hist_colors})
    plotly_caba = json.dumps({"x": caba_vals, "y": caba_labels, "colors": caba_bar_colors})

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Antigüedad de Flota AMBA</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  :root {{
    --celeste: #74b9e0;
    --celeste-mid: #4a90c4;
    --celeste-dark: #2980b9;
    --celeste-light: #d6eaf8;
    --celeste-bg: #eaf4fb;
    --white: #ffffff;
    --red: #c0392b;
    --red-dark: #7b241c;
    --orange: #e67e22;
    --green: #27ae60;
    --text: #1a1a2e;
    --muted: #5a6a7a;
    --border: #b8d4e8;
    --surface: #f5faff;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--celeste-bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; padding: 24px; max-width: 1400px; margin: 0 auto; }}

  .header-stripe {{ background: linear-gradient(180deg, var(--celeste) 33%, var(--white) 33%, var(--white) 66%, var(--celeste) 66%); height: 8px; border-radius: 4px 4px 0 0; }}
  .header-box {{ background: var(--white); border: 1px solid var(--border); border-top: none; border-radius: 0 0 12px 12px; padding: 20px 24px 16px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(74,144,196,0.08); }}
  h1 {{ font-size: 1.75rem; font-weight: 800; color: var(--celeste-dark); }}
  .subtitle {{ color: var(--muted); font-size: 0.875rem; margin-top: 4px; }}

  h2 {{ font-size: 1.1rem; font-weight: 700; color: var(--celeste-dark); margin: 28px 0 12px; padding-bottom: 6px; border-bottom: 2px solid var(--celeste-light); }}

  .kpi-row {{ display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 24px; }}
  .kpi {{ background: var(--white); border: 1px solid var(--border); border-radius: 10px; padding: 16px 22px; flex: 1; min-width: 140px; box-shadow: 0 1px 4px rgba(74,144,196,0.1); }}
  .kpi-val {{ font-size: 1.9rem; font-weight: 800; color: var(--celeste-dark); }}
  .kpi-label {{ font-size: 0.75rem; color: var(--muted); margin-top: 3px; text-transform: uppercase; letter-spacing: 0.03em; }}
  .kpi-red .kpi-val {{ color: var(--red); }}
  .kpi-orange .kpi-val {{ color: var(--orange); }}
  .kpi-darkred .kpi-val {{ color: var(--red-dark); }}
  .kpi-green .kpi-val {{ color: var(--green); }}

  .chart-box {{ background: var(--white); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 4px rgba(74,144,196,0.08); }}

  .legend-row {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; font-size: 0.8rem; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .legend-dot {{ width: 12px; height: 12px; border-radius: 3px; flex-shrink: 0; }}

  .cards-row {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }}
  .card {{ background: var(--white); border: 1px solid var(--border); border-radius: 10px; padding: 16px; flex: 1; min-width: 140px; box-shadow: 0 1px 4px rgba(74,144,196,0.08); }}
  .card-rank {{ font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }}
  .card-line {{ font-size: 1.1rem; font-weight: 800; margin: 3px 0; }}
  .card-pct {{ font-size: 1.8rem; font-weight: 900; }}
  .card-sub {{ font-size: 0.72rem; color: var(--muted); margin-top: 4px; }}
  .card-agency {{ font-size: 0.67rem; color: var(--muted); margin-top: 6px; line-height: 1.3; }}

  table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
  thead th {{ background: var(--celeste-light); padding: 10px 12px; text-align: left; color: var(--celeste-dark); font-weight: 700; font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 2px solid var(--celeste); }}
  tbody tr {{ border-bottom: 1px solid var(--celeste-light); }}
  tbody tr:hover {{ background: var(--surface); }}
  td {{ padding: 9px 12px; }}
  .agency-cell {{ max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); font-size: 0.78rem; }}

  /* Marco normativo */
  .marco {{ background: var(--white); border: 1px solid var(--border); border-radius: 10px; margin-bottom: 24px; box-shadow: 0 1px 4px rgba(74,144,196,0.08); }}
  .marco summary {{ padding: 14px 20px; cursor: pointer; font-weight: 700; color: var(--celeste-dark); font-size: 0.95rem; list-style: none; display: flex; align-items: center; gap: 10px; }}
  .marco summary:hover {{ background: var(--surface); border-radius: 10px; }}
  .marco[open] summary {{ border-bottom: 1px solid var(--border); border-radius: 10px 10px 0 0; }}
  .marco-body {{ padding: 20px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  @media (max-width: 700px) {{ .marco-body {{ grid-template-columns: 1fr; }} }}
  .marco-col {{ border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; }}
  .marco-col h3 {{ font-size: 0.85rem; font-weight: 700; margin-bottom: 8px; }}
  .marco-col.nacional h3 {{ color: var(--orange); }}
  .marco-col.caba h3 {{ color: var(--celeste-dark); }}
  .marco-col ul {{ padding-left: 16px; font-size: 0.8rem; color: var(--muted); line-height: 1.7; }}
  .marco-col .limite {{ font-size: 1.1rem; font-weight: 800; margin-top: 8px; }}
  .marco-col.nacional .limite {{ color: var(--orange); }}
  .marco-col.caba .limite {{ color: var(--red); }}

  /* CABA section */
  .caba-section {{ background: var(--white); border: 2px solid var(--celeste-mid); border-radius: 12px; padding: 20px; margin-bottom: 24px; box-shadow: 0 2px 8px rgba(74,144,196,0.12); }}
  .caba-header {{ display: flex; align-items: center; gap: 14px; margin-bottom: 14px; flex-wrap: wrap; }}
  .caba-title {{ font-size: 1.1rem; font-weight: 800; color: var(--celeste-dark); }}
  .caba-pill {{ background: var(--celeste-dark); color: #fff; padding: 3px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: 700; }}
  .caba-note {{ font-size: 0.8rem; color: var(--muted); border-left: 3px solid var(--celeste-mid); padding-left: 10px; margin-bottom: 16px; line-height: 1.6; }}
  .caba-kpi-row {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }}
  .caba-kpi {{ background: var(--celeste-bg); border: 1px solid var(--border); border-radius: 8px; padding: 12px 18px; flex: 1; min-width: 130px; }}
  .caba-kpi .kpi-val {{ font-size: 1.5rem; font-weight: 800; color: var(--celeste-dark); }}
  .caba-kpi.kpi-red .kpi-val {{ color: var(--red); }}
  .caba-kpi.kpi-darkred .kpi-val {{ color: var(--red-dark); }}
  .caba-kpi .kpi-label {{ font-size: 0.73rem; color: var(--muted); margin-top: 2px; }}

  details.line-detail {{ background: var(--white); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 6px; box-shadow: 0 1px 3px rgba(74,144,196,0.06); }}
  details.line-detail summary {{ padding: 11px 16px; cursor: pointer; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; list-style: none; }}
  details.line-detail summary:hover {{ background: var(--surface); border-radius: 8px; }}
  details.line-detail[open] summary {{ border-bottom: 1px solid var(--border); }}
  .pct-badge {{ padding: 2px 9px; border-radius: 12px; font-size: 0.76rem; font-weight: 700; color: #fff; }}
  .agency-name {{ font-size: 0.73rem; color: var(--muted); margin-left: auto; }}
  .plate-table {{ margin: 0 16px 14px; width: calc(100% - 32px); }}
  .plate-table th {{ font-size: 0.74rem; background: var(--celeste-light); }}
</style>
</head>
<body>

<div class="header-stripe"></div>
<div class="header-box">
  <h1>Antigüedad de Flota — AMBA</h1>
  <p class="subtitle">
    Generado: {TODAY} &nbsp;·&nbsp; Datos: abril–mayo 2026 &nbsp;·&nbsp; Líneas ≤ 200
    &nbsp;·&nbsp; Límite CABA: 10 años (&le;{CUTOFF_10}) &nbsp;·&nbsp; Límite nacional c/prórroga: 13 años (&le;{CUTOFF_13})
  </p>
</div>

<!-- Marco normativo colapsable -->
<details class="marco">
  <summary>&#9878; Marco normativo — Ley 24.449 · Decreto 123/09 · Res. 10/2024 · Ley CABA 2.148 · Res. 70, 139, 170/SECT/25</summary>
  <div class="marco-body">
    <div class="marco-col nacional">
      <h3>Jurisdicción Nacional (líneas 1–199 AMBA)</h3>
      <ul>
        <li><strong>Base:</strong> Ley 24.449 art. 53 inc. b) — límite 10 años</li>
        <li><strong>Prórroga:</strong> Decreto 779/95 art. 53 b.4) habilita extensiones por resolución secretarial</li>
        <li><strong>Dec. 123/2009:</strong> fijó 13 años efectivos (10 + 3) con RTO cuatrimestral</li>
        <li><strong>Res. 2/2022:</strong> extendió modelos 2011 por 3 años adicionales</li>
        <li><strong>Res. 10/2024:</strong> consolida el esquema: 3 años de prórroga desde el décimo año, con fundamento técnico de CNTYSV</li>
      </ul>
      <div class="limite">Límite efectivo: 13 años + RTO cada 4 meses</div>
    </div>
    <div class="marco-col caba">
      <h3>Jurisdicción CABA (líneas Distrito Federal)</h3>
      <ul>
        <li><strong>Base:</strong> Ley CABA 2.148 art. 9.1.2 — límite 10 años, sin válvula de prórroga estructural</li>
        <li><strong>Res. 70/SECT/25:</strong> cronograma de adecuación escalonado</li>
        <li><strong>Res. 170/SECT/25:</strong> desincentivos económicos incrementales por incumplimiento</li>
        <li><strong>Res. 139/SECT/25:</strong> ajusta el cronograma manteniendo penalidades</li>
        <li><strong>Única tolerancia:</strong> 180 días corridos al reemplazar una unidad agotada por 0 km</li>
      </ul>
      <div class="limite">Límite duro: 10 años sin prórroga + multas por incumplimiento</div>
    </div>
  </div>
</details>

<div class="kpi-row">
  <div class="kpi"><div class="kpi-val">{total_in_stats}</div><div class="kpi-label">Vehículos analizados</div></div>
  <div class="kpi"><div class="kpi-val">{total_lines}</div><div class="kpi-label">Líneas</div></div>
  <div class="kpi kpi-orange"><div class="kpi-val">{total_old10}</div><div class="kpi-label">Vehículos &gt;10 años ({pct_old10_global}%)</div></div>
  <div class="kpi kpi-darkred"><div class="kpi-val">{total_old13}</div><div class="kpi-label">Vehículos &gt;13 años ({pct_old13_global}%)</div></div>
</div>

<h2>Ranking — % flota con más de 10 años</h2>
<div class="legend-row">
  <div class="legend-item"><div class="legend-dot" style="background:#27ae60"></div> &lt;20% (normal)</div>
  <div class="legend-item"><div class="legend-dot" style="background:#e67e22"></div> 20–50% (elevado)</div>
  <div class="legend-item"><div class="legend-dot" style="background:#c0392b"></div> &gt;50% (crítico)</div>
</div>
<div class="chart-box">
  <div id="chart-ranking" style="height:{max(420, len(stats)*22)}px;"></div>
</div>

<h2>Distribución global por año de fabricación estimado</h2>
<div class="legend-row">
  <div class="legend-item"><div class="legend-dot" style="background:#7b241c"></div> &gt;13 años — fuera de norma incluso con prórroga nacional</div>
  <div class="legend-item"><div class="legend-dot" style="background:#e67e22"></div> 10–13 años — fuera de norma CABA / dentro de prórroga nacional</div>
  <div class="legend-item"><div class="legend-dot" style="background:#2980b9"></div> &lt;10 años — dentro de norma</div>
</div>
<div class="chart-box">
  <div id="chart-hist" style="height:380px;"></div>
</div>

<h2>Top 5 — Peores líneas (flota más vieja)</h2>
<div class="cards-row">{worst_cards}</div>

<h2>Top 5 — Mejores líneas (flota más nueva)</h2>
<div class="cards-row">{best_cards}</div>

<!-- Sección CABA -->
<div class="caba-section">
  <div class="caba-header">
    <div class="caba-title">Jurisdicción CABA — Política de flota estricta</div>
    <span class="caba-pill">{len(caba_stats)} líneas</span>
  </div>
  <p class="caba-note">
    CABA aplica 10 años duros sin prórroga estructural (Ley 2.148 + Resoluciones 70, 139 y 170/SECT/25).
    Incumplimiento implica desincentivos económicos incrementales. La única tolerancia es de 180 días al reemplazar una unidad por 0&nbsp;km.
    Los vehículos en zona naranja (&gt;10 años) ya están fuera de norma en CABA, independientemente de la prórroga nacional.
  </p>
  <div class="caba-kpi-row">
    <div class="caba-kpi"><div class="kpi-val">{caba_total}</div><div class="kpi-label">Vehículos</div></div>
    <div class="caba-kpi kpi-red"><div class="kpi-val">{caba_old10} ({caba_pct10}%)</div><div class="kpi-label">Fuera norma CABA (&gt;10 años)</div></div>
    <div class="caba-kpi kpi-darkred"><div class="kpi-val">{caba_old13} ({caba_pct13}%)</div><div class="kpi-label">Fuera norma + prórroga (&gt;13 años)</div></div>
  </div>
  <div id="chart-caba" style="height:{max(300, len(caba_stats)*22)}px;"></div>
</div>

<h2>Tabla completa</h2>
<div class="chart-box" style="overflow-x:auto">
  <table>
    <thead>
      <tr>
        <th>#</th><th>Línea</th><th>Empresa</th><th>Vehículos</th>
        <th>% &gt;10 años</th><th>% &gt;13 años</th><th>Año prom</th><th>Más viejo</th><th>Más nuevo</th>
      </tr>
    </thead>
    <tbody>{table_rows}</tbody>
  </table>
</div>

<h2>Diccionario de patentes por línea</h2>
<div class="legend-row" style="margin-bottom:12px">
  <div class="legend-item"><div class="legend-dot" style="background:#7b241c"></div> &#9679; fuera de norma incluso con prórroga (&gt;13 años)</div>
  <div class="legend-item"><div class="legend-dot" style="background:#e67e22"></div> &#9675; fuera de norma CABA (10–13 años)</div>
</div>
{detail_sections}

<script>
const rankData = {plotly_ranking};
const histData = {plotly_hist};
const cabaData = {plotly_caba};

const L = {{
  paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
  font: {{ color: '#1a1a2e', family: 'Segoe UI, system-ui, sans-serif', size: 12 }},
  xaxis: {{ gridcolor: '#d6eaf8', zerolinecolor: '#b8d4e8', linecolor: '#b8d4e8' }},
  yaxis: {{ gridcolor: '#d6eaf8', linecolor: '#b8d4e8' }},
}};

Plotly.newPlot('chart-ranking', [{{
  type: 'bar', orientation: 'h',
  x: rankData.x, y: rankData.y,
  marker: {{ color: rankData.colors }},
  hovertemplate: '%{{y}}<br><b>%{{x:.1f}}%</b> flota &gt;10 años<extra></extra>',
  text: rankData.x.map(v => v + '%'), textposition: 'outside',
  textfont: {{ size: 11, color: '#1a1a2e' }},
}}], {{
  ...L, margin: {{ l: 90, r: 60, t: 16, b: 40 }},
  xaxis: {{ ...L.xaxis, title: '% vehículos > 10 años', range: [0, Math.max(...rankData.x) * 1.18] }},
  yaxis: {{ ...L.yaxis, autorange: 'reversed', tickfont: {{ size: 11 }} }},
}}, {{ responsive: true, displayModeBar: false }});

const maxH = Math.max(...histData.y);
Plotly.newPlot('chart-hist', [{{
  type: 'bar', x: histData.x, y: histData.y,
  marker: {{ color: histData.colors, line: {{ color: '#fff', width: 1 }} }},
  hovertemplate: 'Año %{{x}}<br><b>%{{y}}</b> vehículos<extra></extra>',
}}], {{
  ...L, margin: {{ l: 60, r: 40, t: 16, b: 60 }},
  xaxis: {{ ...L.xaxis, title: 'Año estimado de fabricación', dtick: 1, tickangle: -45 }},
  yaxis: {{ ...L.yaxis, title: 'Cantidad de vehículos' }},
  shapes: [
    {{ type:'line', x0:{CUTOFF_13}+0.5, x1:{CUTOFF_13}+0.5, y0:0, y1:maxH*1.15, line:{{ color:'#7b241c', width:2, dash:'dash' }} }},
    {{ type:'line', x0:{CUTOFF_10}+0.5, x1:{CUTOFF_10}+0.5, y0:0, y1:maxH*1.15, line:{{ color:'#e67e22', width:2, dash:'dash' }} }},
  ],
  annotations: [
    {{ x:{CUTOFF_13}+0.5, y:maxH*1.12, text:'13 años →', showarrow:false, font:{{ color:'#7b241c', size:11 }}, xanchor:'right' }},
    {{ x:{CUTOFF_10}+0.5, y:maxH*1.12, text:'10 años →', showarrow:false, font:{{ color:'#e67e22', size:11 }}, xanchor:'right' }},
  ],
}}, {{ responsive: true, displayModeBar: false }});

Plotly.newPlot('chart-caba', [{{
  type: 'bar', orientation: 'h',
  x: cabaData.x, y: cabaData.y,
  marker: {{ color: cabaData.colors }},
  hovertemplate: '%{{y}}<br><b>%{{x:.1f}}%</b> fuera norma CABA<extra></extra>',
  text: cabaData.x.map(v => v + '%'), textposition: 'outside',
  textfont: {{ size: 11, color: '#1a1a2e' }},
}}], {{
  ...L, margin: {{ l: 90, r: 60, t: 8, b: 40 }},
  xaxis: {{ ...L.xaxis, title: '% vehículos > 10 años (límite CABA)', range: [0, Math.max(...cabaData.x, 1) * 1.18] }},
  yaxis: {{ ...L.yaxis, autorange: 'reversed', tickfont: {{ size: 11 }} }},
  shapes: [{{ type:'line', x0:0, x1:0, y0:-0.5, y1:cabaData.y.length-0.5, line:{{ color:'#c0392b', width:0 }} }}],
}}, {{ responsive: true, displayModeBar: false }});
</script>
</body>
</html>"""


def main():
    print("=== report.py — Generador de Reporte HTML ===\n")
    if not FLEET_DB_PATH.exists():
        print(f"ERROR: {FLEET_DB_PATH} no existe. Correr collect.py primero.")
        return
    db = load_db()
    print(f"fleet_db.json: {len(db)} vehiculos")
    stats, excluded = compute_stats(db)
    print(f"Lineas con >= {MIN_VEHICLES}: {len(stats)}")
    print(f"Excluidas (<{MIN_VEHICLES}): {len(excluded)}")
    if excluded:
        print("  " + ", ".join(f"L{s['line']}({s['n_total']})" for s in excluded))
    html = generate_html(db, stats, excluded)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"\nReporte: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
