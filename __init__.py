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

    unsub_update_listener = entry.add_update_listener(_async_entry_updated)

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "unsub_update_listener": unsub_update_listener,
    }

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    await _async_register_services(hass)

    _LOGGER.info("Irrigation Planner setup complete")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id, None)
        if data:
            unsub_update_listener = data.get("unsub_update_listener")
            if unsub_update_listener:
                unsub_update_listener()
            coordinator = data["coordinator"]
            await coordinator.async_shutdown()

        if not hass.data[DOMAIN]:
            _async_unregister_services(hass)

    return unload_ok


async def _async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when config entry data changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_services(
    hass: HomeAssistant,
) -> None:
    """Register services for Irrigation Planner."""

    def _resolve_coordinators(call: ServiceCall) -> list[IrrigationPlannerCoordinator]:
        """Resolve target coordinators for a service call."""
        entry_id = call.data.get("entry_id")
        domain_data = hass.data.get(DOMAIN, {})

        if entry_id:
            entry_data = domain_data.get(entry_id)
            if not entry_data or "coordinator" not in entry_data:
                _LOGGER.warning(
                    "Service call for unknown irrigation_planner entry_id=%s",
                    entry_id,
                )
                return []
            return [entry_data["coordinator"]]

        return [
            entry_data["coordinator"]
            for entry_data in domain_data.values()
            if "coordinator" in entry_data
        ]

    async def handle_calculate(call: ServiceCall) -> None:
        """Handle calculate service call."""
        coordinators = _resolve_coordinators(call)
        for coordinator in coordinators:
            await coordinator.async_calculate()

    async def handle_refresh_weather(call: ServiceCall) -> None:
        """Handle refresh weather service call."""
        coordinators = _resolve_coordinators(call)
        for coordinator in coordinators:
            await coordinator.async_refresh_weather()

    async def handle_reset_bucket(call: ServiceCall) -> None:
        """Handle reset bucket service call."""
        value = call.data.get("value", 0.0)
        coordinators = _resolve_coordinators(call)
        for coordinator in coordinators:
            await coordinator.async_reset_all_buckets(value)

    if not hass.services.has_service(DOMAIN, SERVICE_CALCULATE):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CALCULATE,
            handle_calculate,
            schema=vol.Schema({
                vol.Optional("entry_id"): cv.string,
            }),
        )

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH_WEATHER):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH_WEATHER,
            handle_refresh_weather,
            schema=vol.Schema({
                vol.Optional("entry_id"): cv.string,
            }),
        )

    if not hass.services.has_service(DOMAIN, SERVICE_RESET_BUCKET):
        hass.services.async_register(
            DOMAIN,
            SERVICE_RESET_BUCKET,
            handle_reset_bucket,
            schema=vol.Schema({
                vol.Optional("entry_id"): cv.string,
                vol.Optional("value", default=0.0): vol.Coerce(float),
            }),
        )

    async def handle_mark_watered(call: ServiceCall) -> None:
        """Handle mark watered service call."""
        coordinators = _resolve_coordinators(call)
        for coordinator in coordinators:
            await coordinator.async_mark_watered()

    if not hass.services.has_service(DOMAIN, "mark_watered"):
        hass.services.async_register(
            DOMAIN,
            "mark_watered",
            handle_mark_watered,
            schema=vol.Schema({
                vol.Optional("entry_id"): cv.string,
            }),
        )


def _async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister domain services when no entries remain."""
    for service in (
        SERVICE_CALCULATE,
        SERVICE_REFRESH_WEATHER,
        SERVICE_RESET_BUCKET,
        "mark_watered",
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
