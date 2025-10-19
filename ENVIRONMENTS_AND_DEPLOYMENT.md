# Development and Production Environments Guide

## Overview

This document provides comprehensive guidance for setting up, configuring, and deploying the Temperature Bot system across different environments. It covers hardware dependencies, software requirements, configuration management, and operational procedures.

## Environment Overview

### Development Environment

**Characteristics:**

-   Runs on developer's local machine (macOS/Ubuntu)
-   Uses simulator mode for hardware-independent development
-   Local SQLite database for testing
-   Live-reload Flask development server
-   No external hardware dependencies required

**Key Features:**

-   Hardware simulation via `AE200_SIMULATOR` environment variable
-   Test data from `app/test_data/` directory
-   Local configuration override capabilities
-   Full debugging and logging capabilities

### Production Environment

**Characteristics:**

-   Ubuntu server with systemd service management
-   Real hardware integration (AE-200 controllers, Hubitat hub)
-   Production SQLite database at `/var/db/temperature-bot.db`
-   Gunicorn WSGI server behind nginx reverse proxy
-   Automated data collection every minute via cron

**Infrastructure:**

-   Single-server deployment
-   Network connectivity to HVAC controllers and IoT hub
-   External API access for weather and air quality data
-   Persistent storage for time-series database

## Configuration Management

### Configuration File Structure

**Primary Configuration:**

```
temperature-bot-config.yaml (or custom path via TEMPERATURE_BOT_CONFIG)
```

**Configuration Hierarchy (precedence):**

1. Environment variables (highest priority)
2. YAML configuration file
3. Default values in code (lowest priority)

### Configuration Sections

**Location Settings:**

```yaml
location:
    latitude: 42.3601
    longitude: -71.0589
    zipcode: "02108"
    city: "boston"
```

**Hardware Integration:**

```yaml
ae200:
    host: "192.168.1.100"

hubitat:
    host: "192.168.1.101"
    appId: "12345678-1234-1234-1234-123456789abc"
```

**Secrets Management:**

```yaml
secrets:
    hubitat:
        access_token: "your-hubitat-token"
    airnow:
        api_key: "your-airnow-key"
    google:
        air_quality_api_key: "your-google-key"
    aqicn:
        token: "your-aqicn-token"
```

### Environment Variable Overrides

**Secret Environment Variables:**

```bash
export HUBITAT_ACCESS_TOKEN="production-token"
export AIRNOW_API_KEY="production-key"
export GOOGLE_AIR_QUALITY_API_KEY="production-key"
export AQICN_TOKEN="production-token"
```

**Configuration Environment Variables:**

```bash
export TEMPERATURE_BOT_CONFIG="/path/to/config.yaml"
export DB_PATH="/var/db/temperature-bot.db"
export AE200_SIMULATOR="1"  # For development
export LOG_LEVEL="DEBUG"
```

## Hardware Dependencies

### Production Hardware Requirements

**AE-200 HVAC Controllers:**

-   **Model:** AE-200 Energy Recovery Ventilator Controller
-   **Network:** Ethernet connection to local network
-   **Protocol:** WebSocket communication on port 80
-   **Functionality:** Controls fan speed (1-4) and drive (ON/OFF)
-   **Expected Devices:** Kitchen ERV, Restrooms ERV (based on rules)

**Hubitat Hub:**

-   **Model:** Hubitat Elevation Hub
-   **Network:** Ethernet connection to local network
-   **Protocol:** REST API on port 80
-   **Functionality:** Temperature sensor data collection
-   **Expected Devices:** Multiple temperature sensors throughout facility

**Network Topology:**

```
Internet
    |
    v
[Router/Firewall]
    |
    +-- [AE-200 Controller] (192.168.1.100)
    +-- [Hubitat Hub] (192.168.1.101)
    +-- [Temperature Bot Server] (192.168.1.102)
```

### Development Hardware Simulation

**AE-200 Simulator:**

-   Uses test data from `app/test_data/ae200_*.json`
-   Simulates device discovery and status queries
-   No network connectivity required
-   Enable with `AE200_SIMULATOR=1`

**Hubitat Simulation:**

-   Uses sample data from `etc/data/sample_hubitat.json`
-   Simulates temperature sensor readings
-   No actual IoT hub required for development

## Software Dependencies

### Python Environment

**Version Requirements:**

-   Python 3.12+ (specified in `pyproject.toml`)
-   Poetry for dependency management
-   Virtual environment in `.venv/` directory

**Core Dependencies:**

```toml
# From pyproject.toml
dependencies = [
    "flask",
    "gunicorn",
    "requests",
    "websockets",
    "pymodbus",
    "clickhouse-connect",
    "python-dotenv",
    "pyyaml",
    "jinja2",
    # ... additional dependencies
]
```

### External API Dependencies

**Air Quality APIs:**

-   **aqicn.org:** Primary AQI data source
-   **airnowapi.org:** Backup AQI source
-   **Google Air Quality API:** Alternative AQI provider

