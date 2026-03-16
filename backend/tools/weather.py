"""Weather tool: location string → current conditions via Open-Meteo (no API key)."""
from __future__ import annotations

import urllib.parse
import urllib.request
import json
from typing import Optional

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather codes (subset for readable summary)
WEATHER_DESCRIPTIONS = {
    0: "clear",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "rain",
    65: "heavy rain",
    71: "slight snow",
    73: "snow",
    75: "heavy snow",
    80: "slight rain showers",
    81: "rain showers",
    82: "heavy rain showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "thunderstorm with heavy hail",
}


def _geocode(location: str) -> Optional[tuple[float, float, str]]:
    """Resolve location string to (lat, lon, display_name). Returns None if not found."""
    location = (location or "").strip()
    if not location:
        return None
    params = urllib.parse.urlencode({"name": location, "count": 1})
    url = f"{GEOCODE_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    results = data.get("results") or []
    if not results:
        return None
    r = results[0]
    lat = r.get("latitude")
    lon = r.get("longitude")
    name = r.get("name") or location
    if lat is None or lon is None:
        return None
    return (float(lat), float(lon), str(name))


def _fetch_weather(lat: float, lon: float) -> Optional[dict]:
    """Get current weather for lat/lon from Open-Meteo."""
    params = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
    })
    url = f"{FORECAST_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def get_weather(location: str) -> str:
    """
    Get current weather for a location (city name or place).
    Uses Open-Meteo; no API key required.
    Returns a short human-readable string or an error message.
    """
    loc = _geocode(location)
    if not loc:
        return f"Could not find location: {location!r}. Try a city name or place."
    lat, lon, name = loc
    data = _fetch_weather(lat, lon)
    if not data:
        return f"Weather unavailable for {name}."
    current = (data.get("current") or {})
    temp = current.get("temperature_2m")
    unit = (data.get("current_units") or {}).get("temperature_2m", "°C")
    humidity = current.get("relative_humidity_2m")
    code = current.get("weather_code", 0)
    wind = current.get("wind_speed_10m")
    wind_unit = (data.get("current_units") or {}).get("wind_speed_10m", "km/h")

    desc = WEATHER_DESCRIPTIONS.get(code, f"code {code}")
    parts = [f"{name}: {desc}"]
    if temp is not None:
        parts.append(f" {temp}{unit}")
    if humidity is not None:
        parts.append(f", humidity {humidity}%")
    if wind is not None:
        parts.append(f", wind {wind} {wind_unit}")
    return "".join(parts).strip()
