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
                "backfilled_dates": [],
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
            self._data.setdefault("backfilled_dates", [])
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
        timestamp = entry.get("timestamp")
        source = entry.get("source")

        # De-duplicate same source/timestamp entries (e.g., repeated manual refresh)
        # by replacing the previous entry instead of appending duplicates.
        if timestamp:
            for idx in range(len(self._data["weather_history"]) - 1, -1, -1):
                existing = self._data["weather_history"][idx]
                if (
                    existing.get("timestamp") == timestamp
                    and existing.get("source") == source
                ):
                    self._data["weather_history"][idx] = entry
                    self._data["last_weather_update"] = datetime.now().isoformat()
                    await self.async_save()
                    _LOGGER.debug(
                        "Replaced weather entry for %s (%s)",
                        timestamp,
                        source,
                    )
                    return

        self._data["weather_history"].append(entry)
        self._data["last_weather_update"] = datetime.now().isoformat()
        await self.async_save()
        _LOGGER.debug(
            "Added weather entry, total history: %d",
            len(self._data["weather_history"]),
        )

    def get_backfilled_dates(self) -> set[str]:
        """Return the set of dates already fetched via OWM timemachine."""
        return set(self._data.get("backfilled_dates", []))

    async def async_mark_date_backfilled(self, date_str: str) -> None:
        """Record that a date has been backfilled so it won't be fetched again."""
        backfilled = self.get_backfilled_dates()
        backfilled.add(date_str)
        self._data["backfilled_dates"] = sorted(backfilled)
        await self.async_save()

    async def async_add_weather_data_batch(self, entries: list[dict[str, Any]]) -> None:
        """Add multiple weather entries with a single save.

        Uses the same dedup logic as async_add_weather_data but avoids
        writing the storage file once per entry.
        """
        for entry in entries:
            timestamp = entry.get("timestamp")
            source = entry.get("source")
            replaced = False
            if timestamp:
                for idx in range(len(self._data["weather_history"]) - 1, -1, -1):
                    existing = self._data["weather_history"][idx]
                    if (
                        existing.get("timestamp") == timestamp
                        and existing.get("source") == source
                    ):
                        self._data["weather_history"][idx] = entry
                        replaced = True
                        break
            if not replaced:
                self._data["weather_history"].append(entry)

        if entries:
            self._data["last_weather_update"] = datetime.now().isoformat()
            await self.async_save()
            _LOGGER.debug("Batch-added %d weather entries", len(entries))

    async def async_set_forecast(self, forecast: list[dict[str, Any]]) -> None:
        """Replace forecast data."""
        self._data["weather_forecast"] = forecast
        await self.async_save()
        _LOGGER.debug("Updated forecast, %d entries", len(forecast))

    def get_weather_history(self, days: int = 2) -> list[dict[str, Any]]:
        """Get weather history for the last N days, deduped to one entry per hour.

        OWM hourly entries (timestamp ending :00:00) are preferred over
        current-poll entries (e.g. :32:09) for the same hour bucket to
        prevent double-counting rain when both types exist in storage.

        Future-timestamped entries (including old UTC-aware NWS entries whose
        string representation sorts after current local-naive timestamps) are
        excluded to prevent stale data from contaminating history[-1].
        """
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
        # Allow a 2-hour future window for minor clock skew, but exclude
        # anything further ahead (e.g. old UTC timestamps that appear as
        # future dates when compared to local-naive timestamps).
        future_cutoff = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
        recent = [
            e for e in self._data["weather_history"]
            if cutoff <= e.get("timestamp", "")[:19] <= future_cutoff
        ]

        # Dedup: keep one entry per hour bucket (YYYY-MM-DDTHH)
        hour_buckets: dict[str, dict] = {}
        for e in recent:
            ts = e.get("timestamp", "")
            bucket = ts[:13]
            if bucket not in hour_buckets:
                hour_buckets[bucket] = e
            else:
                # Prefer the exact :00:00 OWM hourly entry
                existing_ts = hour_buckets[bucket].get("timestamp", "")
                if existing_ts.endswith(":00:00") and not ts.endswith(":00:00"):
                    pass  # keep existing
                elif ts.endswith(":00:00") and not existing_ts.endswith(":00:00"):
                    hour_buckets[bucket] = e  # prefer new :00:00 entry
                # else keep whichever came first

        return sorted(hour_buckets.values(), key=lambda e: e.get("timestamp", ""))

    def get_forecast(self, days: int = 2) -> list[dict[str, Any]]:
        """Get forecast for the next N days."""
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        cutoff = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
        return [
            e for e in self._data["weather_forecast"]
            if now <= e.get("timestamp", "")[:19] <= cutoff
        ]

    def get_accumulated_rain_actual(self, days: int = 2) -> float:
        """Get total actual precipitation over last N days in mm."""
        history = self.get_weather_history(days)
        return sum(e.get("precip_actual_mm", 0.0) for e in history)

    def get_accumulated_rain_forecast(self, days: int = 2) -> float:
        """Get total forecast precipitation over next N days in mm."""
        forecast = self.get_forecast(days)
        return sum(e.get("precip_forecast_mm", 0.0) for e in forecast)

    async def async_prune_old_data(self, retention_days: int = 7) -> None:
        """Delete weather data older than retention_days."""
        cutoff = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%dT%H:%M:%S")
        cutoff_date = cutoff[:10]  # YYYY-MM-DD for backfilled_dates comparison

        future_cutoff = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
        before = len(self._data["weather_history"])
        self._data["weather_history"] = [
            e for e in self._data["weather_history"]
            if cutoff <= e.get("timestamp", "")[:19] <= future_cutoff
        ]
        after = len(self._data["weather_history"])

        # Prune backfilled_dates in sync so pruned dates can be re-fetched
        # if last_watered is ever set to a date that falls in their range again.
        self._data["backfilled_dates"] = [
            d for d in self._data.get("backfilled_dates", [])
            if d >= cutoff_date
        ]

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

    async def async_update_zone(
        self, zone_id: str, data: dict[str, Any], save: bool = True
    ) -> None:
        """Update stored data for a zone.

        Pass save=False when updating multiple zones in a loop to avoid
        writing the full JSON file once per zone; call async_save() manually
        after the loop.
        """
        if zone_id not in self._data["zones"]:
            self._data["zones"][zone_id] = {}
        self._data["zones"][zone_id].update(data)
        self._data["last_calculation"] = datetime.now().isoformat()
        if save:
            await self.async_save()
        _LOGGER.debug("Updated zone %s: bucket=%.1f%%", zone_id, data.get("bucket_percent", 0))

    async def async_record_watering(self, watered_at: str | None = None) -> None:
        """Record that watering happened, optionally at a custom timestamp."""
        if watered_at:
            # Normalize space-separated format from input_datetime to ISO format
            ts = watered_at.replace(" ", "T")
            try:
                datetime.fromisoformat(ts)
                self._data["last_watered"] = ts
            except ValueError:
                _LOGGER.warning("Invalid watered_at timestamp '%s', using now", watered_at)
                self._data["last_watered"] = datetime.now().isoformat()
        else:
            self._data["last_watered"] = datetime.now().isoformat()
        await self.async_save()
        _LOGGER.info("Recorded watering at %s", self._data["last_watered"])

    async def async_clear_last_watered(self) -> None:
        """Clear last watered timestamp (manual override baseline reset)."""
        self._data["last_watered"] = None
        await self.async_save()
        _LOGGER.info("Cleared last_watered baseline")

    async def async_reset_zone_bucket(self, zone_id: str, value: float = 0.0) -> None:
        """Reset a zone's bucket to a specific percentage."""
        if zone_id not in self._data["zones"]:
            self._data["zones"][zone_id] = {}
        self._data["zones"][zone_id]["bucket_percent"] = value
        await self.async_save()
        _LOGGER.info("Reset zone %s bucket to %.1f%%", zone_id, value)
