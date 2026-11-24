"""Identidad vehículo → label → línea.

  vehicleId OBA "708_93193" → id "93193" (= id de la API CABA)
  label = tripStatus.vehicleLabel (vivo) ?? registro[id] ?? aprendido[id]
  línea = sufijo del label → LABEL_LINE_MAP (schema v3, sección `lines` = AMBA)
          vigente a la fecha de Buenos Aires del archivo, + overrides.

El loader del map es una copia mínima de `prediccion/pipeline/shapes_io.py`
(`resolve_label_line_index`): en el contenedor no está el repo.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from limiter import Clock

TZ_BA = timezone(timedelta(hours=-3))


def ba_date(ts_s: float) -> str:
    """Fecha de Buenos Aires (YYYY-MM-DD) de un epoch en segundos."""
    return datetime.fromtimestamp(ts_s, TZ_BA).strftime("%Y-%m-%d")


def strip_prefix(x: str | None) -> str:
    """'708_97938' → '97938'. '' / None → ''."""
    if not x:
        return ""
    i = x.find("_")
    return x[i + 1:] if i >= 0 else x


def _vigente(entry: dict[str, Any], date: str) -> bool:
    f = entry.get("from") or ""
    t = entry.get("to")
    return f <= date and (t is None or t >= date)


class LabelLineMap:
    """LABEL_LINE_MAP.json v3 + overrides, resuelto por fecha. Se recarga si cambia algún archivo."""

    def __init__(self, path: Path, overrides_path: Path | None = None):
        self.path = Path(path)
        self.overrides_path = Path(overrides_path) if overrides_path else None
        self._mtimes: tuple[float, float] = (-1.0, -1.0)
        self.lines: dict[str, dict[str, Any]] = {}
        self.oba_agencies: dict[str, list[str]] = {}
        self._index_cache: dict[str, dict[str, str]] = {}
        self.maybe_reload()

    def _current_mtimes(self) -> tuple[float, float]:
        a = os.path.getmtime(self.path)
        b = os.path.getmtime(self.overrides_path) if self.overrides_path and self.overrides_path.exists() else 0.0
        return a, b

    def maybe_reload(self) -> bool:
        m = self._current_mtimes()
        if m == self._mtimes:
            return False
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        if "lines" not in data:
            raise ValueError(f"{self.path}: LABEL_LINE_MAP sin sección 'lines' (schema v1?)")
        lines = {k: dict(v) for k, v in data["lines"].items()}
        oba: dict[str, list[str]] = {}
        if self.overrides_path and self.overrides_path.exists():
            with open(self.overrides_path, encoding="utf-8") as f:
                ov = json.load(f)
            for line, e in (ov.get("lines") or {}).items():
                if line.startswith("_"):
                    continue
                lines[line] = {"agencies": e.get("agencies", []), "suffixes": e.get("suffixes", [])}
            for line, e in (ov.get("obaAgencies") or {}).items():
                if line.startswith("_"):
                    continue
                oba[line] = [str(a) for a in e.get("agencies", [])]
        self.lines, self.oba_agencies = lines, oba
        self._index_cache = {}
        self._mtimes = m
        return True

    def suffix_index(self, date: str) -> dict[str, str]:
        """{sufijo → línea} vigente a `date`. Si un sufijo tiene varias asignaciones gana el `from` más reciente."""
        idx = self._index_cache.get(date)
        if idx is not None:
            return idx
        idx, latest = {}, {}
        for line, e in self.lines.items():
            for s in e.get("suffixes", []):
                if not _vigente(s, date):
                    continue
                f = s.get("from") or ""
                if s["suffix"] not in idx or f >= latest[s["suffix"]]:
                    idx[s["suffix"]] = line
                    latest[s["suffix"]] = f
        self._index_cache[date] = idx
        return idx

    def line_for_label(self, label: str | None, date: str) -> str | None:
        if not label or "-" not in label:
            return None
        return self.suffix_index(date).get(label.rsplit("-", 1)[1])

    def agencies_for(self, line: str, date: str) -> list[str]:
        e = self.lines.get(line)
        out: list[str] = []
        if e:
            out = [str(a["agencyId"]) for a in e.get("agencies", []) if _vigente(a, date)]
        for a in self.oba_agencies.get(line, []):
            if a not in out:
                out.append(a)
        return out

    def all_agencies(self, date: str) -> set[str]:
        out: set[str] = set()
        for line in self.lines:
            out.update(self.agencies_for(line, date))
        for line in self.oba_agencies:
            out.update(self.agencies_for(line, date))
        return out


def load_registry(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """registry.json → (id → label, id → patente)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("vehicles", {}), data.get("plates", {})


class Identity:
    """Labels: vivo > registro > aprendido. Aprende labels vivos nuevos y registra conflictos."""

    MAX_CONFLICTS = 1000

    def __init__(self, registry: dict[str, str], plates: dict[str, str], learned_path: Path | None, clock: Clock):
        self.registry = registry
        self.plates = plates
        self.learned_path = Path(learned_path) if learned_path else None
        self.clock = clock
        self.learned: dict[str, dict[str, str]] = {}
        self.conflicts: list[dict[str, str]] = []
        self.dirty = False
        if self.learned_path and self.learned_path.exists():
            try:
                with open(self.learned_path, encoding="utf-8") as f:
                    j = json.load(f)
                self.learned = j.get("learned", {})
                self.conflicts = j.get("conflicts", [])
            except (OSError, ValueError):
                pass

    def _iso(self) -> str:
        return datetime.fromtimestamp(self.clock.now(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def resolve(self, vid: str, live_label: str | None) -> tuple[str | None, str | None]:
        """→ (label, fuente) con fuente en 'oba' | 'registry' | 'learned' | None."""
        if live_label:
            self._learn(vid, live_label)
            return live_label, "oba"
        if vid in self.registry:
            return self.registry[vid], "registry"
        if vid in self.learned:
            return self.learned[vid]["label"], "learned"
        return None, None

    def _learn(self, vid: str, label: str) -> None:
        if self.learned.get(vid, {}).get("label") == label:
            return  # ya aprendido (y su conflicto, si lo hubo, ya registrado)
        known = self.registry.get(vid)
        if known is None and vid in self.learned:
            known = self.learned[vid]["label"]
        if known == label:
            return
        if known is not None:
            # Rompería el invariante id → label (debería no pasar nunca): se registra, no se pisa en silencio.
            self.conflicts.append({"id": vid, "known": known, "seen": label, "at": self._iso()})
            self.conflicts = self.conflicts[-self.MAX_CONFLICTS:]
        self.learned[vid] = {"label": label, "first_seen": self._iso()}
        self.dirty = True

    def plate(self, vid: str) -> str:
        return self.plates.get(vid, "")

    def flush(self) -> bool:
        if not self.dirty or not self.learned_path:
            return False
        tmp = self.learned_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"learned": self.learned, "conflicts": self.conflicts}, f, ensure_ascii=False)
        tmp.replace(self.learned_path)
        self.dirty = False
        return True

    def stats(self) -> dict[str, int]:
        return {"registry": len(self.registry), "learned": len(self.learned), "conflicts": len(self.conflicts)}
