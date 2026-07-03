# Ship Threat Defense — Python Applications

Python implementation of the **Aegis Ship Threat Defense** system using
RTI Connext DDS 7.7.0 compiled types.  Three cooperating applications communicate
entirely over DDS topics — no shared memory, no direct function calls.

```
┌──────────────────────────────────────────────────────────────────────┐
│  VectorNav_Publisher.py  (vector_nav_py/)                            │
│  GlobalPoseReportType  →  GPS lat/lon/course at 1 Hz                 │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ GlobalPoseReportType
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                 command_control.py  (pygame GUI)                     │
│  • Left-click map to spawn inbound threats                           │
│  • Ship moves to follow GPS position from VectorNav_Publisher        │
│  • Displays sensor detections, effector actions, GPS panel           │
│  PUBLISHES   → ThreatTopic                                           │
│  SUBSCRIBES  ← SensorDetectionTopic                                  │
│  SUBSCRIBES  ← EffectorActionTopic                                   │
│  SUBSCRIBES  ← GlobalPoseReportType  (VectorNav GPS)                 │
└──────────┬──────────────────────────────────┬────────────────────────┘
           │ ThreatTopic                      │ ThreatTopic
           ▼                                  ▼
┌─────────────────────────┐       ┌───────────────────────────────────┐
│      sensor.py          │       │          effector.py              │
│  Aegis sensor suite:    │       │  Layered weapon defence:          │
│  AN/SPY-1D  412 px      │       │  SM-2 MR · SM-6 · ESSM           │
│  AN/SPQ-9B   75 px      │       │  CIWS · MK 45/62                 │
│  AN/SPS-67   47 px      │       │                                   │
│  AN/SLQ-32  187 px      │       │  PUBLISHES → EffectorActionTopic  │
│  PUBLISHES →            │       └───────────────────────────────────┘
│  SensorDetectionTopic   │
└─────────────────────────┘
```

---

## DDS Topics

| Topic | Type | Publisher → Subscriber |
|---|---|---|
| `ThreatTopic` | `ship::Threat` | `command_control` → `sensor`, `effector` |
| `SensorDetectionTopic` | `ship::SensorDetection` | `sensor` → `command_control` |
| `EffectorActionTopic` | `ship::EffectorAction` | `effector` → `command_control` |
| `UMAA::SA::GlobalPoseStatus::GlobalPoseReportType` | `GlobalPoseReportType` | `VectorNav_Publisher` → `command_control` |

---

## File Structure

```
ship_py/
├── README.md                  ← this file
│
├── command_control.py         ← Application 1  (pygame GUI — Command & Control)
├── sensor.py                  ← Application 2  (Aegis sensor suite)
├── effector.py                ← Application 3  (layered weapon defence)
│
├── ship_topics.py             ← Concrete Writer/Reader topic classes
├── ship_ddsEntities.py        ← Generic Writer(Thread) + Reader(Thread) base classes
├── shipConstants.py           ← IDL compiled types + all application constants
└── application.py             ← Global run_flag + SIGINT handler
```

### Module dependency map

```
command_control.py ──┐
sensor.py          ──┤──► ship_topics.py ──► ship_ddsEntities.py ──► application.py
effector.py        ──┘         │                    │
                               └──► shipConstants.py └──► rti.connextdds
```

---

## Prerequisites

### 1. RTI Connext DDS 7.7.0
```zsh
source /Applications/rti_connext_dds-7.7.0/resource/scripts/rtisetenv_arm64Darwin23clang16.0.zsh
```

### 2. Python virtual environment
```zsh
source ~/.venv/bin/activate
```

Verify:
```zsh
pip show rti.connext      # should show Version: 7.7.0
pip show pygame           # should show Version: 2.6.1  (required by command_control.py)
```

---

## The Three Applications

---

### Application 1 — command_control.py
**Role:** Command & Control — pygame GUI with mouse-driven threat spawning.

**What it does:**
- 1060 × 600 window with ocean background, radar rings and Arleigh Burke ship image
- Left-click the map to spawn an inbound threat; each threat moves toward the ship
- Republishes all active threats on `ThreatTopic` every 0.5 s
- Subscribes to `SensorDetectionTopic` → draws dotted sensor track lines
- Subscribes to `EffectorActionTopic` → fires interceptor/blast effects
- Subscribes to `GlobalPoseReportType` (VectorNav) → moves the ship to the GPS position
- Right-hand status panel shows live sensor detections, effector firings, threat list, GPS position

