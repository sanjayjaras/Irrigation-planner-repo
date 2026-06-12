"""Config flow for Irrigation Planner."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_WEATHER_SOURCE,
    CONF_OWM_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_CALC_TIME,
    CONF_DATA_RETENTION_DAYS,
    CONF_UPDATE_INTERVAL_MINUTES,
    CONF_RAINBIRD_DEBOUNCE_MINUTES,
    CONF_MIN_WATERING_INTERVAL_HOURS,
    CONF_MIN_WATERING_DURATION_MINUTES,
    CONF_AUTO_CALCULATE_ON_WEATHER_UPDATE,
    CONF_ZONES,
    CONF_ZONE_NAME,
    CONF_ZONE_AREA_SQFT,
    CONF_ZONE_SUN_EXPOSURE,
    CONF_ZONE_SOIL_TYPE,
    CONF_ZONE_PLANT_TYPE,
    CONF_ZONE_SPRINKLER_RATE_IN_PER_HR,
    CONF_ZONE_RAINBIRD_ZONE,
    CONF_ZONE_DURATION_MULTIPLIER,
    CONF_ZONE_MAX_DURATION_MINUTES,
    CONF_RAIN_THRESHOLD_MM,
    CONF_RAIN_LIGHT_EFFECTIVENESS,
    CONF_FORECAST_CONFIDENCE,
    SUN_EXPOSURE_OPTIONS,
    SOIL_TYPE_OPTIONS,
    PLANT_TYPE_OPTIONS,
    WEATHER_SOURCE_OPTIONS,
    DEFAULT_WEATHER_SOURCE,
    DEFAULT_CALC_TIME,
    DEFAULT_DATA_RETENTION_DAYS,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DEFAULT_RAINBIRD_DEBOUNCE_MINUTES,
    DEFAULT_MIN_WATERING_INTERVAL_HOURS,
    DEFAULT_MIN_WATERING_DURATION_MINUTES,
    DEFAULT_AUTO_CALCULATE_ON_WEATHER_UPDATE,
    DEFAULT_RAIN_THRESHOLD_MM,
    DEFAULT_RAIN_LIGHT_EFFECTIVENESS,
    DEFAULT_FORECAST_CONFIDENCE,
    DEFAULT_AREA_SQFT,
    DEFAULT_SPRINKLER_RATE_IN_PER_HR,
    DEFAULT_DURATION_MULTIPLIER,
    DEFAULT_MAX_DURATION_MINUTES,
    SUN_FULL,
    SOIL_LOAM,
    PLANT_GRASS,
    WEATHER_SOURCE_NWS,
    WEATHER_SOURCE_OWM,
    OWM_BASE_URL,
)

_LOGGER = logging.getLogger(__name__)


class IrrigationPlannerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Irrigation Planner."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize flow."""
        self._config: dict[str, Any] = {}
        self._zones: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Weather source, API key (if OWM), and location."""
        errors = {}

        if user_input is not None:
            weather_source = user_input.get(CONF_WEATHER_SOURCE, DEFAULT_WEATHER_SOURCE)
            lat = user_input.get(CONF_LATITUDE, self.hass.config.latitude)
            lon = user_input.get(CONF_LONGITUDE, self.hass.config.longitude)

            # Validate OWM API key if OWM is selected
            if weather_source == WEATHER_SOURCE_OWM:
                api_key = user_input.get(CONF_OWM_API_KEY, "")
                if not api_key:
                    errors["base"] = "api_key_required"
                else:
                    valid = await self._test_owm_key(api_key, lat, lon)
                    if not valid:
                        errors["base"] = "invalid_api_key"

            if not errors:
                self._config = {
                    CONF_WEATHER_SOURCE: weather_source,
                    CONF_OWM_API_KEY: user_input.get(CONF_OWM_API_KEY, ""),
                    CONF_LATITUDE: lat,
                    CONF_LONGITUDE: lon,
                }
                return await self.async_step_settings()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_WEATHER_SOURCE,
                    default=DEFAULT_WEATHER_SOURCE,
                ): vol.In(WEATHER_SOURCE_OPTIONS),
                vol.Optional(CONF_OWM_API_KEY): str,
                vol.Optional(
                    CONF_LATITUDE,
                    default=self.hass.config.latitude,
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_LONGITUDE,
                    default=self.hass.config.longitude,
                ): vol.Coerce(float),
            }),
            errors=errors,
            description_placeholders={
                "title": "Irrigation Planner - Weather Setup",
            },
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: General settings."""
        if user_input is not None:
            self._config.update({
                CONF_CALC_TIME: user_input.get(CONF_CALC_TIME, DEFAULT_CALC_TIME),
                CONF_UPDATE_INTERVAL_MINUTES: user_input.get(
                    CONF_UPDATE_INTERVAL_MINUTES, DEFAULT_UPDATE_INTERVAL_MINUTES
                ),
                CONF_DATA_RETENTION_DAYS: user_input.get(
                    CONF_DATA_RETENTION_DAYS, DEFAULT_DATA_RETENTION_DAYS
                ),
                CONF_RAINBIRD_DEBOUNCE_MINUTES: user_input.get(
                    CONF_RAINBIRD_DEBOUNCE_MINUTES, DEFAULT_RAINBIRD_DEBOUNCE_MINUTES
                ),
                CONF_MIN_WATERING_INTERVAL_HOURS: user_input.get(
                    CONF_MIN_WATERING_INTERVAL_HOURS, DEFAULT_MIN_WATERING_INTERVAL_HOURS
                ),
                CONF_AUTO_CALCULATE_ON_WEATHER_UPDATE: user_input.get(
                    CONF_AUTO_CALCULATE_ON_WEATHER_UPDATE, DEFAULT_AUTO_CALCULATE_ON_WEATHER_UPDATE
                ),
                CONF_RAIN_THRESHOLD_MM: user_input.get(
                    CONF_RAIN_THRESHOLD_MM, DEFAULT_RAIN_THRESHOLD_MM
                ),
                CONF_RAIN_LIGHT_EFFECTIVENESS: user_input.get(
                    CONF_RAIN_LIGHT_EFFECTIVENESS, DEFAULT_RAIN_LIGHT_EFFECTIVENESS
                ),
                CONF_FORECAST_CONFIDENCE: user_input.get(
                    CONF_FORECAST_CONFIDENCE, DEFAULT_FORECAST_CONFIDENCE
                ),
            })
            return await self.async_step_zones()

        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_CALC_TIME,
                    default=DEFAULT_CALC_TIME,
                ): str,
                vol.Optional(
                    CONF_UPDATE_INTERVAL_MINUTES,
                    default=DEFAULT_UPDATE_INTERVAL_MINUTES,
                ): vol.All(vol.Coerce(int), vol.Range(min=15, max=360)),
                vol.Optional(
                    CONF_DATA_RETENTION_DAYS,
                    default=DEFAULT_DATA_RETENTION_DAYS,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=14)),
                vol.Optional(
                    CONF_RAINBIRD_DEBOUNCE_MINUTES,
                    default=DEFAULT_RAINBIRD_DEBOUNCE_MINUTES,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                vol.Optional(
                    CONF_MIN_WATERING_INTERVAL_HOURS,
                    default=DEFAULT_MIN_WATERING_INTERVAL_HOURS,
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=168)),
                vol.Optional(
                    CONF_MIN_WATERING_DURATION_MINUTES,
                    default=DEFAULT_MIN_WATERING_DURATION_MINUTES,
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
                vol.Optional(
                    CONF_AUTO_CALCULATE_ON_WEATHER_UPDATE,
                    default=DEFAULT_AUTO_CALCULATE_ON_WEATHER_UPDATE,
                ): bool,
                vol.Optional(
                    CONF_RAIN_THRESHOLD_MM,
                    default=DEFAULT_RAIN_THRESHOLD_MM,
                ): vol.All(vol.Coerce(float), vol.Range(min=0, max=25)),
                vol.Optional(
                    CONF_RAIN_LIGHT_EFFECTIVENESS,
                    default=DEFAULT_RAIN_LIGHT_EFFECTIVENESS,
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                vol.Optional(
                    CONF_FORECAST_CONFIDENCE,
                    default=DEFAULT_FORECAST_CONFIDENCE,
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            }),
        )

    async def async_step_zones(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Add a zone."""
        if user_input is not None:
            zone = {
                CONF_ZONE_NAME: user_input[CONF_ZONE_NAME],
                CONF_ZONE_AREA_SQFT: user_input.get(CONF_ZONE_AREA_SQFT, DEFAULT_AREA_SQFT),
                CONF_ZONE_SUN_EXPOSURE: user_input.get(CONF_ZONE_SUN_EXPOSURE, SUN_FULL),
                CONF_ZONE_SOIL_TYPE: user_input.get(CONF_ZONE_SOIL_TYPE, SOIL_LOAM),
                CONF_ZONE_PLANT_TYPE: user_input.get(CONF_ZONE_PLANT_TYPE, PLANT_GRASS),
                CONF_ZONE_SPRINKLER_RATE_IN_PER_HR: user_input.get(
                    CONF_ZONE_SPRINKLER_RATE_IN_PER_HR, DEFAULT_SPRINKLER_RATE_IN_PER_HR
                ),
                CONF_ZONE_RAINBIRD_ZONE: user_input.get(CONF_ZONE_RAINBIRD_ZONE, 0),
                CONF_ZONE_DURATION_MULTIPLIER: user_input.get(CONF_ZONE_DURATION_MULTIPLIER, DEFAULT_DURATION_MULTIPLIER),
                CONF_ZONE_MAX_DURATION_MINUTES: user_input.get(CONF_ZONE_MAX_DURATION_MINUTES, DEFAULT_MAX_DURATION_MINUTES),
            }
            self._zones.append(zone)

            add_another = user_input.get("add_another", False)
            if add_another:
                return await self.async_step_zones()

            # Done adding zones, create entry
            self._config[CONF_ZONES] = self._zones
            return self.async_create_entry(
                title="Irrigation Planner",
                data=self._config,
            )

        return self.async_show_form(
            step_id="zones",
            data_schema=vol.Schema({
                vol.Required(CONF_ZONE_NAME): str,
                vol.Optional(
                    CONF_ZONE_AREA_SQFT,
                    default=DEFAULT_AREA_SQFT,
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_ZONE_SUN_EXPOSURE,
                    default=SUN_FULL,
                ): vol.In(SUN_EXPOSURE_OPTIONS),
                vol.Optional(
                    CONF_ZONE_SOIL_TYPE,
                    default=SOIL_LOAM,
                ): vol.In(SOIL_TYPE_OPTIONS),
                vol.Optional(
                    CONF_ZONE_PLANT_TYPE,
                    default=PLANT_GRASS,
                ): vol.In(PLANT_TYPE_OPTIONS),
                vol.Optional(
                    CONF_ZONE_SPRINKLER_RATE_IN_PER_HR,
                    default=DEFAULT_SPRINKLER_RATE_IN_PER_HR,
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=5.0)),
                vol.Optional(
                    CONF_ZONE_RAINBIRD_ZONE,
                    default=0,
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_ZONE_DURATION_MULTIPLIER,
                    default=DEFAULT_DURATION_MULTIPLIER,
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=5.0)),
                vol.Optional(
                    CONF_ZONE_MAX_DURATION_MINUTES,
                    default=DEFAULT_MAX_DURATION_MINUTES,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=120)),
                vol.Optional("add_another", default=False): bool,
            }),
            description_placeholders={
                "zone_count": str(len(self._zones)),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow."""
        return IrrigationPlannerOptionsFlow(config_entry)

    async def _test_owm_key(self, api_key: str, lat: float, lon: float) -> bool:
        """Test OWM API key validity."""
        url = f"{OWM_BASE_URL}?lat={lat}&lon={lon}&appid={api_key}&exclude=minutely,hourly,daily,alerts"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    return resp.status == 200
        except Exception:
            return False


class IrrigationPlannerOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Irrigation Planner."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._updated_data: dict[str, Any] = dict(config_entry.data)
        self._zones: list[dict[str, Any]] = list(config_entry.data.get(CONF_ZONES, []))
        self._editing_zone_idx: int | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Main menu: choose what to configure."""
        if user_input is not None:
            next_step = user_input.get("menu")
            if next_step == "general":
                return await self.async_step_general()
            elif next_step == "api":
                return await self.async_step_api()
            elif next_step == "zones":
                return await self.async_step_zone_menu()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("menu", default="general"): vol.In({
                    "general": "General Settings (calc time, intervals)",
                    "api": "Weather API Settings (OWM key, location)",
                    "zones": "Zone Management (add/edit/delete zones)",
                }),
            }),
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """General settings: calc time, intervals, retention."""
        if user_input is not None:
            self._updated_data[CONF_CALC_TIME] = user_input.get(CONF_CALC_TIME, DEFAULT_CALC_TIME)
            self._updated_data[CONF_UPDATE_INTERVAL_MINUTES] = user_input.get(
                CONF_UPDATE_INTERVAL_MINUTES, DEFAULT_UPDATE_INTERVAL_MINUTES
            )
            self._updated_data[CONF_DATA_RETENTION_DAYS] = user_input.get(
                CONF_DATA_RETENTION_DAYS, DEFAULT_DATA_RETENTION_DAYS
            )
            self._updated_data[CONF_RAINBIRD_DEBOUNCE_MINUTES] = user_input.get(
                CONF_RAINBIRD_DEBOUNCE_MINUTES, DEFAULT_RAINBIRD_DEBOUNCE_MINUTES
            )
            self._updated_data[CONF_MIN_WATERING_INTERVAL_HOURS] = user_input.get(
                CONF_MIN_WATERING_INTERVAL_HOURS, DEFAULT_MIN_WATERING_INTERVAL_HOURS
            )
            self._updated_data[CONF_MIN_WATERING_DURATION_MINUTES] = user_input.get(
                CONF_MIN_WATERING_DURATION_MINUTES, DEFAULT_MIN_WATERING_DURATION_MINUTES
            )
            self._updated_data[CONF_AUTO_CALCULATE_ON_WEATHER_UPDATE] = user_input.get(
                CONF_AUTO_CALCULATE_ON_WEATHER_UPDATE,
                DEFAULT_AUTO_CALCULATE_ON_WEATHER_UPDATE,
            )
            self._updated_data[CONF_RAIN_THRESHOLD_MM] = user_input.get(
                CONF_RAIN_THRESHOLD_MM, DEFAULT_RAIN_THRESHOLD_MM
            )
            self._updated_data[CONF_RAIN_LIGHT_EFFECTIVENESS] = user_input.get(
                CONF_RAIN_LIGHT_EFFECTIVENESS, DEFAULT_RAIN_LIGHT_EFFECTIVENESS
            )
            self._updated_data[CONF_FORECAST_CONFIDENCE] = user_input.get(
                CONF_FORECAST_CONFIDENCE, DEFAULT_FORECAST_CONFIDENCE
            )
            self.hass.config_entries.async_update_entry(
                self._config_entry, data=self._updated_data
            )
            return self.async_create_entry(title="", data={})

        current = self._updated_data
        return self.async_show_form(
            step_id="general",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_CALC_TIME,
                    default=current.get(CONF_CALC_TIME, DEFAULT_CALC_TIME),
                ): str,
                vol.Optional(
                    CONF_UPDATE_INTERVAL_MINUTES,
                    default=current.get(CONF_UPDATE_INTERVAL_MINUTES, DEFAULT_UPDATE_INTERVAL_MINUTES),
                ): vol.All(vol.Coerce(int), vol.Range(min=15, max=360)),
                vol.Optional(
                    CONF_DATA_RETENTION_DAYS,
                    default=current.get(CONF_DATA_RETENTION_DAYS, DEFAULT_DATA_RETENTION_DAYS),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=14)),
                vol.Optional(
                    CONF_RAINBIRD_DEBOUNCE_MINUTES,
                    default=current.get(CONF_RAINBIRD_DEBOUNCE_MINUTES, DEFAULT_RAINBIRD_DEBOUNCE_MINUTES),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                vol.Optional(
                    CONF_MIN_WATERING_INTERVAL_HOURS,
                    default=current.get(CONF_MIN_WATERING_INTERVAL_HOURS, DEFAULT_MIN_WATERING_INTERVAL_HOURS),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=168)),
                vol.Optional(
                    CONF_MIN_WATERING_DURATION_MINUTES,
                    default=current.get(CONF_MIN_WATERING_DURATION_MINUTES, DEFAULT_MIN_WATERING_DURATION_MINUTES),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
                vol.Optional(
                    CONF_AUTO_CALCULATE_ON_WEATHER_UPDATE,
                    default=current.get(
                        CONF_AUTO_CALCULATE_ON_WEATHER_UPDATE,
                        DEFAULT_AUTO_CALCULATE_ON_WEATHER_UPDATE,
                    ),
                ): bool,
                vol.Optional(
                    CONF_RAIN_THRESHOLD_MM,
                    default=current.get(CONF_RAIN_THRESHOLD_MM, DEFAULT_RAIN_THRESHOLD_MM),
                ): vol.All(vol.Coerce(float), vol.Range(min=0, max=25)),
                vol.Optional(
                    CONF_RAIN_LIGHT_EFFECTIVENESS,
                    default=current.get(CONF_RAIN_LIGHT_EFFECTIVENESS, DEFAULT_RAIN_LIGHT_EFFECTIVENESS),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                vol.Optional(
                    CONF_FORECAST_CONFIDENCE,
                    default=current.get(CONF_FORECAST_CONFIDENCE, DEFAULT_FORECAST_CONFIDENCE),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            }),
        )

    async def async_step_api(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """API settings: weather source, OWM key (if OWM), lat, lon."""
        errors = {}

        if user_input is not None:
            weather_source = user_input.get(CONF_WEATHER_SOURCE, self._updated_data.get(CONF_WEATHER_SOURCE, DEFAULT_WEATHER_SOURCE))
            lat = user_input.get(CONF_LATITUDE, self.hass.config.latitude)
            lon = user_input.get(CONF_LONGITUDE, self.hass.config.longitude)

            # Validate OWM API key if OWM is selected
            if weather_source == WEATHER_SOURCE_OWM:
                api_key = user_input.get(CONF_OWM_API_KEY, self._updated_data.get(CONF_OWM_API_KEY, ""))
                if not api_key:
                    errors["base"] = "api_key_required"
                else:
                    valid = await self._test_owm_key(api_key, lat, lon)
                    if not valid:
                        errors["base"] = "invalid_api_key"

            if not errors:
                self._updated_data[CONF_WEATHER_SOURCE] = weather_source
                self._updated_data[CONF_OWM_API_KEY] = user_input.get(CONF_OWM_API_KEY, "")
                self._updated_data[CONF_LATITUDE] = lat
                self._updated_data[CONF_LONGITUDE] = lon
                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=self._updated_data
                )
                return self.async_create_entry(title="", data={})

        current = self._updated_data
        return self.async_show_form(
            step_id="api",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_WEATHER_SOURCE,
                    default=current.get(CONF_WEATHER_SOURCE, DEFAULT_WEATHER_SOURCE),
                ): vol.In(WEATHER_SOURCE_OPTIONS),
                vol.Optional(
                    CONF_OWM_API_KEY,
                    default=current.get(CONF_OWM_API_KEY, ""),
                ): str,
                vol.Optional(
                    CONF_LATITUDE,
                    default=current.get(CONF_LATITUDE, self.hass.config.latitude),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_LONGITUDE,
                    default=current.get(CONF_LONGITUDE, self.hass.config.longitude),
                ): vol.Coerce(float),
            }),
            errors=errors,
        )

    async def async_step_zone_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Zone management menu: list zones, add/edit/delete."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "add":
                self._editing_zone_idx = None
                return await self.async_step_zone_edit()
            elif action == "done":
                self._updated_data[CONF_ZONES] = self._zones
                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=self._updated_data
                )
                return self.async_create_entry(title="", data={})
            elif action and action.startswith("edit_"):
                self._editing_zone_idx = int(action.split("_")[1])
                return await self.async_step_zone_edit()
            elif action and action.startswith("delete_"):
                idx = int(action.split("_")[1])
                if 0 <= idx < len(self._zones):
                    deleted = self._zones.pop(idx)
                    _LOGGER.info("Deleted zone: %s", deleted.get(CONF_ZONE_NAME))
                return await self.async_step_zone_menu()

        # Build zone list for menu
        zone_options = {}
        for idx, z in enumerate(self._zones):
            name = z.get(CONF_ZONE_NAME, f"Zone {idx + 1}")
            zone_options[f"edit_{idx}"] = f"Edit: {name}"
            zone_options[f"delete_{idx}"] = f"Delete: {name}"
        zone_options["add"] = "➕ Add New Zone"
        zone_options["done"] = "✅ Save & Done"

        return self.async_show_form(
            step_id="zone_menu",
            data_schema=vol.Schema({
                vol.Required("action"): vol.In(zone_options),
            }),
            description_placeholders={
                "zone_count": str(len(self._zones)),
            },
        )

    async def async_step_zone_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add or edit a zone."""
        if user_input is not None:
            zone = {
                CONF_ZONE_NAME: user_input[CONF_ZONE_NAME],
                CONF_ZONE_AREA_SQFT: user_input.get(CONF_ZONE_AREA_SQFT, DEFAULT_AREA_SQFT),
                CONF_ZONE_SUN_EXPOSURE: user_input.get(CONF_ZONE_SUN_EXPOSURE, SUN_FULL),
                CONF_ZONE_SOIL_TYPE: user_input.get(CONF_ZONE_SOIL_TYPE, SOIL_LOAM),
                CONF_ZONE_PLANT_TYPE: user_input.get(CONF_ZONE_PLANT_TYPE, PLANT_GRASS),
                CONF_ZONE_SPRINKLER_RATE_IN_PER_HR: user_input.get(
                    CONF_ZONE_SPRINKLER_RATE_IN_PER_HR, DEFAULT_SPRINKLER_RATE_IN_PER_HR
                ),
                CONF_ZONE_RAINBIRD_ZONE: user_input.get(CONF_ZONE_RAINBIRD_ZONE, 0),
                CONF_ZONE_DURATION_MULTIPLIER: user_input.get(CONF_ZONE_DURATION_MULTIPLIER, DEFAULT_DURATION_MULTIPLIER),
                CONF_ZONE_MAX_DURATION_MINUTES: user_input.get(CONF_ZONE_MAX_DURATION_MINUTES, DEFAULT_MAX_DURATION_MINUTES),
            }
            if self._editing_zone_idx is not None and 0 <= self._editing_zone_idx < len(self._zones):
                self._zones[self._editing_zone_idx] = zone
            else:
                self._zones.append(zone)
            return await self.async_step_zone_menu()

        # Pre-fill with existing zone data if editing
        defaults = {}
        if self._editing_zone_idx is not None and 0 <= self._editing_zone_idx < len(self._zones):
            defaults = self._zones[self._editing_zone_idx]

        return self.async_show_form(
            step_id="zone_edit",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_ZONE_NAME,
                    default=defaults.get(CONF_ZONE_NAME, ""),
                ): str,
                vol.Optional(
                    CONF_ZONE_AREA_SQFT,
                    default=defaults.get(CONF_ZONE_AREA_SQFT, DEFAULT_AREA_SQFT),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_ZONE_SUN_EXPOSURE,
                    default=defaults.get(CONF_ZONE_SUN_EXPOSURE, SUN_FULL),
                ): vol.In(SUN_EXPOSURE_OPTIONS),
                vol.Optional(
                    CONF_ZONE_SOIL_TYPE,
                    default=defaults.get(CONF_ZONE_SOIL_TYPE, SOIL_LOAM),
                ): vol.In(SOIL_TYPE_OPTIONS),
                vol.Optional(
                    CONF_ZONE_PLANT_TYPE,
                    default=defaults.get(CONF_ZONE_PLANT_TYPE, PLANT_GRASS),
                ): vol.In(PLANT_TYPE_OPTIONS),
                vol.Optional(
                    CONF_ZONE_SPRINKLER_RATE_IN_PER_HR,
                    default=defaults.get(CONF_ZONE_SPRINKLER_RATE_IN_PER_HR, DEFAULT_SPRINKLER_RATE_IN_PER_HR),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=5.0)),
                vol.Optional(
                    CONF_ZONE_RAINBIRD_ZONE,
                    default=defaults.get(CONF_ZONE_RAINBIRD_ZONE, 0),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_ZONE_DURATION_MULTIPLIER,
                    default=defaults.get(CONF_ZONE_DURATION_MULTIPLIER, DEFAULT_DURATION_MULTIPLIER),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=5.0)),
                vol.Optional(
                    CONF_ZONE_MAX_DURATION_MINUTES,
                    default=defaults.get(CONF_ZONE_MAX_DURATION_MINUTES, DEFAULT_MAX_DURATION_MINUTES),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=120)),
            }),
        )

    async def _test_owm_key(self, api_key: str, lat: float, lon: float) -> bool:
        """Test OWM API key validity."""
        url = f"{OWM_BASE_URL}?lat={lat}&lon={lon}&appid={api_key}&exclude=minutely,hourly,daily,alerts"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    return resp.status == 200
        except Exception:
            return False
