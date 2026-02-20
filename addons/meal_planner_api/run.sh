#!/usr/bin/with-contenv bashio
set -e

echo "============================================================"
echo "🍽️  Meal Planner API (Add-on) Starting"
echo "============================================================"

exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
