# =============================================================================
# WATERNODE BACKEND - FLASK APPLICATION
# API endpoint for sensor node POST + Dashboard serving
# =============================================================================

import time
import json
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template, abort

import config
import database as db
import algorithm

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# Initialise database on startup
db.init_db()

# =============================================================================
# MIDDLEWARE — API Key Authentication
# Applied to all /api/* routes
# =============================================================================

def require_api_key():
    """Check x-api-key header. Abort with 401 if missing or wrong."""
    key = request.headers.get("x-api-key", "")
    if key != config.API_KEY:
        abort(401, description="Invalid or missing API key")


# =============================================================================
# SENSOR NODE API
# =============================================================================

@app.route("/api/readings", methods=["POST"])
def receive_readings():
    """
    Receive batch of readings from ESP32 sensor node.

    Expected JSON body:
    {
        "node_id": "WN001",
        "api_key": "wn-dev-key-2026",
        "readings": [
            {
                "ts": 1741478400,
                "tb": 4.2,      turbidity NTU
                "tbr": 2341,    turbidity raw ADC
                "td": 187.3,    TDS mg/L
                "tc": 16.2,     temperature C
                "bv": 3842,     battery mV
                "al": 0,        local alert level
                "ff": 0,        fault flags
                "si": 0         season index
            },
            ...
        ]
    }
    """
    # Validate content type
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    # Validate API key (from body — SIM800L AT+HTTPDATA can't set headers easily)
    if data.get("api_key") != config.API_KEY:
        return jsonify({"error": "Invalid API key"}), 401

    node_id = data.get("node_id", "unknown")
    readings_raw = data.get("readings", [])

    if not isinstance(readings_raw, list) or len(readings_raw) == 0:
        return jsonify({"error": "No readings in payload"}), 400

    # Inject node_id into each reading (firmware includes it in outer object)
    for r in readings_raw:
        r["node_id"] = node_id

    # Store readings in database
    inserted = db.insert_readings(readings_raw)

    # Run CUSUM algorithm on newly inserted readings
    # Get the readings back with full data for processing
    cusum_results = algorithm.process_batch(readings_raw)

    # Log receipt event
    db.log_event(node_id, "batch_received",
                 f"Received {len(readings_raw)} readings, "
                 f"inserted {inserted} new")

    print(f"[API] Node {node_id}: {len(readings_raw)} received, "
          f"{inserted} new, CUSUM processed")

    return jsonify({
        "status": "ok",
        "received": len(readings_raw),
        "inserted": inserted,
        "cusum_processed": len(cusum_results)
    }), 200


# =============================================================================
# DASHBOARD API — Polled every DASHBOARD_POLL_INTERVAL_SEC by frontend
# =============================================================================

@app.route("/api/latest", methods=["GET"])
def api_latest():
    """
    Return current system status for dashboard.
    Includes latest readings, CUSUM states, recent alerts, system info.
    """
    node_id = request.args.get("node_id", "WN001")

    latest = db.get_latest_reading(node_id)
    if not latest:
        return jsonify({"status": "no_data", "node_id": node_id}), 200

    # Get CUSUM states for all parameters
    cusum_states = {}
    for param in algorithm.PARAMETERS:
        state = db.get_cusum_state(node_id, param)
        season_idx = latest.get("season_index", 0)
        mean, std = algorithm.get_baseline(param, season_idx)
        cusum_states[param] = {
            "s_pos":             round(state["s_pos"], 3),
            "s_neg":             round(state["s_neg"], 3),
            "alarm_active":      state["alarm_active"],
            "consecutive_alarms": state["consecutive_alarms"],
            "reading_count":     state["reading_count"],
            "baseline_mean":     mean,
            "baseline_std":      std
        }

    # Get recent alerts
    recent_alerts = db.get_recent_alerts(node_id, limit=20)

    # Determine overall alert level from CUSUM states
    overall_level = 0
    for param, state in cusum_states.items():
        if state["alarm_active"]:
            if state["consecutive_alarms"] >= config.CUSUM_PERSISTENCE:
                overall_level = max(overall_level, 3)
            else:
                overall_level = max(overall_level, 2)

    # Decode fault flags into human-readable list
    faults = decode_fault_flags(latest.get("fault_flags", 0))

    # Format latest reading timestamp
    ts = latest.get("timestamp", 0)
    ts_formatted = datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC") if ts else "Unknown"

    return jsonify({
        "status":          "ok",
        "node_id":         node_id,
        "timestamp":       ts,
        "timestamp_fmt":   ts_formatted,
        "overall_alert":   overall_level,
        "alert_label":     ["NORMAL", "WATCH", "WARNING", "CONFIRMED"][overall_level],
        "readings": {
            "turbidity_ntu":  latest.get("turbidity_ntu"),
            "tds_mgl":        latest.get("tds_mgl"),
            "temperature_c":  latest.get("temperature_c"),
            "battery_mv":     latest.get("battery_mv"),
            "season_index":   latest.get("season_index", 0),
            "season_name":    config.SEASON_NAMES[latest.get("season_index", 0)]
        },
        "cusum":           cusum_states,
        "faults":          faults,
        "recent_alerts":   recent_alerts[:5],   # Last 5 for status panel
        "total_readings":  db.get_reading_count(node_id)
    })


