"""
Gráficos del borrador. Tres, uno por pregunta:

  1. excedencia.png   ¿cuánto tiempo pasa un bondi por encima de X km/h?
  2. por_hora.png     ¿cómo varía la velocidad comercial a lo largo del día?
  3. contrafactico.png ¿cuánto costaría un tope, en el peor escenario?

Uso:
    python -m experiments.velocidades.charts --outdir experiments/velocidades/out
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Paleta categórica validada (validate_palette.js, modo claro, superficie #fcfcfb).
C_BLUE, C_ORANGE, C_AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e3e2dd"
SURFACE = "#fcfcfb"

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK2,
        "text.color": INK,
        "xtick.color": INK2,
        "ytick.color": INK2,
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
    }
)


def _finish(ax, title, subtitle):
    ax.set_title(subtitle, fontsize=9.5, color=INK2, loc="left", pad=8)
    ax.figure.suptitle(title, fontsize=13, color=INK, x=0.055, ha="left", y=0.985)
    ax.grid(axis="y", alpha=0.9)
    ax.set_axisbelow(True)


def chart_exceedance(outdir: Path) -> None:
    exc = pd.read_csv(outdir / "excedencia.csv")
    fig, ax = plt.subplots(figsize=(8, 4.6))

    ax.plot(exc.v_kmh, exc.pct_tiempo_spot, lw=2, color=C_BLUE,
            label="lectura puntual (capta los picos)")
    ax.plot(exc.v_kmh, exc.pct_tiempo_medio, lw=2, color=C_ORANGE,
            label="promedio del minuto (los amortigua)")

    ax.axvline(30, color=GRID, lw=1.2, zorder=0)
    ax.text(30.8, 70, "límite propuesto\n30 km/h", fontsize=8.5, color=INK2, va="top")

    for col, color, dy in [("pct_tiempo_spot", C_BLUE, 12),
                           ("pct_tiempo_medio", C_ORANGE, -16)]:
        y = float(exc.loc[exc.v_kmh == 30, col].iloc[0])
        ax.plot([30], [y], "o", ms=7, color=color, mec=SURFACE, mew=2, zorder=5)
        ax.annotate(f"{y:.1f}%", (30, y), textcoords="offset points",
                    xytext=(10, dy), color=color, fontsize=10, weight="bold")

    ax.set_xlim(0, 70)
    ax.set_ylim(0, 100)
    ax.set_xlabel("umbral de velocidad (km/h)")
    ax.set_ylabel("% del tiempo por encima del umbral")
    ax.legend(frameon=False, fontsize=9, loc="upper right",
              bbox_to_anchor=(1.0, 1.02))
    _finish(ax, "Un colectivo pasa poco tiempo a velocidad alta",
            "Líneas 39 y 42, 4 días completos · 4.238 horas-bondi en servicio")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(outdir / "excedencia.png", dpi=160)
    plt.close(fig)


def chart_by_hour(outdir: Path) -> None:
    ph = pd.read_csv(outdir / "por_hora.csv")
    fig, ax = plt.subplots(figsize=(8, 4.6))

    # Etiqueta directa al final de cada serie en lugar de caja de leyenda: son
    # dos series y la caja chocaba con los datos.
    for line, color, dy in (("39", C_BLUE, -16), ("42", C_ORANGE, 8)):
        d = ph[(ph.line.astype(str) == line) & (ph.n > 200)].sort_values("hour")
        ax.plot(d.hour, d.v_comercial_kmh, lw=2, color=color, marker="o", ms=4.5,
                mec=SURFACE, mew=1.5, label=f"línea {line}")
        last = d.iloc[-1]
        ax.annotate(f"línea {line}", (last.hour, last.v_comercial_kmh),
                    textcoords="offset points", xytext=(8, dy),
                    color=color, fontsize=10, weight="bold")
        pico = d.loc[d.v_comercial_kmh.idxmin()]
        ax.annotate(f"{pico.v_comercial_kmh:.1f}",
                    (pico.hour, pico.v_comercial_kmh),
                    textcoords="offset points", xytext=(0, dy - 4),
                    ha="center", color=color, fontsize=9.5, weight="bold")

    ax.axhline(30, color=C_AQUA, lw=2, ls=(0, (4, 3)))
    ax.text(5, 30.8, "límite propuesto: 30 km/h", fontsize=9, color=C_AQUA)

    ax.set_ylim(0, 36)
    ax.set_xlim(4.5, 25.2)
    ax.set_xticks(range(5, 24, 2))
    ax.set_xlabel("hora del día (días hábiles)")
    ax.set_ylabel("velocidad comercial (km/h)")
    _finish(ax, "La velocidad comercial nunca se acerca al límite",
            "Distancia total sobre tiempo total, incluyendo paradas y semáforos")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(outdir / "por_hora.png", dpi=160)
    plt.close(fig)


def chart_counterfactual(outdir: Path) -> None:
    with open(outdir / "metrics.json", encoding="utf-8") as f:
        m = json.load(f)
    caps = m["contrafactico_por_viaje"]["por_cap"]
    dur = m["contrafactico_por_viaje"]["duracion_mediana_min"]

    fig, ax = plt.subplots(figsize=(8, 4.6))
    y = range(len(caps))
    lo = [c["extra_s_media_bajo"] for c in caps]
    hi = [c["extra_s_media_alto"] for c in caps]
    labels = [f'{c["cap_kmh"]} km/h' for c in caps]

    for i, (a, b) in enumerate(zip(lo, hi)):
        ax.plot([a, b], [i, i], lw=9, color=C_BLUE, alpha=0.22,
                solid_capstyle="round")
        ax.plot([a], [i], "o", ms=9, color=C_BLUE, mec=SURFACE, mew=2, zorder=4)
        ax.plot([b], [i], "o", ms=9, color=C_ORANGE, mec=SURFACE, mew=2, zorder=4)
        # Etiquetas a los costados del rango: adentro se pisan cuando lo/hi
        # están cerca (topes altos).
        ax.annotate(f"+{a/60:.1f} min", (a, i), textcoords="offset points",
                    xytext=(-10, -4), ha="right", color=C_BLUE, fontsize=9.5)
        ax.annotate(f"+{b/60:.1f} min", (b, i), textcoords="offset points",
                    xytext=(12, -4), ha="left", color=C_ORANGE, fontsize=9.5)

    ax.plot([], [], "o", ms=8, color=C_BLUE, label="estimador bajo (promedio del minuto)")
    ax.plot([], [], "o", ms=8, color=C_ORANGE, label="estimador alto (pico sostenido)")

    ax.set_yticks(list(y), labels)
    ax.invert_yaxis()
    ax.set_xlim(-115, 700)
    ax.set_xticks(range(0, 701, 100))
    ax.set_xlabel(f"segundos extra por viaje (viaje mediano: {dur:.0f} min)")
    ax.set_ylabel("tope de velocidad")
    # Arriba a la derecha: el único cuadrante vacío (los topes altos casi no
    # tienen efecto, así que sus marcas quedan pegadas al cero).
    ax.legend(frameon=False, fontsize=9, loc="upper right",
              bbox_to_anchor=(1.0, 1.03))
    ax.grid(axis="x", alpha=0.9)
    ax.grid(axis="y", visible=False)
    ax.set_axisbelow(True)
    ax.set_title("Escenario más pesimista: todo el exceso se paga íntegro, sin ninguna compensación",
                 fontsize=9.5, color=INK2, loc="left", pad=8)
    fig.suptitle("Cuánto tardaría de más un viaje con un tope de velocidad",
                 fontsize=13, color=INK, x=0.055, ha="left", y=0.985)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(outdir / "contrafactico.png", dpi=160)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", type=Path, required=True)
    args = ap.parse_args()
    chart_exceedance(args.outdir)
    chart_by_hour(args.outdir)
    chart_counterfactual(args.outdir)
    print(f"3 gráficos -> {args.outdir}")


if __name__ == "__main__":
    main()
