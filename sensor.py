"""Sensor platform for Irrigation Planner."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_ZONES,
    CONF_ZONE_NAME,
    CONF_ZONE_SUN_EXPOSURE,
    CONF_ZONE_SOIL_TYPE,
    CONF_ZONE_PLANT_TYPE,
    CONF_ZONE_AREA_SQFT,
    CONF_ZONE_SPRINKLER_RATE_IN_PER_HR,
    CONF_ZONE_RAINBIRD_ZONE,
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
    """Set up sensors from a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    zones = config_entry.data.get(CONF_ZONES, [])

    entities = []
    for idx, zone in enumerate(zones):
        zone_id = f"zone_{idx + 1}"
        zone_name = zone.get(CONF_ZONE_NAME, f"Zone {idx + 1}")

        entities.append(ZoneDurationSensor(coordinator, zone_id, zone_name, zone, config_entry))
        entities.append(ZoneBucketSensor(coordinator, zone_id, zone_name, zone, config_entry))
        entities.append(ZoneBreakdownSensor(coordinator, zone_id, zone_name, zone, config_entry))

    # Weather status sensor
    entities.append(WeatherStatusSensor(coordinator, config_entry))
    entities.append(IrrigationLogSensor(coordinator, config_entry))

    async_add_entities(entities)


class ZoneDurationSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing irrigation duration in minutes for a zone."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, zone_id, zone_name, zone_config, config_entry):
        """Initialize."""
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._zone_config = zone_config
        self._attr_unique_id = f"{config_entry.entry_id}_{zone_id}_duration"
        self._attr_name = f"Irrigation {zone_name} Duration"

    @property
    def native_value(self) -> float | None:
        """Return duration in minutes."""
        if self.coordinator.data is None:
            return None
        zone_data = self.coordinator.data.get("zones", {}).get(self._zone_id)
        if zone_data is None:
            return None
        return zone_data.get("duration_minutes", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return calculation details."""
        if self.coordinator.data is None:
            return {}
        zone_data = self.coordinator.data.get("zones", {}).get(self._zone_id, {})
        return {
            "last_calculated": zone_data.get("last_calculated"),
            "bucket_percent": zone_data.get("bucket_percent"),
            "et_inches": zone_data.get("et_inches"),
            "rain_actual_inches": zone_data.get("rain_actual_inches"),
            "rain_forecast_inches": zone_data.get("rain_forecast_inches"),
            "pre_forecast_duration_minutes": zone_data.get("pre_forecast_duration_minutes"),
            "forecast_duration_offset_minutes": zone_data.get("forecast_duration_offset_minutes"),
            "net_change_inches": zone_data.get("net_change_inches"),
            "cooldown_active": zone_data.get("cooldown_active", False),
            "cooldown_remaining_hours": zone_data.get("cooldown_remaining_hours"),
            "explanation": zone_data.get("explanation"),
        }

    @property
    def icon(self) -> str:
        """Return icon."""
        value = self.native_value
        if value and value > 0:
            return "mdi:sprinkler-variant"
        return "mdi:sprinkler"


class ZoneBucketSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing bucket percentage for a zone."""

    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, zone_id, zone_name, zone_config, config_entry):
        """Initialize."""
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._zone_config = zone_config
        self._attr_unique_id = f"{config_entry.entry_id}_{zone_id}_bucket"
        self._attr_name = f"Irrigation {zone_name} Bucket"

    @property
    def native_value(self) -> float | None:
        """Return bucket percentage."""
        if self.coordinator.data is None:
            return None
        zone_data = self.coordinator.data.get("zones", {}).get(self._zone_id)
        if zone_data is None:
            return None
        return zone_data.get("bucket_percent", 0.0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return factor breakdown."""
        # Config-based attributes always available
        sun_key = self._zone_config.get(CONF_ZONE_SUN_EXPOSURE, "")
        soil_key = self._zone_config.get(CONF_ZONE_SOIL_TYPE, "")
        plant_key = self._zone_config.get(CONF_ZONE_PLANT_TYPE, "")
        attrs = {
            "sun_exposure": SUN_EXPOSURE_OPTIONS.get(sun_key, sun_key),
            "soil_type": SOIL_TYPE_OPTIONS.get(soil_key, soil_key),
            "plant_type": PLANT_TYPE_OPTIONS.get(plant_key, plant_key),
            "area_sqft": self._zone_config.get(CONF_ZONE_AREA_SQFT),
            "sprinkler_rate_in_per_hr": self._zone_config.get(CONF_ZONE_SPRINKLER_RATE_IN_PER_HR),
            "rainbird_zone": self._zone_config.get(CONF_ZONE_RAINBIRD_ZONE),
        }
        # Calculation-based attributes (populated after calc)
        if self.coordinator.data is not None:
            zone_data = self.coordinator.data.get("zones", {}).get(self._zone_id, {})
            factors = zone_data.get("factors", {})
            attrs.update({
                "old_bucket_percent": zone_data.get("old_bucket_percent"),
                "net_change_percent": zone_data.get("net_change_percent"),
                "factor_et": factors.get("evapotranspiration"),
                "factor_rain_actual": factors.get("rain_actual"),
                "factor_rain_forecast": factors.get("rain_forecast"),
                "factor_drainage": factors.get("drainage"),
            })
        return attrs

    @property
    def icon(self) -> str:
        """Return icon based on level."""
        value = self.native_value or 0
        if value >= 75:
            return "mdi:water"
        if value >= 25:
            return "mdi:water-outline"
        return "mdi:water-off"


class ZoneBreakdownSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing detailed factor breakdown for a zone."""

    def __init__(self, coordinator, zone_id, zone_name, zone_config, config_entry):
        """Initialize."""
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._zone_config = zone_config
        self._attr_unique_id = f"{config_entry.entry_id}_{zone_id}_breakdown"
        self._attr_name = f"Irrigation {zone_name} Breakdown"

    @property
    def native_value(self) -> str | None:
        """Return summary string."""
        if self.coordinator.data is None:
            return None
        zone_data = self.coordinator.data.get("zones", {}).get(self._zone_id, {})
        bucket = zone_data.get("bucket_percent", 0)
        duration = zone_data.get("duration_minutes", 0)
        if duration > 0:
            return f"Bucket {bucket}% | Water {duration}min"
        return f"Bucket {bucket}% | No water needed"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return full calculation details."""
        if self.coordinator.data is None:
            return {}
        zone_data = self.coordinator.data.get("zones", {}).get(self._zone_id, {})
        return {
            "bucket_percent": zone_data.get("bucket_percent"),
            "old_bucket_percent": zone_data.get("old_bucket_percent"),
            "duration_minutes": zone_data.get("duration_minutes"),
            "pre_forecast_duration_minutes": zone_data.get("pre_forecast_duration_minutes"),
            "forecast_duration_offset_minutes": zone_data.get("forecast_duration_offset_minutes"),
            "et_inches": zone_data.get("et_inches"),
            "et_mm": zone_data.get("et_mm"),
            "rain_actual_inches": zone_data.get("rain_actual_inches"),
            "rain_actual_mm": zone_data.get("rain_actual_mm"),
            "rain_forecast_inches": zone_data.get("rain_forecast_inches"),
            "rain_forecast_mm": zone_data.get("rain_forecast_mm"),
            "drainage_inches": zone_data.get("drainage_inches"),
            "net_change_inches": zone_data.get("net_change_inches"),
            "net_change_percent": zone_data.get("net_change_percent"),
            "hours_of_data": zone_data.get("hours_of_data"),
            "factors": zone_data.get("factors"),
            "weather_summary": zone_data.get("weather_summary"),
            "explanation": zone_data.get("explanation"),
        }

    @property
    def icon(self) -> str:
        return "mdi:chart-bar"


class WeatherStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing weather data collection status."""

    def __init__(self, coordinator, config_entry):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{config_entry.entry_id}_weather_status"
        self._attr_name = "Irrigation Planner Weather"

    @property
    def native_value(self) -> str | None:
        """Return last weather update time."""
        if self.coordinator.data is None:
            return "No data"
        return self.coordinator.data.get("last_weather_update", "No data")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return weather data stats."""
        if self.coordinator.data is None:
            return {}
        return {
            "calc_time": self.coordinator.data.get("calc_time"),
            "update_interval_minutes": self.coordinator.data.get("update_interval_minutes"),
            "data_retention_days": self.coordinator.data.get("data_retention_days"),
            "rainbird_debounce_minutes": self.coordinator.data.get("rainbird_debounce_minutes"),
            "min_watering_interval_hours": self.coordinator.data.get("min_watering_interval_hours"),
            "auto_calculate_on_weather_update": self.coordinator.data.get("auto_calculate_on_weather_update"),
            "rain_threshold_mm": self.coordinator.data.get("rain_threshold_mm"),
            "rain_light_effectiveness": self.coordinator.data.get("rain_light_effectiveness"),
            "forecast_confidence": self.coordinator.data.get("forecast_confidence"),
            "current_temp_c": self.coordinator.data.get("current_temp_c"),
            "current_humidity": self.coordinator.data.get("current_humidity"),
            "current_wind_speed_ms": self.coordinator.data.get("current_wind_speed_ms"),
            "current_dew_point_c": self.coordinator.data.get("current_dew_point_c"),
            "current_pressure_hpa": self.coordinator.data.get("current_pressure_hpa"),
            "current_uv_index": self.coordinator.data.get("current_uv_index"),
            "current_clouds_pct": self.coordinator.data.get("current_clouds_pct"),
            "conditions_source": self.coordinator.data.get("conditions_source"),
            "conditions_observed_at": self.coordinator.data.get("conditions_observed_at"),
            "history_entries": self.coordinator.data.get("history_entries", 0),
            "forecast_entries": self.coordinator.data.get("forecast_entries", 0),
            "rain_actual_2d_mm": self.coordinator.data.get("rain_actual_2d_mm", 0),
            "rain_forecast_2d_mm": self.coordinator.data.get("rain_forecast_2d_mm", 0),
            "last_update": self.coordinator.data.get("last_weather_update"),
            "last_watered": self.coordinator.data.get("last_watered"),
            "hours_since_watering": self.coordinator.data.get("hours_since_watering"),
        }

    @property
    def icon(self) -> str:
        return "mdi:weather-partly-cloudy"


class IrrigationLogSensor(CoordinatorEntity, SensorEntity):
    """Sensor exposing recent irrigation log entries for dashboard display."""

    _attr_icon = "mdi:text-box-outline"
    _attr_should_poll = False

    def __init__(self, coordinator, config_entry):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{config_entry.entry_id}_log"
        self._attr_name = "Irrigation Planner Log"

    @property
    def native_value(self) -> str | None:
        """Return count of buffered log entries."""
        if self.coordinator.data is None:
            return None
        logs = self.coordinator.data.get("recent_logs", [])
        return f"{len(logs)} entries"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return log entries and file path."""
        if self.coordinator.data is None:
            return {}
        logs = self.coordinator.data.get("recent_logs", [])
        return {
            "log_entries": logs,
            "log_count": len(logs),
            "log_file": self.coordinator.data.get("log_file_path"),
        }
