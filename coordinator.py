"""Data coordinator for Irrigation Planner."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import (
    async_track_time_interval,
    async_track_time_change,
    async_track_state_change_event,
    async_call_later,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .calc import IrrigationCalculator
from .const import (
    DOMAIN,
    CONF_CALC_TIME,
    CONF_DATA_RETENTION_DAYS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_OWM_API_KEY,
    CONF_RAINBIRD_DEBOUNCE_MINUTES,
    CONF_MIN_WATERING_INTERVAL_HOURS,
    CONF_AUTO_CALCULATE_ON_WEATHER_UPDATE,
    CONF_UPDATE_INTERVAL_MINUTES,
    CONF_ZONES,
    DEFAULT_CALC_TIME,
    DEFAULT_DATA_RETENTION_DAYS,
    DEFAULT_MIN_WATERING_INTERVAL_HOURS,
    DEFAULT_RAINBIRD_DEBOUNCE_MINUTES,
    DEFAULT_AUTO_CALCULATE_ON_WEATHER_UPDATE,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
)
from .store import IrrigationPlannerStore
from .weather import WeatherCollector

_LOGGER = logging.getLogger(__name__)


class IrrigationPlannerCoordinator(DataUpdateCoordinator):
    """Coordinate weather fetching, calculation, and data pruning."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # We manage our own schedules
        )
        self._config_entry = config_entry
        self._config = config_entry.data

        lat = self._config.get(CONF_LATITUDE, hass.config.latitude)
        lon = self._config.get(CONF_LONGITUDE, hass.config.longitude)

        self.store = IrrigationPlannerStore(hass)
        self.weather = WeatherCollector(
            hass,
            self._config[CONF_OWM_API_KEY],
            lat,
            lon,
        )
        self.calculator = IrrigationCalculator(lat, lon)

        self._unsub_weather_interval = None
        self._unsub_calc_time = None
        self._unsub_prune_time = None
        self._unsub_rainbird_listeners = []
        self._zone_debounce_timers: dict[str, Any] = {}  # zone_id -> unsub callback

        self._calc_min_gap_seconds = 300

    async def async_setup(self) -> None:
        """Set up the coordinator: load data, schedule tasks."""
        await self.store.async_load()

        # Schedule weather updates
        interval = self._config.get(
            CONF_UPDATE_INTERVAL_MINUTES, DEFAULT_UPDATE_INTERVAL_MINUTES
        )
        self._unsub_weather_interval = async_track_time_interval(
            self.hass,
            self._async_weather_update_callback,
            timedelta(minutes=interval),
        )
        _LOGGER.info("Weather update scheduled every %d minutes", interval)

        # Schedule daily calculation
        calc_time = self._config.get(CONF_CALC_TIME, DEFAULT_CALC_TIME)
        try:
            hour, minute = map(int, calc_time.split(":"))
        except (ValueError, AttributeError):
            hour, minute = 5, 0
        self._unsub_calc_time = async_track_time_change(
            self.hass,
            self._async_calc_callback,
            hour=hour,
            minute=minute,
            second=0,
        )
        _LOGGER.info("Daily calculation scheduled at %02d:%02d", hour, minute)

        # Schedule daily data pruning at 03:00
        self._unsub_prune_time = async_track_time_change(
            self.hass,
            self._async_prune_callback,
            hour=3,
            minute=0,
            second=0,
        )
        _LOGGER.info("Data pruning scheduled at 03:00")

        # Listen for Rainbird switches turning off (watering finished)
        # Build mapping: entity_id -> zone_id
        self._rainbird_to_zone = {}
        rainbird_entities = []
        for idx, zone_cfg in enumerate(self._config.get(CONF_ZONES, [])):
            rb_zone = zone_cfg.get("rainbird_zone", 0)
            if rb_zone > 0:
                entity_id = f"switch.rain_bird_sprinkler_{rb_zone}"
                zone_id = f"zone_{idx + 1}"
                self._rainbird_to_zone[entity_id] = zone_id
                rainbird_entities.append(entity_id)
        if rainbird_entities:
            unsub = async_track_state_change_event(
                self.hass,
                rainbird_entities,
                self._async_rainbird_state_change,
            )
            self._unsub_rainbird_listeners.append(unsub)
            _LOGGER.info("Listening for Rainbird state changes: %s", self._rainbird_to_zone)

        # Initial weather fetch
        await self.async_refresh_weather()

        # Build initial coordinator data
        await self._async_update_data_from_store()

    async def async_shutdown(self) -> None:
        """Clean up on shutdown."""
        if self._unsub_weather_interval:
            self._unsub_weather_interval()
        if self._unsub_calc_time:
            self._unsub_calc_time()
        if self._unsub_prune_time:
            self._unsub_prune_time()
        for unsub in self._unsub_rainbird_listeners:
            unsub()
        for unsub in self._zone_debounce_timers.values():
            unsub()
        self._zone_debounce_timers.clear()

    # --- Scheduled Callbacks ---

    async def _async_weather_update_callback(self, now=None) -> None:
        """Scheduled weather update, then recalculate."""
        await self.async_refresh_weather()
        if not self._config.get(
            CONF_AUTO_CALCULATE_ON_WEATHER_UPDATE,
            DEFAULT_AUTO_CALCULATE_ON_WEATHER_UPDATE,
        ):
            _LOGGER.debug("Auto-calculate on weather update disabled")
            return
        if self._calculation_ran_recently(self._calc_min_gap_seconds):
            _LOGGER.debug("Skipping weather-triggered calculate; recently calculated")
            return
        await self.async_calculate()

    async def _async_calc_callback(self, now=None) -> None:
        """Scheduled daily calculation."""
        if self._calculation_ran_recently(self._calc_min_gap_seconds):
            _LOGGER.debug("Skipping scheduled daily calculation; recently calculated")
            return
        _LOGGER.info("Running scheduled daily calculation")
        await self.async_calculate()

    async def _async_prune_callback(self, now=None) -> None:
        """Scheduled data pruning."""
        retention = self._config.get(
            CONF_DATA_RETENTION_DAYS, DEFAULT_DATA_RETENTION_DAYS
        )
        await self.store.async_prune_old_data(retention)
        await self._async_update_data_from_store()

    # --- Public Actions ---

    async def async_refresh_weather(self) -> None:
        """Fetch current weather and forecast from OWM."""
        _LOGGER.debug("Refreshing weather data")
        result = await self.weather.async_fetch_current_and_forecast()

        if not result:
            _LOGGER.warning("No weather data received")
            return

        # Store current observation as history
        if result.get("current"):
            await self.store.async_add_weather_data(result["current"])

        # Update forecast (replace with latest)
        hourly = result.get("hourly_forecast", [])
        daily = result.get("daily_forecast", [])
        all_forecast = hourly + daily
        if all_forecast:
            await self.store.async_set_forecast(all_forecast)

        await self._async_update_data_from_store()
        _LOGGER.info(
            "Weather updated: %d history, %d forecast entries",
            len(self.store.get_weather_history(2)),
            len(self.store.get_forecast(2)),
        )

    async def async_calculate(self) -> None:
        """Run irrigation calculation for all zones."""
        _LOGGER.info("Running irrigation calculation for all zones")
        zones = self._config.get(CONF_ZONES, [])
        min_interval_hours = self._config.get(
            CONF_MIN_WATERING_INTERVAL_HOURS,
            DEFAULT_MIN_WATERING_INTERVAL_HOURS,
        )

        weather_history = self.store.get_weather_history(days=2)
        weather_forecast = self.store.get_forecast(days=2)

        if not weather_history:
            _LOGGER.warning("No weather history available, skipping calculation")
            return

        for idx, zone_config in enumerate(zones):
            zone_id = f"zone_{idx + 1}"
            zone_data = self.store.get_zone_data(zone_id)

            result = self.calculator.calculate_zone(
                zone_config=zone_config,
                zone_data=zone_data,
                weather_history=weather_history,
                weather_forecast=weather_forecast,
            )

            # Safety cooldown: do not water again too soon after last watering
            last_watered = self.store.data.get("last_watered")
            if min_interval_hours > 0 and last_watered:
                try:
                    last_dt = datetime.fromisoformat(last_watered)
                    hours_since = (datetime.now() - last_dt).total_seconds() / 3600
                    if hours_since < min_interval_hours:
                        result["duration_minutes"] = 0.0
                        result["cooldown_active"] = True
                        result["cooldown_remaining_hours"] = round(min_interval_hours - hours_since, 1)
                        explanation = result.get("explanation", "")
                        result["explanation"] = (
                            explanation
                            + f"\n\nCooldown active: next watering allowed in {result['cooldown_remaining_hours']}h"
                        ).strip()
                except (ValueError, TypeError):
                    pass

            await self.store.async_update_zone(zone_id, result)

        await self._async_update_data_from_store()
        _LOGGER.info("Calculation complete for %d zones", len(zones))

    async def async_mark_watered(self) -> None:
        """Record that watering just happened and set all buckets to 100%."""
        await self.store.async_record_watering()
        zones = self._config.get(CONF_ZONES, [])
        for idx in range(len(zones)):
            zone_id = f"zone_{idx + 1}"
            await self.store.async_reset_zone_bucket(zone_id, 100.0)
            await self.store.async_update_zone(zone_id, {
                "bucket_percent": 100.0,
                "duration_minutes": 0.0,
                "cooldown_active": False,
                "cooldown_remaining_hours": None,
            })
        await self._async_update_data_from_store()
        _LOGGER.info("Watering recorded, all buckets set to 100%%")

    async def async_reset_all_buckets(self, value: float = 0.0) -> None:
        """Reset all zone buckets."""
        zones = self._config.get(CONF_ZONES, [])
        for idx in range(len(zones)):
            zone_id = f"zone_{idx + 1}"
            await self.store.async_reset_zone_bucket(zone_id, value)

        await self._async_update_data_from_store()
        _LOGGER.info("All buckets reset to %.1f%%", value)


    async def _async_rainbird_state_change(self, event) -> None:
        """Handle Rainbird switch state change with per-zone debounce."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if not old_state or not new_state:
            return

        entity_id = event.data.get("entity_id", "")
        zone_id = self._rainbird_to_zone.get(entity_id)
        if not zone_id:
            return

        if old_state.state == "on" and new_state.state == "off":
            # Zone turned off — start/restart debounce timer
            # Cancel existing timer if still pending (repeat cycle)
            if zone_id in self._zone_debounce_timers:
                self._zone_debounce_timers[zone_id]()
                _LOGGER.debug("Reset debounce timer for %s (repeat cycle)", zone_id)

            async def _mark_zone_done(_now, _zone_id=zone_id, _entity_id=entity_id):
                """Called after debounce delay — mark zone as watered."""
                _LOGGER.info(
                    "Debounce expired: Rainbird %s done, setting %s to 100%%",
                    _entity_id, _zone_id,
                )
                self._zone_debounce_timers.pop(_zone_id, None)
                await self.store.async_reset_zone_bucket(_zone_id, 100.0)
                await self.store.async_update_zone(_zone_id, {
                    "bucket_percent": 100.0,
                    "duration_minutes": 0.0,
                    "cooldown_active": False,
                    "cooldown_remaining_hours": None,
                })
                await self.store.async_record_watering()
                await self._async_update_data_from_store()

            debounce_seconds = int(
                self._config.get(
                    CONF_RAINBIRD_DEBOUNCE_MINUTES,
                    DEFAULT_RAINBIRD_DEBOUNCE_MINUTES,
                ) * 60
            )
            unsub = async_call_later(self.hass, debounce_seconds, _mark_zone_done)
            self._zone_debounce_timers[zone_id] = unsub
            _LOGGER.info(
                "Rainbird %s turned off, debounce %ds for %s",
                entity_id, debounce_seconds, zone_id,
            )

        elif old_state.state == "off" and new_state.state == "on":
            # Zone turned back on — cancel debounce (another cycle starting)
            if zone_id in self._zone_debounce_timers:
                self._zone_debounce_timers[zone_id]()
                self._zone_debounce_timers.pop(zone_id)
                _LOGGER.info(
                    "Rainbird %s turned on again, cancelled debounce for %s",
                    entity_id, zone_id,
                )

    def _calculation_ran_recently(self, min_gap_seconds: int) -> bool:
        """Return True if a calculation ran recently enough to skip rerun."""
        last_calculation = self.store.data.get("last_calculation")
        if not last_calculation:
            return False
        try:
            last_dt = datetime.fromisoformat(last_calculation)
        except (ValueError, TypeError):
            return False
        return (datetime.now() - last_dt).total_seconds() < min_gap_seconds

    # --- Internal ---

    async def _async_update_data_from_store(self) -> None:
        """Update coordinator data from store for sensor consumption."""
        zones_data = {}
        zones = self._config.get(CONF_ZONES, [])
        for idx, zone_config in enumerate(zones):
            zone_id = f"zone_{idx + 1}"
            zones_data[zone_id] = self.store.get_zone_data(zone_id)

        history = self.store.get_weather_history(2)
        forecast = self.store.get_forecast(2)

        # Get latest temperature and humidity from most recent history entry
        current_temp = None
        current_humidity = None
        if history:
            latest = history[-1]
            current_temp = latest.get("temperature")
            current_humidity = latest.get("humidity")

        # Calculate hours since last watering
        last_watered = self.store.data.get("last_watered")
        hours_since_watering = None
        if last_watered:
            try:
                last_dt = datetime.fromisoformat(last_watered)
                delta = datetime.now() - last_dt
                hours_since_watering = round(delta.total_seconds() / 3600, 1)
            except (ValueError, TypeError):
                pass

        self.async_set_updated_data({
            "zones": zones_data,
            "last_weather_update": self.store.data.get("last_weather_update"),
            "last_calculation": self.store.data.get("last_calculation"),
            "calc_time": self._config.get(CONF_CALC_TIME, DEFAULT_CALC_TIME),
            "update_interval_minutes": self._config.get(
                CONF_UPDATE_INTERVAL_MINUTES,
                DEFAULT_UPDATE_INTERVAL_MINUTES,
            ),
            "data_retention_days": self._config.get(
                CONF_DATA_RETENTION_DAYS,
                DEFAULT_DATA_RETENTION_DAYS,
            ),
            "rainbird_debounce_minutes": self._config.get(
                CONF_RAINBIRD_DEBOUNCE_MINUTES,
                DEFAULT_RAINBIRD_DEBOUNCE_MINUTES,
            ),
            "min_watering_interval_hours": self._config.get(
                CONF_MIN_WATERING_INTERVAL_HOURS,
                DEFAULT_MIN_WATERING_INTERVAL_HOURS,
            ),
            "auto_calculate_on_weather_update": self._config.get(
                CONF_AUTO_CALCULATE_ON_WEATHER_UPDATE,
                DEFAULT_AUTO_CALCULATE_ON_WEATHER_UPDATE,
            ),
            "history_entries": len(history),
            "forecast_entries": len(forecast),
            "rain_actual_2d_mm": round(self.store.get_accumulated_rain_actual(2), 2),
            "rain_forecast_2d_mm": round(self.store.get_accumulated_rain_forecast(2), 2),
            "current_temp_c": current_temp,
            "current_humidity": current_humidity,
            "last_watered": last_watered,
            "hours_since_watering": hours_since_watering,
        })

    async def _async_update_data(self) -> dict[str, Any]:
        """Required by DataUpdateCoordinator but not used (we push updates)."""
        return self.data or {}
