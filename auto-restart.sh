#!/bin/bash
# Auto-restart script for bancho server
# Runs daily at midnight GMT+2

echo "[$(date)] Starting server restart..." >> /root/bancho-new/restart.log

# Navigate to bancho directory
cd /root/bancho-new

# Restart docker containers
docker compose restart

echo "[$(date)] Server restart complete" >> /root/bancho-new/restart.log