@app.route("/api/history", methods=["GET"])
def api_history():
    """
    Return time-series data for trend charts.
    Returns last N hours of readings.
    """
    node_id = request.args.get("node_id", "WN001")
    hours   = int(request.args.get("hours", config.DASHBOARD_HOURS))
    hours   = min(hours, 168)   # Cap at 7 days

    readings = db.get_recent_readings(node_id, hours=hours)

    # Format for Chart.js: separate arrays for labels and each parameter
    labels      = []
    turbidity   = []
    tds         = []
    temperature = []
    battery     = []
    alert_levels = []

    for r in readings:
        ts = r.get("timestamp", 0)
        # Format as HH:MM for chart labels
        labels.append(
            datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d/%m %H:%M")
        )
        turbidity.append(r.get("turbidity_ntu"))
        tds.append(r.get("tds_mgl"))
        temperature.append(r.get("temperature_c"))
        battery.append(r.get("battery_mv"))
        alert_levels.append(r.get("alert_level", 0))

    # Build baseline reference lines for chart overlay
    season_idx = readings[-1].get("season_index", 0) if readings else 0
    baselines = {
        "turbidity_mean": config.SEASONAL_BASELINES["turbidity_mean"][season_idx],
        "turbidity_warn": config.SEASONAL_BASELINES["turbidity_mean"][season_idx] * 3,
        "turbidity_who":  config.WHO_TURBIDITY_NTU,
        "tds_mean":       config.SEASONAL_BASELINES["tds_mean"][season_idx],
        "tds_warn":       config.SEASONAL_BASELINES["tds_mean"][season_idx] * 3,
        "tds_who":        config.WHO_TDS_MGL,
        "temp_mean":      config.SEASONAL_BASELINES["temp_mean"][season_idx],
    }

    return jsonify({
        "labels":       labels,
        "turbidity":    turbidity,
        "tds":          tds,
        "temperature":  temperature,
        "battery":      battery,
        "alert_levels": alert_levels,
        "baselines":    baselines,
        "count":        len(readings)
    })


@app.route("/api/alerts", methods=["GET"])
def api_alerts():
    """Return full alert history for dashboard alert log."""
    node_id = request.args.get("node_id", "WN001")
    limit   = int(request.args.get("limit", 20))
    alerts  = db.get_recent_alerts(node_id, limit=limit)

    # Format timestamps
    for a in alerts:
        ts = a.get("timestamp", 0)
        a["timestamp_fmt"] = datetime.fromtimestamp(
            ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if ts else "-"

    return jsonify({"alerts": alerts, "count": len(alerts)})


# =============================================================================
# DASHBOARD — Served as HTML page
# =============================================================================

@app.route("/")
@app.route("/dashboard")
def dashboard():
    """Serve the main dashboard HTML page."""
    return render_template("dashboard.html",
                           node_id="WN001",
                           poll_interval=config.DASHBOARD_POLL_INTERVAL_SEC,
                           season_names=config.SEASON_NAMES)


# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.route("/health")
def health():
    """Simple health check for monitoring."""
    return jsonify({
        "status":   "ok",
        "time":     int(time.time()),
        "version":  "1.0.0"
    })


# =============================================================================
# UTILITY
# =============================================================================

def decode_fault_flags(flags: int) -> list[str]:
    """Convert fault bitmask to human-readable list."""
    fault_map = {
        0x01: "Turbidity sensor fault",
        0x02: "TDS sensor fault",
        0x04: "Temperature sensor fault",
        0x08: "SD card write failure",
        0x10: "GPRS connection failure",
        0x20: "Low battery",
        0x40: "Tank dry / sensor exposed",
        0x80: "RTC fault"
    }
    return [label for bit, label in fault_map.items() if flags & bit]


# =============================================================================
# ERROR HANDLERS
# =============================================================================

@app.errorhandler(401)
def unauthorized(e):
    return jsonify({"error": str(e)}), 401

@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": str(e)}), 400

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("WaterNode Backend v1.0.0")
    print(f"Database: {config.DATABASE_PATH}")
    print(f"SMS: {'Enabled (Twilio)' if config.SMS_ENABLED else 'Disabled'}")
    print(f"Debug: {config.DEBUG}")
    print("=" * 50)
    app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG)
