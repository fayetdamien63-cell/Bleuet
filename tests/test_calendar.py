import datetime as dt
from pathlib import Path

from bleuet.context.calendar_provider import ICSCalendarProvider

ICS = Path(__file__).resolve().parents[1] / "data" / "calendar" / "famille.ics"


def test_evenement_ponctuel_et_journee_entiere():
    events = ICSCalendarProvider(ICS).events_for_day(dt.date(2026, 9, 11))
    summaries = [event.summary for event in events]
    assert "Anniversaire de mamie" in summaries
    assert "Rendez-vous dentiste (Tom)" in summaries


def test_recurrence_hebdomadaire():
    # Le yoga a lieu tous les mardis ; le 22 septembre 2026 est un mardi.
    events = ICSCalendarProvider(ICS).events_for_day(dt.date(2026, 9, 22))
    assert any(event.summary.startswith("Cours de yoga") for event in events)


def test_jour_sans_evenement():
    events = ICSCalendarProvider(ICS).events_for_day(dt.date(2026, 9, 21))
    assert events == []


def test_avant_le_debut_de_la_recurrence():
    events = ICSCalendarProvider(ICS).events_for_day(dt.date(2026, 8, 25))
    assert events == []