```zsh
cd ship_py
python command_control.py [-d DOMAIN_ID]
```

**Admin Console participant name:** `command_control`  
**Log file:** `command_control.log`

---

### Application 2 — sensor.py
**Role:** Aegis sensor suite — detects threats within range and publishes detections.

**What it does:**
- Subscribes to `ThreatTopic`
- For each received threat, all four Aegis sensors check their detection range:

| Sensor | ID | Range (px) | Confidence |
|---|---|---|---|
| AN/SPY-1D | 1 | 412 | 88–100 % |
| AN/SPQ-9B | 2 |  75 | 72–90 %  |
| AN/SPS-67 | 3 |  47 | 55–75 %  |
| AN/SLQ-32 | 4 | 187 | 65–85 %  |

- Publishes one `SensorDetection` per sensor-threat pair that is within range

```zsh
cd ship_py
python sensor.py [-d DOMAIN_ID]
```

**Admin Console participant name:** `sensor`  
**Log file:** `sensor.log`

---

### Application 3 — effector.py
**Role:** Layered weapon defence — engages threats that enter the engagement envelope.

**What it does:**
- Subscribes to `ThreatTopic`
- Engages each threat (once) when it closes to within 380 px using layered weapons:

| Weapon | ID | Pk % | Speed (px/s) |
|---|---|---|---|
| SM-2 MR | 1 | 75 | 150 |
| SM-6    | 2 | 87 | 175 |
| ESSM    | 3 | 68 | 130 |
| CIWS    | 4 | 52 | 210 |
| MK 45/62| 5 | 36 | 100 |

- Publishes one `EffectorAction` per engagement (destroyed = True/False)

```zsh
cd ship_py
python effector.py [-d DOMAIN_ID]
```

**Admin Console participant name:** `effector`  
**Log file:** `effector.log`

---

## VectorNav GPS Integration

When `vector_nav_py/VectorNav_Publisher.py` is running on the same DDS domain,
`command_control.py` automatically subscribes to `GlobalPoseReportType` and moves
the ship graphic to the corresponding map position.

**Coordinate mapping:**

| VectorNav start | Map pixel | Scale |
|---|---|---|
| 32.7157° N, -117.1611° E (San Diego Bay) | (400, 570) — home position | 5 m / px |

At the VectorNav simulation speed (~3 m/s NE), the ship moves at ~0.6 px/s — visible
drift over a few minutes of runtime.

The **GPS POSITION** panel in the status sidebar shows live Lat, Lon, and Course
when the publisher is running, or **NO FIX** when it is not.

---

## Running All Applications Together

Open **four terminals**, each with the Connext environment and venv activated:

```zsh
# Run once in every terminal before starting any application
source /Applications/rti_connext_dds-7.7.0/resource/scripts/rtisetenv_arm64Darwin23clang16.0.zsh
source ~/.venv/bin/activate
```

| Terminal | Directory | Command | Role |
|---|---|---|---|
| **1** | `ship_py` | `python command_control.py` | GUI — spawn threats, view everything |
| **2** | `ship_py` | `python sensor.py` | Aegis sensor suite |
| **3** | `ship_py` | `python effector.py` | Layered weapon defence |
| **4** | `vector_nav_py` | `python VectorNav_Publisher.py` | GPS position stream (optional) |

All applications default to **DDS Domain 0**.  
To use a different domain pass `-d <ID>` to each application.  
Stop any application with **Ctrl-C** — all threads shut down cleanly.

---

## Architecture — TMS Pattern

These applications follow the same compiled-types threading architecture as the
TMS `pyCompiledTypes/` example, adapted for the ship domain:

| Ship app | TMS equivalent | Purpose |
|---|---|---|
| `application.py` | `application.py` | `run_flag` + SIGINT handler |
| `shipConstants.py` | `tmsConstants.py` | Compiled IDL types + constants |
| `ship_ddsEntities.py` | `ddsEntities.py` | `Writer(Thread)` / `Reader(Thread)` base classes |
| `ship_topics.py` | `topics.py` | Concrete topic classes with `handler()` overrides |
| `sensor.py` | `device.py` | Sensor publisher entry point |
| `effector.py` | `device.py` | Effector publisher entry point |
| `command_control.py` | `controller.py` | GUI subscriber/publisher entry point |

