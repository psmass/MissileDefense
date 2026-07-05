# Ship Threat Defense + VectorNav GPS — Python Applications

Python implementation of the **Aegis Ship Threat Defense** system combined with a
**VectorNav UMAA GPS/IMU** simulation, all communicating over RTI Connext DDS 7.7.0.
Five cooperating applications share a single DDS domain — no shared memory, no direct
function calls.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  VectorNav_Publisher.py                                                         │
│  Simulates USV sensor (dead-reckoning NE from San Diego Bay, speed 0–30 kt)     │
│  PUBLISHES → SpeedReportType (1 Hz)                                             │
│  PUBLISHES → GlobalPoseReportType (1 Hz)                                        │
│  SUBSCRIBES ← VectorNav::SpeedCommand  (from Dashboard speed slider)            │
└──────────────────────────┬──────────────────────┬──────────────────────────────┘
                           │ GlobalPoseReportType  │ SpeedReportType
                           ▼                       ▼
        ┌──────────────────────────┐   ┌───────────────────────────────────────┐
        │  command_control.py      │   │  VectorNav_Dashboard.py               │
        │  (pygame GUI)            │   │  (PyQt6 GUI instrument panel)         │
        │  Ship moves to GPS pos   │   │  Compass, roll/pitch, speed panels    │
        │  PUBLISHES → ThreatTopic │   │  Speed slider 0–30 kt                 │
        │  SUBSCRIBES ← Sensor     │   │  PUBLISHES → SpeedCommand             │
        │  SUBSCRIBES ← Effector   │   └───────────────────────────────────────┘
        │  SUBSCRIBES ← GPS pose   │
        └────────┬─────────────────┘
                 │ ThreatTopic
       ┌─────────┴──────────┐
       ▼                    ▼
┌──────────────┐    ┌─────────────────────────────────────┐
│  sensor.py   │    │  effector.py                        │
│  Aegis suite │    │  Layered weapon defence             │
│  4 sensors   │    │  5 weapons (SM-2, SM-6, ESSM,       │
│  PUBLISHES → │    │            CIWS, MK 45/62)          │
│  Detection   │    │  PUBLISHES → EffectorActionTopic    │
└──────────────┘    └─────────────────────────────────────┘
```

---

## DDS Topics

| Topic | Type | Publisher → Subscriber(s) |
|---|---|---|
| `ThreatTopic` | `ship::Threat` | `command_control` → `sensor`, `effector` |
| `SensorDetectionTopic` | `ship::SensorDetection` | `sensor` → `command_control` |
| `EffectorActionTopic` | `ship::EffectorAction` | `effector` → `command_control` |
| `UMAA::SA::GlobalPoseStatus::GlobalPoseReportType` | `GlobalPoseReportType` | `VectorNav_Publisher` → `command_control`, `VectorNav_Dashboard`, `HSMST_Subscriber` |
| `UMAA::SA::SpeedStatus::SpeedReportType` | `SpeedReportType` | `VectorNav_Publisher` → `VectorNav_Dashboard`, `HSMST_Subscriber` |
| `VectorNav::SpeedCommand` | `SpeedCommand` | `VectorNav_Dashboard` → `VectorNav_Publisher` |

---

## File Structure

```
py/
├── README.md                  ← this file
│
├── # ── Entry points (5 applications) ─────────────────────────────
├── command_control.py         ← App 1  pygame GUI — Command & Control
├── sensor.py                  ← App 2  Aegis sensor suite
├── effector.py                ← App 3  Layered weapon defence
├── VectorNav_Publisher.py     ← App 4  UMAA GPS/IMU publisher
├── VectorNav_Dashboard.py     ← App 5  PyQt6 instrument dashboard
│
├── # ── Support (also runnable standalone) ─────────────────────────
├── command_control_cli.py     ← CLI (non-GUI) version of command_control
├── HSMST_Subscriber.py        ← Console subscriber for VectorNav topics
│
├── # ── Shared infrastructure ───────────────────────────────────────
├── ddsEntities.py             ← Unified Writer(Thread) + Reader(Thread) base classes
│                                 (supports both ship-style and VectorNav-style calling)
├── application.py             ← Global run_flag + SIGINT handler
│
├── # ── Ship domain ─────────────────────────────────────────────────
├── shipConstants.py           ← Compiled IDL types (Threat, SensorDetection,
│                                 EffectorAction) + sensor/effector definitions
├── ship_topics.py             ← Concrete Writer/Reader topic classes for ship apps
│
├── # ── VectorNav / UMAA domain ─────────────────────────────────────
├── umaa_types.py              ← UMAA compiled-type re-exports (from rtiumaapy)
├── vn_topics.py               ← Concrete Writer/Reader topic classes + VectorNavState
│                                 simulation + SpeedCommand IDL struct
└── vn_constants.py            ← VectorNav constants (domain, rate, topic strings,
                                  speed range 0–30 kt)
