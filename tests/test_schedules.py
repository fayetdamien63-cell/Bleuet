import datetime as dt
from pathlib import Path

from bleuet.context.schedules import ScheduleStore

SCHEDULES = Path(__file__).resolve().parents[1] / "data" / "schedules"


def test_semaine_type_du_lundi():
    days = ScheduleStore(SCHEDULES).day(dt.date(2026, 9, 7), child="Léa")
    assert len(days) == 1
    labels = [entry.label for entry in days[0].entries]
    assert "École" in labels
    assert "Judo" in labels


def test_exception_periode_remplace_la_semaine_type():
    # 20 octobre 2026 = mardi des vacances de la Toussaint.
    day = ScheduleStore(SCHEDULES).day(dt.date(2026, 10, 20), child="Léa")[0]
    assert day.entries == []
    assert day.exception_note == "vacances de la Toussaint"


def test_exception_datee():
    day = ScheduleStore(SCHEDULES).day(dt.date(2026, 9, 25), child="Léa")[0]
    assert [entry.label for entry in day.entries] == ["Sortie au musée"]


def test_tous_les_enfants_par_defaut():
    days = ScheduleStore(SCHEDULES).day(dt.date(2026, 9, 8))
    assert {day.child for day in days} == {"Léa", "Tom"}
