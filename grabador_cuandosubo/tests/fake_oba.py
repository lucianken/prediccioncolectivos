"""OBA falso en proceso: sirve las respuestas reales de referencia/fixtures y simula el WAF.

Se usa como `transport` del ObaClient. Registra cada request con su inicio y fin
según el reloj falso (la latencia simulada avanza el reloj).

Modos: 'ok' | 'waf' (302 siempre) | 'waf_once' (302 una vez y vuelve a 'ok') | 'down' (500).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

FIXTURES = Path(__file__).resolve().parent.parent / "referencia" / "fixtures"
TEST_KEY = "test-key"


def load_fixture(resource: str) -> dict:
    return json.loads((FIXTURES / f"{resource.replace('/', '__')}.json").read_text(encoding="utf-8"))


def load_sequence(name: str) -> list[dict]:
    d = FIXTURES / name
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))]


class FakeClock:
    def __init__(self, t: float):
        self.t = float(t)

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            self.t += seconds


class FakeOba:
    def __init__(self, clock: FakeClock, latency_s: float = 0.4):
        self.clock = clock
        self.latency_s = latency_s
        self.mode = "ok"
        self.log: list[dict] = []
        self.overrides: dict[str, dict] = {}
        self.sequences: dict[str, list[dict]] = {}

    def use_sequence(self, resource: str, bodies: list[dict]) -> None:
        """Una foto por request; la última se repite."""
        self.sequences[resource] = [copy.deepcopy(b) for b in bodies]

    def requests(self, prefix: str = "") -> list[dict]:
        return [r for r in self.log if r["resource"].startswith(prefix)]

    def __call__(self, url: str, timeout_s: float) -> tuple[int, str]:
        u = urlparse(url)
        resource = u.path.split("/api/where/", 1)[1].removesuffix(".json")
        key = parse_qs(u.query).get("key", [""])[0]
        start = self.clock.now()
        self.clock.t += self.latency_s
        status, body = self._respond(resource, key)
        self.log.append({"resource": resource, "start": start, "end": self.clock.now(), "status": status})
        return status, body if isinstance(body, str) else json.dumps(body)

    def _respond(self, resource: str, key: str):
        if self.mode in ("waf", "waf_once"):
            if self.mode == "waf_once":
                self.mode = "ok"
            return 302, ""
        if self.mode == "down":
            return 500, "down"
        if key != TEST_KEY:
            return 200, {"code": 401, "text": "permission denied", "version": 2}
        now_ms = int(self.clock.now() * 1000)
        if resource in self.overrides:
            return 200, self.overrides[resource]
        if resource in self.sequences:
            seq = self.sequences[resource]
            return 200, seq.pop(0) if len(seq) > 1 else seq[0]
        f = FIXTURES / f"{resource.replace('/', '__')}.json"
        if f.exists():
            return 200, f.read_text(encoding="utf-8")
        if resource.startswith("vehicles-for-agency/"):  # agencia sin coches: lista vacía, como la API real
            return 200, {"code": 200, "currentTime": now_ms, "text": "OK", "version": 2,
                         "data": {"list": [], "references": {"agencies": [], "routes": [], "stops": [], "trips": [],
                                                             "situations": []}}}
        return 200, {"code": 404, "currentTime": now_ms, "text": "resource not found", "version": 2}
