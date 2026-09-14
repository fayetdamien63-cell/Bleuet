import datetime as dt

from bleuet.context.weather import MockWeatherProvider
from bleuet.orchestrator.prompt import build_system_prompt, french_date


def test_date_en_francais():
    assert french_date(dt.date(2026, 9, 11)) == "vendredi 11 septembre 2026"


def test_le_prompt_contient_la_meteo_et_la_date():
    stable, context = build_system_prompt(
        "Quel temps fait-il ?",
        weather=MockWeatherProvider("Clermont-Ferrand"),
        now=dt.datetime(2026, 9, 11, 7, 30),
    )
    assert "Bleuet" in stable
    assert "vendredi 11 septembre 2026" in context
    assert "Clermont-Ferrand" in context


def test_sections_absentes_si_provider_absent():
    _, context = build_system_prompt("test", now=dt.datetime(2026, 9, 11, 7, 30))
    assert "Météo" not in context
    assert "Agenda" not in context