**Key pattern:**
- `ship_ddsEntities.Writer` — blocks on a WaitSet; calls `write()` on periodic timeout
- `ship_ddsEntities.Reader` — blocks on a WaitSet + ReadCondition; calls `handler(data)` per sample
- Static sample fields set in `__init__`; dynamic fields updated in `write()` / read in `handler()`
- All threads poll `application.run_flag`; Ctrl-C triggers clean exit

---

## VectorNav Applications (vector_nav_py/)

Python implementation of the **VectorNav Block Diagram** using RTI Connext DDS 7.7.0
compiled types from the `rtiumaapy` package (generated by `rtiddsgen` 4.6.0).

```
┌────────────────────────────────────────────────────────────────┐
│              VectorNav Component  (VectorNav_Publisher.py)     │
│  ┌─────────────────────────┐   ┌────────────────────────────┐  │
│  │ SpeedStatus Provider    │   │ GlobalPoseStatus Provider  │  │
│  │ (Writer)                │   │ (Writer)                   │  │
│  └────────────┬────────────┘   └─────────────┬──────────────┘  │
└───────────────┼──────────────────────────────┼─────────────────┘
                │  SpeedReportType             │  GlobalPoseReportType
                ▼                              ▼
        ════════════════════════════════════════════════
                DDS Databus  (UMAA Autonomy Bus)
        ════════════════════════════════════════════════
                │                              │
                ▼                              ▼
┌───────────────────────────────────────────────────────────────────┐
│          HSMST Control Component  (HSMST_Subscriber.py /          │
│                                    VectorNav_Dashboard.py)        │
│  ┌─────────────────────────┐   ┌────────────────────────────┐     │
│  │ SpeedStatus Consumer    │   │ GlobalPoseStatus Consumer  │     │
│  │ (Reader)                │   │ (Reader)                   │     │
│  └─────────────────────────┘   └────────────────────────────┘     │
└───────────────────────────────────────────────────────────────────┘
```

### VectorNav DDS Topics

| Topic | IDL Type | Direction |
|---|---|---|
| `UMAA::SA::SpeedStatus::SpeedReportType` | `SpeedReportType` | VectorNav → HSMST |
| `UMAA::SA::GlobalPoseStatus::GlobalPoseReportType` | `GlobalPoseReportType` | VectorNav → HSMST |

### VectorNav File Structure

```
vector_nav_py/
├── VectorNav_Publisher.py     ← Application 1  (VectorNav Component)
├── HSMST_Subscriber.py        ← Application 2  (HSMST Console Consumer)
├── VectorNav_Dashboard.py     ← Application 3  (HSMST GUI Dashboard)
│
├── vn_topics.py               ← Concrete Writer/Reader topic classes
├── ddsEntities.py             ← Generic Writer(Thread) + Reader(Thread) base classes
├── umaa_types.py              ← UMAA compiled-type re-exports (from rtiumaapy)
├── vn_constants.py            ← Application constants (domain, rate, GUIDs, topic strings)
└── application.py             ← Global run_flag + SIGINT handler
```

#### Module dependency map

```
VectorNav_Publisher.py  ──┐
HSMST_Subscriber.py     ──┤──► vn_topics.py ──► ddsEntities.py ──► application.py
VectorNav_Dashboard.py  ──┘         │                                  │
                                    └──► umaa_types.py (rtiumaapy)     └── rti.connextdds
                                    └──► vn_constants.py
```

### VectorNav Prerequisites

```zsh
pip show rti.connext      # should show Version: 7.7.0
pip show rtiumaapy        # should show Version: 0.1.0
pip show pyqt6            # required by VectorNav_Dashboard.py only
```

Install PyQt6 if needed:
```zsh
pip install pyqt6
```

---

### VectorNav Application 1 — VectorNav_Publisher.py
**Role:** VectorNav Component — publishes simulated USV sensor data at 1 Hz.

**What it does:**
- Creates one `DomainParticipant` with two periodic `Writer` threads
- `SpeedReport_Wtr` publishes `SpeedReportType` (SOG, STW, mode)
- `GlobalPoseReport_Wtr` publishes `GlobalPoseReportType` (lat/lon, altitude, roll/pitch/yaw, course)
- Simulates a USV dead-reckoning NE from San Diego Bay with realistic wave motion

```zsh
cd vector_nav_py
python VectorNav_Publisher.py [-d DOMAIN_ID]
```

**Example output:**
```
[VN][Speed ][1782934372.376046000]  SOG=3.032 m/s  STW=3.082 m/s  Mode=MRC
[VN][Pose  ][1782934372.376565000]  Lat=+32.715719°  Lon=-117.1610770°  Alt=0.3m  Course=45.0°TN  Roll=+0.50°  Pitch=+0.16°
```

