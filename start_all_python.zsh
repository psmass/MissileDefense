#!/usr/bin/env zsh
# =============================================================================
# start_all_python.zsh  —  Ship Defense + VectorNav launcher with menu
#
# Screen layout (four quadrants):
#   Upper left  — command_control pygame GUI
#   Upper right — VectorNav_Dashboard Qt GUI
#   Lower left  — THIS menu terminal
#   Lower right — sensor, effector, VectorNav_Publisher Terminal windows (stacked)
#
# Each option may only be selected once.  Option 3 kills all processes and
# closes all Terminal windows that were opened.
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
# Compute screen quadrant bounds
# ---------------------------------------------------------------------------
# Fetch logical screen dimensions from Finder (points, not Retina pixels)
read SW SH <<< $(osascript \
    -e 'tell application "Finder"' \
    -e '  set b to bounds of window of desktop' \
    -e '  return ((item 3 of b) as text) & " " & ((item 4 of b) as text)' \
    -e 'end tell')

MB=25                           # macOS menu bar height (pts)
HW=$((SW / 2))                  # half screen width
HH=$(( (SH - MB) / 2 ))        # half usable screen height
MID_Y=$((MB + HH))              # y of the horizontal dividing line

# Individual quadrant corner variables (used in AppleScript set bounds)
UL_X1=0;    UL_Y1=$MB;     UL_X2=$HW;  UL_Y2=$MID_Y   # upper left
UR_X1=$HW;  UR_Y1=$MB;     UR_X2=$SW;  UR_Y2=$MID_Y   # upper right
LL_X1=0;    LL_Y1=$MID_Y;  LL_X2=$HW;  LL_Y2=$SH      # lower left
LR_X1=$HW;  LR_Y1=$MID_Y;  LR_X2=$SW;  LR_Y2=$SH      # lower right

# Reposition THIS terminal window to lower left immediately
osascript \
    -e 'tell application "Terminal"' \
    -e '  activate' \
    -e "  set bounds of front window to {$LL_X1, $LL_Y1, $LL_X2, $LL_Y2}" \
    -e 'end tell'

# ---------------------------------------------------------------------------
# Track Terminal window IDs opened by this script so stop_all() can close them
# ---------------------------------------------------------------------------
typeset -a TERMINAL_WINDOW_IDS

# ---------------------------------------------------------------------------
# Helper: open a new Terminal window, cap it at 125×30 chars, position it,
#         minimize it, and record its ID.
#   open_terminal <cmd> <x1> <y1> <x2> <y2> [minimize_delay_secs]
#   x1,y1 = desired top-left corner.  x2,y2 accepted but ignored — size is
#   controlled by columns/rows so the window is never larger than 125×30.
#   minimize_delay: seconds to wait before minimizing (default 1.5).
#   GUI-hosting apps (pygame, Qt) use 2.5 s so their window appears first.
# ---------------------------------------------------------------------------
open_terminal() {
    local cmd="$1" x1="$2" y1="$3"
    local min_delay="${6:-1.5}"   # arg 6; args 4&5 (x2,y2) accepted but unused
    local wid
    wid=$(osascript \
        -e 'tell application "Terminal"' \
        -e '  activate' \
        -e "  do script \"$cmd\"" \
        -e '  delay 0.4' \
        -e '  set number of columns of front window to 125' \
        -e '  set number of rows of front window to 30' \
        -e '  set wb to bounds of front window' \
        -e '  set ww to (item 3 of wb) - (item 1 of wb)' \
        -e '  set wh to (item 4 of wb) - (item 2 of wb)' \
        -e "  set nx2 to $x1 + ww" \
        -e "  set ny2 to $y1 + wh" \
        -e "  set bounds of front window to {$x1, $y1, nx2, ny2}" \
        -e "  set wid to id of front window" \
        -e "  delay $min_delay" \
        -e "  set miniaturized of (first window whose id is wid) to true" \
        -e '  return wid' \
        -e 'end tell')
    TERMINAL_WINDOW_IDS+=($wid)
}

# ---------------------------------------------------------------------------
# Option handlers
# ---------------------------------------------------------------------------
start_ship_defense() {
    print -P "\n%F{green}Starting Ship Defense apps …%f"

    # command_control: 2.5 s delay lets pygame window appear before Terminal is minimized
    open_terminal \
        "export SDL_VIDEO_WINDOW_POS='0,$MB' && source '$RTI_ENV' && cd '$APP_DIR' && '$PYTHON' command_control.py" \
        $UL_X1 $UL_Y1 $UL_X2 $UL_Y2 2.5

    sleep 1   # let C2 participant come up first

    # sensor → lower right
    open_terminal \
        "source '$RTI_ENV' && cd '$APP_DIR' && '$PYTHON' sensor.py" \
        $LR_X1 $LR_Y1 $LR_X2 $LR_Y2

    # effector → lower right (stacked on sensor window)
    open_terminal \
        "source '$RTI_ENV' && cd '$APP_DIR' && '$PYTHON' effector.py" \
        $LR_X1 $LR_Y1 $LR_X2 $LR_Y2

    print -P "  %F{green}✓%f  command_control  → upper left"
    print -P "  %F{green}✓%f  sensor           → lower right"
    print -P "  %F{green}✓%f  effector         → lower right (stacked)"
    STARTED_SHIP=1
}

start_vectornav() {
    print -P "\n%F{green}Starting VectorNav apps …%f"

    # VectorNav_Dashboard: 2.5 s delay lets Qt window appear before Terminal is minimized
    open_terminal \
        "export WINDOW_POS='$HW,$MB' && source '$RTI_ENV' && cd '$APP_DIR' && '$PYTHON' VectorNav_Dashboard.py" \
        $UR_X1 $UR_Y1 $UR_X2 $UR_Y2 2.5

    # VectorNav_Publisher → lower right (stacked)
    open_terminal \
        "source '$RTI_ENV' && cd '$APP_DIR' && '$PYTHON' VectorNav_Publisher.py" \
        $LR_X1 $LR_Y1 $LR_X2 $LR_Y2

    print -P "  %F{green}✓%f  VectorNav_Dashboard → upper right"
    print -P "  %F{green}✓%f  VectorNav_Publisher → lower right (stacked)"
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

