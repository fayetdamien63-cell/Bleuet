from bleuet.context.open_meteo import describe
from bleuet.context.weather import MockWeatherProvider, Weather


def test_codes_wmo_en_francais():
    assert describe(0) == "ciel dégagé"
    assert describe(95) == "orage"
    assert describe(None) == "temps indéterminé"
    assert describe(12345) == "temps indéterminé"


def test_texte_meteo_lisible():
    text = Weather(
        city="Clermont-Ferrand",
        description="averses",
        temperature=13.4,
        feels_like=11.0,
        temp_min=8.0,
        temp_max=17.0,
        wind_kmh=22.0,
        rain_chance=70,
    ).to_text()
    assert text.startswith("Clermont-Ferrand : averses, 13 °C")
    assert "ressenti 11 °C" in text
    assert "pluie 70 %" in text


def test_ressenti_omis_si_proche_de_la_temperature():
    text = Weather("Lyon", "ciel dégagé", 20.0, 20.5).to_text()
    assert "ressenti" not in text


def test_provider_mock_ne_depend_de_rien():
    weather = MockWeatherProvider("Ambert").current()
    assert weather.city == "Ambert"
    assert weather.to_text()
