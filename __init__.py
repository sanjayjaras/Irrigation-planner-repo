"""Irrigation Planner - Smart irrigation duration calculator for Home Assistant.

Calculates watering durations based on weather data, soil conditions,
and zone characteristics with full transparency.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    PLATFORMS,
    SERVICE_CALCULATE,
    SERVICE_REFRESH_WEATHER,
    SERVICE_RESET_BUCKET,
)
from .coordinator import IrrigationPlannerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Irrigation Planner from YAML (not used, config flow only)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Irrigation Planner from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = IrrigationPlannerCoordinator(hass, entry)
    await coordinator.async_setup()

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
    }

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    await _async_register_services(hass, coordinator)

    _LOGGER.info("Irrigation Planner setup complete")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id, None)
        if data:
            coordinator = data["coordinator"]
            await coordinator.async_shutdown()

    return unload_ok


async def _async_register_services(
    hass: HomeAssistant, coordinator: IrrigationPlannerCoordinator
) -> None:
    """Register services for Irrigation Planner."""

    async def handle_calculate(call: ServiceCall) -> None:
        """Handle calculate service call."""
        await coordinator.async_calculate()

    async def handle_refresh_weather(call: ServiceCall) -> None:
        """Handle refresh weather service call."""
        await coordinator.async_refresh_weather()

    async def handle_reset_bucket(call: ServiceCall) -> None:
        """Handle reset bucket service call."""
        value = call.data.get("value", 0.0)
        await coordinator.async_reset_all_buckets(value)

    if not hass.services.has_service(DOMAIN, SERVICE_CALCULATE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CALCULATE,
            handle_calculate,
            schema=vol.Schema({}),
        )

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_WEATHER):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH_WEATHER,
            handle_refresh_weather,
            schema=vol.Schema({}),
        )

    if not hass.services.has_service(DOMAIN, SERVICE_RESET_BUCKET):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RESET_BUCKET,
            handle_reset_bucket,
            schema=vol.Schema({
                vol.Optional("value", default=0.0): vol.Coerce(float),
            }),
        )

    async def handle_mark_watered(call: ServiceCall) -> None:
        """Handle mark watered service call."""
        await coordinator.async_mark_watered()

    if not hass.services.has_service(DOMAIN, "mark_watered"):
        hass.services.async_register(
            DOMAIN,
            "mark_watered",
            handle_mark_watered,
            schema=vol.Schema({}),
        )