```

### Module dependency map

```
command_control.py ──┐
sensor.py          ──┤──► ship_topics.py ──► shipConstants.py
effector.py        ──┘         │
                               │
VectorNav_Publisher.py ──┐     ├──► ddsEntities.py ──► application.py
VectorNav_Dashboard.py ──┤──► vn_topics.py              │
HSMST_Subscriber.py    ──┘         │                    └──► rti.connextdds
                               ├──► umaa_types.py (rtiumaapy)
                               └──► vn_constants.py
```

---

## Prerequisites

### 1. RTI Connext DDS 7.7.0
```zsh
source /Applications/rti_connext_dds-7.7.0/resource/scripts/rtisetenv_arm64Darwin23clang16.0.zsh
```

### 2. Python virtual environment (`~/.venv`)
```zsh
source ~/.venv/bin/activate
```

Verify installed packages:
```zsh
pip show rti.connext      # 7.7.0  — core DDS binding
pip show rtiumaapy        # 0.1.0  — UMAA compiled types (VectorNav topics)
pip show pygame           # 2.6.1  — required by command_control.py
pip show pyqt6            # any    — required by VectorNav_Dashboard.py
```

---

## Quickstart — Launch Script

The recommended way to start all applications:

```zsh
cd /path/to/MissileDefense
./start_all_python.zsh
```

This opens an interactive menu in the lower-left quadrant of your screen:

```
═══════════════════════════════════════════════════════
  Ship Defense  —  Launch Menu
═══════════════════════════════════════════════════════

  1) Start Ship Defense  (command_control, sensor, effector)
  2) Start VectorNav  (Publisher + Dashboard)
  3) Stop & Terminate All

