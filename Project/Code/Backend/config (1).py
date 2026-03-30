# =============================================================================
# WATERNODE BACKEND - CONFIGURATION
# Flask + SQLite + CUSUM Early Warning System
# Dublin City University - Final Year Project
# =============================================================================

import os

# -----------------------------------------------------------------------------
# SERVER
# -----------------------------------------------------------------------------
DEBUG = os.getenv("DEBUG", "true").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY", "wn-dev-secret-2026")
PORT = int(os.getenv("PORT", 5000))

# -----------------------------------------------------------------------------
# DATABASE
# SQLite — single file, no server required
# -----------------------------------------------------------------------------
DATABASE_PATH = os.getenv("DATABASE_PATH", "waternode.db")

# -----------------------------------------------------------------------------
# SECURITY
# Simple shared API key — must match firmware config.h API_KEY
# -----------------------------------------------------------------------------
API_KEY = os.getenv("API_KEY", "wn-dev-key-2026")

# -----------------------------------------------------------------------------
# SMS ALERTS — Twilio (on PythonAnywhere whitelist)
# Sign up at twilio.com for free trial ($15 credit)
# Set these as environment variables — never hardcode credentials in source
# -----------------------------------------------------------------------------
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")    # e.g. "+15551234567"
ALERT_PHONE_NUMBER = os.getenv("ALERT_PHONE_NUMBER", "")    # Recipient number

# If Twilio credentials are empty, SMS sending is disabled (logged only)
SMS_ENABLED = all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
                   TWILIO_FROM_NUMBER, ALERT_PHONE_NUMBER])

# -----------------------------------------------------------------------------
# CUSUM ALGORITHM PARAMETERS
# k = slack/allowance parameter (0.5 = detect 1-sigma shift in ~10 samples)
# h = decision threshold (4.0-5.0 = ~465 samples average run length to false alarm)
# See algorithm.py for full mathematical derivation and justification
# -----------------------------------------------------------------------------
CUSUM_K = 0.5       # Slack parameter
CUSUM_H = 4.5       # Detection threshold

# Minimum readings before CUSUM is considered reliable
# During this period CUSUM scores are computed but alerts suppressed
CUSUM_WARMUP_READINGS = 20

# Persistence: consecutive CUSUM alarms before backend confirms alert
CUSUM_PERSISTENCE = 1

# SMS suppression: minimum minutes between backend alert SMS for same parameter
SMS_SUPPRESSION_MINUTES = 60

# -----------------------------------------------------------------------------
# SEASONAL BASELINE PARAMETERS
# Must match firmware config.h exactly
# Used for CUSUM initialisation and dashboard reference lines
# Season indices: 0=Dry(Nov-Apr), 1=PreMonsoon(May-Jun),
#                 2=Monsoon(Jul-Sep),  3=PostMonsoon(Oct)
# -----------------------------------------------------------------------------
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

# WHO absolute limits (source: WHO Guidelines for Drinking-Water Quality, 4th ed.)
# Must match firmware config.h WHO_TURBIDITY_LIMIT_NTU and WHO_TDS_LIMIT_MGL
WHO_TURBIDITY_NTU = 4.0     # WHO guideline value
WHO_TDS_MGL       = 900.0   # Above palatability threshold (matches firmware)

# -----------------------------------------------------------------------------
# DASHBOARD
# How many hours of data to show on trend charts
# -----------------------------------------------------------------------------
DASHBOARD_HOURS = 24
DASHBOARD_POLL_INTERVAL_SEC = 30    # Frontend polling interval

# -----------------------------------------------------------------------------
# DATA RETENTION
# Archive readings older than this many days to keep DB lean
# (All data preserved in CSV on SD card regardless)
# -----------------------------------------------------------------------------
DB_RETENTION_DAYS = 90
