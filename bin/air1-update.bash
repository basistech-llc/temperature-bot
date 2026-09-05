#!/bin/bash

set -euo pipefail               # fail on anything


# 1. Stop the service using your current user's sudo privileges
echo "Stopping service..."
sudo systemctl stop air_basistech_net.service

# 2. Run the repository updates as simsong
echo "Pulling updates and migrating database..."
# Note: If git complains about ownership, we temporarily tell it to trust this directory
cd /home/air/temperature-bot/ && sudo -u simsong git pull
cd /home/air/temperature-bot && make migrate-db


# 3. Start the service back up
echo "Starting service..."
sudo systemctl start air_basistech_net.service

# 4. Verify the application is up
echo "Verifying endpoint..."
curl -s https://air.basistech.net/ | tail -n 1
echo ""
