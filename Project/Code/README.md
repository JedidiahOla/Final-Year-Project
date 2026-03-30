# WaterNode Backend

Flask + SQLite backend for the WaterNode water quality monitoring system.

## Local Development Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the server
python app.py

# 3. Open dashboard
# http://localhost:5000

# 4. Expose to internet for ESP32 testing (install ngrok first)
# ngrok http 5000
# Copy the https URL into firmware config.h SERVER_URL
```

## Environment Variables

Set these before running (or create a .env file):

```bash
API_KEY=wn-dev-key-2026          # Must match firmware config.h
DATABASE_PATH=waternode.db
DEBUG=true

# Twilio SMS (optional — get free trial at twilio.com)
TWILIO_ACCOUNT_SID=ACxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxx
TWILIO_FROM_NUMBER=+15551234567
ALERT_PHONE_NUMBER=+353XXXXXXXXX
```

## PythonAnywhere Deployment

1. Upload all files to PythonAnywhere via Files tab
2. Create a new Web App → Manual Configuration → Python 3.11
3. Set WSGI file to point to `app.py`:
   ```python
   import sys
   sys.path.insert(0, '/home/YOURUSERNAME/waternode-backend')
   from app import app as application
   ```
4. Set environment variables in the Web tab
5. Click Reload

## API Endpoints

| Method | URL              | Auth     | Description                    |
|--------|-----------------|----------|-------------------------------|
| POST   | /api/readings   | API key  | Receive batch from ESP32      |
| GET    | /api/latest     | None     | Current status for dashboard  |
| GET    | /api/history    | None     | Time-series for charts        |
| GET    | /api/alerts     | None     | Alert log                     |
| GET    | /health         | None     | Health check                  |
| GET    | /               | None     | Dashboard HTML                |

## Testing the API manually

```bash
curl -X POST http://localhost:5000/api/readings \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "WN001",
    "api_key": "wn-dev-key-2026",
    "readings": [{
      "ts": 1741478400,
      "tb": 4.2,
      "tbr": 2341,
      "td": 187.3,
      "tc": 16.2,
      "bv": 3842,
      "al": 0,
      "ff": 0,
      "si": 0
    }]
  }'
```
