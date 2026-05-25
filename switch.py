"""Switch platform for Irrigation Planner runtime-configurable toggles."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_AUTO_CALCULATE_ON_WEATHER_UPDATE,
    DEFAULT_AUTO_CALCULATE_ON_WEATHER_UPDATE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities from config entry."""
    async_add_entities([AutoCalculateOnWeatherUpdateSwitch(config_entry)])


class AutoCalculateOnWeatherUpdateSwitch(SwitchEntity):
    """Toggle auto-calculate whenever weather refresh runs."""

    _attr_name = "Irrigation Planner Auto Calculate on Weather Update"
    _attr_icon = "mdi:autorenew"

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize auto-calculate switch."""
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}_auto_calculate_on_weather_update"

    @property
    def is_on(self) -> bool:
        """Return current toggle state."""
        return bool(
            self._config_entry.data.get(
                CONF_AUTO_CALCULATE_ON_WEATHER_UPDATE,
                DEFAULT_AUTO_CALCULATE_ON_WEATHER_UPDATE,
            )
        )

    async def _async_update_entry_value(self, value: Any) -> None:
        """Persist value to config entry and refresh coordinator data."""
        hass = self.hass
        if hass is None:
            return

        data = dict(self._config_entry.data)
        data[CONF_AUTO_CALCULATE_ON_WEATHER_UPDATE] = value
        hass.config_entries.async_update_entry(self._config_entry, data=data)

        domain_data = hass.data.get(DOMAIN, {})
        entry_data = domain_data.get(self._config_entry.entry_id)
        if entry_data:
            coordinator = entry_data.get("coordinator")
            if coordinator:
                coordinator._config = data
                await coordinator._async_update_data_from_store()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on auto-calculate."""
        _LOGGER.info("Enabling auto-calculate on weather update")
        await self._async_update_entry_value(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off auto-calculate."""
        _LOGGER.info("Disabling auto-calculate on weather update")
        await self._async_update_entry_value(False)
