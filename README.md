# Aegis Ship Defense Demo

A real-time, distributed ship defense simulation built with **RTI Connext DDS 7.7** and **SDL2/pygame**.  
Three independent processes — Command & Control, Sensor Suite, and Weapons/Effectors — communicate
exclusively over a DDS data bus, demonstrating a publish/subscribe architecture modelled on the
U.S. Navy's Aegis Combat System aboard an Arleigh Burke-class destroyer.

Two implementations are provided: the original **C++ / SDL2** apps in `apps/`, and a full
**Python / pygame + PyQt6** port in `py/` that adds VectorNav UMAA GPS/IMU integration and
a live instrument dashboard.

---

## Repository Structure

```
MissileDefense/
├── apps/                       # C++ / SDL2 implementation (CMake)
│   ├── command_control/        #   SDL2 GUI — threat publisher + DDS subscriber
│   ├── sensor/                 #   Aegis sensor suite
│   └── effector/               #   Weapons / effector system
├── py/                         # Python / pygame / PyQt6 implementation (5 apps)
│   ├── command_control.py      #   App 1  pygame GUI — Command & Control
│   ├── sensor.py               #   App 2  Aegis sensor suite
│   ├── effector.py             #   App 3  Layered weapon defence
│   ├── VectorNav_Publisher.py  #   App 4  UMAA GPS/IMU publisher (VectorNav sim)
│   ├── VectorNav_Dashboard.py  #   App 5  PyQt6 instrument dashboard + speed slider
│   ├── ddsEntities.py          #   Shared DDS Writer/Reader base classes
│   ├── ship_topics.py          #   Ship-domain topic classes
│   ├── vn_topics.py            #   VectorNav topic classes + SpeedCommand IDL
│   ├── shipConstants.py        #   Compiled IDL types + sensor/effector constants
│   ├── vn_constants.py         #   VectorNav constants
│   ├── umaa_types.py           #   UMAA type re-exports (rtiumaapy)
│   ├── application.py          #   run_flag + SIGINT handler
│   ├── HSMST_Subscriber.py     #   Console subscriber for VectorNav topics
│   ├── command_control_cli.py  #   CLI (non-GUI) version of command_control
│   └── README.md               #   Full Python app documentation
├── idl/
│   ├── ShipThreat.idl          # DDS topic definitions (C++ implementation)
│   └── generated/              # rtiddsgen C++ type-support output
├── start_all_python.zsh        # macOS launcher — menu-driven, quadrant screen layout
├── ArleighBurke-class.png      # Ship side-profile PNG
├── CMakeLists.txt
└── README.md                   # this file
```

---

## Overview

The simulation places an Arleigh Burke-class destroyer at the waterline of a tactical display.
The operator clicks the map to spawn incoming threats (Anti-Ship Cruise Missiles, Ballistic
Missiles, or Drones). Each threat is published onto the DDS bus. Independent sensor and weapons
processes subscribe, apply their own logic, and publish back detections and intercept results —
all without any direct function calls between processes.

In the Python implementation the ship's position is driven by live **VectorNav GPS** data
(simulated dead-reckoning from San Diego Bay). A **speed slider** (0–30 kt) in the VectorNav
Dashboard controls the ship speed in real time; the ship continues from its current position
when the speed changes.

---

## DDS Architecture

All three ship-defense processes share three DDS topics:

```
  ┌─────────────────────────────────────────────────────────────────────┐
  │                        DDS Domain (Domain 0)                        │
  │   Topic: ship::Threat          Topic: ship::SensorDetection         │
  │   Topic: ship::EffectorAction                                       │
  └─────────────────────────────────────────────────────────────────────┘
         ▲  publish                subscribe ▼          subscribe ▼
         │                                  │                    │
  ┌──────┴──────┐              ┌─────────────┴──┐    ┌───────────┴────┐
  │  command_   │  subscribe   │    sensor      │    │   effector     │
  │  control    │◄─────────────│                │    │                │
  │             │  SensorDet.  │  AN/SPY-1D     │    │  SM-2 Block IV │
  │  GUI        │              │  AN/SPQ-9B     │    │  SM-6          │
  │  Threat     │◄─────────────│  AN/SPS-67     │    │  ESSM          │
  │  Publisher  │  EffectorAct.│  AN/SLQ-32     │    │  CIWS Phalanx  │
  │             │              │                │    │  MK 45 Gun     │
  └─────────────┘              └────────────────┘    └────────────────┘
```

