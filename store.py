"""Persistent storage for Irrigation Planner."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
    CONF_ZONES,
)

_LOGGER = logging.getLogger(__name__)


class IrrigationPlannerStore:
    """Manage persistent storage for Irrigation Planner."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the store."""
        self._hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] = {}

    async def async_load(self) -> dict[str, Any]:
        """Load data from storage."""
        stored = await self._store.async_load()
        if stored is None:
            self._data = {
                "weather_history": [],
                "weather_forecast": [],
                "zones": {},
                "last_weather_update": None,
                "last_calculation": None,
                "last_watered": None,
            }
        else:
            self._data = stored
            # Ensure all keys exist
            self._data.setdefault("weather_history", [])
            self._data.setdefault("weather_forecast", [])
            self._data.setdefault("zones", {})
            self._data.setdefault("last_weather_update", None)
            self._data.setdefault("last_calculation", None)
            self._data.setdefault("last_watered", None)
        return self._data

    async def async_save(self) -> None:
        """Save data to storage."""
        await self._store.async_save(self._data)

    @property
    def data(self) -> dict[str, Any]:
        """Return current data."""
        return self._data

    # --- Weather History ---

    async def async_add_weather_data(self, entry: dict[str, Any]) -> None:
        """Add a weather data entry to history."""
        self._data["weather_history"].append(entry)
        self._data["last_weather_update"] = datetime.now().isoformat()
        await self.async_save()
        _LOGGER.debug(
            "Added weather entry, total history: %d",
            len(self._data["weather_history"]),
        )

    async def async_set_forecast(self, forecast: list[dict[str, Any]]) -> None:
        """Replace forecast data."""
        self._data["weather_forecast"] = forecast
        await self.async_save()
        _LOGGER.debug("Updated forecast, %d entries", len(forecast))

    def get_weather_history(self, days: int = 2) -> list[dict[str, Any]]:
        """Get weather history for the last N days."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        return [
            e for e in self._data["weather_history"]
            if e.get("timestamp", "") >= cutoff
        ]

    def get_forecast(self, days: int = 2) -> list[dict[str, Any]]:
        """Get forecast for the next N days."""
        now = datetime.now().isoformat()
        cutoff = (datetime.now() + timedelta(days=days)).isoformat()
        return [
            e for e in self._data["weather_forecast"]
            if now <= e.get("timestamp", "") <= cutoff
        ]

    def get_accumulated_rain_actual(self, days: int = 2) -> float:
        """Get total actual precipitation over last N days in mm."""
        history = self.get_weather_history(days)
        return sum(e.get("precip_actual_mm", 0.0) for e in history)

    def get_accumulated_rain_forecast(self, days: int = 2) -> float:
        """Get total forecast precipitation over next N days in mm."""
        forecast = self.get_forecast(days)
        return sum(e.get("precip_forecast_mm", 0.0) for e in forecast)

    async def async_prune_old_data(self, retention_days: int = 3) -> None:
        """Delete weather data older than retention_days."""
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        before = len(self._data["weather_history"])
        self._data["weather_history"] = [
            e for e in self._data["weather_history"]
            if e.get("timestamp", "") >= cutoff
        ]
        after = len(self._data["weather_history"])
        if before != after:
            _LOGGER.info(
                "Pruned weather history: %d -> %d entries (retention: %d days)",
                before, after, retention_days,
            )
            await self.async_save()

    # --- Zone Data ---

    def get_zone_data(self, zone_id: str) -> dict[str, Any]:
        """Get stored data for a zone."""
        return self._data["zones"].get(zone_id, {
            "bucket_percent": 0.0,
            "last_duration_minutes": 0,
            "last_calculated": None,
            "last_et_inches": 0.0,
            "last_rain_actual_inches": 0.0,
            "last_rain_forecast_inches": 0.0,
            "last_drainage_inches": 0.0,
            "last_net_change_inches": 0.0,
            "factors": {},
        })

    async def async_update_zone(self, zone_id: str, data: dict[str, Any]) -> None:
        """Update stored data for a zone."""
        if zone_id not in self._data["zones"]:
            self._data["zones"][zone_id] = {}
        self._data["zones"][zone_id].update(data)
        self._data["last_calculation"] = datetime.now().isoformat()
        await self.async_save()
        _LOGGER.debug("Updated zone %s: bucket=%.1f%%", zone_id, data.get("bucket_percent", 0))

    async def async_record_watering(self) -> None:
        """Record that watering just happened."""
        self._data["last_watered"] = datetime.now().isoformat()
        await self.async_save()
        _LOGGER.info("Recorded watering at %s", self._data["last_watered"])

    async def async_reset_zone_bucket(self, zone_id: str, value: float = 0.0) -> None:
        """Reset a zone's bucket to a specific percentage."""
        if zone_id not in self._data["zones"]:
            self._data["zones"][zone_id] = {}
        self._data["zones"][zone_id]["bucket_percent"] = value
        await self.async_save()
        _LOGGER.info("Reset zone %s bucket to %.1f%%", zone_id, value)
