#!/usr/bin/env python3
"""
CLI unificado de entrenamiento para todas las fases.

Uso:
  # Phase 1 (30 días mínimo):
  python prediccion/train.py --phase 1 \\
    --data-dir "\\\\192.168.0.18\\buffer\\grabaciones" \\
    --ml-dir "\\\\192.168.0.18\\buffer\\ml" \\
    --shapes-url http://localhost:3000/api/line-shapes \\
    --lines 39,42,151 \\
    --validate-projection

  # Phase 2 (90 días mínimo):
  python prediccion/train.py --phase 2 --ml-dir ... --line 39

  # Phase 3 (90 días mínimo):
  python prediccion/train.py --phase 3 --ml-dir ...
"""
import argparse
import sys
from pathlib import Path

from prediccion.pipeline.shapes_io import DEFAULT_SHAPES_PATH as _DEFAULT_SHAPES


def main():
    parser = argparse.ArgumentParser(description="Entrenamiento ML para predicción ETA")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--ml-dir", type=Path, required=True)
    parser.add_argument("--shapes-url", default=str(_DEFAULT_SHAPES))
    parser.add_argument("--label-map", type=Path, default=Path("LABEL_LINE_MAP.json"))
    parser.add_argument("--lines", default=None)
    parser.add_argument("--line", default=None, help="Línea específica para Phase 2")
    parser.add_argument("--validate-projection", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    args = parser.parse_args()

    if args.phase == 1:
        _run_phase1(args)
    elif args.phase == 2:
        _run_phase2(args)
    elif args.phase == 3:
        _run_phase3(args)


def _run_phase1(args):
    from prediccion.pipeline.build_dataset import run_build_dataset
    from prediccion.models.trainer import train_phase1

    if args.data_dir is None:
        print("Error: --data-dir requerido para Phase 1", file=sys.stderr)
        sys.exit(1)
    if args.shapes_url is None:
        print("Error: --shapes-url requerido para Phase 1", file=sys.stderr)
        sys.exit(1)

    if args.validate_projection:
        from prediccion.scripts.validate_projection import run_validation
        lines = args.lines.split(",") if args.lines else None
        result = run_validation(args.data_dir, args.shapes_url, lines)
        if not result.get("ok"):
            print("Validación de proyección fallida. Abortando.", file=sys.stderr)
            sys.exit(1)

    print("[1/4] Build dataset...")
    run_build_dataset(
        data_dir=args.data_dir,
        ml_dir=args.ml_dir,
        shapes_url=args.shapes_url,
        lines=args.lines.split(",") if args.lines else None,
        validate_projection=False,
        label_map_path=args.label_map,
    )

    print("[2/4] Entrenar A1Baseline...")
    output_dir = args.output_dir or (args.ml_dir / "models")
    metrics = train_phase1(ml_dir=args.ml_dir, output_dir=output_dir)

    print(f"[3/4] Métricas: MAE = {metrics.get('mae_min', 'N/A')} min")
    print(f"[4/4] Modelo guardado en: {metrics.get('model_path', 'N/A')}")


def _run_phase2(args):
    from prediccion.models import check_data_sufficiency, DataInsufficientError

    if args.data_dir is None:
        print("Error: --data-dir requerido para Phase 2", file=sys.stderr)
        sys.exit(1)
    if args.line is None:
        print("Error: --line requerido para Phase 2", file=sys.stderr)
        sys.exit(1)

    try:
        days = check_data_sufficiency(args.data_dir)
    except DataInsufficientError as e:
        print(f"{e}", file=sys.stderr)
        sys.exit(1)

    print(f"Datos suficientes: {days} días")

    from prediccion.models.trainer import train_phase2
    output_dir = args.output_dir or (args.ml_dir / "models")
    metrics = train_phase2(
        ml_dir=args.ml_dir,
        output_dir=output_dir,
        line=args.line,
        n_ramales=6,  # TODO: leer del shapes
        device=args.device,
    )
    print(f"Phase 2 completado: accuracy={metrics.get('val_accuracy', 'N/A')}")


def _run_phase3(args):
    from prediccion.models import check_data_sufficiency, DataInsufficientError

    if args.data_dir is None:
        print("Error: --data-dir requerido para Phase 3", file=sys.stderr)
        sys.exit(1)

    try:
        check_data_sufficiency(args.data_dir)
    except DataInsufficientError as e:
        print(f"{e}", file=sys.stderr)
        sys.exit(1)

    from prediccion.models.trainer import train_phase3
    output_dir = args.output_dir or (args.ml_dir / "models")
    metrics = train_phase3(
        ml_dir=args.ml_dir,
        output_dir=output_dir,
        device=args.device,
    )
    print(f"Phase 3 completado: MAE={metrics.get('val_mae_min', 'N/A')} min")


if __name__ == "__main__":
    main()
