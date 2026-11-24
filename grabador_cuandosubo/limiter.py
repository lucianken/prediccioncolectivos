"""Reloj inyectable y limitador de requests a CuandoSubo.

El WAF de SUBE corta con 302 apenas detecta concurrencia, así que acá no hay
hilos ni colas concurrentes: el grabador es de un solo hilo y cada request pasa
por `RateLimiter.run`, que espera hasta que

  - pasaron >= min_interval_s desde que TERMINÓ el request anterior, y
  - terminó la pausa por WAF (`pause`).

La prioridad (tier A > arribos > horarios > rotación C) la da el orden en que el
scheduler arma la cola del ciclo (`grabador.Recorder._plan_cycle`).
"""

from __future__ import annotations

import time
from typing import Callable, Protocol, TypeVar

T = TypeVar("T")


class Clock(Protocol):
    def now(self) -> float: ...           # epoch en segundos
    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


class RateLimiter:
    def __init__(self, min_interval_s: float, clock: Clock):
        self.min_interval_s = min_interval_s
        self.clock = clock
        self._last_end = float("-inf")
        self._paused_until = 0.0
        self.executed = 0

    def pause(self, seconds: float) -> None:
        """Frena todos los requests hasta now + seconds (backoff de WAF)."""
        self._paused_until = max(self._paused_until, self.clock.now() + seconds)

    @property
    def paused(self) -> bool:
        return self.clock.now() < self._paused_until

    def next_start(self) -> float:
        """Momento más temprano en que puede empezar el próximo request."""
        return max(self.clock.now(), self._paused_until, self._last_end + self.min_interval_s)

    def run(self, fn: Callable[[], T]) -> T:
        while True:
            wait = self.next_start() - self.clock.now()
            if wait <= 0:
                break
            self.clock.sleep(wait)
        try:
            return fn()
        finally:
            self._last_end = self.clock.now()
            self.executed += 1
