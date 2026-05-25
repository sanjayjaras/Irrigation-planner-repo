"""Number platform for Irrigation Planner runtime-configurable settings."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_RAINBIRD_DEBOUNCE_MINUTES,
    CONF_MIN_WATERING_INTERVAL_HOURS,
    DEFAULT_RAINBIRD_DEBOUNCE_MINUTES,
    DEFAULT_MIN_WATERING_INTERVAL_HOURS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities from config entry."""
    async_add_entities(
        [
            DebounceMinutesNumber(config_entry),
            MinWateringIntervalNumber(config_entry),
        ]
    )


class _BaseConfigNumber(NumberEntity):
    """Base class for number entities backed by config entry data."""

    _attr_mode = NumberMode.SLIDER

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize base settings number."""
        self._config_entry = config_entry

    @property
    def available(self) -> bool:
        """Return entity availability."""
        return True

    async def _async_update_entry_value(self, key: str, value: Any) -> None:
        """Persist value to config entry and update coordinators."""
        hass = self.hass
        if hass is None:
            return

        data = dict(self._config_entry.data)
        data[key] = value
        hass.config_entries.async_update_entry(self._config_entry, data=data)

        domain_data = hass.data.get(DOMAIN, {})
        entry_data = domain_data.get(self._config_entry.entry_id)
        if entry_data:
            coordinator = entry_data.get("coordinator")
            if coordinator:
                coordinator._config = data
                await coordinator._async_update_data_from_store()


class DebounceMinutesNumber(_BaseConfigNumber):
    """Number entity for Rainbird debounce minutes."""

    _attr_name = "Irrigation Planner Rainbird Debounce"
    _attr_icon = "mdi:timer-sand"
    _attr_native_min_value = 1
    _attr_native_max_value = 60
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "min"

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize debounce slider."""
        super().__init__(config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_rainbird_debounce_minutes"

    @property
    def native_value(self) -> float:
        """Return current debounce value."""
        return float(
            self._config_entry.data.get(
                CONF_RAINBIRD_DEBOUNCE_MINUTES,
                DEFAULT_RAINBIRD_DEBOUNCE_MINUTES,
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set debounce minutes."""
        minutes = int(value)
        _LOGGER.info("Setting Rainbird debounce to %d minutes", minutes)
        await self._async_update_entry_value(CONF_RAINBIRD_DEBOUNCE_MINUTES, minutes)


class MinWateringIntervalNumber(_BaseConfigNumber):
    """Number entity for minimum watering interval hours."""

    _attr_name = "Irrigation Planner Min Watering Interval"
    _attr_icon = "mdi:av-timer"
    _attr_native_min_value = 0
    _attr_native_max_value = 168
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "h"

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize minimum interval slider."""
        super().__init__(config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_min_watering_interval_hours"

    @property
    def native_value(self) -> float:
        """Return current minimum interval value."""
        return float(
            self._config_entry.data.get(
                CONF_MIN_WATERING_INTERVAL_HOURS,
                DEFAULT_MIN_WATERING_INTERVAL_HOURS,
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set minimum watering interval hours."""
        hours = int(value)
        _LOGGER.info("Setting minimum watering interval to %d hours", hours)
        await self._async_update_entry_value(CONF_MIN_WATERING_INTERVAL_HOURS, hours)