**Log file:** `vector_nav_py/vecnav.log`

---

### VectorNav Application 2 — HSMST_Subscriber.py
**Role:** HSMST Control Component — console subscriber.

**What it does:**
- Creates one `DomainParticipant` with two `Reader` threads
- `SpeedReport_Rdr` receives and prints each `SpeedReportType` sample
- `GlobalPoseReport_Rdr` receives and prints each `GlobalPoseReportType` sample

```zsh
cd vector_nav_py
python HSMST_Subscriber.py [-d DOMAIN_ID]
```

**Example output:**
```
[HSMST][Speed ] t=1782934372.376046000  SOG=     3.032 m/s  STW=     3.082 m/s  Mode=MRC
[HSMST][Pose  ] t=1782934372.376565000  Lat=+32.715719°  Lon=-117.1610771°  Alt=   0.30m  Course=45.0°TN  Roll=+0.50°  Pitch=+0.16°  Yaw=45.0°  Nav=MEASURED
```

**Log file:** `vector_nav_py/hsmst.log`

---

### VectorNav Application 3 — VectorNav_Dashboard.py
**Role:** HSMST Control Component — live PyQt6 GUI instrument dashboard.

**What it does:**
- Subscribes to the same two topics as `HSMST_Subscriber.py`
- Renders a dark-theme PyQt6 instrument panel with four data cards and a compass widget
- Status bar turns amber if no data received for > 2.5 seconds

#### Dashboard panels

| Panel | Fields | Source topic |
|---|---|---|
| **Position** | Latitude (°N+), Longitude (°E+), Altitude (m MSL) | `GlobalPoseReportType` |
| **Orientation** | Roll (°), Pitch (°), Yaw / Heading (°TN) | `GlobalPoseReportType` |
| **Speed** | SOG (m/s), STW (m/s), STA (m/s), Mode | `SpeedReportType` |
| **Navigation** | Course True North (°), Nav Solution, Timestamp | `GlobalPoseReportType` |
| **Compass widget** | Combined heading rose + roll arc + pitch bar | `GlobalPoseReportType` |

#### Compass widget

```
              N
              ▲  ← red needle (fixed, always points up = current heading)
         W ───●─── E         ● = centre dot
              ▼
              S
        ──────────  ← green horizontal bar: rises (bow up) / falls (bow down) with pitch
        ╰────╯      ← amber arc: sweeps CW (starboard roll) / CCW (port roll)

        045.0°      ← live heading readout at bottom
```

| Indicator | Colour | Field | Range |
|---|---|---|---|
| Rotating compass rose | Sky-blue ticks + N/E/S/W labels | `attitude.yaw.yaw` | Full 360° |
| Fixed red heading needle | Red | `attitude.yaw.yaw` | Always points to top |
| Roll arc (outer ring) | Amber | `attitude.roll.roll` | ±45° clamped |
| Pitch bar (horizontal) | Emerald | `attitude.pitch.pitch` | ±30° clamped |

```zsh
cd vector_nav_py
python VectorNav_Dashboard.py [-d DOMAIN_ID]
```

> **Note:** `HSMST_Subscriber.py` and `VectorNav_Dashboard.py` are independent consumers
> of the same publisher — run one or both simultaneously.

---

### Running VectorNav Applications

| Terminal | Directory | Command | Role |
|---|---|---|---|
| **1** | `vector_nav_py` | `python VectorNav_Publisher.py` | Sensor publisher |
| **2** | `vector_nav_py` | `python HSMST_Subscriber.py` | Console consumer |
| **3** | `vector_nav_py` | `python VectorNav_Dashboard.py` | GUI consumer |

---

### VectorNav Architecture — TMS Pattern

| VectorNav | TMS equivalent | Purpose |
|---|---|---|
| `application.py` | `application.py` | `run_flag` + SIGINT |
| `vn_constants.py` | `constants.py` | App-level constants |
| `umaa_types.py` | `tmsConstants.py` | Compiled DDS types |
| `ddsEntities.py` | `ship_ddsEntities.py` | `Writer(Thread)` / `Reader(Thread)` |
| `vn_topics.py` | `ship_topics.py` | Concrete topic classes |
| `VectorNav_Publisher.py` | `sensor.py` / `effector.py` | Publisher entry point |
| `HSMST_Subscriber.py` | `command_control.py` | Subscriber entry point |

