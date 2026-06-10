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
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .calc import IrrigationCalculator
from .log_handler import IrrigationLogBuffer
from .const import (
    DOMAIN,
    CONF_CALC_TIME,
    CONF_DATA_RETENTION_DAYS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_WEATHER_SOURCE,
    CONF_OWM_API_KEY,
    CONF_RAINBIRD_DEBOUNCE_MINUTES,
    CONF_MIN_WATERING_INTERVAL_HOURS,
    CONF_AUTO_CALCULATE_ON_WEATHER_UPDATE,
    CONF_RAIN_THRESHOLD_MM,
    CONF_RAIN_LIGHT_EFFECTIVENESS,
    CONF_FORECAST_CONFIDENCE,
    CONF_UPDATE_INTERVAL_MINUTES,
    CONF_ZONES,
    DEFAULT_CALC_TIME,
    DEFAULT_DATA_RETENTION_DAYS,
    DEFAULT_MIN_WATERING_INTERVAL_HOURS,
    DEFAULT_RAINBIRD_DEBOUNCE_MINUTES,
    DEFAULT_AUTO_CALCULATE_ON_WEATHER_UPDATE,
    DEFAULT_RAIN_THRESHOLD_MM,
    DEFAULT_RAIN_LIGHT_EFFECTIVENESS,
    DEFAULT_FORECAST_CONFIDENCE,
    DEFAULT_UPDATE_INTERVAL_MINUTES,
    DEFAULT_WEATHER_SOURCE,
)
from .store import IrrigationPlannerStore
from .weather import get_weather_service

_LOGGER = logging.getLogger(__name__)


