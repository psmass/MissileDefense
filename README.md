# Aegis Ship Defense Demo

A real-time, distributed ship defense simulation built with **RTI Connext DDS 7.7** and **SDL2**.  
Three independent processes — Command & Control, Sensor Suite, and Weapons/Effectors — communicate
exclusively over a DDS data bus, demonstrating a publish/subscribe architecture modelled on the
U.S. Navy's Aegis Combat System aboard an Arleigh Burke-class destroyer.

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

## How Does It Work?

The three executables share no code at runtime.  They are connected solely through three
DDS **Topics** defined in `idl/ShipThreat.idl`:

```
  ┌─────────────────────────────────────────────────────────────────────┐
  │                        DDS Domain (Domain 0)                        │
  │                                                                     │
  │   Topic: ship::Threat          Topic: ship::SensorDetection         │
  │   Topic: ship::EffectorAction                                       │
  └─────────────────────────────────────────────────────────────────────┘
         ▲  publish                subscribe ▼          subscribe ▼
         │                                  │                    │
  ┌──────┴──────┐              ┌─────────────┴──┐    ┌───────────┴────┐
  │  command_   │  subscribe   │    sensor      │    │   effector     │
  │  control    │◄─────────────│                │    │                │
  │             │  SensorDet.  │  AN/SPY-1D     │    │  SM-2 Block IV │
  │  SDL2 GUI   │              │  AN/SPQ-9B     │    │  SM-6          │
  │  Threat     │◄─────────────│  AN/SPS-67     │    │  ESSM          │
  │  Publisher  │  EffectorAct.│  AN/SLQ-32     │    │  CIWS Phalanx  │
  │             │              │                │    │  MK 45 Gun     │
  └─────────────┘              └────────────────┘    └────────────────┘
       │  publish Threat                │ publish          │ publish
       │  (click to spawn)              │ SensorDetection  │ EffectorAction
       └────────────────────────────────┘──────────────────┘
                  All three processes read/write the same DDS bus
```

### Data flow — step by step

| Step | Process | Action |
|------|---------|--------|
| 1 | **command_control** | Operator clicks the display → a `ship::Threat` sample is published with position, heading, speed, and severity. Re-published every 500 ms as the threat moves. |
| 2 | **sensor** | Subscribes to `ship::Threat`. Each of the four sensor models checks whether the threat has entered its detection radius. If so, it publishes a `ship::SensorDetection` with a confidence score. |
| 3 | **command_control** | Subscribes to `ship::SensorDetection`. Updates the status panel: sensor row changes from IDLE → active with threat ID and confidence %. |
| 4 | **effector** | Subscribes to `ship::Threat`. Once a threat crosses the SPY-1D engagement boundary (~380 px / ~200 nm), all applicable weapons publish `ship::EffectorAction` (with a probabilistic kill assessment). Each threat is engaged only once. |
| 5 | **command_control** | Subscribes to `ship::EffectorAction`. Renders interceptor missiles, launch plumes, and kill blasts. Updates the weapons panel: IDLE → FIRING → KILL. |

---

## Features

- **Three-process DDS architecture** — command_control, sensor, and effector are fully decoupled;
  any process can be stopped, restarted, or replaced without affecting the others.
- **Aegis sensor suite** with realistic detection radii:
  | Sensor | Role | Range |
  |--------|------|-------|
  | AN/SPY-1D | Phased-array radar | 220 nm |
  | AN/SLQ-32 | Electronic warfare | 100 nm |
  | AN/SPQ-9B | Gun fire-control radar | 40 nm |
  | AN/SPS-67 | Surface search radar | 25 nm |
- **Layered weapon engagement** — SM-2 Block IV, SM-6, ESSM, CIWS Phalanx, MK 45 5" Gun, each
  with independent Pk (probability of kill) and engagement rules.
- **Visual game loop** — scaled 350 nm display, side-profile Arleigh Burke PNG, typed threat icons
  (ASCM / Ballistic / Drone), launch plumes, interceptor missiles, and kill-blast effects.
- **Live status panel** — per-sensor confidence, per-weapon IDLE/FIRING/KILL, and an incoming
  threats table (type, speed, time-to-impact).
