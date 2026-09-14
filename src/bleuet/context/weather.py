"""Météo du jour.

Trois providers : `openmeteo` (défaut, gratuit et sans clé), `openweathermap`
(nécessite une clé) et `mock` (données figées, pour développer hors ligne).
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..logging_setup import get_logger

log = get_logger("bleuet.context.weather")


@dataclass
class Weather:
    city: str
    description: str
    temperature: float
    feels_like: float
    temp_min: float | None = None
    temp_max: float | None = None
    wind_kmh: float | None = None
    rain_chance: int | None = None

    def to_text(self) -> str:
        parts = [f"{self.city} : {self.description}, {self.temperature:.0f} °C"]
        if self.feels_like is not None and abs(self.feels_like - self.temperature) >= 2:
            parts.append(f"ressenti {self.feels_like:.0f} °C")
        if self.temp_min is not None and self.temp_max is not None:
            parts.append(f"min {self.temp_min:.0f} °C / max {self.temp_max:.0f} °C")
        if self.wind_kmh:
            parts.append(f"vent {self.wind_kmh:.0f} km/h")
        if self.rain_chance is not None:
            parts.append(f"pluie {self.rain_chance} %")
        return ", ".join(parts)


class WeatherProvider(ABC):
    @abstractmethod
    def current(self) -> Weather | None:
        ...


class MockWeatherProvider(WeatherProvider):
    """Données figées, pour développer sans clé API."""

    def __init__(self, city: str = "Clermont-Ferrand"):
        self.city = city

    def current(self) -> Weather:
        log.info("météo simulée (provider mock)")
        return Weather(
            city=self.city,
            description="ciel voilé, averses en fin d'après-midi",
            temperature=14.0,
            feels_like=12.5,
            temp_min=9.0,
            temp_max=17.0,
            wind_kmh=18.0,
            rain_chance=40,
        )


class OpenWeatherMapProvider(WeatherProvider):
    ENDPOINT = "https://api.openweathermap.org/data/2.5/weather"

    def __init__(self, api_key: str, latitude: float, longitude: float, city: str = ""):
        self.api_key = api_key
        self.latitude = latitude
        self.longitude = longitude
        self.city = city

    def current(self) -> Weather | None:
        import requests

        try:
            response = requests.get(
                self.ENDPOINT,
                params={
                    "lat": self.latitude,
                    "lon": self.longitude,
                    "appid": self.api_key,
                    "units": "metric",
                    "lang": "fr",
                },
                timeout=6,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # réseau coupé, clé invalide, quota…
            # La météo est un bonus : on ne fait jamais échouer une question pour ça.
            log.warning("météo indisponible : %s", exc)
            return None

        main = data.get("main", {})
        weather = Weather(
            city=self.city or data.get("name", ""),
            description=(data.get("weather") or [{}])[0].get("description", "inconnu"),
            temperature=main.get("temp", 0.0),
            feels_like=main.get("feels_like", 0.0),
            temp_min=main.get("temp_min"),
            temp_max=main.get("temp_max"),
            wind_kmh=(data.get("wind", {}).get("speed", 0.0) or 0.0) * 3.6,
        )
        log.info("météo récupérée : %s", weather.to_text())
        return weather


def build_weather_provider(cfg) -> WeatherProvider:
    provider = os.environ.get("BLEUET_WEATHER_PROVIDER") or cfg.get(
        "context.weather_provider", "openmeteo"
    )
    city = os.environ.get("BLEUET_CITY", "Clermont-Ferrand")
    latitude = os.environ.get("BLEUET_LATITUDE")
    longitude = os.environ.get("BLEUET_LONGITUDE")

    if provider == "openmeteo":
        from .open_meteo import OpenMeteoProvider

        if latitude and longitude:
            return OpenMeteoProvider(float(latitude), float(longitude), city)
        # Pas de coordonnées : on les déduit du nom de la ville, une fois.
        resolved = OpenMeteoProvider.from_city(city)
        if resolved is not None:
            return resolved
        log.warning("géocodage impossible : retour au provider mock")
        return MockWeatherProvider(city)

    if provider == "openweathermap":
        api_key = os.environ.get("OPENWEATHER_API_KEY", "").strip()
        if not api_key:
            log.warning("OPENWEATHER_API_KEY absente : retour au provider mock")
            return MockWeatherProvider(city)
        return OpenWeatherMapProvider(
            api_key=api_key,
            latitude=float(latitude or 45.7772),
            longitude=float(longitude or 3.0870),
            city=city,
        )

    return MockWeatherProvider(city)