Select option [1/2/3]:
```

**Screen layout (four quadrants):**

```
┌─────────────────────┬─────────────────────┐
│  command_control    │  VectorNav_Dashboard │
│  pygame GUI         │  Qt GUI              │
│  (upper left)       │  (upper right)       │
├─────────────────────┼─────────────────────┤
│  start_all_python   │  sensor terminal     │
│  menu terminal      │  effector terminal   │
│  (lower left)       │  VectorNav_Publisher │
│                     │  (lower right stack) │
└─────────────────────┴─────────────────────┘
```

- Terminal windows are **minimized** automatically after launch (GUIs stay visible)
- All Terminal windows are **closed** when option 3 is selected
- Each option can only be selected **once**

---

## The Five Applications

---

### App 1 — `command_control.py`  *(pygame GUI)*

**Role:** Command & Control — the tactical map operator console.

**What it does:**
- 1060 × 600 window: left 800 px = tactical map, right 250 px = status panel
- Left-click the map to spawn an inbound threat; threats move toward the ship
- Republishes all active threats on `ThreatTopic` every 0.5 s
- Subscribes to `SensorDetectionTopic` → draws dotted sensor track lines
- Subscribes to `EffectorActionTopic` → fires interceptor / blast effects
- Subscribes to `GlobalPoseReportType` → moves ship to GPS position (stays still until VectorNav_Publisher runs)
- Orange **HOME** buoy marks the starting position so GPS drift is visible
- Status panel: live sensor detections, effector firings, active threats, GPS Lat/Lon/Course

```zsh
cd py && python command_control.py [-d DOMAIN_ID]
```

**Admin Console name:** `command_control` | **Log:** `command_control.log`

---

### App 2 — `sensor.py`  *(Aegis sensor suite)*

**Role:** Detects threats within sensor range and publishes detections.

**What it does:**
- Subscribes to `ThreatTopic`
- Each received threat is range-checked by all four Aegis sensors:

| Sensor | ID | Range (px) | Confidence |
|---|---|---|---|
| AN/SPY-1D | 1 | 412 | 88–100 % |
| AN/SPQ-9B | 2 |  75 | 72–90 %  |
| AN/SPS-67 | 3 |  47 | 55–75 %  |
| AN/SLQ-32 | 4 | 187 | 65–85 %  |

- Publishes one `SensorDetection` per in-range sensor-threat pair

```zsh
cd py && python sensor.py [-d DOMAIN_ID]
```

**Admin Console name:** `sensor` | **Log:** `sensor.log`

---

### App 3 — `effector.py`  *(layered weapon defence)*

**Role:** Engages threats that enter the engagement envelope.

**What it does:**
- Subscribes to `ThreatTopic`
- Engages each threat **once** when it closes to within 380 px using all weapons:

| Weapon   | ID | Kill Probability | Notes |
|---|---|---|---|
| SM-2 MR  | 1 | 75 % | VLS |
| SM-6     | 2 | 87 % | VLS extended range |
| ESSM     | 3 | 68 % | VLS close-in |
| CIWS     | 4 | 52 % | Phalanx gun |
| MK 45/62 | 5 | 36 % | Surface threats only (severity ≥ 3) |

- Publishes one `EffectorAction` per engagement (`destroyed = True/False`)

```zsh
cd py && python effector.py [-d DOMAIN_ID]
```

**Admin Console name:** `effector` | **Log:** `effector.log`

---

### App 4 — `VectorNav_Publisher.py`  *(UMAA GPS/IMU publisher)*

**Role:** Simulates a VectorNav USV sensor — publishes position and speed at 1 Hz.

**What it does:**
- Dead-reckons NE from San Diego Bay (32.7157°N, 117.1611°W) at commanded speed
- Speed is set by the Dashboard slider (0–30 kt); default 5 kt
- When speed changes the ship **continues from its current position** (no reset to home)
- Publishes `SpeedReportType` (SOG, STW, mode) and `GlobalPoseReportType` (lat/lon, alt, roll/pitch/yaw, course)
- Subscribes to `VectorNav::SpeedCommand` to receive slider updates from the Dashboard

```zsh
cd py && python VectorNav_Publisher.py [-d DOMAIN_ID]
```

**Example output:**
```
[VN][Speed ][...] SOG=2.580 m/s  STW=2.630 m/s  Mode=MRC
[VN][Pose  ][...] Lat=+32.715717°  Lon=-117.1610804°  Course=45.0°TN  Roll=+0.50°  Pitch=+0.16°
```

**Admin Console name:** `VectorNav_Publisher` | **Log:** `VectorNav_Publisher.log`

---

### App 5 — `VectorNav_Dashboard.py`  *(PyQt6 instrument dashboard)*

**Role:** Live instrument panel showing GPS, attitude, and speed data.

**What it does:**
- Subscribes to `SpeedReportType` and `GlobalPoseReportType`
- Dark-theme PyQt6 dashboard with four data cards and a compass widget:

| Panel | Fields |
|---|---|
| **Position** | Latitude (°N), Longitude (°E), Altitude (m MSL) |
| **Orientation** | Roll (°), Pitch (°), Yaw / Heading (°TN) |
| **Speed** | SOG (m/s), STW (m/s), STA (m/s), Mode |
| **Navigation** | Course True North (°), Nav Solution, Timestamp |
| **Compass widget** | Rotating rose + roll arc (amber) + pitch bar (emerald) |

- **Speed slider** (0–30 kt) publishes `VectorNav::SpeedCommand` → `VectorNav_Publisher`
  updates ship speed and continues dead-reckoning from current position
- Status bar turns amber if no data received for > 2.5 s

```zsh
cd py && python VectorNav_Dashboard.py [-d DOMAIN_ID]
```

**Admin Console name:** `VectorNav_Dashboard` | **Log:** `VectorNav_Dashboard.log`

---

## Coordinate System

The tactical map pins the VectorNav start position to the ship's home pixel:

| Geodetic | Map pixel | Scale |
|---|---|---|
| 32.7157°N, 117.1611°W (San Diego Bay) | (400, 570) — HOME buoy | 5 m / px |

At 5 kt (≈ 2.57 m/s) the ship moves ≈ 0.51 px/s — visible drift after ~30 seconds.
The HOME buoy stays fixed so GPS drift is immediately apparent.

---

## Architecture — Unified ddsEntities.py

All five applications use the single `ddsEntities.py` which detects two calling styles:

| Style | `Writer` 2nd arg | `Reader` 2nd arg | Used by |
|---|---|---|---|
| **Ship** — caller creates Publisher/Subscriber/Topic | `dds.Topic` | `dds.Topic` | `sensor`, `effector`, `command_control` |
| **VectorNav** — entities created internally | `bool` (periodic) | type class | `VectorNav_Publisher`, `VectorNav_Dashboard`, `HSMST_Subscriber` |

```python
# Ship style
ddsEntities.Writer(publisher, topic, shipConstants.Threat, False, 1.0)

# VectorNav style
ddsEntities.Writer(participant, True, 1.0, SpeedReportType, SpeedReportTypeTopic)
```

| Module | Purpose |
|---|---|
| `application.py` | Global `run_flag` + SIGINT handler (shared by all apps) |
| `ddsEntities.py` | `Writer(Thread)` / `Reader(Thread)` + `register_ship_types()` |
| `shipConstants.py` | `@idl.struct` types + sensor/effector/geometry constants |
| `ship_topics.py` | Concrete ship topic classes with `handler()` / `write()` overrides |
| `vn_constants.py` | VectorNav constants (topic strings, speed range, rate) |
| `umaa_types.py` | UMAA type re-exports from `rtiumaapy` package |
| `vn_topics.py` | VectorNav topic classes + `VectorNavState` simulation + `SpeedCommand` IDL |

---

## Manual Launch (without the script)

```zsh
# Source RTI environment once per terminal session
source /Applications/rti_connext_dds-7.7.0/resource/scripts/rtisetenv_arm64Darwin23clang16.0.zsh

cd py

# Terminal 1 — Command & Control GUI (start first)
python command_control.py

# Terminal 2 — Sensor suite
python sensor.py

# Terminal 3 — Effector suite
python effector.py
