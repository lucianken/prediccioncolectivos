#!/usr/bin/env python3
"""
CLI unificado de entrenamiento para todas las fases.

NOTA: Phase 2 (Ramal ID) NO es ML — es la lookup geométrica offline en ramal_lookup/.
Ver ramal_lookup/build_ramal_map.py.

Uso:
  # Phase 1 — build dataset + entrenar A1Baseline (30+ días de datos):
  python prediccion/train.py --phase 1 \\
    --data-dir "\\\\192.168.0.18\\buffer\\grabaciones" \\
    --ml-dir "\\\\192.168.0.18\\buffer\\ml" \\
    --shapes-url prediccion/data/line_shapes.json \\
    --lines 39

  # Phase 3 — entrenar A3ETAModel (90+ días, requiere Phase 1 completada):
  python prediccion/train.py --phase 3 --ml-dir ...
"""
import argparse
import logging
import sys
from pathlib import Path

from prediccion.pipeline.shapes_io import DEFAULT_SHAPES_PATH as _DEFAULT_SHAPES

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)


def main():
    parser = argparse.ArgumentParser(description="Entrenamiento ML para predicción ETA")
    parser.add_argument("--phase", type=int, choices=[1, 3], default=1,
                        help="1=build dataset+A1Baseline, 3=entrenar A3ETAModel")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--ml-dir", type=Path, required=True)
    parser.add_argument("--shapes-url", default=str(_DEFAULT_SHAPES))
    parser.add_argument("--label-map", type=Path, default=Path("LABEL_LINE_MAP.json"))
    parser.add_argument("--lines", default=None)
    parser.add_argument("--line", default=None, help="Línea específica (no usada en phase 3)")
    parser.add_argument("--validate-projection", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    # Hiperparámetros phase 3
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--patience", type=int, default=8)
    parser.add_argument("--d-model", type=int, default=128)
    parser.add_argument("--no-fleet", action="store_true",
                        help="Deshabilitar FleetEncoder (más rápido, útil para baseline sin tráfico)")
    parser.add_argument("--resume", action="store_true",
                        help="Reanudar desde eta_a3_best.pt si existe (recuperación tras corte)")
    parser.add_argument("--max-groups", type=int, default=None,
                        help="Limitar a N row groups por epoch (para iteración rápida). Ej: --max-groups 30 ≈ 10%% del dato")
    parser.add_argument("--fleet-same-dir-cap", type=int, default=None,
                        help="Filtrar fleet a vehículos same_direction y capear a N. Ej: --fleet-same-dir-cap 20")
    parser.add_argument(
        "--merge-only",
        action="store_true",
        help="Phase 1: solo re-mergear eta_train/eta_val desde caché (sin releer NDJSON)",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Phase 1: saltar build_dataset, usar parquet existente. Útil para re-evaluar A1 sin regenerar datos.",
    )
    args = parser.parse_args()

    if args.phase == 1:
        _run_phase1(args)
    elif args.phase == 3:
        _run_phase3(args)


def _run_phase1(args):
    from prediccion.models.trainer import train_phase1

    skip_build = getattr(args, "skip_build", False)

    if not skip_build:
        from prediccion.pipeline.build_dataset import run_build_dataset

        if args.data_dir is None:
            print("Error: --data-dir requerido para Phase 1 (o usar --skip-build)", file=sys.stderr)
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
            merge_only=getattr(args, "merge_only", False),
        )
        step_offset = 0
    else:
        print("[skip] Build dataset omitido (--skip-build)")
        step_offset = -2

    print(f"[{2 + step_offset}/4] Entrenar A1Baseline...")
    output_dir = args.output_dir or (args.ml_dir / "models")
    metrics = train_phase1(ml_dir=args.ml_dir, output_dir=output_dir)

    print(f"[{3 + step_offset}/4] Metricas: MAE = {metrics.get('mae_min', 'N/A')} min")
    print(f"[{4 + step_offset}/4] Modelo guardado en: {metrics.get('model_path', 'N/A')}")



def _run_phase3(args):
    from prediccion.models.trainer import train_phase3

    print(f"[1/2] Entrenando A3ETAModel...")
    output_dir = args.output_dir or (args.ml_dir / "models")
    metrics = train_phase3(
        ml_dir=args.ml_dir,
        output_dir=output_dir,
        epochs=getattr(args, "epochs", 50),
        batch_size=getattr(args, "batch_size", 256),
        lr=getattr(args, "lr", 1e-3),
        device=args.device,
        patience=getattr(args, "patience", 8),
        d_model=getattr(args, "d_model", 128),
        use_fleet=not getattr(args, "no_fleet", False),
        resume=getattr(args, "resume", False),
        max_groups=getattr(args, "max_groups", None),
        fleet_same_dir_cap=getattr(args, "fleet_same_dir_cap", None),
    )
    val_mae = metrics.get("val_mae_min")
    val_str = f"{val_mae:.2f} min" if val_mae is not None else "N/A"
    print(f"[2/2] A3 completado: val MAE = {val_str}")
    print(f"      Modelo: {metrics.get('model_path')}")
    print(f"      ONNX:   {metrics.get('onnx_path')}")



if __name__ == "__main__":
    main()