**Weather APIs:**

-   **US National Weather Service:** Free weather data
-   **Required:** Latitude/longitude coordinates

**Network Requirements:**

-   HTTPS access to external APIs
-   DNS resolution for external domains
-   No firewall restrictions on outbound HTTPS

### Database

**SQLite Database:**

-   **Development:** `var/db/temperature-bot.db` (local)
-   **Production:** `/var/db/temperature-bot.db`
-   **Schema:** Defined in `etc/schema.sql`
-   **Backup:** Manual SQLite dump or rsync

### Web Server

**Production Stack:**

-   **Gunicorn:** WSGI application server
-   **nginx:** Reverse proxy and static file serving
-   **systemd:** Service management

**Development:**

-   **Flask dev server:** With live-reload
-   **livereload:** File watching for development

## Build & Deployment Steps

### Local Development Setup

**1. Prerequisites Installation:**

```bash
# macOS
make install-macos

# Ubuntu
make install-ubuntu
```

**2. Environment Setup:**

```bash
# Clone repository
git clone <repository-url>
cd temperature-bot

# Install dependencies
poetry install

# Create development database
make make-dev-db
```

**3. Configuration:**

```bash
# Create local config file
cp temperature-bot-config-example.yaml temperature-bot-config.yaml

# Edit configuration with local settings
# Set AE200_SIMULATOR=1 for hardware simulation
```

**4. Start Development Server:**

```bash
# Run with live reload
make local-dev

# Or manually:
FLASK_DEBUG=True DB_PATH=var/db/temperature-bot.db AE200_SIMULATOR=1 python run_local.py
```

### Production Deployment

**1. Server Setup:**

```bash
# Install system dependencies (Ubuntu)
sudo apt update
sudo apt install python3-pip pipx nginx sqlite3

# Install Python tools
make install-ubuntu
```

**2. Application Deployment:**

```bash
# Clone to production location
sudo git clone <repository-url> /home/air/temperature-bot
cd /home/air/temperature-bot

# Install dependencies
poetry install

# Create production database
sudo mkdir -p /var/db
sudo sqlite3 /var/db/temperature-bot.db < etc/schema.sql
sudo chown air:air /var/db/temperature-bot.db
```

**3. Configuration:**

```bash
# Create production config
sudo cp temperature-bot-config-example.yaml /etc/temperature-bot-config.yaml
sudo chown air:air /etc/temperature-bot-config.yaml

# Edit with production settings
sudo nano /etc/temperature-bot-config.yaml
```

**4. Service Configuration:**

```bash
# Install systemd service
sudo cp etc/air_basistech_net.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable air_basistech_net.service
sudo systemctl start air_basistech_net.service
```

**5. Cron Job Setup:**

```bash
# Add to crontab for user 'air'
sudo crontab -u air -e

# Add this line for every-minute data collection:
* * * * * /home/air/temperature-bot/.venv/bin/python -m bin.runner
```

### nginx Configuration

**Reverse Proxy Setup:**

```nginx
server {
    listen 80;
    server_name air.basistech.net;

    location / {
        proxy_pass http://127.0.0.1:8100;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /home/air/temperature-bot/app/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

## Testing Strategies

### Local Testing Without Hardware

**Simulator Mode:**

```bash
# Enable simulator for all components
export AE200_SIMULATOR=1
export PYTEST=1

# Run tests
make pytest

# Run specific hardware simulation
python -c "
import os
os.environ['AE200_SIMULATOR'] = '1'
from app import ae200
print(ae200.get_devices())
"
```

**Test Database:**

```bash
# Create isolated test database
export TEST_DB_NAME=/tmp/test.db
python -m pytest tests/test_db.py -v

# Test with sample data
python -m pytest tests/test_ae200.py -v
```

### Component Testing

**Database Operations:**

```bash
# Test database connectivity
python -c "
from app import db
conn = db.get_db_connection()
print('Database connected successfully')
conn.close()
"
```

**API Testing:**

```bash
# Test API endpoints
curl http://localhost:8000/api/v1/status
curl http://localhost:8000/api/v1/weather
```

**Rules Engine Testing:**

```bash
# Test rules without execution
python -m bin.runner --rules test

# Test rules with specific AQI
python -c "
from app import db, rules_engine
conn = db.get_db_connection()
print(rules_engine.rules_results(conn, aqi=150))
"
```

### CI/CD Testing

**GitHub Actions Compatible:**

-   All tests run without external dependencies
-   Simulator mode enabled automatically
-   No hardware access required
-   Fast execution (~6 seconds for full suite)

**Test Categories:**

-   **Unit Tests:** Individual module testing
-   **Integration Tests:** API and database integration
-   **Browser Tests:** UI testing with Playwright
-   **Bin Tools Tests:** Command-line tool testing

## Troubleshooting & Operations

### Log Locations

**Application Logs:**

```bash
# Systemd service logs
sudo journalctl -u air_basistech_net.service -f

