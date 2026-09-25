#!/usr/bin/env bash
# build_usd.sh — Bake URDF and open Isaac Sim URDF importer
#
# Step 1: Bakes omnibot.urdf.xacro → /tmp/omnibot.urdf
# Step 2: Prints the manual Isaac Sim import steps (CLI importer is not yet
#         stable across Isaac Sim 4.x releases; GUI import is recommended).
#
# Prerequisites:
#   - ROS 2 Jazzy sourced (for xacro)
#   - robot_ws built and sourced
#
# Usage:
#   source robot_ws/install/setup.bash
#   bash digital_twin/scripts/build_usd.sh
#   # Then follow the printed Isaac Sim instructions.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
URDF_OUT="/tmp/omnibot.urdf"
USD_DIR="${REPO_ROOT}/robot_ws/src/omnibot_description/usd"
XACRO_FILE="${REPO_ROOT}/robot_ws/src/omnibot_description/urdf/omnibot.urdf.xacro"

echo "=== OmniBot USD Build Script ==="
echo ""

# ── Step 1: Bake xacro → URDF ─────────────────────────────────────────────
echo "[1/2] Baking xacro → ${URDF_OUT}"
if ! command -v xacro &>/dev/null; then
    echo "ERROR: xacro not found. Source robot_ws/install/setup.bash first."
    exit 1
fi
xacro "${XACRO_FILE}" -o "${URDF_OUT}"
echo "      Written: ${URDF_OUT}"
echo ""

# ── Step 2: Print Isaac Sim import instructions ────────────────────────────
echo "[2/2] Isaac Sim import instructions"
echo "--------------------------------------------------------------"
echo " The generated URDF is at: ${URDF_OUT}"
echo ""
echo " Option A — GUI import (recommended for Isaac Sim 4.x):"
echo "   1. Launch Isaac Sim via Omniverse Launcher."
echo "   2. Isaac Utils → Workflows → URDF Importer"
echo "   3. Input file : ${URDF_OUT}"
echo "   4. Settings:"
echo "        Fix Base Link     = OFF  (mobile robot)"
echo "        Merge Fixed Joints= ON   (better performance)"
echo "        Self-collision    = OFF"
echo "   5. Click 'Import'. Save as: ${USD_DIR}/omnibot.usd"
echo ""
echo " Option B — headless import (Isaac Sim 4.1+):"
echo "   ISAACSIM=~/.local/share/ov/pkg/isaac-sim-4.1.0"
echo "   \${ISAACSIM}/python.sh \\"
echo "     \${ISAACSIM}/standalone_examples/api/omni.isaac.urdf/urdf_import.py \\"
echo "     --urdf_path ${URDF_OUT} \\"
echo "     --usd_path  ${USD_DIR}/omnibot.usd \\"
echo "     --merge_fixed_joints"
echo ""
echo " After importing, run setup_omnigraph.py inside Isaac Sim to wire"
echo " the ROS 2 action graph:"
echo "   Isaac Sim → Window → Script Editor → open + run"
echo "   ${REPO_ROOT}/digital_twin/scripts/setup_omnigraph.py"
echo "--------------------------------------------------------------"
