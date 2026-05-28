"""Irrigation calculation engine for Irrigation Planner.

Calculates ET (evapotranspiration), bucket percentage, and watering durations
with full transparency on how each factor affects the result.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any

from .const import (
    WEATHER_TEMPERATURE,
    WEATHER_HUMIDITY,
    WEATHER_WIND_SPEED,
    WEATHER_PRESSURE,
    WEATHER_DEW_POINT,
    WEATHER_PRECIP_ACTUAL,
    WEATHER_PRECIP_FORECAST,
    WEATHER_PRECIP_POP,
    WEATHER_UV_INDEX,
    WEATHER_CLOUDS,
    SUN_EXPOSURE_MULTIPLIER,
    SUN_FULL,
    SOIL_DRAINAGE_PCT_PER_DAY,
    SOIL_LOAM,
    PLANT_WATER_MULTIPLIER,
    PLANT_GRASS,
    BUCKET_MAX_PERCENT,
    BUCKET_MIN_PERCENT,
    BUCKET_IRRIGATION_THRESHOLD,
    BUCKET_TARGET_REFILL,
    CONF_ZONE_DURATION_MULTIPLIER,
    CONF_ZONE_MAX_DURATION_MINUTES,
    DEFAULT_DURATION_MULTIPLIER,
    DEFAULT_MAX_DURATION_MINUTES,
    DEFAULT_SPRINKLER_RATE_IN_PER_HR,
)

_LOGGER = logging.getLogger(__name__)

# Conversion constants
MM_TO_INCHES = 0.03937
INCHES_TO_MM = 25.4


def estimate_et_hargreaves(
    temp_max_c: float,
    temp_min_c: float,
    temp_mean_c: float,
    latitude_deg: float,
    day_of_year: int,
) -> float:
    """Estimate daily reference ET (ET0) using Hargreaves method.

    Returns ET0 in mm/day.
    This is simpler than Penman-Monteith but works well with limited data.
    """
    # Extraterrestrial radiation approximation
    lat_rad = math.radians(latitude_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
    delta = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)
    ws = math.acos(-math.tan(lat_rad) * math.tan(delta))

    # Ra in MJ/m2/day
    ra = (
        (24 * 60 / math.pi)
        * 0.0820
        * dr
        * (ws * math.sin(lat_rad) * math.sin(delta)
           + math.cos(lat_rad) * math.cos(delta) * math.sin(ws))
    )

    # Hargreaves equation: ET0 = 0.0023 * Ra * (Tmean + 17.8) * (Tmax - Tmin)^0.5
    temp_range = max(temp_max_c - temp_min_c, 0.1)
    et0 = 0.0023 * (ra * 0.408) * (temp_mean_c + 17.8) * math.sqrt(temp_range)

    return max(et0, 0.0)


def estimate_et_penman_simplified(
    temp_c: float,
    humidity: float,
    wind_speed_ms: float,
    pressure_hpa: float,
    dew_point_c: float | None,
    clouds_pct: float,
    latitude_deg: float,
    day_of_year: int,
    hours: float = 24.0,
) -> float:
    """Estimate ET using simplified Penman-Monteith for the given period.

    Returns ET in mm for the specified number of hours.
    Uses available data to get the best estimate possible.
    """
    # Saturation vapor pressure
    es = 0.6108 * math.exp(17.27 * temp_c / (temp_c + 237.3))

    # Actual vapor pressure from humidity or dew point
    if dew_point_c is not None:
        ea = 0.6108 * math.exp(17.27 * dew_point_c / (dew_point_c + 237.3))
    else:
        ea = es * humidity / 100.0

    # Slope of saturation vapor pressure curve
    delta_svp = 4098 * es / (temp_c + 237.3) ** 2

    # Psychrometric constant
    gamma = 0.665e-3 * pressure_hpa

    # Net radiation estimate from cloud cover
    lat_rad = math.radians(latitude_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
    solar_decl = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)
    ws = math.acos(
        max(-1, min(1, -math.tan(lat_rad) * math.tan(solar_decl)))
    )

    ra = (
        (24 * 60 / math.pi)
        * 0.0820
        * dr
        * (ws * math.sin(lat_rad) * math.sin(solar_decl)
           + math.cos(lat_rad) * math.cos(solar_decl) * math.sin(ws))
    )

    # Solar radiation estimate (reduced by cloud cover)
    rs = ra * (0.25 + 0.50 * (1 - clouds_pct / 100.0))

    # Net shortwave
    rns = 0.77 * rs

    # Net longwave (simplified)
    sigma = 4.903e-9  # Stefan-Boltzmann
    tk = temp_c + 273.16
    rnl = sigma * tk**4 * (0.34 - 0.14 * math.sqrt(ea)) * (1.35 * rs / (ra * 0.75 + 0.001) - 0.35)
    rnl = max(rnl, 0)

    rn = rns - rnl
    g = 0  # soil heat flux approx 0 for daily

    # FAO56 Penman-Monteith reference ET
    wind_2m = wind_speed_ms  # assume already at 2m
    numerator = 0.408 * delta_svp * (rn - g) + gamma * (900 / (temp_c + 273)) * wind_2m * (es - ea)
    denominator = delta_svp + gamma * (1 + 0.34 * wind_2m)

    et0_daily = max(numerator / denominator, 0.0) if denominator > 0 else 0.0

    # Scale to hours
    et0 = et0_daily * (hours / 24.0)

    return et0


class IrrigationCalculator:
    """Calculate irrigation needs with full transparency."""

    def __init__(self, latitude: float, longitude: float) -> None:
        """Initialize calculator."""
        self._lat = latitude
        self._lon = longitude

    def calculate_zone(
        self,
        zone_config: dict[str, Any],
        zone_data: dict[str, Any],
        weather_history: list[dict[str, Any]],
        weather_forecast: list[dict[str, Any]],
        rain_threshold_mm: float = 5.0,
        rain_light_effectiveness: float = 50.0,
        forecast_confidence: float = 50.0,
        last_watered: str | None = None,
    ) -> dict[str, Any]:
        """Calculate irrigation for a single zone.

        Args:
            zone_config: Zone configuration (area, sun, soil, plant, sprinkler rate)
            zone_data: Current zone state (bucket_percent, etc.)
            weather_history: Actual weather data from last 2 days
            weather_forecast: Forecast data for next 2 days
            last_watered: ISO timestamp when zone was last watered (global)

        Returns:
            Dict with calculation results and factor breakdown.
        """
        now = datetime.now()
        doy = now.timetuple().tm_yday

        # Filter weather history to only include data since last watering.
        # This applies ET only for time periods after water was actually applied.
        original_history = weather_history  # Keep reference for fallback
        if last_watered:
            try:
                last_watered_dt = datetime.fromisoformat(last_watered)
                # Only include weather entries after last watering
                filtered_history = [
                    e for e in weather_history
                    if e.get("timestamp") and datetime.fromisoformat(e["timestamp"]) > last_watered_dt
                ]
                # If we have filtered data, use it; otherwise fall back to
                # all available history (e.g., after restart when last_watered
                # is very recent but weather updates were missed)
                if filtered_history:
                    weather_history = filtered_history
                else:
                    _LOGGER.debug(
                        "No new weather data since %s, using all %d entries",
                        last_watered, len(original_history)
                    )
                    weather_history = original_history
            except (ValueError, TypeError):
                pass  # Use full history if parsing fails

        # Get zone parameters
        sun_exposure = zone_config.get("sun_exposure", SUN_FULL)
        soil_type = zone_config.get("soil_type", SOIL_LOAM)
        plant_type = zone_config.get("plant_type", PLANT_GRASS)
        sprinkler_rate = float(zone_config.get("sprinkler_rate_in_per_hr", 1.0) or 0.0)
        max_duration = max(
            1,
            int(zone_config.get(CONF_ZONE_MAX_DURATION_MINUTES, DEFAULT_MAX_DURATION_MINUTES) or DEFAULT_MAX_DURATION_MINUTES),
        )
        duration_multiplier = max(
            0.0,
            float(zone_config.get(CONF_ZONE_DURATION_MULTIPLIER, DEFAULT_DURATION_MULTIPLIER) or DEFAULT_DURATION_MULTIPLIER),
        )

        # Current bucket
        # When we filter weather from last_watered, we're recalculating the
        # full moisture loss since watering.  The bucket was 100% at that
        # moment, so we must start from 100% — not the already-reduced
        # stored value which would compound losses across hourly calcs.
        if last_watered and weather_history is not original_history:
            old_bucket = BUCKET_MAX_PERCENT
        else:
            old_bucket = zone_data.get("bucket_percent", 0.0)

        # --- Calculate ET from weather history ---
        et_total_mm = 0.0
        hours_spanned = 0.0
        if weather_history:
            avg_temp = self._avg(weather_history, WEATHER_TEMPERATURE, 20.0)
            avg_humidity = self._avg(weather_history, WEATHER_HUMIDITY, 50.0)
            avg_wind = self._avg(weather_history, WEATHER_WIND_SPEED, 2.0)
            avg_pressure = self._avg(weather_history, WEATHER_PRESSURE, 1013.0)
            avg_dew_point = self._avg(weather_history, WEATHER_DEW_POINT, None)
            avg_clouds = self._avg(weather_history, WEATHER_CLOUDS, 50.0)

            # Calculate hours spanned by data
            timestamps = [
                e.get("timestamp", "") for e in weather_history if e.get("timestamp")
            ]
            if len(timestamps) >= 2:
                first = datetime.fromisoformat(min(timestamps))
                last = datetime.fromisoformat(max(timestamps))
                hours_spanned = max((last - first).total_seconds() / 3600, 1.0)
            else:
                hours_spanned = 1.0  # single data point, assume 1 hour

            et_total_mm = estimate_et_penman_simplified(
                temp_c=avg_temp,
                humidity=avg_humidity,
                wind_speed_ms=avg_wind,
                pressure_hpa=avg_pressure,
                dew_point_c=avg_dew_point,
                clouds_pct=avg_clouds,
                latitude_deg=self._lat,
                day_of_year=doy,
                hours=hours_spanned,
            )
        elif last_watered:
            # No new weather data but we know when last watered — use actual elapsed time
            try:
                hours_spanned = max(
                    (now - datetime.fromisoformat(last_watered)).total_seconds() / 3600,
                    0.0,
                )
            except (ValueError, TypeError):
                hours_spanned = 0.0

        et_total_inches = et_total_mm * MM_TO_INCHES

        # --- Apply zone multipliers ---
        sun_mult = SUN_EXPOSURE_MULTIPLIER.get(sun_exposure, 1.0)
        plant_mult = PLANT_WATER_MULTIPLIER.get(plant_type, 0.8)
        adjusted_et_inches = et_total_inches * sun_mult * plant_mult

        # --- Actual rain (last 2 days) ---
        rain_actual_mm = sum(
            e.get(WEATHER_PRECIP_ACTUAL, 0.0) for e in weather_history
        )
        # Apply non-linear effectiveness: light rain below threshold is less effective
        # (e.g., drizzle evaporates quickly or runs off)
        light_effectiveness_frac = rain_light_effectiveness / 100.0
        if rain_actual_mm <= rain_threshold_mm:
            effective_rain_actual_mm = rain_actual_mm * light_effectiveness_frac
        else:
            # Rain above threshold: first part at reduced rate, remainder at 100%
            effective_rain_actual_mm = (
                rain_threshold_mm * light_effectiveness_frac
                + (rain_actual_mm - rain_threshold_mm)
            )
        rain_actual_inches = effective_rain_actual_mm * MM_TO_INCHES

        # --- Forecast rain (next 2 days) ---
        # Step 1: Weight each entry's precipitation by OWM probability of precipitation (pop).
        # pop=0.0 means no chance of rain, pop=1.0 means certain rain.
        # Entries without pop (old storage data) default to 1.0 (no discount).
        rain_forecast_mm = sum(
            e.get(WEATHER_PRECIP_FORECAST, 0.0) * e.get(WEATHER_PRECIP_POP, 1.0)
            for e in weather_forecast
        )
        rain_forecast_raw_mm = sum(
            e.get(WEATHER_PRECIP_FORECAST, 0.0) for e in weather_forecast
        )
        avg_pop = (
            sum(e.get(WEATHER_PRECIP_POP, 1.0) for e in weather_forecast) / len(weather_forecast)
            if weather_forecast else 1.0
        )
        rain_forecast_inches = rain_forecast_mm * MM_TO_INCHES

        # Step 2: Apply user-configurable confidence on top of pop-weighted rain.
        # pop captures OWM model uncertainty; forecast_confidence is an additional user discount.
        forecast_confidence_frac = forecast_confidence / 100.0
        effective_forecast_inches = rain_forecast_inches * forecast_confidence_frac

        # Derive bucket capacity from zone's max_duration and sprinkler_rate
        # so that 100% deficit = exactly max_duration minutes of watering
        # This makes proportional scaling intuitive: 50% deficit = 50% duration
        if sprinkler_rate > 0:
            bucket_rate = sprinkler_rate
        else:
            bucket_rate = DEFAULT_SPRINKLER_RATE_IN_PER_HR
            _LOGGER.warning(
                "Invalid sprinkler_rate %.3f for zone %s; using %.2f in/hr for bucket math",
                sprinkler_rate,
                zone_config.get("name", "unknown"),
                bucket_rate,
            )
        bucket_capacity_inches = (max_duration / 60.0) * bucket_rate

        # --- Drainage ---
        # Drainage is a percentage of bucket lost per day, scaled by current level
        drainage_pct_per_day = SOIL_DRAINAGE_PCT_PER_DAY.get(soil_type, 10.0)
        days_elapsed = hours_spanned / 24.0
        drainage_source_pct = max(0.0, min(old_bucket, 100.0))
        drainage_pct = drainage_pct_per_day * days_elapsed * (drainage_source_pct / 100.0)
        drainage_inches = (drainage_pct / 100.0) * bucket_capacity_inches

        # --- Net change in bucket ---
        # Positive = gaining moisture, negative = losing moisture
        # Forecast rain is NOT added to bucket moisture (option 2 behavior).
        # It is only applied later as a reduction to irrigation duration.
        moisture_gain = rain_actual_inches
        moisture_loss = adjusted_et_inches + drainage_inches
        net_change_inches = moisture_gain - moisture_loss
        net_change_pct = (net_change_inches / bucket_capacity_inches) * 100.0

        new_bucket = max(
            -100.0,  # allow negative to indicate deficit
            min(BUCKET_MAX_PERCENT, old_bucket + net_change_pct)
        )

        # --- Duration calculation ---
        # Calculate duration proportional to deficit from 100% (fully watered)
        # 100% bucket -> 0% deficit -> 0 min
        # 50% bucket -> 50% deficit -> half duration
        # 0% bucket -> 100% deficit -> full duration
        # Negative bucket -> >100% deficit -> extra watering to recover
        deficit_pct = max(0, BUCKET_TARGET_REFILL - new_bucket)  # deficit from fully-watered
        deficit_inches = (deficit_pct / 100.0) * bucket_capacity_inches

        # Apply forecast only to duration (not bucket).
        # Forecast can reduce irrigation need, but never below zero.
        forecast_duration_offset_inches = min(
            deficit_inches,
            max(0.0, effective_forecast_inches),
        )
        adjusted_deficit_inches = max(0.0, deficit_inches - forecast_duration_offset_inches)

        # Pre-forecast duration (what irrigation would be without forecast reduction)
        pre_forecast_duration = 0.0
        if sprinkler_rate > 0:
            pre_forecast_duration = (deficit_inches / sprinkler_rate) * 60
        pre_forecast_duration *= duration_multiplier
        pre_forecast_duration = min(pre_forecast_duration, max_duration)

        duration_minutes = 0.0
        if sprinkler_rate > 0:
            duration_minutes = (adjusted_deficit_inches / sprinkler_rate) * 60
        # Apply user multiplier
        duration_minutes *= duration_multiplier
        # Cap at max duration
        duration_minutes = min(duration_minutes, max_duration)
        # Minimum practical threshold: below 1 minute is not useful
        if duration_minutes < 1.0:
            duration_minutes = 0.0

        # --- Factor breakdown (impact on bucket in %) ---
        et_impact_pct = -(adjusted_et_inches / bucket_capacity_inches) * 100
        rain_actual_impact_pct = (rain_actual_inches / bucket_capacity_inches) * 100
        rain_forecast_impact_pct = 0.0  # forecast does not alter bucket moisture
        drainage_impact_pct = -(drainage_inches / bucket_capacity_inches) * 100
        sun_impact_pct = et_impact_pct * (1 - sun_mult) / sun_mult if sun_mult != 1.0 and sun_mult > 0 else 0
        temp_impact_pct = et_impact_pct  # ET is primarily temp-driven

        result = {
            "bucket_percent": round(new_bucket, 1),
            "old_bucket_percent": round(old_bucket, 1),
            "duration_minutes": round(duration_minutes, 1),
            "pre_forecast_duration_minutes": round(pre_forecast_duration, 1),
            "forecast_duration_offset_minutes": round(
                max(0.0, pre_forecast_duration - duration_minutes),
                1,
            ),
            "last_calculated": now.isoformat(),
            "hours_of_data": round(hours_spanned, 1),

            # Absolute values
            "et_inches": round(adjusted_et_inches, 4),
            "et_mm": round(adjusted_et_inches * INCHES_TO_MM, 2),
            "rain_actual_raw_mm": round(rain_actual_mm, 2),
            "rain_actual_mm": round(effective_rain_actual_mm, 2),
            "rain_actual_inches": round(rain_actual_inches, 4),
            "rain_forecast_mm": round(rain_forecast_mm, 2),
            "rain_forecast_inches": round(rain_forecast_inches, 4),
            "effective_forecast_inches": round(effective_forecast_inches, 4),
            "forecast_duration_offset_inches": round(forecast_duration_offset_inches, 4),
            "drainage_inches": round(drainage_inches, 4),
            "net_change_inches": round(net_change_inches, 4),
            "net_change_percent": round(net_change_pct, 1),

            # Factor breakdown (% impact on bucket)
            "factors": {
                "evapotranspiration": round(et_impact_pct, 1),
                "rain_actual": round(rain_actual_impact_pct, 1),
                "rain_forecast": round(rain_forecast_impact_pct, 1),
                "drainage": round(drainage_impact_pct, 1),
                "sun_exposure": f"{sun_exposure} ({sun_mult}x)",
                "soil_type": f"{zone_config.get('soil_type', SOIL_LOAM)} ({drainage_pct_per_day}%/day)",
                "plant_type": f"{plant_type} ({plant_mult}x)",
            },

            # Weather summary
            "weather_summary": {
                "avg_temp_c": round(self._avg(weather_history, WEATHER_TEMPERATURE, 20), 1) if weather_history else None,
                "avg_humidity": round(self._avg(weather_history, WEATHER_HUMIDITY, 50), 0) if weather_history else None,
                "avg_wind_ms": round(self._avg(weather_history, WEATHER_WIND_SPEED, 2), 1) if weather_history else None,
                "data_points": len(weather_history),
                "forecast_points": len(weather_forecast),
            },

            # Human-readable explanation
            "explanation": self._build_explanation(
                old_bucket, new_bucket, adjusted_et_inches, rain_actual_inches,
                rain_forecast_raw_mm * MM_TO_INCHES, rain_forecast_inches,
                effective_forecast_inches,
                forecast_duration_offset_inches, forecast_confidence,
                avg_pop,
                drainage_inches,
                net_change_inches, net_change_pct,
                pre_forecast_duration, duration_minutes,
                sun_exposure, sun_mult, soil_type, plant_type, plant_mult,
                hours_spanned, len(weather_history),
            ),
        }

        _LOGGER.info(
            "Zone calc: bucket %.1f%% -> %.1f%%, ET=%.3f in, rain=%.3f in, duration=%.1f min",
            old_bucket, new_bucket, adjusted_et_inches, rain_actual_inches, duration_minutes,
        )

        return result

    def _avg(self, data: list[dict], key: str, default: float | None) -> float | None:
        """Calculate average of a key across data entries."""
        values = [e[key] for e in data if key in e and e[key] is not None]
        if not values:
            return default
        return sum(values) / len(values)

    def _build_explanation(
        self,
        old_bucket, new_bucket, et_inches, rain_actual,
        rain_forecast_raw, rain_forecast_pop_weighted,
        effective_forecast, forecast_duration_offset, forecast_confidence,
        avg_pop,
        drainage, net_change, net_change_pct,
        pre_forecast_duration, duration,
        sun_exposure, sun_mult, soil_type, plant_type,
        plant_mult, hours, data_points,
    ) -> str:
        """Build human-readable explanation of the calculation."""
        lines = []
        lines.append(f"Calculation based on {data_points} weather data points over {hours:.1f} hours.")
        lines.append("")
        lines.append("Water Loss:")
        lines.append(f"  ET (evapotranspiration): -{et_inches:.4f} inches")
        lines.append(f"    Sun: {sun_exposure} ({sun_mult}x multiplier)")
        lines.append(f"    Plant: {plant_type} ({plant_mult}x multiplier)")
        lines.append(f"  Drainage ({soil_type} soil): -{drainage:.4f} inches")
        lines.append("")
        lines.append("Water Gain (bucket):")
        lines.append(f"  Actual rain (2 days): +{rain_actual:.4f} inches ({rain_actual * INCHES_TO_MM:.2f} mm)")
        lines.append("")
        lines.append("Forecast Adjustment (duration only):")
        lines.append(f"  Forecast rain (2 days): +{rain_forecast_raw:.4f} inches ({rain_forecast_raw * INCHES_TO_MM:.2f} mm) raw")
        lines.append(f"    OWM probability (avg pop {avg_pop * 100:.0f}%): +{rain_forecast_pop_weighted:.4f} inches")
        lines.append(f"    User confidence ({forecast_confidence:.0f}%): +{effective_forecast:.4f} inches")
        lines.append(f"    Applied to irrigation reduction: -{forecast_duration_offset:.4f} inches")
        lines.append("")
        lines.append(f"Net change (bucket): {net_change:+.4f} inches ({net_change_pct:+.1f}%)")
        lines.append(f"Bucket: {old_bucket:.1f}% -> {new_bucket:.1f}%")
        lines.append("")
        if pre_forecast_duration > 0:
            lines.append(f"Irrigation need (before forecast): {pre_forecast_duration:.1f} minutes")
        if duration > 0:
            lines.append(f"IRRIGATION NEEDED: {duration:.1f} minutes")
        elif pre_forecast_duration > 0:
            lines.append(f"Irrigation reduced to 0 by forecast rain.")
        else:
            lines.append("No irrigation needed.")

        return "\n".join(lines)
