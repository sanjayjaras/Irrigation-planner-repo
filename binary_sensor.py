"""Binary sensor platform for Irrigation Planner."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_MAX_WEATHER_STALENESS_HOURS,
    DEFAULT_MAX_WEATHER_STALENESS_HOURS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors from a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    async_add_entities([WeatherDataStaleBinarySensor(coordinator, config_entry)])


class WeatherDataStaleBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Problem sensor: on when weather data hasn't refreshed recently.

    Surfaces the same staleness condition the coordinator uses internally to
    withhold watering, so a dashboard/automation can alert a human instead of
    the outage staying silent (e.g. a network/DNS failure that blocks the
    weather provider for days).
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_weather_data_stale"
        self._attr_name = "Irrigation Planner Weather Data Stale"

    def _staleness_hours(self) -> float | None:
        if self.coordinator.data is None:
            return None
        last_update = self.coordinator.data.get("last_weather_update")
        if not last_update:
            return None
        try:
            last_dt = datetime.fromisoformat(last_update)
        except (ValueError, TypeError):
            return None
        return (datetime.now() - last_dt).total_seconds() / 3600

    @property
    def is_on(self) -> bool | None:
        """Return True if weather data is older than the configured threshold."""
        staleness_hours = self._staleness_hours()
        if staleness_hours is None:
            # No data ever received yet — not "stale", just not started.
            return None
        max_staleness_hours = self._config_entry.data.get(
            CONF_MAX_WEATHER_STALENESS_HOURS, DEFAULT_MAX_WEATHER_STALENESS_HOURS
        )
        return staleness_hours > max_staleness_hours

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return staleness details."""
        staleness_hours = self._staleness_hours()
        return {
            "staleness_hours": round(staleness_hours, 2) if staleness_hours is not None else None,
            "max_staleness_hours": self._config_entry.data.get(
                CONF_MAX_WEATHER_STALENESS_HOURS, DEFAULT_MAX_WEATHER_STALENESS_HOURS
            ),
            "last_weather_update": (
                self.coordinator.data.get("last_weather_update") if self.coordinator.data else None
            ),
        }

    @property
    def icon(self) -> str:
        """Return icon."""
        return "mdi:weather-cloudy-alert" if self.is_on else "mdi:weather-partly-cloudy"