- **SPY-1D radar ring** — dashed red arc visualises the detection boundary; effectors hold fire
  until the threat crosses inside it.
- **Probabilistic intercept** — each weapon rolls against its Pk independently; a miss still
  animates a passing interceptor.

---

## Getting Started

### Download

Clone the repository:

```bash
git clone https://github.com/<your-username>/MissileDefense.git
cd MissileDefense
```

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Windows 10/11 (x64) | — | Only platform tested |
| Visual Studio 2022 | 17.x | Desktop C++ workload required |
| CMake | ≥ 3.10 | Must be on `PATH` |
| RTI Connext DDS | 7.7.0 | Install to `C:\RTI\rti_connext_dds-7.7.0` |
| vcpkg | current | Install to `C:\RTI\vcpkg` |
| SDL2 | via vcpkg | `vcpkg install sdl2:x64-windows` |
| SDL2_image | via vcpkg | `vcpkg install sdl2-image:x64-windows` |

**Install vcpkg dependencies** (run once):

```powershell
C:\RTI\vcpkg\vcpkg.exe install sdl2:x64-windows sdl2-image:x64-windows
```

**Generate DDS type-support code** from the IDL (run once, requires `rtiddsgen` on `PATH`):

```bat
generate_rtiddsgen.bat
```

This reads `idl/ShipThreat.idl` and writes C++ type-support files into `idl/generated/`.

### Build

```powershell
# From the repository root
cmake -S . -B build `
      -G "Visual Studio 17 2022" -A x64 `
      -DCMAKE_TOOLCHAIN_FILE="C:/RTI/vcpkg/scripts/buildsystems/vcpkg.cmake" `
      -DUSE_CONNEXT=ON `
      -DRTI_CONNEXTDDS_DIR="C:/RTI/rti_connext_dds-7.7.0"

cmake --build build --config Debug
```

> **Without RTI Connext:** omit `-DUSE_CONNEXT=ON` and `-DRTI_CONNEXTDDS_DIR`. The three
> executables will still build and run using local fallback structs, but DDS communication
> between processes will be disabled.

Compiled binaries land in `build\apps\<app>\Debug\`.

### Usage

Open **three separate terminals** from `C:\RTI\Demos\MissileDefense` and launch each process:

**Terminal 1 — Command & Control (SDL2 display):**
```powershell
cd .\build\apps\command_control\Debug
command_control.exe
```

**Terminal 2 — Sensor Suite:**
```powershell
cd .\build\apps\sensor\Debug
sensor.exe
```

**Terminal 3 — Weapons / Effectors:**
```powershell
cd .\build\apps\effector\Debug
effector.exe
```

Once all three are running:

1. **Click anywhere** above the ship in the SDL2 window to spawn an incoming threat.
2. Watch the **Sensors panel** light up as the threat crosses each sensor's detection radius.
3. When the threat crosses the **red SPY-1D ring**, the **Effectors panel** changes from IDLE →
   FIRING, interceptor missiles animate toward the target, and a KILL or miss blast is rendered.
4. The **Threats table** at the bottom of the panel shows live type, speed, and time-to-impact for
   every active contact.

Processes can be stopped and restarted independently at any time — DDS will reconnect them
automatically when they come back online.

---

## Project Structure

```
MissileDefense/
├── idl/
│   ├── ShipThreat.idl          # DDS topic definitions (Threat, SensorDetection, EffectorAction)
│   └── generated/              # rtiddsgen output (C++ type-support — generated, not committed)
├── apps/
│   ├── command_control/        # SDL2 GUI — threat publisher + DDS subscriber for sensor/effector data
│   ├── sensor/                 # Aegis sensor suite — subscribes Threat, publishes SensorDetection
│   └── effector/               # Weapons system  — subscribes Threat, publishes EffectorAction
├── ArleighBurke-class.png      # Ship side-profile (transparent PNG, copied to build output)
├── CMakeLists.txt
└── README.md
```

---

## License

This project is provided as a demonstration and is not affiliated with or endorsed by Raytheon,
Lockheed Martin, the U.S. Navy, or RTI.  RTI Connext DDS is a product of Real-Time Innovations,
Inc. and requires a separate license.
