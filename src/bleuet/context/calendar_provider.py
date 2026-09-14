"""Agenda familial.

Une interface `CalendarProvider` + une implémentation qui lit un fichier .ics
local. Ajouter CalDAV (Nextcloud/iCloud) ou Google Calendar plus tard = écrire
une nouvelle classe ici, rien d'autre ne bouge.
"""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from ..logging_setup import get_logger

log = get_logger("bleuet.context.calendar")


@dataclass
class Event:
    summary: str
    start: dt.datetime | dt.date
    end: dt.datetime | dt.date | None = None
    location: str | None = None
    all_day: bool = False

    def to_text(self) -> str:
        if self.all_day:
            when = "toute la journée"
        else:
            when = self.start.strftime("%H:%M")
            if isinstance(self.end, dt.datetime):
                when += f"–{self.end.strftime('%H:%M')}"
        text = f"{when} : {self.summary}"
        if self.location:
            text += f" ({self.location})"
        return text


class CalendarProvider(ABC):
    @abstractmethod
    def events_for_day(self, day: dt.date) -> list[Event]:
        ...


class MockCalendarProvider(CalendarProvider):
    def events_for_day(self, day: dt.date) -> list[Event]:  # noqa: ARG002
        return [
            Event("Réunion parents-professeurs", dt.datetime.combine(day, dt.time(18, 0)),
                  dt.datetime.combine(day, dt.time(19, 0)), "École Jean Moulin"),
        ]


class ICSCalendarProvider(CalendarProvider):
    """Lit un fichier .ics local (export d'un agenda partagé, ou données de test).

    Gère les événements ponctuels et les règles de répétition simples
    (RRULE FREQ=DAILY/WEEKLY/MONTHLY/YEARLY avec BYDAY, UNTIL et COUNT).
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _load_calendar(self):
        from icalendar import Calendar

        if not self.path.exists():
            log.warning("fichier agenda absent : %s", self.path)
            return None
        with open(self.path, "rb") as handle:
            return Calendar.from_ical(handle.read())

    def events_for_day(self, day: dt.date) -> list[Event]:
        calendar = self._load_calendar()
        if calendar is None:
            return []

        events: list[Event] = []
        for component in calendar.walk("VEVENT"):
            events.extend(self._expand_component(component, day))
        events.sort(key=_sort_key)
        log.info("%d événement(s) d'agenda pour le %s", len(events), day.isoformat())
        return events

    def _expand_component(self, component, day: dt.date) -> list[Event]:
        start = component.get("DTSTART")
        if start is None:
            return []
        start_value = start.dt
        end_value = component.get("DTEND").dt if component.get("DTEND") else None
        all_day = not isinstance(start_value, dt.datetime)
        summary = str(component.get("SUMMARY", "(sans titre)"))
        location = str(component.get("LOCATION")) if component.get("LOCATION") else None

        occurrences: list[dt.date] = []
        rrule = component.get("RRULE")
        if rrule:
            occurrences = self._matching_recurrence(start_value, rrule, day)
        elif _as_date(start_value) == day:
            occurrences = [day]

        result = []
        for occurrence in occurrences:
            shifted_start = _shift_to(start_value, occurrence)
            shifted_end = _shift_to(end_value, occurrence) if end_value is not None else None
            result.append(Event(summary, shifted_start, shifted_end, location, all_day))
        return result

    @staticmethod
    def _matching_recurrence(start_value, rrule, day: dt.date) -> list[dt.date]:
        """Vrai si la règle de répétition tombe sur `day`. Volontairement limité
        aux cas courants d'un agenda familial (hebdo, quotidien, mensuel, annuel)."""
        start_date = _as_date(start_value)
        if day < start_date:
            return []

        until = rrule.get("UNTIL")
        if until:
            until_date = _as_date(until[0])
            if day > until_date:
                return []

        frequency = str(rrule.get("FREQ", ["WEEKLY"])[0]).upper()
        interval = int(rrule.get("INTERVAL", [1])[0])
        by_day = [str(value).upper()[-2:] for value in rrule.get("BYDAY", [])]
        weekday_codes = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]

        delta_days = (day - start_date).days
        matches = False
        if frequency == "DAILY":
            matches = delta_days % interval == 0
        elif frequency == "WEEKLY":
            weeks = delta_days // 7
            if weeks % interval == 0 or not by_day:
                same_week_slot = delta_days % (7 * interval) < 7
                if by_day:
                    matches = same_week_slot and weekday_codes[day.weekday()] in by_day
                else:
                    matches = delta_days % (7 * interval) == 0
        elif frequency == "MONTHLY":
            months = (day.year - start_date.year) * 12 + (day.month - start_date.month)
            matches = months % interval == 0 and day.day == start_date.day
        elif frequency == "YEARLY":
            years = day.year - start_date.year
            matches = (
                years % interval == 0
                and (day.month, day.day) == (start_date.month, start_date.day)
            )

        if not matches:
            return []

        count = rrule.get("COUNT")
        if count:
            # Approximation suffisante : on borne par la date de fin théorique.
            step = {"DAILY": 1, "WEEKLY": 7, "MONTHLY": 30, "YEARLY": 365}.get(frequency, 7)
            horizon = start_date + dt.timedelta(days=step * interval * (int(count[0]) - 1))
            if day > horizon:
                return []
        return [day]


def _as_date(value) -> dt.date:
    return value.date() if isinstance(value, dt.datetime) else value


def _shift_to(value, day: dt.date):
    """Replace un DTSTART/DTEND sur la date `day` en gardant l'heure d'origine."""
    if isinstance(value, dt.datetime):
        return value.replace(year=day.year, month=day.month, day=day.day)
    return day


def _sort_key(event: Event):
    start = event.start
    if isinstance(start, dt.datetime):
        return (0, start.hour, start.minute)
    return (0, 0, 0) if event.all_day else (1, 0, 0)


def build_calendar_provider(cfg) -> CalendarProvider:
    provider = cfg.get("context.calendar_provider", "ics")
    if provider == "mock":
        return MockCalendarProvider()
    path = cfg.resolve_path("context.calendar_path", "data/calendar/famille.ics")
    return ICSCalendarProvider(path)
