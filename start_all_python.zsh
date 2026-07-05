#!/usr/bin/env zsh
# =============================================================================
# start_all_python.zsh  —  Ship Defense + VectorNav launcher with menu
#
# Menu options:
#   1) Start Ship Defense  (command_control, sensor, effector)
#   2) Start VectorNav     (VectorNav_Publisher, VectorNav_Dashboard)
#   3) Stop & Terminate All
#
# Each app runs in its own macOS Terminal window so output stays separate.
# Cleanup uses pkill -f on the script name — no duplicate shadow PIDs.
# Each option may only be selected once.
# =============================================================================

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$REPO_DIR/py"
RTI_ENV="/Applications/rti_connext_dds-7.7.0/resource/scripts/rtisetenv_arm64Darwin23clang16.0.zsh"
PYTHON="$HOME/.venv/bin/python3"

# Flags — 0 = available, 1 = already launched
STARTED_SHIP=0
STARTED_VN=0

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

source "$RTI_ENV"

# ---------------------------------------------------------------------------
# Track Terminal window IDs so stop_all() can close them
# ---------------------------------------------------------------------------
typeset -a TERMINAL_WINDOW_IDS

# ---------------------------------------------------------------------------
# Helper: open a new Terminal window, run cmd, store window ID for cleanup
# ---------------------------------------------------------------------------
open_terminal() {
    local cmd="$1"
    local wid
    wid=$(osascript \
        -e 'tell application "Terminal"' \
        -e '  activate' \
        -e "  do script \"$cmd\"" \
        -e '  delay 0.5' \
        -e '  return id of window 1' \
        -e 'end tell')
    TERMINAL_WINDOW_IDS+=($wid)
}

# ---------------------------------------------------------------------------
# Option handlers
# ---------------------------------------------------------------------------
start_ship_defense() {
    print -P "\n%F{green}Starting Ship Defense apps …%f"

    open_terminal "source '$RTI_ENV' && cd '$APP_DIR' && '$PYTHON' command_control.py"
    sleep 1   # let C2 participant come up first
    open_terminal "source '$RTI_ENV' && cd '$APP_DIR' && '$PYTHON' sensor.py"
    open_terminal "source '$RTI_ENV' && cd '$APP_DIR' && '$PYTHON' effector.py"

    print -P "  %F{green}✓%f  command_control  → Terminal window"
    print -P "  %F{green}✓%f  sensor           → Terminal window"
    print -P "  %F{green}✓%f  effector         → Terminal window"
    STARTED_SHIP=1
}

start_vectornav() {
    print -P "\n%F{green}Starting VectorNav apps …%f"

    open_terminal "source '$RTI_ENV' && cd '$APP_DIR' && '$PYTHON' VectorNav_Publisher.py"
    open_terminal "source '$RTI_ENV' && cd '$APP_DIR' && '$PYTHON' VectorNav_Dashboard.py"

    print -P "  %F{green}✓%f  VectorNav_Publisher → Terminal window"
    print -P "  %F{green}✓%f  VectorNav_Dashboard → Terminal window"
    STARTED_VN=1
}

stop_all() {
    print -P "\n%F{yellow}Stopping all applications …%f"
    local apps=(command_control sensor effector VectorNav_Publisher VectorNav_Dashboard)
    for app in $apps; do
        if pkill -f "python.*${app}.py" 2>/dev/null; then
            print -P "  %F{red}✗%f  $app stopped"
        else
            print -P "  %F{grey}–%f  $app was not running%f"
        fi
    done

    # Wait for processes to exit, then close their Terminal windows by stored ID
    sleep 1
    if [[ ${#TERMINAL_WINDOW_IDS[@]} -gt 0 ]]; then
        print -P "%F{yellow}Closing Terminal windows …%f"
        for wid in "${TERMINAL_WINDOW_IDS[@]}"; do
            osascript \
                -e 'tell application "Terminal"' \
                -e "  close (first window whose id is $wid)" \
                -e 'end tell' 2>/dev/null || true
        done
    fi

    print -P "\n%F{cyan}All applications stopped. Goodbye.%f\n"
}

# ---------------------------------------------------------------------------
# Menu loop
# ---------------------------------------------------------------------------
print -P "\n%F{cyan}═══════════════════════════════════════════════════════%f"
print -P "%F{cyan}  Ship Defense  —  Launch Menu%f"
print -P "%F{cyan}═══════════════════════════════════════════════════════%f"

while true; do
    print ""
    if [[ $STARTED_SHIP -eq 0 ]]; then
        print -P "  %F{green}1)%f Start Ship Defense  (command_control, sensor, effector)"
    else
        print -P "  %F{grey}1) Ship Defense already running%f"
    fi

    if [[ $STARTED_VN -eq 0 ]]; then
        print -P "  %F{green}2)%f Start VectorNav  (Publisher + Dashboard)"
    else
        print -P "  %F{grey}2) VectorNav already running%f"
    fi

    print -P "  %F{red}3)%f Stop & Terminate All"
    print ""
    print -n "Select option [1/2/3]: "
    read -r CHOICE

    case "$CHOICE" in
        1)
            if [[ $STARTED_SHIP -eq 1 ]]; then
                print -P "%F{yellow}Ship Defense is already running — option not available.%f"
            else
                start_ship_defense
            fi
            ;;
        2)
            if [[ $STARTED_VN -eq 1 ]]; then
                print -P "%F{yellow}VectorNav is already running — option not available.%f"
            else
                start_vectornav
            fi
            ;;
        3)
            stop_all
            exit 0
            ;;
        *)
            print -P "%F{red}Invalid choice.%f  Please enter 1, 2, or 3."
            ;;
    esac
done

