# =============================================================================
# NOTIFICATIONS MODULE
# Twilio SMS for backend-confirmed CUSUM alerts
# Twilio is on PythonAnywhere's external domain whitelist
# Falls back to log-only if credentials not configured
# =============================================================================

import config

def send_sms(message: str) -> bool:
    """
    Send alert SMS via Twilio.
    Returns True if sent successfully, False otherwise.
    If SMS_ENABLED is False (no credentials), logs message and returns False.
    """
    if not config.SMS_ENABLED:
        print(f"[SMS] Disabled (no Twilio credentials). Message: {message}")
        return False

    try:
        from twilio.rest import Client
        client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)

        msg = client.messages.create(
            body=message[:1600],     # Twilio supports up to 1600 chars
            from_=config.TWILIO_FROM_NUMBER,
            to=config.ALERT_PHONE_NUMBER
        )

        print(f"[SMS] Sent via Twilio. SID: {msg.sid}")
        return True

    except ImportError:
        print("[SMS] Twilio library not installed. Run: pip install twilio")
        return False

    except Exception as e:
        print(f"[SMS] Twilio error: {e}")
        return False
