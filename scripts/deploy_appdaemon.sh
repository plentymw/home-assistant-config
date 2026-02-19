#!/bin/sh
set -eu

SRC="/config/appdaemon"
DST="/addon_configs/a0d7b954_appdaemon"

echo "Deploying AppDaemon:"
echo "  from: $SRC"
echo "  to:   $DST"

# ensure destination exists
mkdir -p "$DST/apps"

# wipe only .py files in destination apps (keeps folder structure clean)
find "$DST/apps" -maxdepth 1 -type f -name "*.py" -delete

# copy apps folder contents (includes apps.yaml + .py files)
cp -a "$SRC/apps/." "$DST/apps/"

# copy main config
cp -a "$SRC/appdaemon.yaml" "$DST/appdaemon.yaml"

echo "Deploy complete."
echo "Restart the AppDaemon add-on to reload apps."
