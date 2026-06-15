"""Constants for Irrigation Planner."""

DOMAIN = "irrigation_planner"
PLATFORMS = ["sensor", "button", "number", "switch"]

# Configuration keys
CONF_WEATHER_SOURCE = "weather_source"
CONF_OWM_API_KEY = "owm_api_key"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_CALC_TIME = "calc_time"
CONF_DATA_RETENTION_DAYS = "data_retention_days"
CONF_RAIN_ACCUMULATION_DAYS = "rain_accumulation_days"
CONF_UPDATE_INTERVAL_MINUTES = "update_interval_minutes"
CONF_RAINBIRD_DEBOUNCE_MINUTES = "rainbird_debounce_minutes"
CONF_MIN_WATERING_INTERVAL_HOURS = "min_watering_interval_hours"
CONF_MIN_WATERING_DURATION_MINUTES = "min_watering_duration_minutes"
CONF_AUTO_CALCULATE_ON_WEATHER_UPDATE = "auto_calculate_on_weather_update"
CONF_RAIN_THRESHOLD_MM = "rain_threshold_mm"
CONF_RAIN_LIGHT_EFFECTIVENESS = "rain_light_effectiveness"
CONF_FORECAST_CONFIDENCE = "forecast_confidence"

# Zone configuration
CONF_ZONES = "zones"
CONF_ZONE_NAME = "name"
CONF_ZONE_AREA_SQFT = "area_sqft"
CONF_ZONE_SUN_EXPOSURE = "sun_exposure"
CONF_ZONE_SOIL_TYPE = "soil_type"
CONF_ZONE_PLANT_TYPE = "plant_type"
CONF_ZONE_SPRINKLER_RATE_IN_PER_HR = "sprinkler_rate_in_per_hr"
CONF_ZONE_RAINBIRD_ZONE = "rainbird_zone"
CONF_ZONE_DURATION_MULTIPLIER = "duration_multiplier"
CONF_ZONE_MAX_DURATION_MINUTES = "max_duration_minutes"

# Sun exposure options
SUN_FULL = "full_sun"
SUN_PARTIAL = "partial_sun"
SUN_SHADE = "shade"

SUN_EXPOSURE_OPTIONS = {
    SUN_FULL: "Full Sun",
    SUN_PARTIAL: "Partial Sun/Shade",
    SUN_SHADE: "Full Shade",
}

# Sun exposure multipliers (how much more/less ET due to sun)
SUN_EXPOSURE_MULTIPLIER = {
    SUN_FULL: 1.0,
    SUN_PARTIAL: 0.75,
    SUN_SHADE: 0.5,
}

# Soil type options
SOIL_SANDY = "sandy"
SOIL_LOAM = "loam"
SOIL_CLAY = "clay"
SOIL_SILT = "silt"

SOIL_TYPE_OPTIONS = {
    SOIL_SANDY: "Sandy",
    SOIL_LOAM: "Loam",
    SOIL_CLAY: "Clay",
    SOIL_SILT: "Silt",
}

# Soil drainage as percentage of bucket lost per day
# e.g., loam at 10% means full bucket drains to 0% in ~10 days from drainage alone
SOIL_DRAINAGE_PCT_PER_DAY = {
    SOIL_SANDY: 25.0,   # drains fast (~4 days to empty)
    SOIL_LOAM: 10.0,    # moderate (~10 days to empty)
    SOIL_CLAY: 3.0,     # drains slow (~33 days to empty)
    SOIL_SILT: 6.0,     # moderate-slow (~17 days to empty)
}

# Plant type options
PLANT_GRASS = "grass"
PLANT_SHRUBS = "shrubs"
PLANT_FLOWERS = "flowers"
PLANT_VEGETABLES = "vegetables"
PLANT_TREES = "trees"

PLANT_TYPE_OPTIONS = {
    PLANT_GRASS: "Grass/Lawn",
    PLANT_SHRUBS: "Shrubs",
    PLANT_FLOWERS: "Flowers",
    PLANT_VEGETABLES: "Vegetables",
    PLANT_TREES: "Trees",
}

# Plant water need multiplier relative to reference ET
PLANT_WATER_MULTIPLIER = {
    PLANT_GRASS: 0.8,
    PLANT_SHRUBS: 0.5,
    PLANT_FLOWERS: 0.7,
    PLANT_VEGETABLES: 0.9,
    PLANT_TREES: 0.4,
}