class IrrigationPlannerCoordinator(DataUpdateCoordinator):
    """Coordinate weather fetching, calculation, and data pruning."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        log_buffer: IrrigationLogBuffer | None = None,
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
        self._log_buffer = log_buffer

        lat = self._config.get(CONF_LATITUDE, hass.config.latitude)
        lon = self._config.get(CONF_LONGITUDE, hass.config.longitude)
        weather_source = self._config.get(CONF_WEATHER_SOURCE, DEFAULT_WEATHER_SOURCE)
        api_key = self._config.get(CONF_OWM_API_KEY, "")

        self.store = IrrigationPlannerStore(hass)
        self.weather = get_weather_service(
            hass,
            weather_source,
            api_key,
            lat,
            lon,
        )
        self.calculator = IrrigationCalculator(lat, lon)

        self._unsub_weather_interval = None
        self._unsub_calc_time = None
        self._unsub_prune_time = None
        self._unsub_program_listener = None
        # Holds the most recent "current" observation from the weather service.
        # Tracked in memory so display always reflects the actual latest reading
        # rather than the hour-bucket-deduped history entry (which preferentially
        # keeps the :00:00 model value over the actual current-poll timestamp).
        self._current_conditions: dict = {}

    async def async_setup(self) -> None:
        """Set up the coordinator: load data, schedule tasks."""
        await self.store.async_load()

        debounce_minutes = self._config.get(
            CONF_RAINBIRD_DEBOUNCE_MINUTES,
            DEFAULT_RAINBIRD_DEBOUNCE_MINUTES,
        )
        self._calc_min_gap_seconds = max(0, int(debounce_minutes) * 60)

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

        # Listen for Irrigation Controller program switch turning off
        # (entire watering cycle complete, including all zones and ECO repeats).
        program_entity = self._IC_PROGRAM_ENTITY
        self._unsub_program_listener = async_track_state_change_event(
            self.hass,
            [program_entity],
            self._async_program_state_change,
        )
        _LOGGER.info("Listening for program end: %s", program_entity)

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
        if self._unsub_program_listener:
            self._unsub_program_listener()

    # --- Scheduled Callbacks ---

    async def _async_weather_update_callback(self, now=None) -> None:
        """Scheduled weather update, then recalculate."""
        # Skip entirely during irrigation window to avoid any state
        # changes that could interfere with the running program.
        if self._is_in_irrigation_window():
            _LOGGER.info(
                "Skipping weather update & calculation: inside irrigation window"
            )
            return
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
        """Fetch current weather and forecast from the configured weather service."""
        _LOGGER.debug("Refreshing weather data")
        result = await self.weather.async_fetch_current_and_forecast()

        if not result:
            _LOGGER.warning("No weather data received")
            return

        # Cache actual current conditions for sensor display.
        # The history store deduplicates to one entry per hour, preferring the
        # :00:00 OWM model entry over the actual current-observation timestamp.
        # Using result["current"] directly avoids showing the model forecast
        # value instead of the true observed reading.
        # Resolve the best available "current" observation.
        # OWM One Call 3.0 sometimes omits the separate "current" block;
        # fall back to the most recent hourly history entry in that case
        # (OWM hourly starts at the current hour, so the first past entry is
        # the current-hour analyzed value — a good temperature proxy).
        current_obs = result.get("current")
        if not current_obs:
            hourly_hist = result.get("hourly_history", [])
            if hourly_hist:
                current_obs = hourly_hist[-1]
                _LOGGER.debug(
                    "No 'current' block from weather service; "
                    "using most recent hourly entry (%s) for current conditions",
                    current_obs.get("timestamp"),
                )
            else:
                _LOGGER.warning(
                    "Weather fetch returned no 'current' observation and no "
                    "hourly history; result keys: %s",
                    list(result.keys()),
                )

        if current_obs:
            self._current_conditions = {
                "temperature": current_obs.get("temperature"),
                "humidity": current_obs.get("humidity"),
                "wind_speed": current_obs.get("wind_speed"),
                "dew_point": current_obs.get("dew_point"),
                "pressure": current_obs.get("pressure"),
                "uv_index": current_obs.get("uv_index"),
                "clouds": current_obs.get("clouds"),
                "observed_at": current_obs.get("timestamp"),
            }
            _LOGGER.info(
                "Current conditions: temp=%.1f°C, humidity=%s%%, observed_at=%s",
                self._current_conditions.get("temperature") or 0,
                self._current_conditions.get("humidity"),
                self._current_conditions.get("observed_at"),
            )

        # Store hourly_history entries (past hours from the weather service).
        # These contain accurate per-hour rain data and are more reliable than
        # the single-snapshot current observation.
        # Do NOT also store current precip — it overlaps with the hourly
        # entries and causes double-counting (different timestamps, same rain).
        hourly_history = result.get("hourly_history", [])
        for entry in hourly_history:
            await self.store.async_add_weather_data(entry)

        # Store current observation with rain zeroed out - we only want it
        # for temperature/humidity/etc display, not for rain accumulation.
        # Skip when it duplicates an hourly_history entry (same timestamp +
        # source): some providers (NWS) derive "current" from the latest
        # observation, so storing the rain-zeroed copy would overwrite that
        # observation's real precip via the store's (timestamp, source) dedup.
        current = result.get("current")
        if current:
            cur_ts = current.get("timestamp")
            cur_src = current.get("source")
            duplicates_history = any(
                e.get("timestamp") == cur_ts and e.get("source") == cur_src
                for e in hourly_history
            )
            if not duplicates_history:
                current_no_rain = dict(current)
                current_no_rain["precip_actual_mm"] = 0.0
                await self.store.async_add_weather_data(current_no_rain)

        # Update forecast (replace with latest)
        # Avoid overlap double-counting by preferring hourly forecast
        # for the near-term horizon we use in calculations.
        hourly = result.get("hourly_forecast", [])
        daily = result.get("daily_forecast", [])
        if hourly:
            all_forecast = hourly
        else:
            all_forecast = daily
        if all_forecast:
            await self.store.async_set_forecast(all_forecast)

        await self._async_update_data_from_store()
        _LOGGER.info(
            "Weather updated: %d hourly_history ingested, %d history total, %d forecast entries",
            len(hourly_history),
            len(self.store.get_weather_history(2)),
            len(self.store.get_forecast(2)),
        )

        # Fill gaps for days beyond the ~48-hour observation window
        await self.async_backfill_history()

    async def async_backfill_history(self) -> None:
        """Fetch historical weather data for days beyond the ~48-hour observation window.

        The weather service's hourly data only goes back ~48 hours.  Any rain
        that fell between last_watered and that boundary would otherwise be
        missing.  This method calls async_fetch_history() day-by-day to fill
        those gaps so rain accumulation since last watering is accurate.

        Each date is fetched at most once (tracked in store.backfilled_dates).
        Providers that do not support history return an empty list from
        async_fetch_history() and the date is still marked to avoid retrying.
        """
        retention = self._config.get(CONF_DATA_RETENTION_DAYS, DEFAULT_DATA_RETENTION_DAYS)
        last_watered = self.store.data.get("last_watered")

        # Determine the oldest date we care about
        if last_watered:
            try:
                start_date = datetime.fromisoformat(last_watered).date()
            except (ValueError, TypeError):
                start_date = (datetime.now() - timedelta(days=retention)).date()
        else:
            start_date = (datetime.now() - timedelta(days=retention)).date()

        # Hourly observations cover the past ~48 h; backfill fills older days
        owm_cutoff_date = (datetime.now() - timedelta(hours=48)).date()

        if start_date >= owm_cutoff_date:
            return  # Everything is within the OWM hourly window — nothing to backfill

        backfilled = self.store.get_backfilled_dates()
        current_date = start_date
        while current_date < owm_cutoff_date:
            date_str = current_date.isoformat()
            if date_str not in backfilled:
                try:
                    entries = await self.weather.async_fetch_history(
                        datetime.combine(current_date, datetime.min.time())
                    )
                    if entries:
                        await self.store.async_add_weather_data_batch(entries)
                        _LOGGER.info(
                            "Backfilled %d history entries for %s",
                            len(entries),
                            date_str,
                        )
                    else:
                        _LOGGER.debug("No history entries returned for %s; skipping", date_str)
                    # Always mark as done so we don't retry on the next refresh
                    await self.store.async_mark_date_backfilled(date_str)
                except Exception:
                    _LOGGER.exception("Failed to backfill weather history for %s", date_str)
                    # Do NOT mark as backfilled on exception — allow one retry next refresh
            current_date += timedelta(days=1)

    async def async_calculate(self, ignore_irrigation_window: bool = False) -> None:
        """Run irrigation calculation for all zones."""
        _LOGGER.info("Running irrigation calculation for all zones")
        zones = self._config.get(CONF_ZONES, [])
        min_interval_hours = self._config.get(
            CONF_MIN_WATERING_INTERVAL_HOURS,
            DEFAULT_MIN_WATERING_INTERVAL_HOURS,
        )

        # Use the full retention window so ET and rain since last_watered are
        # fully captured — a 2-day hardcoded window would miss data when the
        # inter-watering interval is longer than 2 days.
        retention = self._config.get(CONF_DATA_RETENTION_DAYS, DEFAULT_DATA_RETENTION_DAYS)
        weather_history = self.store.get_weather_history(days=retention)
        weather_forecast = self.store.get_forecast(days=2)
        last_watered = self.store.data.get("last_watered")

        if not weather_history:
            _LOGGER.warning("No weather history available, skipping calculation")
            return

        # Get rain effectiveness and forecast confidence settings
        rain_threshold_mm = self._config.get(
            CONF_RAIN_THRESHOLD_MM, DEFAULT_RAIN_THRESHOLD_MM
        )
        rain_light_effectiveness = self._config.get(
            CONF_RAIN_LIGHT_EFFECTIVENESS, DEFAULT_RAIN_LIGHT_EFFECTIVENESS
        )
        forecast_confidence = self._config.get(
            CONF_FORECAST_CONFIDENCE, DEFAULT_FORECAST_CONFIDENCE
        )

        # Skip calculation if we are inside the Irrigation Controller's
        # watering window.  The window runs from (start_time - buffer)
        # through (start_time + program_duration + buffer).  We also
        # fall back to checking the program switch state in case the
        # start time or duration entities are unavailable.
        if not ignore_irrigation_window and self._is_in_irrigation_window():
            _LOGGER.info(
                "Skipping calculation: inside Irrigation Controller watering window"
            )
            return

        for idx, zone_config in enumerate(zones):
            zone_id = f"zone_{idx + 1}"
            zone_data = self.store.get_zone_data(zone_id)

            try:
                result = self.calculator.calculate_zone(
                    zone_config=zone_config,
                    zone_data=zone_data,
                    weather_history=weather_history,
                    weather_forecast=weather_forecast,
                    rain_threshold_mm=rain_threshold_mm,
                    rain_light_effectiveness=rain_light_effectiveness,
                    forecast_confidence=forecast_confidence,
                    last_watered=last_watered,
                )

                # Always reset cooldown fields first so stale values
                # don't persist when cooldown has expired.
                result["cooldown_active"] = False
                result["cooldown_remaining_hours"] = None

                # Safety cooldown: do not water again too soon after last watering
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

                await self.store.async_update_zone(zone_id, result, save=False)
            except Exception:
                _LOGGER.exception("Failed calculation for zone %s", zone_id)

        # Single save after all zones are updated instead of one per zone
        await self.store.async_save()
        await self._async_update_data_from_store()
        _LOGGER.info("Calculation complete for %d zones", len(zones))

    async def async_mark_watered(self, watered_at: str | None = None) -> None:
        """Record that watering happened and update buckets.

        If the forecast reduced watering duration, the bucket is only filled
        proportional to what was actually watered — the remaining deficit is
        expected from forecasted rain but has not fallen yet.
        """
        await self.store.async_record_watering(watered_at)
        zones = self._config.get(CONF_ZONES, [])
        now_iso = datetime.now().isoformat()
        for idx in range(len(zones)):
            zone_id = f"zone_{idx + 1}"
            zone_data = self.store.get_zone_data(zone_id)
            prior_duration = zone_data.get("duration_minutes", 0.0)
            pre_forecast_duration = zone_data.get("pre_forecast_duration_minutes", 0.0)
            current_bucket = zone_data.get("bucket_percent", 0.0)

            # If forecast shortened the watering, only fill the bucket by the
            # fraction that was actually watered. The remaining deficit is left
            # in the bucket, expecting forecasted rain to cover it.
            if pre_forecast_duration > 0 and prior_duration < pre_forecast_duration:
                watered_fill = (prior_duration / pre_forecast_duration) * (100.0 - current_bucket)
                new_bucket = round(min(100.0, current_bucket + watered_fill), 1)
            else:
                new_bucket = 100.0

            await self.store.async_reset_zone_bucket(zone_id, new_bucket)
            await self.store.async_update_zone(zone_id, {
                "bucket_percent": new_bucket,
                "duration_minutes": 0.0,
                "last_watered_duration_minutes": prior_duration,
                "cooldown_active": False,
                "cooldown_remaining_hours": None,
                "last_calculated": now_iso,
            })
        await self._async_update_data_from_store()
        _LOGGER.info("Watering recorded at %s, buckets updated after watering", watered_at or "now")

    async def async_reset_all_buckets(self, value: float = 0.0) -> None:
        """Reset all zone buckets."""
        zones = self._config.get(CONF_ZONES, [])
        for idx in range(len(zones)):
            zone_id = f"zone_{idx + 1}"
            await self.store.async_reset_zone_bucket(zone_id, value)

        # Manual reset is an explicit user override. Clear watering baseline
        # so subsequent calculations honor the manually-set bucket state.
        await self.store.async_clear_last_watered()

        await self._async_update_data_from_store()
        _LOGGER.info("All buckets reset to %.1f%%", value)


    async def _async_program_state_change(self, event) -> None:
        """Handle Irrigation Controller program switch state change.

        When the program turns off, mark all zones as watered and trigger
        a fresh calculation.
        """
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if not old_state or not new_state:
            return

        if old_state.state == "on" and new_state.state == "off":
            _LOGGER.info(
                "Irrigation Controller program ended, marking all zones watered"
            )
            await self.async_mark_watered()
            # Fetch fresh weather since updates were skipped during the
            # irrigation window, then calculate with the new baseline.
            await self.async_refresh_weather()
            await self.async_calculate(ignore_irrigation_window=True)

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

    # --- Irrigation Window Detection ---

    _IC_PROGRAM_ENTITY = "switch.sprinkler_scheduler"
    _IC_WINDOW_BUFFER_MINUTES = 5  # buffer before start and after end

    def _is_in_irrigation_window(self) -> bool:
        """Return True if current time falls inside the Irrigation Controller's watering window.

        Window = (start_time - buffer) to (start_time + duration + buffer).
        Falls back to checking the program switch if entities are unavailable.
        """
        now = datetime.now()
        buffer = timedelta(minutes=self._IC_WINDOW_BUFFER_MINUTES)

        # Get entity IDs from the program's attributes
        program_state = self.hass.states.get(self._IC_PROGRAM_ENTITY)
        if not program_state:
            return False

        start_time_entity = program_state.attributes.get("start_time")
        duration_entity = program_state.attributes.get("default_run_time")

        if not start_time_entity or not duration_entity:
            if program_state.state == "on":
                _LOGGER.debug(
                    "Fallback: missing start_time/default_run_time attrs, program %s is on",
                    self._IC_PROGRAM_ENTITY,
                )
                return True
            return False

        start_state = self.hass.states.get(start_time_entity)
        duration_state = self.hass.states.get(duration_entity)

        if start_state and duration_state:
            try:
                # Parse start time (HH:MM:SS) into today's datetime
                parts = start_state.state.split(":")
                start_time = now.replace(
                    hour=int(parts[0]),
                    minute=int(parts[1]),
                    second=int(parts[2]) if len(parts) > 2 else 0,
                    microsecond=0,
                )

                # Parse duration (HH:MM:SS) into timedelta
                d_parts = duration_state.state.split(":")
                duration_td = timedelta(
                    hours=int(d_parts[0]),
                    minutes=int(d_parts[1]),
                    seconds=int(d_parts[2]) if len(d_parts) > 2 else 0,
                )

                window_start = start_time - buffer
                window_end = start_time + duration_td + buffer

                if window_start <= now <= window_end:
                    _LOGGER.debug(
                        "Inside irrigation window: %s to %s (now=%s)",
                        window_start.strftime("%H:%M"),
                        window_end.strftime("%H:%M"),
                        now.strftime("%H:%M"),
                    )
                    return True
                return False

            except (ValueError, TypeError, IndexError) as err:
                _LOGGER.debug("Could not parse irrigation window entities: %s", err)

        # Fallback: if we couldn't parse the time window, check if program is running
        if program_state.state == "on":
            _LOGGER.debug("Fallback: program switch %s is on", self._IC_PROGRAM_ENTITY)
            return True

        return False

    # --- Internal ---

    async def _async_update_data_from_store(self) -> None:
        """Update coordinator data from store for sensor consumption."""
        zones_data = {}
        zones = self._config.get(CONF_ZONES, [])
        for idx, zone_config in enumerate(zones):
            zone_id = f"zone_{idx + 1}"
            zones_data[zone_id] = self.store.get_zone_data(zone_id)

        retention = self._config.get(CONF_DATA_RETENTION_DAYS, DEFAULT_DATA_RETENTION_DAYS)
        history = self.store.get_weather_history(retention)
        forecast = self.store.get_forecast(2)

        # Use _current_conditions (set on each successful weather fetch) so the
        # sensor always shows the true observed reading rather than the
        # hour-bucket-deduped :00:00 model value from history.
        # Fall back to the most recent history entry on startup or when the
        # first fetch has not yet succeeded (e.g. network not ready after restart).
        current_temp = self._current_conditions.get("temperature")
        current_humidity = self._current_conditions.get("humidity")
        current_wind_speed = self._current_conditions.get("wind_speed")
        current_dew_point = self._current_conditions.get("dew_point")
        current_pressure = self._current_conditions.get("pressure")
        current_uv_index = self._current_conditions.get("uv_index")
        current_clouds = self._current_conditions.get("clouds")

        conditions_source = "live"
        conditions_observed_at = self._current_conditions.get("observed_at")
        if current_temp is None and history:
            latest = history[-1]
            current_temp = latest.get("temperature")
            current_humidity = latest.get("humidity")
            current_wind_speed = latest.get("wind_speed")
            current_dew_point = latest.get("dew_point")
            current_pressure = latest.get("pressure")
            current_uv_index = latest.get("uv_index")
            current_clouds = latest.get("clouds")
            conditions_source = "history_fallback"
            conditions_observed_at = latest.get("timestamp")
            _LOGGER.debug(
                "Using history fallback for current conditions: temp=%s°C from %s",
                current_temp, conditions_observed_at,
            )

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

        recent_logs = self._log_buffer.get_recent_logs() if self._log_buffer else []

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
            "rain_threshold_mm": self._config.get(
                CONF_RAIN_THRESHOLD_MM, DEFAULT_RAIN_THRESHOLD_MM
            ),
            "rain_light_effectiveness": self._config.get(
                CONF_RAIN_LIGHT_EFFECTIVENESS, DEFAULT_RAIN_LIGHT_EFFECTIVENESS
            ),
            "forecast_confidence": self._config.get(
                CONF_FORECAST_CONFIDENCE, DEFAULT_FORECAST_CONFIDENCE
            ),
            "history_entries": len(history),
            "forecast_entries": len(forecast),
            "rain_actual_mm": round(self.store.get_accumulated_rain_actual(retention), 2),
            "rain_forecast_mm": round(self.store.get_accumulated_rain_forecast(2), 2),
            "current_temp_c": current_temp,
            "current_humidity": current_humidity,
            "current_wind_speed_ms": current_wind_speed,
            "current_dew_point_c": current_dew_point,
            "current_pressure_hpa": current_pressure,
            "current_uv_index": current_uv_index,
            "current_clouds_pct": current_clouds,
            "conditions_source": conditions_source,
            "conditions_observed_at": conditions_observed_at,
            "last_watered": last_watered,
            "hours_since_watering": hours_since_watering,
            "recent_logs": recent_logs,
            "log_file_path": self._log_buffer.log_file_path if self._log_buffer else None,
        })

    async def _async_update_data(self) -> dict[str, Any]:
        """Required by DataUpdateCoordinator but not used (we push updates)."""
        return self.data or {}
