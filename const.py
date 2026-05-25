"""Constants for Irrigation Planner."""

DOMAIN = "irrigation_planner"
PLATFORMS = ["sensor", "button"]

# Configuration keys
CONF_OWM_API_KEY = "owm_api_key"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_CALC_TIME = "calc_time"
CONF_DATA_RETENTION_DAYS = "data_retention_days"
CONF_UPDATE_INTERVAL_MINUTES = "update_interval_minutes"

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

# Soil water holding capacity (inches of water per inch of soil depth)
# Used to determine how fast water drains
SOIL_DRAINAGE_RATE_IN_PER_DAY = {
    SOIL_SANDY: 2.0,   # drains fast
    SOIL_LOAM: 0.5,    # moderate
    SOIL_CLAY: 0.15,   # drains slow
    SOIL_SILT: 0.3,    # moderate-slow
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
DEFAULT_CALC_TIME = "05:00"
DEFAULT_DATA_RETENTION_DAYS = 3
DEFAULT_UPDATE_INTERVAL_MINUTES = 60
DEFAULT_AREA_SQFT = 500
DEFAULT_SPRINKLER_RATE_IN_PER_HR = 1.0
DEFAULT_DURATION_MULTIPLIER = 1.0
DEFAULT_MAX_DURATION_MINUTES = 30

# Bucket
BUCKET_MAX_PERCENT = 100.0
BUCKET_MIN_PERCENT = 0.0
BUCKET_IRRIGATION_THRESHOLD = 0.0  # irrigate when bucket goes below 0%
BUCKET_TARGET_REFILL = 100.0  # refill target: 100% = fully watered

# Weather data keys
WEATHER_TEMPERATURE = "temperature"
WEATHER_HUMIDITY = "humidity"
WEATHER_WIND_SPEED = "wind_speed"
WEATHER_PRESSURE = "pressure"
WEATHER_DEW_POINT = "dew_point"
WEATHER_PRECIP_ACTUAL = "precip_actual_mm"
WEATHER_PRECIP_FORECAST = "precip_forecast_mm"
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