# Defaults
DEFAULT_WEATHER_SOURCE = "nws"
DEFAULT_CALC_TIME = "05:00"
DEFAULT_DATA_RETENTION_DAYS = 7
DEFAULT_RAIN_ACCUMULATION_DAYS = 3
DEFAULT_UPDATE_INTERVAL_MINUTES = 60
DEFAULT_RAINBIRD_DEBOUNCE_MINUTES = 10
DEFAULT_MIN_WATERING_INTERVAL_HOURS = 24
DEFAULT_MIN_WATERING_DURATION_MINUTES = 1
DEFAULT_AUTO_CALCULATE_ON_WEATHER_UPDATE = True
DEFAULT_RAIN_THRESHOLD_MM = 5.0
DEFAULT_RAIN_LIGHT_EFFECTIVENESS = 50
DEFAULT_FORECAST_CONFIDENCE = 50
DEFAULT_AREA_SQFT = 500
DEFAULT_SPRINKLER_RATE_IN_PER_HR = 1.0
DEFAULT_DURATION_MULTIPLIER = 1.0
DEFAULT_MAX_DURATION_MINUTES = 30

# Weather source options
WEATHER_SOURCE_NWS = "nws"
WEATHER_SOURCE_OWM = "owm"

WEATHER_SOURCE_OPTIONS = {
    WEATHER_SOURCE_NWS: "National Weather Service (NWS) - US Only",
    WEATHER_SOURCE_OWM: "OpenWeatherMap (OWM) - Global",
}

# Bucket
BUCKET_MAX_PERCENT = 100.0
BUCKET_MIN_PERCENT = 0.0
BUCKET_IRRIGATION_THRESHOLD = 0.0  # irrigate when bucket is at/below 0%
BUCKET_TARGET_REFILL = 100.0  # refill target: 100% = fully watered

# Weather data keys
WEATHER_TEMPERATURE = "temperature"
WEATHER_HUMIDITY = "humidity"
WEATHER_WIND_SPEED = "wind_speed"
WEATHER_PRESSURE = "pressure"
WEATHER_DEW_POINT = "dew_point"
WEATHER_PRECIP_ACTUAL = "precip_actual_mm"
WEATHER_PRECIP_FORECAST = "precip_forecast_mm"
WEATHER_PRECIP_POP = "precip_pop"
WEATHER_UV_INDEX = "uv_index"
WEATHER_CLOUDS = "clouds"
WEATHER_TIMESTAMP = "timestamp"
WEATHER_SOURCE = "source"  # "actual" or "forecast"

# Calculation result keys
CALC_DURATION_MINUTES = "duration_minutes"
CALC_BUCKET_PERCENT = "bucket_percent"
CALC_ET_INCHES = "et_inches"
CALC_RAIN_ACTUAL_INCHES = "rain_actual_inches"
CALC_RAIN_FORECAST_INCHES = "rain_forecast_inches"
CALC_DRAINAGE_INCHES = "drainage_inches"
CALC_NET_CHANGE_INCHES = "net_change_inches"
CALC_FACTOR_SUN = "factor_sun_pct"
CALC_FACTOR_TEMP = "factor_temp_pct"
CALC_FACTOR_RAIN_ACTUAL = "factor_rain_actual_pct"
CALC_FACTOR_RAIN_FORECAST = "factor_rain_forecast_pct"
CALC_FACTOR_HUMIDITY = "factor_humidity_pct"
CALC_FACTOR_WIND = "factor_wind_pct"
CALC_LAST_CALCULATED = "last_calculated"

# Storage
STORAGE_KEY = f"{DOMAIN}.storage"
STORAGE_VERSION = 1

# Services
SERVICE_CALCULATE = "calculate"
SERVICE_CALCULATE_ZONE = "calculate_zone"
SERVICE_REFRESH_WEATHER = "refresh_weather"
SERVICE_RESET_BUCKET = "reset_bucket"

# OWM API
OWM_BASE_URL = "https://api.openweathermap.org/data/3.0/onecall"
OWM_HISTORY_URL = "https://api.openweathermap.org/data/3.0/onecall/timemachine"

# Reference ET constants (Hargreaves simplified)
# When full solar/wind data not available
HARGREAVES_COEFF = 0.0023
HARGREAVES_TEMP_OFFSET = 17.8
SOLAR_CONSTANT_APPROX = 0.408  # MJ/m2/day to mm/day conversion
