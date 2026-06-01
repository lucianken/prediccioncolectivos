import pickle
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from prediccion.pipeline.features import get_segment_index, SEGMENT_SIZE_M

_TZ_BA = ZoneInfo("America/Argentina/Buenos_Aires")


class A1Baseline:
    """
    Lookup table de velocidades históricas por segmento.
    4 niveles de fallback:
      1. (ramal_id, seg_idx, hour, dow) — exacto
      2. (ramal_id, hour, dow) — ignorar seg_idx
      3. (ramal_id, hour) — ignorar dow
      4. ramal_id global
    """

    def __init__(self):
        self._table: dict[tuple[str, int, int, int], float] = {}
        self._fallback_l2: dict[tuple[str, int, int], float] = {}
        self._fallback_l3: dict[tuple[str, int], float] = {}
        self._fallback_global: dict[str, float] = {}
        self._model_version: str = ""

    def fit(self, train_parquet) -> "A1Baseline":
        """
        Lee train_parquet con DuckDB. Construye los 4 niveles de lookup.
        train_parquet puede ser Path o str.

        Para cada fila: avg_speed = dist_remaining_m / observed_eta_s
        Agrupar por (ramal_id, seg_idx, hour, dow) para nivel 1.
        """
        import duckdb

        path = str(train_parquet)
        con = duckdb.connect()

        # Decodifica el encoding cíclico hour_sin/hour_cos a hora entera 0-23.
        # hour_sin/hour_cos = sin/cos(2π·h/24), así que h = atan2(sin,cos)·24/(2π).
        _HOUR_EXPR = (
            "CAST(ROUND("
            "  CASE"
            "    WHEN ATAN2(hour_sin, hour_cos) * 24 / (2 * 3.14159265) < 0"
            "    THEN ATAN2(hour_sin, hour_cos) * 24 / (2 * 3.14159265) + 24"
            "    ELSE ATAN2(hour_sin, hour_cos) * 24 / (2 * 3.14159265)"
            "  END"
            ") AS INTEGER) % 24"
        )

        _WHERE = "WHERE observed_eta_s > 0 AND dist_remaining_m > 0"
        _AVG   = "AVG(dist_remaining_m / observed_eta_s) AS avg_speed"
        _FROM  = f"FROM read_parquet('{path}')"

        # Nivel 1: exacto
        rows = con.execute(f"""
            SELECT ramal_id, seg_idx,
                   {_HOUR_EXPR} AS hour,
                   dow,
                   {_AVG}
            {_FROM}
            {_WHERE}
            GROUP BY ramal_id, seg_idx, hour, dow
        """).fetchall()

        for ramal_id, seg_idx, hour, dow, avg_speed in rows:
            if avg_speed and avg_speed > 0:
                self._table[(ramal_id, seg_idx, hour, dow)] = avg_speed

        # Nivel 2: (ramal_id, hour, dow)
        rows2 = con.execute(f"""
            SELECT ramal_id,
                   {_HOUR_EXPR} AS hour,
                   dow,
                   {_AVG}
            {_FROM}
            {_WHERE}
            GROUP BY ramal_id, hour, dow
        """).fetchall()

        for ramal_id, hour, dow, avg_speed in rows2:
            if avg_speed and avg_speed > 0:
                self._fallback_l2[(ramal_id, hour, dow)] = avg_speed

        # Nivel 3: (ramal_id, hour)
        rows3 = con.execute(f"""
            SELECT ramal_id,
                   {_HOUR_EXPR} AS hour,
                   {_AVG}
            {_FROM}
            {_WHERE}
            GROUP BY ramal_id, hour
        """).fetchall()

        for ramal_id, hour, avg_speed in rows3:
            if avg_speed and avg_speed > 0:
                self._fallback_l3[(ramal_id, hour)] = avg_speed

        # Nivel 4: global por ramal
        rows4 = con.execute(f"""
            SELECT ramal_id, AVG(dist_remaining_m / observed_eta_s) AS avg_speed
            FROM read_parquet('{path}')
            WHERE observed_eta_s > 0 AND dist_remaining_m > 0
            GROUP BY ramal_id
        """).fetchall()

        for ramal_id, avg_speed in rows4:
            if avg_speed and avg_speed > 0:
                self._fallback_global[ramal_id] = avg_speed

        self._model_version = f"a1_v{int(time.time())}"
        con.close()
        return self

    def _get_speed(
        self,
        ramal_id: str,
        seg_idx: int,
        hour: int,
        dow: int,
    ) -> tuple[float, str]:
        """Lookup con fallback jerárquico. Returns (speed_mps, confidence_level)."""
        key1 = (ramal_id, seg_idx, hour, dow)
        if key1 in self._table:
            return self._table[key1], "high"

        key2 = (ramal_id, hour, dow)
        if key2 in self._fallback_l2:
            return self._fallback_l2[key2], "medium"

        key3 = (ramal_id, hour)
        if key3 in self._fallback_l3:
            return self._fallback_l3[key3], "medium"

        if ramal_id in self._fallback_global:
            return self._fallback_global[ramal_id], "low"

        # Fallback final: velocidad genérica de 7 m/s (~25 km/h)
        return 7.0, "low"

    def predict(
        self,
        ramal_id: str,
        dist_vehicle_m: float,
        dist_target_m: float,
        timestamp_unix: int,
    ) -> tuple[float, str]:
        """
        Predice ETA en segundos desde dist_vehicle_m hasta dist_target_m.
        Returns (eta_seconds, confidence).
        """
        if dist_target_m <= dist_vehicle_m:
            return 0.0, "high"

        dt = datetime.fromtimestamp(timestamp_unix, tz=_TZ_BA)
        hour = dt.hour
        dow = dt.weekday()

        MIN_SPEED = 0.5
        MAX_ETA = 7200.0

        total_eta = 0.0
        worst_confidence = "high"
        CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}

        # Iterar por segmentos de 500m
        current = dist_vehicle_m
        while current < dist_target_m:
            seg_end = min(current + SEGMENT_SIZE_M, dist_target_m)
            seg_dist = seg_end - current
            seg_idx = get_segment_index(current)

            speed, conf = self._get_speed(ramal_id, seg_idx, hour, dow)
            speed = max(speed, MIN_SPEED)

            total_eta += seg_dist / speed

            if CONFIDENCE_RANK[conf] > CONFIDENCE_RANK[worst_confidence]:
                worst_confidence = conf

            current = seg_end

        total_eta = min(total_eta, MAX_ETA)
        return total_eta, worst_confidence

    def get_historical_headway(
        self,
        ramal_id: str,
        dist_m: float,
        timestamp_unix: int,
    ) -> tuple[float, str]:
        """Estima headway histórico cuando no hay bus visible. Fallback fijo de 10 min."""
        return 600.0, "low"

    def save(self, path) -> None:
        path = Path(path)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, path) -> "A1Baseline":
        path = Path(path)
        with open(path, "rb") as f:
            obj = pickle.load(f)
        if not isinstance(obj, A1Baseline):
            raise TypeError(f"Expected A1Baseline, got {type(obj)}")
        return obj

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def ramal_ids(self) -> list[str]:
        seen = set()
        for k in self._table:
            seen.add(k[0])
        for k in self._fallback_global:
            seen.add(k)
        return sorted(s for s in seen if s is not None)
