"""Weather data collector for Irrigation Planner.

Supports multiple weather services:
- National Weather Service (NWS) - US only, free, no API key
- OpenWeatherMap (OWM) - Global, requires API key
"""
from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant

from .const import (
    OWM_BASE_URL,
    OWM_HISTORY_URL,
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
    WEATHER_TIMESTAMP,
    WEATHER_SOURCE,
)

_LOGGER = logging.getLogger(__name__)


class WeatherService(ABC):
    """Abstract base class for weather data collectors."""

    @abstractmethod
    async def async_fetch_current_and_forecast(self) -> dict[str, Any]:
        """Fetch current weather and forecast.

        Returns dict with keys:
            - "current": dict of current weather data
            - "hourly_history": list of past hourly entries (actual rain)
            - "hourly_forecast": list of future hourly entries (forecast)
            - "daily_forecast": list of daily forecast entries
        """
        pass

    async def async_fetch_history(self, dt: datetime) -> list[dict[str, Any]]:
        """Fetch historical weather entries for a specific date.

        Default returns empty list; providers that support history backfill
        override this method.
        """
        return []


class OWMWeatherCollector(WeatherService):
    """Collect weather data from OpenWeatherMap One Call API 3.0."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_key: str,
        latitude: float,
        longitude: float,
    ) -> None:
        """Initialize OWM weather collector."""
        self._hass = hass
        self._api_key = api_key
        self._lat = latitude
        self._lon = longitude

    async def async_fetch_current_and_forecast(self) -> dict[str, Any]:
        """Fetch current weather and 48-hour forecast from OWM One Call 3.0."""
        url = (
            f"{OWM_BASE_URL}"
            f"?lat={self._lat}&lon={self._lon}"
            f"&appid={self._api_key}"
            f"&units=metric"
            f"&exclude=minutely,alerts"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        _LOGGER.error(
                            "OWM API error %s: %s", resp.status, text[:200]
                        )
                        return {}
                    data = await resp.json()
        except Exception as err:
            _LOGGER.error("Failed to fetch OWM data: %s", err)
            return {}

        result = {"current": None, "hourly_history": [], "hourly_forecast": [], "daily_forecast": []}

        # Parse current weather
        if "current" in data:
            c = data["current"]
            rain_1h = c.get("rain", {}).get("1h", 0.0) if isinstance(c.get("rain"), dict) else 0.0
            snow_1h = c.get("snow", {}).get("1h", 0.0) if isinstance(c.get("snow"), dict) else 0.0

            result["current"] = {
                WEATHER_TEMPERATURE: c.get("temp"),
                WEATHER_HUMIDITY: c.get("humidity"),
                WEATHER_WIND_SPEED: c.get("wind_speed"),
                WEATHER_PRESSURE: c.get("pressure"),
                WEATHER_DEW_POINT: c.get("dew_point"),
                WEATHER_PRECIP_ACTUAL: rain_1h + snow_1h,
                WEATHER_UV_INDEX: c.get("uvi"),
                WEATHER_CLOUDS: c.get("clouds"),
                WEATHER_TIMESTAMP: datetime.fromtimestamp(c["dt"]).isoformat(),
                WEATHER_SOURCE: "actual",
            }

        # Parse hourly data (48 hours).
        # OWM hourly includes past hours (actual rain) and future hours (forecast).
        # Split by current time: past -> hourly_history, future -> hourly_forecast.
        now_ts = datetime.now().timestamp()
        for h in data.get("hourly", []):
            rain_1h = h.get("rain", {}).get("1h", 0.0) if isinstance(h.get("rain"), dict) else 0.0
            snow_1h = h.get("snow", {}).get("1h", 0.0) if isinstance(h.get("snow"), dict) else 0.0

            if h["dt"] <= now_ts:
                result["hourly_history"].append({
                    WEATHER_TEMPERATURE: h.get("temp"),
                    WEATHER_HUMIDITY: h.get("humidity"),
                    WEATHER_WIND_SPEED: h.get("wind_speed"),
                    WEATHER_PRESSURE: h.get("pressure"),
                    WEATHER_DEW_POINT: h.get("dew_point"),
                    WEATHER_PRECIP_ACTUAL: rain_1h + snow_1h,
                    WEATHER_UV_INDEX: h.get("uvi"),
                    WEATHER_CLOUDS: h.get("clouds"),
                    WEATHER_TIMESTAMP: datetime.fromtimestamp(h["dt"]).isoformat(),
                    WEATHER_SOURCE: "actual",
                })
            else:
                result["hourly_forecast"].append({
                    WEATHER_TEMPERATURE: h.get("temp"),
                    WEATHER_HUMIDITY: h.get("humidity"),
                    WEATHER_WIND_SPEED: h.get("wind_speed"),
                    WEATHER_PRESSURE: h.get("pressure"),
                    WEATHER_DEW_POINT: h.get("dew_point"),
                    WEATHER_PRECIP_FORECAST: rain_1h + snow_1h,
                    WEATHER_PRECIP_POP: h.get("pop", 1.0),
                    WEATHER_UV_INDEX: h.get("uvi"),
                    WEATHER_CLOUDS: h.get("clouds"),
                    WEATHER_TIMESTAMP: datetime.fromtimestamp(h["dt"]).isoformat(),
                    WEATHER_SOURCE: "forecast",
                })

        # Parse daily forecast (8 days)
        for d in data.get("daily", []):
            rain_mm = d.get("rain", 0.0)
            snow_mm = d.get("snow", 0.0)

            result["daily_forecast"].append({
                WEATHER_TEMPERATURE: d.get("temp", {}).get("day"),
                "temp_min": d.get("temp", {}).get("min"),
                "temp_max": d.get("temp", {}).get("max"),
                WEATHER_HUMIDITY: d.get("humidity"),
                WEATHER_WIND_SPEED: d.get("wind_speed"),
                WEATHER_PRESSURE: d.get("pressure"),
                WEATHER_DEW_POINT: d.get("dew_point"),
                WEATHER_PRECIP_FORECAST: rain_mm + snow_mm,
                WEATHER_PRECIP_POP: d.get("pop", 1.0),
                WEATHER_UV_INDEX: d.get("uvi"),
                WEATHER_CLOUDS: d.get("clouds"),
                WEATHER_TIMESTAMP: datetime.fromtimestamp(d["dt"]).isoformat(),
                WEATHER_SOURCE: "daily_forecast",
            })

        _LOGGER.debug(
            "Fetched OWM data: current=%s, hourly_history=%d, hourly_forecast=%d, daily=%d",
            result["current"] is not None,
            len(result["hourly_history"]),
            len(result["hourly_forecast"]),
            len(result["daily_forecast"]),
        )
        return result

    async def async_fetch_history(self, dt: datetime) -> list[dict[str, Any]]:
        """Fetch hourly history for a date using OWM timemachine API."""
        # Request at noon of the target day so the timemachine response
        # covers the full 24-hour window around that date.
        target_ts = int(dt.replace(hour=12, minute=0, second=0, microsecond=0).timestamp())
        url = (
            f"{OWM_HISTORY_URL}"
            f"?lat={self._lat}&lon={self._lon}"
            f"&dt={target_ts}"
            f"&appid={self._api_key}"
            f"&units=metric"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        _LOGGER.error(
                            "OWM timemachine error %s: %s",
                            resp.status, (await resp.text())[:200],
                        )
                        return []
                    data = await resp.json()
        except Exception as err:
            _LOGGER.error("OWM timemachine fetch failed: %s", err)
            return []

        entries = []
        for h in data.get("data", []):
            rain_1h = h.get("rain", {}).get("1h", 0.0) if isinstance(h.get("rain"), dict) else 0.0
            snow_1h = h.get("snow", {}).get("1h", 0.0) if isinstance(h.get("snow"), dict) else 0.0
            entries.append({
                WEATHER_TEMPERATURE: h.get("temp"),
                WEATHER_HUMIDITY: h.get("humidity"),
                WEATHER_WIND_SPEED: h.get("wind_speed"),
                WEATHER_PRESSURE: h.get("pressure"),
                WEATHER_DEW_POINT: h.get("dew_point"),
                WEATHER_PRECIP_ACTUAL: rain_1h + snow_1h,
                WEATHER_UV_INDEX: h.get("uvi"),
                WEATHER_CLOUDS: h.get("clouds"),
                WEATHER_TIMESTAMP: datetime.fromtimestamp(h["dt"]).isoformat(),
                WEATHER_SOURCE: "actual",
            })
        return entries


class NWSWeatherCollector(WeatherService):
    """Collect weather data from National Weather Service API.

    NWS is US-only, free, and requires no API key.
    Data source: https://api.weather.gov

    Flow:
      1. /points/{lat},{lon}          -> grid info + station list URL
      2. {observationStations}        -> nearest station ID (cached)
      3. /stations/{id}/observations  -> actual past observations (history + current)
      4. {forecastHourly}             -> future hourly forecast
    """

    # Map NWS cloud-layer amount codes to approximate percentage coverage
    _CLOUD_COVERAGE: dict[str, int] = {
        "SKC": 0, "CLR": 0, "FEW": 15, "SCT": 38, "BKN": 75, "OVC": 100, "VV": 100,
    }

    def __init__(
        self,
        hass: HomeAssistant,
        latitude: float,
        longitude: float,
    ) -> None:
        """Initialize NWS weather collector."""
        self._hass = hass
        self._lat = latitude
        self._lon = longitude
        self._user_agent = "homeassistant-irrigation-planner/1.0"
        self._base_url = "https://api.weather.gov"
        # Cached from /points endpoint — re-fetched when None
        self._forecast_hourly_url: str | None = None
        self._observation_stations_url: str | None = None
        self._station_id: str | None = None
        self._wfo: str | None = None
        self._grid_x: int | None = None
        self._grid_y: int | None = None

    # ------------------------------------------------------------------
    # Unit conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _nws_val(field: Any, target: str) -> float | None:
        """Extract and convert a NWS quantity field.

        NWS returns quantities as {"unitCode": "wmoUnit:X", "value": Y}.
        Strips the "wmoUnit:" / "unit:" namespace prefix before comparing.
        """
        if not isinstance(field, dict):
            return None
        raw = field.get("value")
        if raw is None:
            return None
        v = float(raw)
        unit = field.get("unitCode", "").split(":")[-1]  # e.g. "Pa" from "wmoUnit:Pa"

        if target == "degC":
            return (v - 32.0) * 5.0 / 9.0 if unit == "degF" else v
        if target == "hPa":
            return v / 100.0 if unit == "Pa" else v
        if target == "m_s":
            if unit == "km_h-1":
                return v / 3.6
            if unit in ("mph", "mi_h-1"):
                return v * 0.44704
            return v  # wmoUnit:m_s-1 or unknown → assume m/s
        if target == "mm":
            return v * 25.4 if unit in ("in", "[in_i]") else v
        return v

    @staticmethod
    def _parse_forecast_wind(wind: Any) -> float | None:
        """Parse NWS hourly forecast windSpeed to m/s.

        The forecastHourly endpoint returns windSpeed as a plain string
        ("10 mph", "10 to 15 mph") rather than the structured dict used
        by the observations endpoint.
        """
        if isinstance(wind, dict):
            raw = wind.get("value")
            if raw is None:
                return None
            v = float(raw)
            unit = wind.get("unitCode", "").split(":")[-1]
            if unit == "km_h-1":
                return v / 3.6
            if unit in ("mph", "mi_h-1"):
                return v * 0.44704
            return v
        if isinstance(wind, str):
            parts = wind.split()
            try:
                v = float(parts[0])
            except (ValueError, IndexError):
                return None
            unit = parts[-1].lower() if len(parts) > 1 else "mph"
            if unit == "mph":
                return v * 0.44704
            if unit in ("km/h", "kph"):
                return v / 3.6
            return v
        return None

    # ------------------------------------------------------------------
    # QPF helpers — gridded quantitative precipitation forecast
    # ------------------------------------------------------------------

    @staticmethod
    def _to_local_naive_iso(dt: datetime) -> str:
        """Convert a datetime to a naive-local ISO string.

        NWS returns timezone-aware UTC, but the rest of the system (OWM
        collector, last_watered, datetime.now(), the store's string-based
        forecast-window and hour-dedup logic) uses naive-local timestamps.
        Normalizing here keeps storage consistent and avoids tz-mixing.
        """
        if dt.tzinfo is not None:
            dt = dt.astimezone()  # convert to system-local tz
        return dt.replace(tzinfo=None).isoformat()

    @staticmethod
    def _parse_iso_duration(duration_str: str) -> timedelta:
        """Parse an ISO 8601 duration string (e.g. PT1H, PT6H) to timedelta."""
        m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", duration_str)
        if not m:
            return timedelta(hours=1)
        return timedelta(
            hours=int(m.group(1) or 0),
            minutes=int(m.group(2) or 0),
            seconds=int(m.group(3) or 0),
        )

    @classmethod
    def _expand_grid_values(cls, values: list) -> dict[str, float]:
        """Expand NWS gridded time-series (variable intervals) to a per-hour dict.

        NWS encodes each value as::

            {"validTime": "2024-01-15T06:00:00+00:00/PT6H", "value": 12.7}

        meaning 12.7 mm total over 6 hours.  This distributes the total equally
        over each hour in the interval and returns a dict keyed by UTC hour
        string ``YYYYMMDDHH`` → mm/h.
        """
        hour_map: dict[str, float] = {}
        for entry in values:
            valid_time = entry.get("validTime", "")
            raw_value = entry.get("value")
            if raw_value is None or "/" not in valid_time:
                continue
            time_str, duration_str = valid_time.split("/", 1)
            try:
                start_dt = datetime.fromisoformat(
                    time_str.replace("Z", "+00:00")
                ).astimezone(timezone.utc)
                duration = cls._parse_iso_duration(duration_str)
            except (ValueError, AttributeError):
                continue
            n_hours = max(1, round(duration.total_seconds() / 3600))
            per_hour = float(raw_value) / n_hours
            for h in range(n_hours):
                key = (start_dt + timedelta(hours=h)).strftime("%Y%m%d%H")
                hour_map[key] = per_hour
        return hour_map

    async def _async_fetch_gridded_qpf(
        self, session: aiohttp.ClientSession
    ) -> dict[str, float]:
        """Fetch quantitative precipitation forecast from the NWS gridded endpoint.

        Returns a dict of UTC-hour key (``YYYYMMDDHH``) → mm/hour so callers
        can look up QPF for any forecast period by its UTC hour.
        Returns an empty dict on any error (QPF is best-effort).
        """
        if not (self._wfo and self._grid_x is not None and self._grid_y is not None):
            return {}

        url = f"{self._base_url}/gridpoints/{self._wfo}/{self._grid_x},{self._grid_y}"
        headers = {"User-Agent": self._user_agent, "Accept": "application/geo+json"}
        try:
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("NWS gridded data error %s (QPF unavailable)", resp.status)
                    return {}
                data = await resp.json()
        except Exception as err:
            _LOGGER.warning("NWS gridded QPF fetch failed: %s", err)
            return {}

        qpf_entries = (
            data.get("properties", {})
            .get("quantitativePrecipitation", {})
            .get("values", [])
        )
        qpf = self._expand_grid_values(qpf_entries)
        _LOGGER.debug("NWS gridded QPF: %d hourly buckets fetched", len(qpf))
        return qpf

    # ------------------------------------------------------------------
    # Grid / station bootstrapping (cached after first call)
    # ------------------------------------------------------------------

    async def _async_ensure_grid_info(self, session: aiohttp.ClientSession) -> bool:
        """Populate forecast and station URLs from /points if not already cached."""
        if self._forecast_hourly_url and self._observation_stations_url:
            return True

        url = f"{self._base_url}/points/{self._lat:.4f},{self._lon:.4f}"
        headers = {"User-Agent": self._user_agent, "Accept": "application/geo+json"}
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    _LOGGER.error(
                        "NWS Points API error %s: %s",
                        resp.status, (await resp.text())[:200],
                    )
                    return False
                props = (await resp.json()).get("properties", {})
        except Exception as err:
            _LOGGER.error("NWS Points API failed: %s", err)
            return False

        self._forecast_hourly_url = props.get("forecastHourly")
        self._observation_stations_url = props.get("observationStations")
        self._wfo = props.get("cwa")
        self._grid_x = props.get("gridX")
        self._grid_y = props.get("gridY")

        if not self._forecast_hourly_url or not self._observation_stations_url:
            _LOGGER.error(
                "NWS: Missing forecastHourly or observationStations in points response"
            )
            return False
        return True

    async def _async_ensure_station(self, session: aiohttp.ClientSession) -> str | None:
        """Return the nearest observation station ID, fetching it if needed."""
        if self._station_id:
            return self._station_id
        if not self._observation_stations_url:
            return None

        headers = {"User-Agent": self._user_agent, "Accept": "application/geo+json"}
        try:
            async with session.get(
                self._observation_stations_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.error("NWS stations list error %s", resp.status)
                    return None
                features = (await resp.json()).get("features", [])
        except Exception as err:
            _LOGGER.error("NWS stations list failed: %s", err)
            return None

        if not features:
            _LOGGER.error("NWS: No observation stations returned for this location")
            return None

        self._station_id = features[0].get("properties", {}).get("stationIdentifier")
        if not self._station_id:
            _LOGGER.error("NWS: Could not parse stationIdentifier from stations response")
        else:
            _LOGGER.debug("NWS: Using observation station %s", self._station_id)
        return self._station_id

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    def _parse_observations(self, data: dict) -> list[dict[str, Any]]:
        """Parse NWS station observations GeoJSON into weather history entries.

        NWS returns observations newest-first; this method sorts oldest-first.
        """
        entries = []
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            ts_str = props.get("timestamp")
            if not ts_str:
                continue
            try:
                period_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except ValueError:
                continue

            # Cloud cover: pick highest layer coverage reported
            clouds: int | None = None
            cloud_layers = props.get("cloudLayers") or []
            if cloud_layers:
                clouds = max(
                    (self._CLOUD_COVERAGE.get(layer.get("amount", ""), 0) for layer in cloud_layers),
                    default=None,
                )

            precip_mm = self._nws_val(props.get("precipitationLastHour"), "mm") or 0.0

            entries.append({
                WEATHER_TEMPERATURE: self._nws_val(props.get("temperature"), "degC"),
                WEATHER_HUMIDITY: self._nws_val(props.get("relativeHumidity"), "percent"),
                WEATHER_WIND_SPEED: self._nws_val(props.get("windSpeed"), "m_s"),
                WEATHER_PRESSURE: self._nws_val(props.get("barometricPressure"), "hPa"),
                WEATHER_DEW_POINT: self._nws_val(props.get("dewpoint"), "degC"),
                WEATHER_PRECIP_ACTUAL: precip_mm,
                WEATHER_UV_INDEX: None,
                WEATHER_CLOUDS: clouds,
                WEATHER_TIMESTAMP: self._to_local_naive_iso(period_dt),
                WEATHER_SOURCE: "actual",
            })

        entries.sort(key=lambda e: e[WEATHER_TIMESTAMP])
        return entries

    def _parse_hourly_forecast(
        self,
        data: dict,
        qpf_by_hour: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        """Parse NWS forecastHourly periods into forecast entries.

        ``qpf_by_hour`` is a ``YYYYMMDDHH`` → mm/hour dict from the gridded
        endpoint.  When absent, precipitation amounts default to 0.
        """
        now_utc = datetime.now(tz=timezone.utc)
        entries = []

        for period in data.get("properties", {}).get("periods", []):
            start_time = period.get("startTime")
            if not start_time:
                continue
            try:
                period_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except ValueError:
                continue
            if period_dt <= now_utc:
                continue  # forecastHourly should only contain future periods, but guard anyway

            temp_c = None
            if period.get("temperature") is not None:
                temp_c = float(period["temperature"])
                if period.get("temperatureUnit") == "F":
                    temp_c = (temp_c - 32.0) * 5.0 / 9.0

            humidity = self._nws_val(period.get("relativeHumidity"), "percent")
            wind_ms = self._parse_forecast_wind(period.get("windSpeed"))

            pop_field = period.get("probabilityOfPrecipitation")
            pop_value = pop_field.get("value") if isinstance(pop_field, dict) else None
            precip_pop = float(pop_value) / 100.0 if pop_value is not None else 0.0

            # QPF from gridded data (forecastHourly does not carry this field)
            precip_mm = 0.0
            if qpf_by_hour:
                hour_key = period_dt.astimezone(timezone.utc).strftime("%Y%m%d%H")
                precip_mm = qpf_by_hour.get(hour_key, 0.0)

            entries.append({
                WEATHER_TEMPERATURE: temp_c,
                WEATHER_HUMIDITY: humidity,
                WEATHER_WIND_SPEED: wind_ms,
                WEATHER_PRESSURE: None,  # not present in forecastHourly
                WEATHER_DEW_POINT: self._nws_val(period.get("dewpoint"), "degC"),
                WEATHER_PRECIP_FORECAST: precip_mm,
                WEATHER_PRECIP_POP: precip_pop,
                WEATHER_UV_INDEX: None,  # not in NWS hourly forecast
                WEATHER_CLOUDS: None,    # not reliably in forecastHourly
                WEATHER_TIMESTAMP: self._to_local_naive_iso(period_dt),
                WEATHER_SOURCE: "forecast",
            })

        return entries

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def async_fetch_current_and_forecast(self) -> dict[str, Any]:
        """Fetch current weather, recent observations, and hourly forecast from NWS."""
        result: dict[str, Any] = {
            "current": None,
            "hourly_history": [],
            "hourly_forecast": [],
            "daily_forecast": [],
        }
        headers = {"User-Agent": self._user_agent, "Accept": "application/geo+json"}

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: resolve grid info (cached after first call)
                if not await self._async_ensure_grid_info(session):
                    return {}

                # Step 2: resolve nearest observation station (cached after first call)
                station_id = await self._async_ensure_station(session)

                # Step 3: fetch recent observations for hourly history + current
                if station_id:
                    start = (
                        datetime.now(tz=timezone.utc) - timedelta(hours=49)
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                    obs_url = (
                        f"{self._base_url}/stations/{station_id}/observations?start={start}"
                    )
                    async with session.get(
                        obs_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                    ) as resp:
                        if resp.status == 200:
                            obs_entries = self._parse_observations(await resp.json())
                            result["hourly_history"] = obs_entries
                            if obs_entries:
                                result["current"] = {
                                    **obs_entries[-1],
                                    WEATHER_SOURCE: "actual",
                                }
                        else:
                            _LOGGER.warning(
                                "NWS observations error %s: %s",
                                resp.status, (await resp.text())[:200],
                            )
                else:
                    _LOGGER.warning(
                        "NWS: No observation station available; history and current will be empty"
                    )

                # Step 4: fetch QPF from gridded endpoint (best-effort; empty dict on failure)
                qpf_by_hour = await self._async_fetch_gridded_qpf(session)

                # Step 5: fetch hourly forecast and merge QPF
                async with session.get(
                    self._forecast_hourly_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        _LOGGER.error(
                            "NWS Hourly Forecast error %s: %s",
                            resp.status, (await resp.text())[:200],
                        )
                        return result  # return observations we already have
                    result["hourly_forecast"] = self._parse_hourly_forecast(
                        await resp.json(), qpf_by_hour
                    )

        except Exception as err:
            _LOGGER.error("Failed to fetch NWS data: %s", err)
            return {}

        _LOGGER.debug(
            "Fetched NWS data: current=%s, hourly_history=%d, hourly_forecast=%d",
            result["current"] is not None,
            len(result["hourly_history"]),
            len(result["hourly_forecast"]),
        )
        return result

    async def async_fetch_history(self, dt: datetime) -> list[dict[str, Any]]:
        """Fetch historical observations for a specific date from the nearest station.

        Used by the coordinator's backfill logic to fill gaps older than 48 hours.
        """
        headers = {"User-Agent": self._user_agent, "Accept": "application/geo+json"}

        try:
            async with aiohttp.ClientSession() as session:
                if not await self._async_ensure_grid_info(session):
                    return []
                station_id = await self._async_ensure_station(session)
                if not station_id:
                    return []

                start = dt.strftime("%Y-%m-%dT00:00:00Z")
                end = (dt + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
                url = (
                    f"{self._base_url}/stations/{station_id}"
                    f"/observations?start={start}&end={end}"
                )
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        _LOGGER.warning(
                            "NWS history fetch error %s for %s: %s",
                            resp.status, start, (await resp.text())[:200],
                        )
                        return []
                    return self._parse_observations(await resp.json())

        except Exception as err:
            _LOGGER.error("NWS history fetch failed for %s: %s", dt.date(), err)
            return []


def get_weather_service(
    hass: HomeAssistant,
    weather_source: str,
    api_key: str | None,
    latitude: float,
    longitude: float,
) -> WeatherService:
    """Factory function to get the appropriate weather service."""
    if weather_source == "nws":
        return NWSWeatherCollector(hass, latitude, longitude)
    elif weather_source == "owm":
        if not api_key:
            raise ValueError("OWM API key is required when using OpenWeatherMap")
        return OWMWeatherCollector(hass, api_key, latitude, longitude)
    else:
        raise ValueError(f"Unknown weather source: {weather_source}")
