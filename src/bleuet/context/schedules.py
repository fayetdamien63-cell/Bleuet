"""Emploi du temps des enfants : un YAML par enfant (semaine type + exceptions)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..logging_setup import get_logger

log = get_logger("bleuet.context.schedules")

WEEKDAY_KEYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


@dataclass
class ScheduleEntry:
    label: str
    start: str | None = None
    end: str | None = None
    location: str | None = None
    note: str | None = None

    def to_text(self) -> str:
        when = ""
        if self.start and self.end:
            when = f"{self.start}–{self.end} "
        elif self.start:
            when = f"{self.start} "
        text = f"{when}{self.label}"
        if self.location:
            text += f" ({self.location})"
        if self.note:
            text += f" — {self.note}"
        return text


@dataclass
class ChildDay:
    child: str
    day: dt.date
    entries: list[ScheduleEntry] = field(default_factory=list)
    exception_note: str | None = None

    def to_text(self) -> str:
        if self.exception_note and not self.entries:
            return f"{self.child} : {self.exception_note}"
        if not self.entries:
            return f"{self.child} : rien de prévu"
        lines = "; ".join(entry.to_text() for entry in self.entries)
        prefix = f"{self.child} : "
        if self.exception_note:
            prefix += f"[{self.exception_note}] "
        return prefix + lines


class ScheduleStore:
    """Charge `data/schedules/*.yaml` et calcule la journée d'un enfant.

    Une exception datée remplace la semaine type pour ce jour-là (`remplace: true`,
    le défaut) ou s'y ajoute (`remplace: false`).
    """

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def _load_files(self) -> list[dict]:
        if not self.directory.exists():
            log.warning("dossier d'emplois du temps absent : %s", self.directory)
            return []
        documents = []
        for path in sorted(self.directory.glob("*.y*ml")):
            with open(path, "r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
            data.setdefault("enfant", path.stem.capitalize())
            documents.append(data)
        return documents

    def children(self) -> list[str]:
        return [document["enfant"] for document in self._load_files()]

    def day(self, day: dt.date, child: str | None = None) -> list[ChildDay]:
        results: list[ChildDay] = []
        for document in self._load_files():
            name = document["enfant"]
            if child and child.lower() != name.lower():
                continue
            results.append(self._child_day(document, day))
        log.info("emplois du temps chargés pour le %s (%d enfant·s)", day.isoformat(), len(results))
        return results

    def _child_day(self, document: dict, day: dt.date) -> ChildDay:
        name = document["enfant"]
        weekday_key = WEEKDAY_KEYS[day.weekday()]
        base = document.get("semaine_type", {}).get(weekday_key, []) or []
        entries = [_entry(item) for item in base]
        note = None

        for exception in document.get("exceptions", []) or []:
            if _exception_matches(exception, day):
                note = exception.get("motif")
                extra = [_entry(item) for item in exception.get("activites", []) or []]
                if exception.get("remplace", True):
                    entries = extra
                else:
                    entries = entries + extra
                break

        return ChildDay(child=name, day=day, entries=entries, exception_note=note)


def _entry(item) -> ScheduleEntry:
    if isinstance(item, str):
        return ScheduleEntry(label=item)
    return ScheduleEntry(
        label=item.get("activite") or item.get("label") or "(sans nom)",
        start=_time_str(item.get("debut")),
        end=_time_str(item.get("fin")),
        location=item.get("lieu"),
        note=item.get("note"),
    )


def _time_str(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, dt.time):
        return value.strftime("%H:%M")
    return str(value)


def _exception_matches(exception: dict, day: dt.date) -> bool:
    single = exception.get("date")
    if single is not None and _as_date(single) == day:
        return True
    start, end = exception.get("du"), exception.get("au")
    if start is not None and end is not None:
        return _as_date(start) <= day <= _as_date(end)
    return False


def _as_date(value) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def build_schedule_store(cfg) -> ScheduleStore:
    return ScheduleStore(cfg.resolve_path("context.schedules_dir", "data/schedules"))
