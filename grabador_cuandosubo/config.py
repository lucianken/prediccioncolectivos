"""Configuración por variables de entorno. Nada hardcodeado salvo defaults; la key solo por env (OBA_KEY)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent


def _first_existing(*candidates: Path) -> Path:
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def _f(env: dict[str, str], k: str, d: float) -> float:
    v = env.get(k, "")
    return float(v) if v.strip() else d


def _i(env: dict[str, str], k: str, d: int) -> int:
    v = env.get(k, "")
    return int(v) if v.strip() else d


def _list(v: str) -> list[str]:
    return [x for x in v.replace(",", " ").split() if x]


@dataclass
class Config:
    oba_key: str
    data_dir: Path
    base_url: str = "https://cuandosubo.sube.gob.ar/onebusaway-api-webapp/api/where"
    record_lines: list[str] = field(default_factory=lambda: ["39", "26", "42", "92", "152", "168"])
    min_interval_s: float = 3.0          # separación mínima fin → inicio entre requests
    timeout_s: float = 20.0
    waf_backoff_s: float = 120.0
    cycle_s: float = 45.0                # ciclo del scheduler (tier A cada ciclo)
    arrivals_per_cycle: int = 4          # paradas del panel consultadas por ciclo (en rotación)
    trips_per_cycle: int = 2             # horarios de trips nuevos por ciclo (en los huecos)
    sweep: bool = True                   # rotación C (resto de AMBA) en los huecos
    keyframe_every: int = 100
    gap_threshold_s: float = 600.0
    stale_max_s: float = 120.0           # tier A: usar el último dato si tiene menos de esto
    sweep_max_age_s: float = 7200.0      # tier C: idem (la rotación tarda decenas de minutos)
    disk_min_gb: float = 2.0
    disk_check_every: int = 100
    fatal_fail_s: float = 600.0          # tier A fallando (no WAF) por más de esto → exit(1)
    label_line_map_path: Path = _first_existing(APP_DIR / "LABEL_LINE_MAP.json", APP_DIR.parent / "LABEL_LINE_MAP.json")
    overrides_path: Path = APP_DIR / "referencia" / "datos" / "label_line_map_overrides.json"
    registry_path: Path = APP_DIR / "referencia" / "datos" / "registry.json"
    arrival_stops_path: Path = APP_DIR / "arrival_stops.json"
    arrival_stops_filter: list[str] | None = None  # ARRIVAL_STOPS: subconjunto de ids del panel

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Config":
        env = dict(os.environ if env is None else env)
        d = cls(oba_key="", data_dir=Path("/data"))
        return cls(
            oba_key=env.get("OBA_KEY", ""),
            data_dir=Path(env.get("DATA_DIR", "/data")),
            base_url=env.get("OBA_BASE_URL", d.base_url),
            record_lines=_list(env["RECORD_LINES"]) if env.get("RECORD_LINES", "").strip() else d.record_lines,
            min_interval_s=_f(env, "OBA_MIN_INTERVAL_MS", d.min_interval_s * 1000) / 1000,
            timeout_s=_f(env, "OBA_TIMEOUT_MS", d.timeout_s * 1000) / 1000,
            waf_backoff_s=_f(env, "OBA_WAF_BACKOFF_MS", d.waf_backoff_s * 1000) / 1000,
            cycle_s=_f(env, "CYCLE_S", d.cycle_s),
            arrivals_per_cycle=_i(env, "ARRIVALS_PER_CYCLE", d.arrivals_per_cycle),
            trips_per_cycle=_i(env, "TRIPS_PER_CYCLE", d.trips_per_cycle),
            sweep=env.get("SWEEP", "1") != "0",
            keyframe_every=_i(env, "KEYFRAME_EVERY", d.keyframe_every),
            gap_threshold_s=_f(env, "GAP_THRESHOLD_S", d.gap_threshold_s),
            stale_max_s=_f(env, "STALE_MAX_S", d.stale_max_s),
            sweep_max_age_s=_f(env, "SWEEP_MAX_AGE_S", d.sweep_max_age_s),
            disk_min_gb=_f(env, "DISK_MIN_GB", d.disk_min_gb),
            fatal_fail_s=_f(env, "FATAL_FAIL_S", d.fatal_fail_s),
            label_line_map_path=Path(env["LABEL_LINE_MAP"]) if env.get("LABEL_LINE_MAP")
            else d.label_line_map_path,
            overrides_path=Path(env.get("LABEL_LINE_MAP_OVERRIDES", d.overrides_path)),
            registry_path=Path(env.get("REGISTRY_PATH", d.registry_path)),
            arrival_stops_path=Path(env.get("ARRIVAL_STOPS_FILE", d.arrival_stops_path)),
            arrival_stops_filter=_list(env["ARRIVAL_STOPS"]) if env.get("ARRIVAL_STOPS", "").strip() else None,
        )
