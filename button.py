"""Button platform for Irrigation Planner."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up buttons from a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    async_add_entities([
        CalculateButton(coordinator, config_entry),
        RefreshWeatherButton(coordinator, config_entry),
        ResetBucketsButton(coordinator, config_entry),
    ])


class CalculateButton(ButtonEntity):
    """Button to trigger irrigation calculation."""

    def __init__(self, coordinator, config_entry):
        """Initialize."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{config_entry.entry_id}_calculate"
        self._attr_name = "Irrigation Planner Calculate"
        self._attr_icon = "mdi:calculator"

    async def async_press(self) -> None:
        """Handle button press."""
        _LOGGER.info("Calculate button pressed")
        await self._coordinator.async_calculate()


class RefreshWeatherButton(ButtonEntity):
    """Button to refresh weather data."""

    def __init__(self, coordinator, config_entry):
        """Initialize."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{config_entry.entry_id}_refresh_weather"
        self._attr_name = "Irrigation Planner Refresh Weather"
        self._attr_icon = "mdi:cloud-refresh"

    async def async_press(self) -> None:
        """Handle button press."""
        _LOGGER.info("Refresh weather button pressed")
        await self._coordinator.async_refresh_weather()


class ResetBucketsButton(ButtonEntity):
    """Button to reset all zone buckets to 0% (needs watering)."""

    def __init__(self, coordinator, config_entry):
        """Initialize."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{config_entry.entry_id}_reset_buckets"
        self._attr_name = "Irrigation Planner Reset Buckets"
        self._attr_icon = "mdi:restart"

    async def async_press(self) -> None:
        """Handle button press."""
        _LOGGER.info("Reset buckets button pressed")
        await self._coordinator.async_reset_all_buckets()
