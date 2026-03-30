# Backend config - Flask + SQLite + CUSUM
# Jed Olagbemiro, DCU FYP 2026

import os

# Server
DEBUG = os.getenv("DEBUG", "true").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY", "wn-dev-secret-2026")
PORT = int(os.getenv("PORT", 5000))

# Database - just SQLite, keeps things simple
DATABASE_PATH = os.getenv("DATABASE_PATH", "waternode.db")

# API key - must match what's in firmware config.h
API_KEY = os.getenv("API_KEY", "wn-dev-key-2026")

# Twilio SMS config
# Set these as env vars, don't hardcode credentials
# Sign up at twilio.com for free trial
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
ALERT_PHONE_NUMBER = os.getenv("ALERT_PHONE_NUMBER", "")

SMS_ENABLED = all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
                   TWILIO_FROM_NUMBER, ALERT_PHONE_NUMBER])

# CUSUM parameters
# k=0.5 is optimal for detecting a 1-sigma shift
# h=4.5 gives about 465 readings average run length before false alarm
# See algorithm.py for the maths
CUSUM_K = 0.5
CUSUM_H = 4.5

CUSUM_WARMUP_READINGS = 20  # suppress alerts for first 20 readings (~5 hours)
CUSUM_PERSISTENCE = 1       # consecutive alarms before backend confirms

SMS_SUPPRESSION_MINUTES = 60  # max 1 SMS per hour per parameter

# Seasonal baselines - must match firmware config.h
# Season: 0=Dry(Nov-Apr), 1=PreMonsoon(May-Jun), 2=Monsoon(Jul-Sep), 3=PostMonsoon(Oct)
SEASONAL_BASELINES = {
    #                   [Dry,   PreMon, Monsoon, PostMon]
    "turbidity_mean":   [3.0,   8.0,    25.0,    10.0],    # NTU
    "turbidity_std":    [1.5,   5.0,    15.0,     6.0],
    "tds_mean":         [180.0, 150.0,  120.0,   160.0],   # mg/L
    "tds_std":          [40.0,   50.0,   60.0,    45.0],
    "temp_mean":        [14.0,  19.0,   22.0,    17.0],    # deg C
    "temp_std":         [3.0,    3.0,    2.0,     3.0],
}

SEASON_NAMES = ["Dry (Nov-Apr)", "Pre-Monsoon (May-Jun)",
                "Monsoon (Jul-Sep)", "Post-Monsoon (Oct)"]

# WHO limits - must match firmware
WHO_TURBIDITY_NTU = 4.0
WHO_TDS_MGL       = 900.0

# Dashboard
DASHBOARD_HOURS = 24
DASHBOARD_POLL_INTERVAL_SEC = 30

# Keep 90 days of readings in DB, older stuff is on the SD card anyway
DB_RETENTION_DAYS = 90
