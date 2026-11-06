#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/PX4-Autopilot"
PX4_GZ_SIM_RENDER_ENGINE=ogre make px4_sitl gz_x500
