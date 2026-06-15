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
    CONF_MIN_WATERING_DURATION_MINUTES,
    CONF_RAIN_THRESHOLD_MM,
    CONF_RAIN_LIGHT_EFFECTIVENESS,
    CONF_FORECAST_CONFIDENCE,
    CONF_RAIN_ACCUMULATION_DAYS,
    CONF_ZONES,
    CONF_ZONE_NAME,
    CONF_ZONE_MAX_DURATION_MINUTES,
    CONF_ZONE_DURATION_MULTIPLIER,
    CONF_ZONE_SPRINKLER_RATE_IN_PER_HR,
    DEFAULT_RAINBIRD_DEBOUNCE_MINUTES,
    DEFAULT_MIN_WATERING_INTERVAL_HOURS,
    DEFAULT_MIN_WATERING_DURATION_MINUTES,
    DEFAULT_RAIN_THRESHOLD_MM,
    DEFAULT_RAIN_LIGHT_EFFECTIVENESS,
    DEFAULT_FORECAST_CONFIDENCE,
    DEFAULT_RAIN_ACCUMULATION_DAYS,
    DEFAULT_MAX_DURATION_MINUTES,
    DEFAULT_DURATION_MULTIPLIER,
    DEFAULT_SPRINKLER_RATE_IN_PER_HR,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities from config entry."""
    entities = [
        DebounceMinutesNumber(config_entry),
        MinWateringIntervalNumber(config_entry),
        MinWateringDurationNumber(config_entry),
        RainThresholdMMNumber(config_entry),
        RainLightEffectivenessNumber(config_entry),
        ForecastConfidenceNumber(config_entry),
        RainAccumulationDaysNumber(config_entry),
    ]

    # Add zone-specific config entities
    zones = config_entry.data.get(CONF_ZONES, [])
    for idx, zone_cfg in enumerate(zones):
        zone_id = f"zone_{idx + 1}"
        zone_name = zone_cfg.get(CONF_ZONE_NAME, f"Zone {idx + 1}")
        entities.append(ZoneMaxDurationNumber(config_entry, zone_id, zone_name, idx))
        entities.append(ZoneDurationMultiplierNumber(config_entry, zone_id, zone_name, idx))
        entities.append(ZoneSprinklerRateNumber(config_entry, zone_id, zone_name, idx))

    async_add_entities(entities)


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


class MinWateringDurationNumber(_BaseConfigNumber):
    """Number entity for minimum watering duration that triggers watering."""

    _attr_name = "Irrigation Planner Min Watering Duration"
    _attr_icon = "mdi:timer-check-outline"
    _attr_native_min_value = 0
    _attr_native_max_value = 60
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "min"

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize minimum duration slider."""
        super().__init__(config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_min_watering_duration_minutes"

    @property
    def native_value(self) -> float:
        """Return current minimum watering duration value."""
        return float(
            self._config_entry.data.get(
                CONF_MIN_WATERING_DURATION_MINUTES,
                DEFAULT_MIN_WATERING_DURATION_MINUTES,
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set minimum watering duration minutes."""
        minutes = int(value)
        _LOGGER.info("Setting minimum watering duration to %d minutes", minutes)
        await self._async_update_entry_value(CONF_MIN_WATERING_DURATION_MINUTES, minutes)


class RainThresholdMMNumber(_BaseConfigNumber):
    """Number entity for rain threshold (mm below which rain is less effective)."""

    _attr_name = "Irrigation Planner Rain Threshold"
    _attr_icon = "mdi:water-alert"
    _attr_native_min_value = 0
    _attr_native_max_value = 20
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = "mm"

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize rain threshold slider."""
        super().__init__(config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_rain_threshold_mm"

    @property
    def native_value(self) -> float:
        """Return current rain threshold value."""
        return float(
            self._config_entry.data.get(
                CONF_RAIN_THRESHOLD_MM,
                DEFAULT_RAIN_THRESHOLD_MM,
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set rain threshold mm."""
        mm = round(float(value), 1)
        _LOGGER.info("Setting rain threshold to %.1f mm", mm)
        await self._async_update_entry_value(CONF_RAIN_THRESHOLD_MM, mm)


class RainLightEffectivenessNumber(_BaseConfigNumber):
    """Number entity for light rain effectiveness percentage."""

    _attr_name = "Irrigation Planner Light Rain Effectiveness"
    _attr_icon = "mdi:water-percent"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 5
    _attr_native_unit_of_measurement = "%"

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize light rain effectiveness slider."""
        super().__init__(config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_rain_light_effectiveness"

    @property
    def native_value(self) -> float:
        """Return current light rain effectiveness value."""
        return float(
            self._config_entry.data.get(
                CONF_RAIN_LIGHT_EFFECTIVENESS,
                DEFAULT_RAIN_LIGHT_EFFECTIVENESS,
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set light rain effectiveness percent."""
        pct = int(value)
        _LOGGER.info("Setting light rain effectiveness to %d%%", pct)
        await self._async_update_entry_value(CONF_RAIN_LIGHT_EFFECTIVENESS, pct)


class ForecastConfidenceNumber(_BaseConfigNumber):
    """Number entity for forecast rain confidence percentage."""

    _attr_name = "Irrigation Planner Forecast Confidence"
    _attr_icon = "mdi:cloud-percent"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 5
    _attr_native_unit_of_measurement = "%"

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize forecast confidence slider."""
        super().__init__(config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_forecast_confidence"

    @property
    def native_value(self) -> float:
        """Return current forecast confidence value."""
        return float(
            self._config_entry.data.get(
                CONF_FORECAST_CONFIDENCE,
                DEFAULT_FORECAST_CONFIDENCE,
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set forecast confidence percent."""
        pct = int(value)
        _LOGGER.info("Setting forecast confidence to %d%%", pct)
        await self._async_update_entry_value(CONF_FORECAST_CONFIDENCE, pct)


class RainAccumulationDaysNumber(_BaseConfigNumber):
    """Number entity for rain accumulation days used in calculations."""

    _attr_name = "Irrigation Planner Rain Accumulation Days"
    _attr_icon = "mdi:water-check"
    _attr_native_min_value = 1
    _attr_native_max_value = 14
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "days"

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize rain accumulation days slider."""
        super().__init__(config_entry)
        self._attr_unique_id = f"{config_entry.entry_id}_rain_accumulation_days"

    @property
    def native_value(self) -> float:
        """Return current rain accumulation days value."""
        return float(
            self._config_entry.data.get(
                CONF_RAIN_ACCUMULATION_DAYS,
                DEFAULT_RAIN_ACCUMULATION_DAYS,
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set rain accumulation days."""
        days = int(value)
        _LOGGER.info("Setting rain accumulation days to %d", days)
        await self._async_update_entry_value(CONF_RAIN_ACCUMULATION_DAYS, days)


class _BaseZoneConfigNumber(NumberEntity):
    """Base class for zone-specific config number entities."""

    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        config_entry: ConfigEntry,
        zone_id: str,
        zone_name: str,
        zone_idx: int,
    ) -> None:
        """Initialize zone config number."""
        self._config_entry = config_entry
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._zone_idx = zone_idx

    @property
    def available(self) -> bool:
        """Return entity availability."""
        return True

    def _get_zone_config(self) -> dict:
        """Get current zone config dict."""
        zones = self._config_entry.data.get(CONF_ZONES, [])
        if self._zone_idx < len(zones):
            return dict(zones[self._zone_idx])
        return {}

    async def _async_update_zone_value(self, key: str, value: Any) -> None:
        """Persist value to zone config and update coordinator."""
        hass = self.hass
        if hass is None:
            return

        # Get current zones list
        data = dict(self._config_entry.data)
        zones = list(data.get(CONF_ZONES, []))

        if self._zone_idx < len(zones):
            # Update specific zone
            zone_cfg = dict(zones[self._zone_idx])
            zone_cfg[key] = value
            zones[self._zone_idx] = zone_cfg
            data[CONF_ZONES] = zones

            # Save config entry
            hass.config_entries.async_update_entry(self._config_entry, data=data)

            # Update coordinator
            domain_data = hass.data.get(DOMAIN, {})
            entry_data = domain_data.get(self._config_entry.entry_id)
            if entry_data:
                coordinator = entry_data.get("coordinator")
                if coordinator:
                    coordinator._config = data
                    await coordinator._async_update_data_from_store()


class ZoneMaxDurationNumber(_BaseZoneConfigNumber):
    """Number entity for zone max duration minutes."""

    _attr_icon = "mdi:timer"
    _attr_native_min_value = 1
    _attr_native_max_value = 60
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "min"

    def __init__(
        self,
        config_entry: ConfigEntry,
        zone_id: str,
        zone_name: str,
        zone_idx: int,
    ) -> None:
        """Initialize zone max duration slider."""
        super().__init__(config_entry, zone_id, zone_name, zone_idx)
        self._attr_unique_id = f"{config_entry.entry_id}_{zone_id}_max_duration"
        self._attr_name = f"Irrigation {zone_name} Max Duration"

    @property
    def native_value(self) -> float:
        """Return current max duration value."""
        zone_cfg = self._get_zone_config()
        return float(
            zone_cfg.get(CONF_ZONE_MAX_DURATION_MINUTES, DEFAULT_MAX_DURATION_MINUTES)
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set zone max duration minutes."""
        minutes = int(value)
        _LOGGER.info("Setting %s max duration to %d minutes", self._zone_id, minutes)
        await self._async_update_zone_value(CONF_ZONE_MAX_DURATION_MINUTES, minutes)


class ZoneDurationMultiplierNumber(_BaseZoneConfigNumber):
    """Number entity for zone duration multiplier."""

    _attr_icon = "mdi:multiplication"
    _attr_native_min_value = 0.1
    _attr_native_max_value = 3.0
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = "x"

    def __init__(
        self,
        config_entry: ConfigEntry,
        zone_id: str,
        zone_name: str,
        zone_idx: int,
    ) -> None:
        """Initialize zone duration multiplier slider."""
        super().__init__(config_entry, zone_id, zone_name, zone_idx)
        self._attr_unique_id = f"{config_entry.entry_id}_{zone_id}_duration_multiplier"
        self._attr_name = f"Irrigation {zone_name} Duration Multiplier"

    @property
    def native_value(self) -> float:
        """Return current duration multiplier value."""
        zone_cfg = self._get_zone_config()
        return float(
            zone_cfg.get(CONF_ZONE_DURATION_MULTIPLIER, DEFAULT_DURATION_MULTIPLIER)
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set zone duration multiplier."""
        mult = round(float(value), 1)
        _LOGGER.info("Setting %s duration multiplier to %.1f", self._zone_id, mult)
        await self._async_update_zone_value(CONF_ZONE_DURATION_MULTIPLIER, mult)


class ZoneSprinklerRateNumber(_BaseZoneConfigNumber):
    """Number entity for zone sprinkler rate."""

    _attr_icon = "mdi:sprinkler"
    _attr_native_min_value = 0.1
    _attr_native_max_value = 5.0
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = "in/hr"

    def __init__(
        self,
        config_entry: ConfigEntry,
        zone_id: str,
        zone_name: str,
        zone_idx: int,
    ) -> None:
        """Initialize zone sprinkler rate slider."""
        super().__init__(config_entry, zone_id, zone_name, zone_idx)
        self._attr_unique_id = f"{config_entry.entry_id}_{zone_id}_sprinkler_rate"
        self._attr_name = f"Irrigation {zone_name} Sprinkler Rate"

    @property
    def native_value(self) -> float:
        """Return current sprinkler rate value."""
        zone_cfg = self._get_zone_config()
        return float(
            zone_cfg.get(CONF_ZONE_SPRINKLER_RATE_IN_PER_HR, DEFAULT_SPRINKLER_RATE_IN_PER_HR)
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set zone sprinkler rate."""
        rate = round(float(value), 1)
        _LOGGER.info("Setting %s sprinkler rate to %.1f in/hr", self._zone_id, rate)
        await self._async_update_zone_value(CONF_ZONE_SPRINKLER_RATE_IN_PER_HR, rate)
