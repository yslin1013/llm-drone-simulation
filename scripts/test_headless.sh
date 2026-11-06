#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/PX4-Autopilot"
HEADLESS=1 make px4_sitl gz_x500
