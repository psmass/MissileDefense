#!/usr/bin/env zsh
# =============================================================================
# start_all_python.zsh  —  Start all five Ship Defense + VectorNav Python apps
#
# Applications started (all from py/):
#   1. command_control.py     — pygame GUI Command & Control
#   2. sensor.py              — Aegis sensor suite
#   3. effector.py            — Layered weapon defence
#   4. VectorNav_Publisher.py — UMAA GPS/IMU publisher
#   5. VectorNav_Dashboard.py — PyQt6 instrument dashboard
# =============================================================================

set -e  # exit on error during setup

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$REPO_DIR/py"
RTI_ENV="/Applications/rti_connext_dds-7.7.0/resource/scripts/rtisetenv_arm64Darwin23clang16.0.zsh"
PYTHON="$HOME/.venv/bin/python3"

# ---------------------------------------------------------------------------
# Validate environment
# ---------------------------------------------------------------------------
if [[ ! -f "$RTI_ENV" ]]; then
    print -P "%F{red}ERROR:%f RTI environment script not found:\n  $RTI_ENV"
    exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
    print -P "%F{red}ERROR:%f Python not found at $PYTHON"
    exit 1
fi

# Source RTI Connext environment (sets NDDSHOME, LD_LIBRARY_PATH, etc.)
source "$RTI_ENV"

# ---------------------------------------------------------------------------
# Launch applications  (each in background, stdout/stderr to its own log)
# ---------------------------------------------------------------------------
set +e  # don't exit if a background process fails to start

cd "$APP_DIR"

print -P "\n%F{cyan}═══════════════════════════════════════════════════════%f"
print -P "%F{cyan}  Ship Defense — Starting All Applications%f"
print -P "%F{cyan}═══════════════════════════════════════════════════════%f\n"

print -P "%F{green}[1/5]%f Starting command_control.py  …"
"$PYTHON" "$APP_DIR/command_control.py" &
PID_CC=$!

sleep 1   # allow participant to initialise before peers join

print -P "%F{green}[2/5]%f Starting sensor.py           …"
"$PYTHON" "$APP_DIR/sensor.py" &
PID_SENSOR=$!

print -P "%F{green}[3/5]%f Starting effector.py          …"
"$PYTHON" "$APP_DIR/effector.py" &
PID_EFFECTOR=$!

print -P "%F{green}[4/5]%f Starting VectorNav_Publisher.py …"
"$PYTHON" "$APP_DIR/VectorNav_Publisher.py" &
PID_VN_PUB=$!

print -P "%F{green}[5/5]%f Starting VectorNav_Dashboard.py …"
"$PYTHON" "$APP_DIR/VectorNav_Dashboard.py" &
PID_VN_DASH=$!

print -P "\n%F{yellow}All five applications launched.%f"
print    "  command_control     PID $PID_CC"
print    "  sensor              PID $PID_SENSOR"
print    "  effector            PID $PID_EFFECTOR"
print    "  VectorNav_Publisher PID $PID_VN_PUB"
print    "  VectorNav_Dashboard PID $PID_VN_DASH"

# ---------------------------------------------------------------------------
# Wait for user confirmation to stop
# ---------------------------------------------------------------------------
print -P "\n%F{cyan}═══════════════════════════════════════════════════════%f"

while true; do
    print -n "Stop all applications? [Y/n]: "
    read -r ANSWER
    case "$ANSWER" in
        Y|y|"")
            break
            ;;
        N|n)
            print "Continuing — press Enter again when ready to stop."
            ;;
        *)
            print "Please enter Y to stop or N to keep running."
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Stop all applications
# ---------------------------------------------------------------------------
print -P "\n%F{yellow}Stopping all applications …%f"

stop_pid() {
    local name=$1 pid=$2
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null
        print -P "  %F{red}✗%f  $name (PID $pid) stopped"
    else
        print -P "  %F{grey}–%f  $name (PID $pid) already exited"
    fi
}

stop_pid "command_control    " $PID_CC
stop_pid "sensor             " $PID_SENSOR
stop_pid "effector           " $PID_EFFECTOR
stop_pid "VectorNav_Publisher" $PID_VN_PUB
stop_pid "VectorNav_Dashboard" $PID_VN_DASH

# Give processes a moment to handle SIGTERM, then force-kill any survivors
sleep 1
for pid in $PID_CC $PID_SENSOR $PID_EFFECTOR $PID_VN_PUB $PID_VN_DASH; do
    kill -9 "$pid" 2>/dev/null
done

print -P "\n%F{cyan}All applications stopped. Goodbye.%f\n"