The Python implementation adds two more topics for VectorNav GPS/speed integration:

```
  VectorNav_Publisher ──► GlobalPoseReportType ──► command_control (ship moves)
                      ──► SpeedReportType      ──► VectorNav_Dashboard
  VectorNav_Dashboard ──► SpeedCommand         ──► VectorNav_Publisher (slider)
```

---

## Python Implementation — Quickstart

> See [`py/README.md`](py/README.md) for full documentation.

### Prerequisites

| Requirement | Notes |
|---|---|
| RTI Connext DDS 7.7.0 | macOS arm64 |
| Python 3.12 + `~/.venv` | `pip install rti.connext rtiumaapy pygame pyqt6` |

```zsh
source /Applications/rti_connext_dds-7.7.0/resource/scripts/rtisetenv_arm64Darwin23clang16.0.zsh
```

### Launch all five apps (recommended)

```zsh
./start_all_python.zsh
```

This opens an interactive menu that divides the screen into four quadrants:

```
┌────────────────────┬────────────────────┐
│  command_control   │  VectorNav_        │
│  pygame GUI        │  Dashboard Qt GUI  │
│  (upper left)      │  (upper right)     │
├────────────────────┼────────────────────┤
│  menu terminal     │  sensor            │
│  (lower left)      │  effector          │
│                    │  VectorNav_Pub     │
│                    │  (lower right)     │
└────────────────────┴────────────────────┘
```

| Option | Starts |
|---|---|
| `1` | Ship Defense — command_control, sensor, effector |
| `2` | VectorNav — Publisher + Dashboard |
| `3` | Stop all processes and close all Terminal windows |

### Manual launch

```zsh
cd py
python command_control.py    # Terminal 1 — start first
python sensor.py             # Terminal 2
python effector.py           # Terminal 3
python VectorNav_Publisher.py  # Terminal 4  (optional — GPS)
python VectorNav_Dashboard.py  # Terminal 5  (optional — instrument panel)
```

---

## Python Implementation — Key Features

- **Ship-centred viewport** — ship is fixed on screen; the tactical world scrolls beneath it
- **VectorNav GPS** — ship moves to follow live lat/lon (San Diego Bay → NE at 0–30 kt)
- **Speed slider** — 0–30 kt published via DDS `SpeedCommand` topic; position is continuous (no reset)
- **Orange HOME buoy** — fixed world marker shows GPS drift from starting position
- **Layered Aegis defence** — 4 sensors, 5 weapons, probabilistic kill assessment
- **Interceptor animations** — launch plumes, missiles, kill blasts driven by `EffectorActionTopic`
- **Status panel** — sensor detections, effector firings, threat table, GPS lat/lon/course

---

## C++ / SDL2 Implementation

> See [`apps/README.md`](apps/README.md) for build instructions.

### Prerequisites

| Requirement | Version |
|---|---|
| CMake | ≥ 3.10 |
| RTI Connext DDS | 7.7.0 |
| SDL2 + SDL2_image | via vcpkg |

### Build

```powershell
cmake -S . -B build -G "Visual Studio 17 2022" -A x64 \
      -DCMAKE_TOOLCHAIN_FILE="C:/RTI/vcpkg/scripts/buildsystems/vcpkg.cmake" \
      -DUSE_CONNEXT=ON \
      -DRTI_CONNEXTDDS_DIR="C:/RTI/rti_connext_dds-7.7.0"
cmake --build build --config Debug
```

### Run

```powershell
build\apps\command_control\Debug\command_control.exe   # Terminal 1
build\apps\sensor\Debug\sensor.exe                     # Terminal 2
build\apps\effector\Debug\effector.exe                 # Terminal 3
```

---

## License

This project is provided as a demonstration and is not affiliated with or endorsed by Raytheon,
Lockheed Martin, the U.S. Navy, or RTI.  RTI Connext DDS is a product of Real-Time Innovations,
Inc. and requires a separate license.


---

## Overview

The simulation places an Arleigh Burke-class destroyer at the bottom of a 350-nautical-mile
display.  The operator clicks anywhere on the screen to spawn incoming threats (Anti-Ship Cruise
Missiles, Ballistic Missiles, or Drones).  Each threat is published onto the DDS bus.  Independent
sensor and weapons processes subscribe, apply their own logic, and publish back detections and
intercept results — all without any direct function calls between processes.

The result is a live, visual demonstration of how DDS decouples producers from consumers in a
real-time C2 (Command and Control) system.

---
