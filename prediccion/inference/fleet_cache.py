import asyncio
import logging
import time
import httpx
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Bounding box CABA/GBA
LAT_MIN, LAT_MAX = -35.1, -34.3
LON_MIN, LON_MAX = -59.1, -57.9


@dataclass
class LiveVehicle:
    id: str
    route_id: str
    direction_id: int
    lat: float
    lon: float
    speed: float          # m/s
    ts: int               # unix timestamp
    label: str
    line_number: str | None  # LD_linea enriquecida


class FleetCache:
    """
    Mantiene un snapshot vivo de la flota, actualizando cada 30s.
    Thread-safe mediante asyncio.Lock.
    """

    def __init__(
        self,
        source_url: str,
        refresh_interval_s: int = 30,
        timeout_s: float = 20.0,
    ):
        self._source_url = source_url
        self._refresh_interval = refresh_interval_s
        self._timeout = timeout_s
        self._state: dict[str, LiveVehicle] = {}
        self._last_refresh: float = 0.0
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._consecutive_errors = 0
        self._MAX_ERRORS = 10

    async def start(self) -> None:
        """Primer fetch inmediato, luego loop en background."""
        await self._do_refresh()
        self._task = asyncio.create_task(self._refresh_loop())

    async def stop(self) -> None:
        """Cancela el loop de refresh."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def get_vehicles(self) -> list[LiveVehicle]:
        async with self._lock:
            return list(self._state.values())

    async def get_line_vehicles(self, line: str) -> list[LiveVehicle]:
        async with self._lock:
            return [v for v in self._state.values() if v.line_number == line]

    async def get_agency_vehicles(self, route_ids: set[str]) -> list[LiveVehicle]:
        async with self._lock:
            return [v for v in self._state.values() if v.route_id in route_ids]

    @property
    def age_s(self) -> float:
        if self._last_refresh == 0.0:
            return float("inf")
        return time.time() - self._last_refresh

    @property
    def vehicle_count(self) -> int:
        return len(self._state)

    async def _do_refresh(self) -> None:
        """Realiza un fetch y actualiza el estado."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(self._source_url)
                resp.raise_for_status()
                raw = resp.json()
            async with self._lock:
                self._state = self._parse_vehicle_positions(raw)
                self._last_refresh = time.time()
            self._consecutive_errors = 0
        except Exception as e:
            self._consecutive_errors += 1
            if self._consecutive_errors >= self._MAX_ERRORS:
                logger.critical(
                    f"FleetCache: {self._consecutive_errors} errores consecutivos. "
                    f"Último: {e}"
                )
            else:
                logger.warning(f"FleetCache: error de refresh: {e}")

    async def _refresh_loop(self) -> None:
        while True:
            await asyncio.sleep(self._refresh_interval)
            await self._do_refresh()

    def _parse_vehicle_positions(self, raw_data: list[dict[str, Any]]) -> dict[str, LiveVehicle]:
        """Convierte respuesta de /api/vehiclePositions a dict de LiveVehicle."""
        result = {}
        for item in raw_data:
            # Intentar varios nombres de campo posibles
            vid = str(item.get("VP_vehicle_id") or item.get("id") or "")
            if not vid:
                continue
            lat = float(item.get("VP_latitude") or item.get("lat") or 0)
            lon = float(item.get("VP_longitude") or item.get("lon") or 0)
            # Filtrar fuera de bounding box
            if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
                continue
            route_id = str(item.get("VP_route_id") or item.get("route_id") or "")
            direction_id = int(item.get("VP_direction_id") or item.get("direction_id") or 0)
            speed = float(item.get("VPS_speed") or item.get("speed") or 0.0)
            ts = int(item.get("VP_timestamp") or item.get("ts") or time.time())
            label = str(item.get("LD_label") or item.get("VP_label") or item.get("label") or "")
            line_number = item.get("LD_linea") or item.get("line_number")
            if line_number is not None:
                line_number = str(line_number)
            result[vid] = LiveVehicle(
                id=vid, route_id=route_id, direction_id=direction_id,
                lat=lat, lon=lon, speed=speed, ts=ts,
                label=label, line_number=line_number,
            )
        return result
