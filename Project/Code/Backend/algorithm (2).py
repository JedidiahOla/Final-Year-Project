# CUSUM early warning algorithm
# Runs on each incoming reading from the sensor node
# Based on Page (1954) cumulative sum control chart
#
# How it works:
# - Normalise each reading against seasonal baseline (z-score)
# - Feed z-score into upper (S+) and lower (S-) accumulators
# - If either accumulator crosses threshold h, that's an alarm
# - Accumulators reset after alarm so next event can be detected independently
#
# k=0.5 means deviations under half a sigma get ignored (noise filtering)
# h=4.5 means you need ~465 normal readings before a false alarm on average
#
# Also does Mahalanobis distance across all parameters for multi-sensor fusion
# D^2 > 11.34 = anomaly at p<0.01 (chi-squared, 3 degrees of freedom)

import math
import time
import numpy as np
import config
import database as db
import notifications

# Fault flags - must match firmware config.h
FAULT_TURB_SENSOR  = 0x01
FAULT_TDS_SENSOR   = 0x02
FAULT_TEMP_SENSOR  = 0x04
FAULT_TANK_DRY     = 0x40

PARAMETERS = ["turbidity", "tds", "temperature"]


# --- Key mapping ---
# Firmware sends short keys to save bytes over GPRS (ts, tb, td etc)
# Backend uses full names internally

def normalise_reading_keys(reading: dict) -> dict:
    """Convert short firmware keys to long keys. Handles both formats."""
    KEY_MAP = {
        "ts":  "timestamp",
        "tb":  "turbidity_ntu",
        "tbr": "turbidity_raw",
        "td":  "tds_mgl",
        "tc":  "temperature_c",
        "bv":  "battery_mv",
        "al":  "alert_level",
        "ff":  "fault_flags",
        "si":  "season_index",
    }

    normalised = {}
    for key, value in reading.items():
        long_key = KEY_MAP.get(key, key)
        normalised[long_key] = value

    return normalised


# --- Seasonal baseline lookup ---

def get_season_index(month: int) -> int:
    """Month (1-12) -> season index for the baseline arrays."""
    if month in (11, 12, 1, 2, 3, 4):
        return 0    # dry
    elif month in (5, 6):
        return 1    # pre-monsoon
    elif month in (7, 8, 9):
        return 2    # monsoon
    else:
        return 3    # post-monsoon (Oct)

def get_baseline(parameter: str, season_index: int) -> tuple[float, float]:
    """Get (mean, std) for a parameter in a given season."""
    mean_key = f"{parameter}_mean"
    std_key  = f"{parameter}_std"

    baselines = config.SEASONAL_BASELINES
    if mean_key not in baselines:
        return (0.0, 1.0)

    mean = baselines[mean_key][season_index]
    std  = baselines[std_key][season_index]

    if std <= 0:
        std = 0.1   # avoid divide by zero

    return (mean, std)

def normalise(value: float, mean: float, std: float) -> float:
    """Z-score: (value - mean) / std"""
    return (value - mean) / std


# --- CUSUM ---

def update_cusum(state: dict, z: float) -> dict:
    """Update CUSUM accumulators with new z-score. Returns updated state."""
    k = config.CUSUM_K
    h = config.CUSUM_H

    state["s_pos"] = max(0.0, state["s_pos"] + z - k)
    state["s_neg"] = max(0.0, state["s_neg"] - z - k)
    state["reading_count"] += 1

    alarm = (state["s_pos"] > h) or (state["s_neg"] > h)

    # Save peak score BEFORE reset, otherwise logged score would be 0
    state["peak_score"] = max(state["s_pos"], state["s_neg"])

    if alarm:
        state["consecutive_alarms"] += 1
        state["alarm_active"] = True
        state["last_alarm_time"] = int(time.time())
        # Reset so the next event can accumulate fresh
        state["s_pos"] = 0.0
        state["s_neg"] = 0.0
    else:
        # Gradually wind down consecutive count when readings go back to normal
        if state["consecutive_alarms"] > 0:
            state["consecutive_alarms"] = max(0, state["consecutive_alarms"] - 1)
        if state["consecutive_alarms"] == 0:
            state["alarm_active"] = False

    return state

def cusum_score(state: dict) -> float:
    """Peak score (captured before reset so it shows the actual trigger value)."""
    return state.get("peak_score", max(state["s_pos"], state["s_neg"]))


# --- Mahalanobis distance ---
# Combines z-scores from all parameters into one number
# With identity covariance (independent params), D^2 is just sum of z^2

def mahalanobis_distance(z_scores: list[float],
                         cov_matrix: np.ndarray) -> float:
    """Squared Mahalanobis distance. D^2 > 11.34 = anomaly at p<0.01 for 3 params."""
    if len(z_scores) == 0:
        return 0.0

    z = np.array(z_scores)

    try:
        if cov_matrix is not None and cov_matrix.shape == (len(z), len(z)):
            cov_inv = np.linalg.inv(cov_matrix)
            d_sq = float(z.T @ cov_inv @ z)
        else:
            d_sq = float(np.dot(z, z))  # fall back to sum of squares
    except np.linalg.LinAlgError:
        d_sq = float(np.dot(z, z))      # singular matrix, just use diagonal

    return max(0.0, d_sq)

