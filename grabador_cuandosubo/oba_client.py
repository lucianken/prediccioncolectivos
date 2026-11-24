"""Cliente OBA (CuandoSubo): GET + key, detección de WAF, caché por recurso.

Transporte inyectable: `transport(url, timeout_s) -> (status_code, text)`.
El de producción usa `requests` SIN seguir redirects (el WAF responde 302).

Errores:
  WafError        — 301/302/303/307/403/429 o cuerpo no JSON (HTML). Pausa el limitador 120 s.
  KeyInvalidError — cuerpo con code 401. Error fatal de configuración.
  ObaError        — 5xx, timeout, red, code != 200.

La key nunca aparece en logs ni en mensajes de error (se reemplaza por ***).
"""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import quote, urlencode

from limiter import Clock, RateLimiter

Transport = Callable[[str, float], tuple[int, str]]

WAF_STATUS = {301, 302, 303, 307, 403, 429}


class ObaError(Exception):
    def __init__(self, msg: str, status: int | None = None):
        super().__init__(msg)
        self.status = status


class WafError(ObaError):
    pass


class KeyInvalidError(ObaError):
    pass


def requests_transport() -> Transport:
    import requests

    session = requests.Session()
    session.headers.update({"User-Agent": "grabador-cuandosubo/1.0", "Accept": "application/json"})

    def get(url: str, timeout_s: float) -> tuple[int, str]:
        r = session.get(url, timeout=timeout_s, allow_redirects=False)
        return r.status_code, r.text

    return get


class ObaClient:
    def __init__(
        self,
        base_url: str,
        key: str,
        limiter: RateLimiter,
        transport: Transport,
        clock: Clock,
        timeout_s: float = 20.0,
        waf_backoff_s: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.key = key
        self.limiter = limiter
        self.transport = transport
        self.clock = clock
        self.timeout_s = timeout_s
        self.waf_backoff_s = waf_backoff_s
        self.cache: dict[str, tuple[dict[str, Any], float]] = {}  # recurso → (body, fetched_at)
        self.counters = {"requests": 0, "waf": 0, "errors": 0}
        self.durations: list[float] = []  # últimas duraciones (para estimar si entra otro request)

    def _url(self, resource: str, params: dict[str, Any] | None) -> str:
        q = {"key": self.key, **(params or {})}
        return f"{self.base_url}/{quote(resource, safe='/_-.')}.json?{urlencode(q)}"

    def _redact(self, msg: str) -> str:
        if self.key:
            msg = msg.replace(self.key, "***").replace(quote(self.key, safe=""), "***")
        return msg

    def _once(self, resource: str, params: dict[str, Any] | None) -> dict[str, Any]:
        url = self._url(resource, params)
        t0 = self.clock.now()
        self.counters["requests"] += 1
        try:
            status, text = self.transport(url, self.timeout_s)
        except Exception as e:  # timeout, DNS, conexión
            raise ObaError(self._redact(f"network: {type(e).__name__}: {e}")) from None
        finally:
            self.durations = (self.durations + [self.clock.now() - t0])[-20:]
        if status in WAF_STATUS:
            raise WafError(f"WAF/rate limit (HTTP {status})", status)
        if status >= 400:
            raise ObaError(f"HTTP {status}", status)
        try:
            body = json.loads(text)
        except ValueError:
            raise WafError("respuesta no JSON (probable WAF)", status) from None
        code = body.get("code") if isinstance(body, dict) else None
        if code == 401:
            raise KeyInvalidError("OBA code 401: key inválida", 401)
        if code != 200:
            raise ObaError(f"OBA code {code}: {body.get('text', '') if isinstance(body, dict) else ''}", code)
        return body

    def fetch(self, resource: str, params: dict[str, Any] | None = None, retry_waf: bool = True) -> dict[str, Any]:
        """GET a través del limitador. Ante WAF pausa 120 s y reintenta una vez."""
        attempts = 2 if retry_waf else 1
        for i in range(attempts):
            try:
                body = self.limiter.run(lambda: self._once(resource, params))
            except WafError:
                self.counters["waf"] += 1
                self.limiter.pause(self.waf_backoff_s)
                if i + 1 < attempts:
                    continue
                raise
            except ObaError:
                self.counters["errors"] += 1
                raise
            self.cache[resource] = (body, self.clock.now())
            return body
        raise AssertionError("unreachable")

    def cached(self, resource: str, max_age_s: float) -> dict[str, Any] | None:
        """Última respuesta buena de un recurso si tiene menos de max_age_s."""
        entry = self.cache.get(resource)
        if entry and self.clock.now() - entry[1] <= max_age_s:
            return entry[0]
        return None

    def typical_duration(self) -> float:
        if not self.durations:
            return 1.0
        s = sorted(self.durations)
        return s[len(s) // 2]
