"""Select platform for Irrigation Planner zone settings."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_ZONES,
    CONF_ZONE_NAME,
    CONF_ZONE_SUN_EXPOSURE,
    CONF_ZONE_SOIL_TYPE,
    CONF_ZONE_PLANT_TYPE,
    SUN_FULL,
    SOIL_LOAM,
    PLANT_GRASS,
    SUN_EXPOSURE_OPTIONS,
    SOIL_TYPE_OPTIONS,
    PLANT_TYPE_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities from a config entry."""
    zones = config_entry.data.get(CONF_ZONES, [])
    entities = []
    for idx, zone_cfg in enumerate(zones):
        zone_id = f"zone_{idx + 1}"
        zone_name = zone_cfg.get(CONF_ZONE_NAME, f"Zone {idx + 1}")
        entities.append(ZoneSunExposureSelect(config_entry, zone_id, zone_name, idx))
        entities.append(ZoneSoilTypeSelect(config_entry, zone_id, zone_name, idx))
        entities.append(ZonePlantTypeSelect(config_entry, zone_id, zone_name, idx))

    async_add_entities(entities)


class _BaseZoneConfigSelect(SelectEntity):
    """Base class for zone config select entities."""

    _attr_should_poll = False

    def __init__(
        self,
        config_entry: ConfigEntry,
        zone_id: str,
        zone_name: str,
        zone_idx: int,
    ) -> None:
        """Initialize zone config select."""
        self._config_entry = config_entry
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._zone_idx = zone_idx
        self._options_map: dict[str, str] = {}
        self._config_key: str = ""
        self._default_key: str = ""

    def _get_zone_config(self) -> dict:
        """Return current zone config dict from config entry data."""
        zones = self._config_entry.data.get(CONF_ZONES, [])
        if self._zone_idx < len(zones):
            return dict(zones[self._zone_idx])
        return {}

    async def _async_update_zone_value(self, key: str, value: Any) -> None:
        """Persist value to zone config and update coordinator."""
        hass = self.hass
        if hass is None:
            return

        data = dict(self._config_entry.data)
        zones = list(data.get(CONF_ZONES, []))

        if self._zone_idx < len(zones):
            zone_cfg = dict(zones[self._zone_idx])
            zone_cfg[key] = value
            zones[self._zone_idx] = zone_cfg
            data[CONF_ZONES] = zones

            hass.config_entries.async_update_entry(self._config_entry, data=data)

            domain_data = hass.data.get(DOMAIN, {})
            entry_data = domain_data.get(self._config_entry.entry_id)
            if entry_data:
                coordinator = entry_data.get("coordinator")
                if coordinator:
                    coordinator._config = data
                    await coordinator.async_calculate(ignore_irrigation_window=True)

    def _key_from_label(self, label: str) -> str:
        """Map a display label back to the stored config key."""
        for key, value in self._options_map.items():
            if value == label:
                return key
        return label

    @property
    def current_option(self) -> str | None:
        """Return the current selected label."""
        zone_cfg = self._get_zone_config()
        key = zone_cfg.get(self._config_key, self._default_key)
        return self._options_map.get(key, key)

    async def async_select_option(self, option: str) -> None:
        """Handle user selection."""
        key = self._key_from_label(option)
        _LOGGER.info(
            "Setting %s %s to %s (%s)",
            self._zone_id,
            self._config_key,
            key,
            option,
        )
        await self._async_update_zone_value(self._config_key, key)
        self.async_write_ha_state()


class ZoneSunExposureSelect(_BaseZoneConfigSelect):
    """Select entity for zone sun exposure."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        zone_id: str,
        zone_name: str,
        zone_idx: int,
    ) -> None:
        """Initialize sun exposure select."""
        super().__init__(config_entry, zone_id, zone_name, zone_idx)
        self._attr_unique_id = f"{config_entry.entry_id}_{zone_id}_sun_exposure"
        self._attr_name = f"Irrigation {zone_name} Sun Exposure"
        self._options_map = SUN_EXPOSURE_OPTIONS
        self._config_key = CONF_ZONE_SUN_EXPOSURE
        self._default_key = SUN_FULL
        self._attr_options = list(SUN_EXPOSURE_OPTIONS.values())


class ZoneSoilTypeSelect(_BaseZoneConfigSelect):
    """Select entity for zone soil type."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        zone_id: str,
        zone_name: str,
        zone_idx: int,
    ) -> None:
        """Initialize soil type select."""
        super().__init__(config_entry, zone_id, zone_name, zone_idx)
        self._attr_unique_id = f"{config_entry.entry_id}_{zone_id}_soil_type"
        self._attr_name = f"Irrigation {zone_name} Soil Type"
        self._options_map = SOIL_TYPE_OPTIONS
        self._config_key = CONF_ZONE_SOIL_TYPE
        self._default_key = SOIL_LOAM
        self._attr_options = list(SOIL_TYPE_OPTIONS.values())


class ZonePlantTypeSelect(_BaseZoneConfigSelect):
    """Select entity for zone plant type."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        zone_id: str,
        zone_name: str,
        zone_idx: int,
    ) -> None:
        """Initialize plant type select."""
        super().__init__(config_entry, zone_id, zone_name, zone_idx)
        self._attr_unique_id = f"{config_entry.entry_id}_{zone_id}_plant_type"
        self._attr_name = f"Irrigation {zone_name} Plant Type"
        self._options_map = PLANT_TYPE_OPTIONS
        self._config_key = CONF_ZONE_PLANT_TYPE
        self._default_key = PLANT_GRASS
        self._attr_options = list(PLANT_TYPE_OPTIONS.values())