def build_initial_covariance(n_params: int) -> np.ndarray:
    """Identity matrix - assumes parameters are independent (for now).
    TODO: update with real covariance after enough data collected."""
    return np.eye(n_params)


# --- Main processing ---

def process_reading(reading: dict) -> dict:
    """Run CUSUM on one reading. Updates DB state, sends alerts if needed."""

    reading = normalise_reading_keys(reading)

    node_id      = reading.get("node_id", "unknown")
    timestamp    = reading.get("timestamp", int(time.time()))
    season_index = reading.get("season_index", 0)
    fault_flags  = reading.get("fault_flags", 0)

    param_values = {
        "turbidity":   reading.get("turbidity_ntu"),
        "tds":         reading.get("tds_mgl"),
        "temperature": reading.get("temperature_c")
    }

    # Which sensors are faulted
    param_faults = {
        "turbidity":   bool(fault_flags & FAULT_TURB_SENSOR),
        "tds":         bool(fault_flags & FAULT_TDS_SENSOR),
        "temperature": bool(fault_flags & FAULT_TEMP_SENSOR)
    }

    # Don't bother processing if the tank is dry
    if fault_flags & FAULT_TANK_DRY:
        return {"status": "tank_dry", "cusum_scores": {}, "alert_level": 0}

    results = {}
    z_scores_valid = []
    confirmed_alarms = []

    # Run CUSUM for each parameter
    for param in PARAMETERS:
        value = param_values.get(param)

        if param_faults[param] or value is None:
            results[param] = {"skipped": True, "reason": "sensor_fault"}
            continue

        mean, std = get_baseline(param, season_index)
        z = normalise(value, mean, std)
        z_scores_valid.append(z)

        state = db.get_cusum_state(node_id, param)

        # Don't fire alarms during warmup period
        in_warmup = state["reading_count"] < config.CUSUM_WARMUP_READINGS

        state = update_cusum(state, z)

        is_confirmed = (
            state["alarm_active"] and
            state["consecutive_alarms"] >= config.CUSUM_PERSISTENCE and
            not in_warmup
        )

        if is_confirmed:
            confirmed_alarms.append({
                "param": param,
                "value": value,
                "mean":  mean,
                "score": cusum_score(state),
                "state": state
            })

        results[param] = {
            "z_score":    round(z, 3),
            "s_pos":      round(state["s_pos"], 3),
            "s_neg":      round(state["s_neg"], 3),
            "cusum_score": round(cusum_score(state), 3),
            "alarm":      state["alarm_active"],
            "confirmed":  is_confirmed,
            "in_warmup":  in_warmup,
            "baseline_mean": mean,
            "baseline_std":  std
        }

        db.save_cusum_state(node_id, param, state)

    # Mahalanobis fusion - need at least 2 valid parameters
    d_squared = 0.0
    multivariate_alarm = False

    if len(z_scores_valid) >= 2:
        cov = build_initial_covariance(len(z_scores_valid))
        d_squared = mahalanobis_distance(z_scores_valid, cov)
        multivariate_alarm = d_squared > 11.34  # chi-squared p=0.01, 3 df

    # Work out overall alert level
    backend_alert_level = 0
    if multivariate_alarm:
        backend_alert_level = max(backend_alert_level, 2)
    if confirmed_alarms:
        backend_alert_level = 3

    # Send SMS for confirmed alarms
    for alarm in confirmed_alarms:
        param = alarm["param"]
        state = alarm["state"]

        # Check if we've sent an SMS for this param recently
        suppression_seconds = config.SMS_SUPPRESSION_MINUTES * 60
        time_since_last_sms = timestamp - state["last_sms_time"]
        sms_allowed = time_since_last_sms > suppression_seconds

        message = (
            f"WATER ALERT CONFIRMED: {param.upper()} anomaly detected. "
            f"Value: {alarm['value']:.1f}, "
            f"Baseline: {alarm['mean']:.1f}. "
            f"CUSUM score: {alarm['score']:.2f}. "
            f"Node {node_id}."
        )

        sms_sent = False
        if sms_allowed:
            sms_sent = notifications.send_sms(message)
            if sms_sent:
                state["last_sms_time"] = timestamp
                db.save_cusum_state(node_id, param, state)

        db.insert_alert(
            node_id=node_id,
            timestamp=timestamp,
            parameter=param,
            alert_level=3,
            cusum_score=alarm["score"],
            value=alarm["value"],
            baseline_mean=alarm["mean"],
            sms_sent=sms_sent,
            message=message
        )

        print(f"[CUSUM] CONFIRMED: {param} | "
              f"value={alarm['value']:.2f} | "
              f"score={alarm['score']:.2f} | "
              f"SMS={'sent' if sms_sent else 'suppressed'}")

    return {
        "status":             "processed",
        "backend_alert_level": backend_alert_level,
        "cusum_scores":       {p: results[p].get("cusum_score", 0)
                               for p in PARAMETERS if p in results},
        "d_squared":          round(d_squared, 3),
        "multivariate_alarm": multivariate_alarm,
        "confirmed_alarms":   [a["param"] for a in confirmed_alarms],
        "parameter_detail":   results
    }


def process_batch(readings: list[dict]) -> list[dict]:
    """Process a list of readings in time order."""
    sorted_readings = sorted(readings,
                             key=lambda r: r.get("ts", r.get("timestamp", 0)))
    return [process_reading(r) for r in sorted_readings]
