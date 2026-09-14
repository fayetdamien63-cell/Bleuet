"""Météo via Open-Meteo : gratuit, sans clé API, données structurées.

https://open-meteo.com — le palier gratuit couvre largement un usage domestique
(et reste réservé à l'usage non commercial).
"""

from __future__ import annotations

from ..logging_setup import get_logger
from .weather import Weather, WeatherProvider

log = get_logger("bleuet.context.open_meteo")

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# Codes WMO -> français parlé. Volontairement dit « comme à l'oral » : c'est
# lu par une synthèse vocale, pas affiché.
WMO_CODES = {
    0: "ciel dégagé",
    1: "plutôt ensoleillé",
    2: "partiellement nuageux",
    3: "ciel couvert",
    45: "brouillard",
    48: "brouillard givrant",
    51: "bruine légère",
    53: "bruine",
    55: "bruine forte",
    56: "bruine verglaçante",
    57: "bruine verglaçante forte",
    61: "pluie faible",
    63: "pluie",
    65: "fortes pluies",
    66: "pluie verglaçante",
    67: "pluie verglaçante forte",
    71: "neige faible",
    73: "neige",
    75: "fortes chutes de neige",
    77: "grésil",
    80: "averses éparses",
    81: "averses",
    82: "fortes averses",
    85: "averses de neige",
    86: "fortes averses de neige",
    95: "orage",
    96: "orage avec grêle",
    99: "orage violent avec grêle",
}


def describe(code: int | None) -> str:
    if code is None:
        return "temps indéterminé"
    return WMO_CODES.get(int(code), "temps indéterminé")


def geocode(city: str) -> tuple[float, float] | None:
    """Ville -> (latitude, longitude). Sans clé API non plus."""
    import requests

    try:
        response = requests.get(
            GEOCODING_URL,
            params={"name": city, "count": 1, "language": "fr", "format": "json"},
            timeout=6,
        )
        response.raise_for_status()
        results = response.json().get("results") or []
    except Exception as exc:
        log.warning("géocodage de %r impossible : %s", city, exc)
        return None
    if not results:
        log.warning("ville introuvable : %r", city)
        return None
    first = results[0]
    log.info("géocodage : %s -> %.4f, %.4f", city, first["latitude"], first["longitude"])
    return first["latitude"], first["longitude"]


class OpenMeteoProvider(WeatherProvider):
    def __init__(self, latitude: float, longitude: float, city: str = ""):
        self.latitude = latitude
        self.longitude = longitude
        self.city = city

    @classmethod
    def from_city(cls, city: str) -> "OpenMeteoProvider | None":
        coordinates = geocode(city)
        if coordinates is None:
            return None
        return cls(coordinates[0], coordinates[1], city)

    def current(self) -> Weather | None:
        import requests

        try:
            response = requests.get(
                FORECAST_URL,
                params={
                    "latitude": self.latitude,
                    "longitude": self.longitude,
                    "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min,"
                             "precipitation_probability_max,weather_code",
                    "timezone": "auto",
                    "forecast_days": 1,
                },
                timeout=6,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            # La météo est un bonus : elle ne doit jamais faire échouer une question.
            log.warning("météo indisponible : %s", exc)
            return None

        current = data.get("current", {})
        daily = data.get("daily", {})

        def first(key: str):
            values = daily.get(key) or []
            return values[0] if values else None

        rain = first("precipitation_probability_max")
        weather = Weather(
            city=self.city,
            # Le code du jour décrit mieux « la météo d'aujourd'hui » que
            # l'instantané, qui peut être « ciel dégagé » à 7 h un jour de pluie.
            description=describe(first("weather_code") or current.get("weather_code")),
            temperature=current.get("temperature_2m", 0.0),
            feels_like=current.get("apparent_temperature", 0.0),
            temp_min=first("temperature_2m_min"),
            temp_max=first("temperature_2m_max"),
            wind_kmh=current.get("wind_speed_10m"),
            rain_chance=int(rain) if rain is not None else None,
        )
        log.info("météo Open-Meteo : %s", weather.to_text())
        return weather
