#!/usr/bin/with-contenv bashio
set -e

bashio::log.info "============================================================"
bashio::log.info "🍽️  Meal Planner API (Add-on) Starting"
bashio::log.info "============================================================"

exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