---

### UMAA Data Model

Topic IDL source files are in `data_model/UMAA/SA/`:

```
data_model/UMAA/SA/
├── SpeedStatus/
│   └── SpeedReportType.idl      ← UMAA::SA::SpeedStatus::SpeedReportType
└── GlobalPoseStatus/
    └── GlobalPoseReportType.idl ← UMAA::SA::GlobalPoseStatus::GlobalPoseReportType
```

Python compiled types are provided by the `rtiumaapy` package
(`rticonnextdds-usecases-umaa/python`), generated by `rtiddsgen` 4.6.0.

---

### AI Cost of Implementation

This example was built end-to-end in a single AI-assisted coding session (GitHub Copilot / Claude).

| Type | Tokens | Rate | Cost |
|---|---|---|---|
| Input  | ~72,000 | $3.00 / 1M | **$0.22** |
| Output | ~26,000 | $15.00 / 1M | **$0.39** |
| **Total** | **~98,000** | | **~$0.61** |

> Output tokens are only ~27 % of total volume but account for **64 % of cost**
> (5× higher rate).  Multiple file rewrites during debugging were the primary
> cost driver.  Using the Connext MCP code validator *before* writing files
> would have reduced cost to **~$0.35–0.40**.



---

## What changed vs. `python/`

| Area | `python/` (DynamicData) | `pyCompiledTypes/` (compiled types) |
|---|---|---|
| Sample creation | `dds.DynamicData(type_from_qos_provider)` | `TypeClass()` — plain Python dataclass |
| Field write | `sample["fieldName"] = val` | `sample.fieldName = val` |
| Nested field write | `sample["a.b"] = val` | `sample.a.b = val` |
| Field read | `data["fieldName"]` | `data.fieldName` |
| DataWriter lookup | `dds.DynamicData.DataWriter.find_by_name(p, name)` | `dds.DataWriter(participant.find_datawriter(name))` |
| DataReader lookup | `dds.DynamicData.DataReader.find_by_name(p, name)` | `dds.DataReader(participant.find_datareader(name))` |
| Listener base | `dds.DynamicData.NoOpDataWriterListener` | `dds.NoOpDataWriterListener` |
| CFT find | `dds.DynamicData.ContentFilteredTopic.find(p, name)` | `dds.ContentFilteredTopic.find(p, name)` |
| Type registration | Not needed (QosProvider resolves from XML) | `dds.DomainParticipant.register_idl_type(TypeClass, "tms::TypeName")` called **before** `create_participant_from_config()` |

### Key files

| File | Purpose |
|---|---|
| `ddsEntities.py` | Base `Writer` / `Reader` thread classes — compiled-types version |
| `topics.py` | Concrete topic classes (all `sample["field"]` → `sample.field`) |
| `controller.py` | Master Controller application — registers types, runs state machine |
| `device.py` | Generator Device application — registers types, runs state machine |
| `constants.py` | Application constants (identical to `python/constants.py`) |
| `tmsConstants.py` | Thin shim that re-exports the auto-generated compiled types from `python/tmsConstants.py` |
| `application.py` | Signal-handler / run-flag (identical to `python/application.py`) |

---

## Prerequisites

Same as `python/` — install the RTI Connext DDS Python binding:

```
pip install rti.connextdds
```

See the full setup instructions in `python/README.md`.

---

## Type registration

The critical difference is the call to `ddsEntities.register_tms_types()` at
the top of both `controller_main()` and `device_main()`, **before**
`qos_provider.create_participant_from_config()`:

```python
ddsEntities.register_tms_types()                          # <-- new step
qos_provider = dds.QosProvider(constants.QOS_URL)
participant  = qos_provider.create_participant_from_config(...)
```

`register_tms_types()` calls `dds.DomainParticipant.register_idl_type()` for
each compiled type, binding the XML `<register_type name="tms::XYZ">` entries
in `tmsExampleApp.xml` to the corresponding Python `@idl.struct` classes in
`tmsConstants.py`.

---

## Running

```bash
cd pyCompiledTypes
python3 device.py
```

```bash
cd pyCompiledTypes
python3 controller.py
```

Both applications must be run from the `pyCompiledTypes/` directory so the
relative path `../model_distroA/tmsExampleApp.xml` resolves correctly.

---

## Environment

Tested with:

* macOS / Ubuntu 20.04
* RTI Connext DDS Professional 7.x
* Python 3.10+
