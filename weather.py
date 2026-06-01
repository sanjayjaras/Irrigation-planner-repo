"""Weather data collector for Irrigation Planner using OpenWeatherMap."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant

from .const import (
    OWM_BASE_URL,
    OWM_HISTORY_URL,
    WEATHER_TEMPERATURE,
    WEATHER_HUMIDITY,
    WEATHER_WIND_SPEED,
    WEATHER_PRESSURE,
    WEATHER_DEW_POINT,
    WEATHER_PRECIP_ACTUAL,
    WEATHER_PRECIP_FORECAST,
    WEATHER_PRECIP_POP,
    WEATHER_UV_INDEX,
    WEATHER_CLOUDS,
    WEATHER_TIMESTAMP,
    WEATHER_SOURCE,
)

_LOGGER = logging.getLogger(__name__)


class WeatherCollector:
    """Collect weather data from OpenWeatherMap One Call API 3.0."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_key: str,
        latitude: float,
        longitude: float,
    ) -> None:
        """Initialize weather collector."""
        self._hass = hass
        self._api_key = api_key
        self._lat = latitude
        self._lon = longitude

    async def async_fetch_current_and_forecast(self) -> dict[str, Any]:
        """Fetch current weather and 48-hour forecast from OWM One Call 3.0.

        Returns dict with keys:
            - "current": dict of current weather data
            - "hourly_forecast": list of hourly forecast entries (48 hours)
            - "daily_forecast": list of daily forecast entries (8 days)
        """
        url = (
            f"{OWM_BASE_URL}"
            f"?lat={self._lat}&lon={self._lon}"
            f"&appid={self._api_key}"
            f"&units=metric"
            f"&exclude=minutely,alerts"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        _LOGGER.error(
                            "OWM API error %s: %s", resp.status, text[:200]
                        )
                        return {}
                    data = await resp.json()
        except Exception as err:
            _LOGGER.error("Failed to fetch OWM data: %s", err)
            return {}

        result = {"current": None, "hourly_history": [], "hourly_forecast": [], "daily_forecast": []}

        # Parse current weather
        if "current" in data:
            c = data["current"]
            rain_1h = 0.0
            if "rain" in c and "1h" in c["rain"]:
                rain_1h = c["rain"]["1h"]
            snow_1h = 0.0
            if "snow" in c and "1h" in c["snow"]:
                snow_1h = c["snow"]["1h"]

            result["current"] = {
                WEATHER_TEMPERATURE: c.get("temp"),
                WEATHER_HUMIDITY: c.get("humidity"),
                WEATHER_WIND_SPEED: c.get("wind_speed"),
                WEATHER_PRESSURE: c.get("pressure"),
                WEATHER_DEW_POINT: c.get("dew_point"),
                WEATHER_PRECIP_ACTUAL: rain_1h + snow_1h,
                WEATHER_UV_INDEX: c.get("uvi"),
                WEATHER_CLOUDS: c.get("clouds"),
                WEATHER_TIMESTAMP: datetime.fromtimestamp(c["dt"]).isoformat(),
                WEATHER_SOURCE: "actual",
            }

        # Parse hourly data (48 hours)
        # OWM hourly includes past hours (actual rain) and future hours (forecast).
        # Split by current time: past -> history_actual, future -> forecast.
        now_ts = datetime.now().timestamp()
        for h in data.get("hourly", []):
            rain_1h = 0.0
            if "rain" in h and "1h" in h["rain"]:
                rain_1h = h["rain"]["1h"]
            snow_1h = 0.0
            if "snow" in h and "1h" in h["snow"]:
                snow_1h = h["snow"]["1h"]

            if h["dt"] <= now_ts:
                # Past hour: treat as actual measured data
                result["hourly_history"].append({
                    WEATHER_TEMPERATURE: h.get("temp"),
                    WEATHER_HUMIDITY: h.get("humidity"),
                    WEATHER_WIND_SPEED: h.get("wind_speed"),
                    WEATHER_PRESSURE: h.get("pressure"),
                    WEATHER_DEW_POINT: h.get("dew_point"),
                    WEATHER_PRECIP_ACTUAL: rain_1h + snow_1h,
                    WEATHER_UV_INDEX: h.get("uvi"),
                    WEATHER_CLOUDS: h.get("clouds"),
                    WEATHER_TIMESTAMP: datetime.fromtimestamp(h["dt"]).isoformat(),
                    WEATHER_SOURCE: "actual",
                })
            else:
                # Future hour: forecast
                result["hourly_forecast"].append({
                    WEATHER_TEMPERATURE: h.get("temp"),
                    WEATHER_HUMIDITY: h.get("humidity"),
                    WEATHER_WIND_SPEED: h.get("wind_speed"),
                    WEATHER_PRESSURE: h.get("pressure"),
                    WEATHER_DEW_POINT: h.get("dew_point"),
                    WEATHER_PRECIP_FORECAST: rain_1h + snow_1h,
                    WEATHER_PRECIP_POP: h.get("pop", 1.0),
                    WEATHER_UV_INDEX: h.get("uvi"),
                    WEATHER_CLOUDS: h.get("clouds"),
                    WEATHER_TIMESTAMP: datetime.fromtimestamp(h["dt"]).isoformat(),
                    WEATHER_SOURCE: "forecast",
                })

        # Parse daily forecast (8 days)
        for d in data.get("daily", []):
            rain_mm = d.get("rain", 0.0)
            snow_mm = d.get("snow", 0.0)

            result["daily_forecast"].append({
                WEATHER_TEMPERATURE: d.get("temp", {}).get("day"),
                "temp_min": d.get("temp", {}).get("min"),
                "temp_max": d.get("temp", {}).get("max"),
                WEATHER_HUMIDITY: d.get("humidity"),
                WEATHER_WIND_SPEED: d.get("wind_speed"),
                WEATHER_PRESSURE: d.get("pressure"),
                WEATHER_DEW_POINT: d.get("dew_point"),
                WEATHER_PRECIP_FORECAST: rain_mm + snow_mm,
                WEATHER_PRECIP_POP: d.get("pop", 1.0),
                WEATHER_UV_INDEX: d.get("uvi"),
                WEATHER_CLOUDS: d.get("clouds"),
                WEATHER_TIMESTAMP: datetime.fromtimestamp(d["dt"]).isoformat(),
                WEATHER_SOURCE: "daily_forecast",
            })

        _LOGGER.debug(
            "Fetched OWM data: current=%s, hourly_history=%d, hourly_forecast=%d, daily=%d",
            result["current"] is not None,
            len(result["hourly_history"]),
            len(result["hourly_forecast"]),
            len(result["daily_forecast"]),
        )
        return result

    async def async_fetch_history(self, date: datetime) -> list[dict[str, Any]]:
        """Fetch historical weather data for a specific date.

        Uses OWM One Call 3.0 timemachine endpoint.
        Returns list of hourly weather entries for that date.
        """
        dt_timestamp = int(date.timestamp())
        url = (
            f"{OWM_HISTORY_URL}"
            f"?lat={self._lat}&lon={self._lon}"
            f"&dt={dt_timestamp}"
            f"&appid={self._api_key}"
            f"&units=metric"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        _LOGGER.error(
                            "OWM History API error %s: %s", resp.status, text[:200]
                        )
                        return []
                    data = await resp.json()
        except Exception as err:
            _LOGGER.error("Failed to fetch OWM history: %s", err)
            return []

        entries = []
        for h in data.get("data", []):
            rain_1h = 0.0
            if "rain" in h and "1h" in h["rain"]:
                rain_1h = h["rain"]["1h"]
            snow_1h = 0.0
            if "snow" in h and "1h" in h["snow"]:
                snow_1h = h["snow"]["1h"]

            entries.append({
                WEATHER_TEMPERATURE: h.get("temp"),
                WEATHER_HUMIDITY: h.get("humidity"),
                WEATHER_WIND_SPEED: h.get("wind_speed"),
                WEATHER_PRESSURE: h.get("pressure"),
                WEATHER_DEW_POINT: h.get("dew_point"),
                WEATHER_PRECIP_ACTUAL: rain_1h + snow_1h,
                WEATHER_UV_INDEX: h.get("uvi"),
                WEATHER_CLOUDS: h.get("clouds"),
                WEATHER_TIMESTAMP: datetime.fromtimestamp(h["dt"]).isoformat(),
                WEATHER_SOURCE: "history",
            })

        _LOGGER.debug("Fetched %d history entries for %s", len(entries), date.date())
        return entries
