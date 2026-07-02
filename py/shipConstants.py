"""
 * (c) Copyright, Real-Time Innovations, 2022.  All rights reserved.
 * RTI grants Licensee a license to use, modify, compile, and create derivative
 * works of the software solely for use with RTI Connext DDS. Licensee may
 * redistribute copies of the software provided that all such copies are subject
 * to this license. The software is provided "as is", with no warranty of any
 * type, including any warranty for fitness for any purpose. RTI is under no
 * obligation to maintain or support the software. RTI shall not be liable for
 * any incidental or consequential damages arising out of the use or inability
 * to use the software.

 Ship Threat Defense – compiled IDL types and application constants.

 This module mirrors idl/ShipThreat.idl using RTI Connext DDS Python compiled
 types (@rti.types.struct) and is the Python equivalent of the shared data
 definitions used by the C++ apps in apps/sensor, apps/effector, and
 apps/command_control.

 Analogy within the TMS codebase:
   tmsConstants.py  →  shipConstants.py
   (TMS IDL types)     (ship threat IDL types)

 Compiled (validated 2026-07-02):
   - Plain `int` is used for IDL `long` fields (idl.int32 rejected by mypy).
   - Plain `float` is used for IDL `double` fields.
   - Plain `bool` is used for IDL `boolean` fields.
"""

import rti.connextdds as dds  # noqa: F401  (imported for type stubs / side-effects)
import rti.types as idl

# ---------------------------------------------------------------------------
# DDS topic names  (must match across sensor, effector, and command_control)
# ---------------------------------------------------------------------------

THREAT_TOPIC           = "ThreatTopic"
SENSOR_DETECTION_TOPIC = "SensorDetectionTopic"
EFFECTOR_ACTION_TOPIC  = "EffectorActionTopic"

# ---------------------------------------------------------------------------
# Application-wide constants
# ---------------------------------------------------------------------------

DOMAIN_ID    = 0
HEARTBEAT_PERIOD = 1.0   # seconds

# Ship pixel position used in all range calculations (matches C++ constants)
SHIP_X_PX = 400.0
SHIP_Y_PX = 570.0

# Effectors engage when a threat crosses inside this radius (px)
EFFECTOR_ENGAGEMENT_RANGE_PX = 380.0

# ---------------------------------------------------------------------------
# Compiled IDL types  (mirrors module ship { ... } in idl/ShipThreat.idl)
# ---------------------------------------------------------------------------


@idl.struct(member_annotations={"id": [idl.key]})
class Threat:
    """Inbound threat originated by command_control and tracked by all apps.

    IDL equivalent:
        struct Threat { long id; double x; double y;
                        double heading; double speed; long severity; };
    """
    id:       idl.int32 = 0
    x:        float     = 0.0
    y:        float     = 0.0
    heading:  float     = 0.0
    speed:    float     = 0.0
    severity: idl.int32 = 0


@idl.struct(member_annotations={"sensor_id": [idl.key], "threat_id": [idl.key]})
class SensorDetection:
    """Detection report published by the sensor app.

    IDL equivalent:
        struct SensorDetection { long sensor_id; long threat_id;
                                 double x; double y; long confidence; };
    """
    sensor_id:  idl.int32 = 0
    threat_id:  idl.int32 = 0
    x:          float     = 0.0
    y:          float     = 0.0
    confidence: idl.int32 = 0


@idl.struct(member_annotations={"effector_id": [idl.key], "threat_id": [idl.key]})
class EffectorAction:
    """Engagement report published by the effector app.

    IDL equivalent:
        struct EffectorAction { long effector_id; long threat_id;
                                boolean destroyed; double x; double y; };
    """
    effector_id: idl.int32 = 0
    threat_id:   idl.int32 = 0
    destroyed:   bool      = False
    x:           float     = 0.0
    y:           float     = 0.0


# ---------------------------------------------------------------------------
# Aegis sensor suite definitions  (mirrors C++ SENSOR_DEFS in sensor app)
# ---------------------------------------------------------------------------

class SensorDef:
    """Describes one sensor in the Aegis sensor suite."""

    def __init__(self, sensor_id: int, name: str,
                 conf_min: int, conf_max: int, range_px: float) -> None:
        self.sensor_id = sensor_id
        self.name      = name
        self.conf_min  = conf_min
        self.conf_max  = conf_max
        self.range_px  = range_px   # detection radius from ship (pixels)


SENSOR_DEFS: list[SensorDef] = [
    SensorDef(1, "AN/SPY-1D",  88, 100, 412.0),  # 220 nm – primary Aegis phased-array radar
    SensorDef(2, "AN/SPQ-9B",  72,  90,  75.0),  #  40 nm – horizon search / gun FC radar
    SensorDef(3, "AN/SPS-67",  55,  75,  47.0),  #  25 nm – surface search radar
    SensorDef(4, "AN/SLQ-32",  65,  85, 187.0),  # 100 nm – electronic warfare / ESM
]


# ---------------------------------------------------------------------------
# Aegis weapon system definitions  (mirrors C++ EFFECTOR_DEFS in effector app)
# ---------------------------------------------------------------------------

class EffectorDef:
    """Describes one weapon system in the Aegis effector suite."""

    def __init__(self, effector_id: int, name: str, pk: int,
                 speed: float, surface_only: bool = False) -> None:
        self.effector_id  = effector_id
        self.name         = name
        self.pk           = pk            # probability of kill (%)
        self.speed        = speed         # interceptor speed (px / sec)
        self.surface_only = surface_only  # True → MK 45 only engages severity >= 3


EFFECTOR_DEFS: list[EffectorDef] = [
    EffectorDef(1, "SM-2 MR",   75, 150.0, False),  # Standard Missile 2 MR (VLS)
    EffectorDef(2, "SM-6",      87, 175.0, False),  # Standard Missile 6 extended range (VLS)
    EffectorDef(3, "ESSM",      68, 130.0, False),  # Evolved Sea Sparrow Missile (VLS)
    EffectorDef(4, "CIWS",      52, 210.0, False),  # Phalanx Close-In Weapon System
    EffectorDef(5, "MK 45/62",  36, 100.0, True ),  # 5-inch / 62-cal gun (surface threats only)
]