# Application logs (if configured)
tail -f /var/log/temperature-bot.log
```

**Database Inspection:**

```bash
# Connect to database
sqlite3 /var/db/temperature-bot.db

# Check recent data
SELECT * FROM devlog ORDER BY logtime DESC LIMIT 10;

# Check device status
SELECT * FROM devices;

# Check AQI data
SELECT * FROM aqi ORDER BY logtime DESC LIMIT 5;
```

### Common Issues

**Service Won't Start:**

```bash
# Check service status
sudo systemctl status air_basistech_net.service

# Check configuration
python -c "from app.util import get_config; print(get_config())"

# Check database permissions
ls -la /var/db/temperature-bot.db
```

**Hardware Communication Issues:**

```bash
# Test AE-200 connectivity
python -c "
from app import ae200
try:
    devices = ae200.get_devices()
    print('AE-200 connected:', devices)
except Exception as e:
    print('AE-200 error:', e)
"

# Test Hubitat connectivity
python -c "
from app import hubitat
try:
    devices = hubitat.get_all_devices()
    print('Hubitat connected:', len(devices), 'devices')
except Exception as e:
    print('Hubitat error:', e)
"
```

**Database Issues:**

```bash
# Check database integrity
sqlite3 /var/db/temperature-bot.db "PRAGMA integrity_check;"

# Backup database
sqlite3 /var/db/temperature-bot.db ".backup backup-$(date +%Y%m%d).db"

# Restore from backup
sqlite3 /var/db/temperature-bot.db ".restore backup-20240101.db"
```

### Service Management

**Service Control:**

```bash
# Start/stop/restart service
sudo systemctl start air_basistech_net.service
sudo systemctl stop air_basistech_net.service
sudo systemctl restart air_basistech_net.service

# Check service status
sudo systemctl status air_basistech_net.service

# View service logs
sudo journalctl -u air_basistech_net.service --since "1 hour ago"
```

**Manual Operations:**

```bash
# Run data collection manually
python -m bin.runner

# Run rules manually
python -m bin.runner --rules run

# Test rules
python -m bin.runner --rules test

# Daily cleanup
python -m bin.runner --daily

# Update AQI only
python -m bin.runner --aqi
```

### Database Maintenance

**Data Cleanup:**

```bash
# Manual daily cleanup
python -m bin.runner --daily

# Check database size
du -h /var/db/temperature-bot.db

# Analyze database performance
sqlite3 /var/db/temperature-bot.db "ANALYZE;"
```

**Backup Strategy:**

```bash
# Daily backup script
#!/bin/bash
BACKUP_DIR="/backup/temperature-bot"
DATE=$(date +%Y%m%d)
sqlite3 /var/db/temperature-bot.db ".backup $BACKUP_DIR/temperature-bot-$DATE.db"

# Keep only last 30 days
find $BACKUP_DIR -name "temperature-bot-*.db" -mtime +30 -delete
```

## Security Considerations

### Production Security

**Network Security:**

-   Firewall rules to restrict access
-   VPN access for remote administration
-   No external port exposure except through nginx

**Application Security:**

-   No authentication on web interface (internal network only)
-   Secrets via environment variables
-   Regular security updates

**Data Security:**

-   Database file permissions (600)
-   Regular backups
-   No sensitive data in logs

### Development Security

**Local Development:**

-   Use simulator mode to avoid exposing real hardware
-   Test data only (no production secrets)
-   Local firewall if needed

## Monitoring & Alerting

### Health Checks

**Service Health:**

```bash
# Check if service is running
curl -f http://localhost:8100/health || echo "Service down"

# Check database connectivity
python -c "from app import db; conn = db.get_db_connection(); conn.close(); print('DB OK')"
```

**Data Collection Health:**

```bash
# Check recent data collection
sqlite3 /var/db/temperature-bot.db "
SELECT
  datetime(logtime, 'unixepoch') as last_update,
  COUNT(*) as recent_records
FROM devlog
WHERE logtime > strftime('%s', 'now', '-5 minutes')
GROUP BY device_id;
"
```

### Alerting Setup

**Simple Health Check Script:**

```bash
#!/bin/bash
# /usr/local/bin/temperature-bot-health-check.sh

# Check service
if ! systemctl is-active --quiet air_basistech_net.service; then
    echo "Temperature Bot service is down" | mail -s "Alert" admin@basistech.com
fi

# Check recent data
RECENT_COUNT=$(sqlite3 /var/db/temperature-bot.db "
SELECT COUNT(*) FROM devlog
WHERE logtime > strftime('%s', 'now', '-10 minutes')
")

if [ "$RECENT_COUNT" -eq 0 ]; then
    echo "No recent temperature data" | mail -s "Alert" admin@basistech.com
fi
```

This comprehensive guide provides everything needed to understand, deploy, and operate the Temperature Bot system across different environments.
