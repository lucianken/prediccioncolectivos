#!/usr/bin/env python3
"""
Arranca el servidor de predicción de ETA.

Uso:
  python prediccion/serve.py \\
    --model "\\\\192.168.0.18\\buffer\\ml\\models\\a1_v1.pkl" \\
    --shapes-url http://localhost:3000/api/line-shapes \\
    --fleet-url http://localhost:3000/api/vehiclePositions \\
    --port 8000
"""
import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Servidor de predicción ETA")
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--a3-model", type=Path, default=None)
    parser.add_argument("--shapes-url", required=True)
    parser.add_argument("--fleet-url", required=True)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    if not args.model.exists():
        print(f"Error: modelo no encontrado: {args.model}", file=sys.stderr)
        sys.exit(1)

    import uvicorn
    from prediccion.api.app import app

    app.state.config = {
        "model_path": args.model,
        "a3_model_path": str(args.a3_model) if args.a3_model else None,
        "shapes_url": args.shapes_url,
        "fleet_url": args.fleet_url,
    }

    print(f"Arrancando servidor en http://{args.host}:{args.port}")
    print(f"  Modelo: {args.model}")
    print(f"  A3: {args.a3_model or 'no disponible (usando A1)'}")
    print(f"  Shapes: {args.shapes_url}")
    print(f"  Docs: http://localhost:{args.port}/docs")

    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
