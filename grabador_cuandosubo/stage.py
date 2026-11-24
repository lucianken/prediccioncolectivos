"""Arma el contexto de build para el NUC en dist/grabador-cuandosubo/.

Copia el código, docker-compose.yml, Dockerfile, el panel de paradas, los datos de identidad,
el LABEL_LINE_MAP.json de prediccion colectivos/ y delta.py del grabador CABA (sin modificarlo).
Si existe grabador_cuandosubo/.env (ignorado por git) también lo copia; si no, hay que crear
~/grabador-cuandosubo/.env en el NUC a mano (ver README, "Cómo correr/deployar").

Uso:  python stage.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
OUT = HERE / "dist" / "grabador-cuandosubo"

FILES = {
    "grabador.py": HERE / "grabador.py",
    "config.py": HERE / "config.py",
    "identity.py": HERE / "identity.py",
    "limiter.py": HERE / "limiter.py",
    "oba_client.py": HERE / "oba_client.py",
    "requirements.txt": HERE / "requirements.txt",
    "Dockerfile": HERE / "Dockerfile",
    "docker-compose.yml": HERE / "docker-compose.yml",
    ".env.example": HERE / ".env.example",
    "arrival_stops.json": HERE / "arrival_stops.json",
    "referencia/datos/registry.json": HERE / "referencia" / "datos" / "registry.json",
    "referencia/datos/label_line_map_overrides.json": HERE / "referencia" / "datos" / "label_line_map_overrides.json",
    "LABEL_LINE_MAP.json": REPO / "LABEL_LINE_MAP.json",
    "delta.py": REPO / "grabador" / "delta.py",
}


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    for dst, src in FILES.items():
        if not src.exists():
            raise SystemExit(f"falta {src}")
        (OUT / dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, OUT / dst)
    env = HERE / ".env"
    if env.exists():
        shutil.copy2(env, OUT / ".env")
        print("  .env copiado")
    else:
        print("  AVISO: sin .env local; crear ~/grabador-cuandosubo/.env en el NUC (OBA_KEY=...)")
    print(f"listo: {OUT}")


if __name__ == "__main__":
    main()
