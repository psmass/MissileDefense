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

 Ship Threat Defense – topic Writers and Readers with application business logic.

 This module is the ship-domain equivalent of topics.py in the TMS app.
 Each class inherits shipEntities.Writer or shipEntities.Reader and overrides
 handler() with the application-specific logic for that topic.

 Analogy with the TMS codebase:
   topics.py (TMS)        →  ship_topics.py  (Ship Threat Defense)
   HeartbeatGD_Wtr        →  ThreatWtr
   HeartbeatGD_Rdr        →  ThreatRdr        (sensor app)
   DeviceInfoGD_Wtr       →  SensorDetectionWtr
   DeviceInfoGD_Rdr       →  SensorDetectionRdr (C2 app)
   ESSReqGD_Rdr           →  EffectorThreatRdr  (effector app)
   ESSStateGD_Wtr         →  EffectorActionWtr
   ATEResultMC_Rdr        →  EffectorActionRdr  (C2 app)

 INSTANTIATE YOUR TOPICS IN THIS FILE.
 Your topics must inherit either shipEntities.Reader or shipEntities.Writer
 and override handler() for topic-specific data access.

 Validated with RTI Connext Python API mypy checker (2026-07-02).
"""

from __future__ import annotations

from typing import Any, Dict, Set
import logging
import math
import random

import application    # noqa: F401  (imported for run_flag side-effects in base classes)
import shipConstants
import shipEntities
import rti.connextdds as dds


# ---------------------------------------------------------------------------
# ApplicationStateObj
# ---------------------------------------------------------------------------

class ApplicationStateObj:
    """Holds shared runtime state for ship-threat-defense applications.

    A single instance is shared across all topic Writers and Readers so they
    can exchange data without direct coupling.

    Mirrors the TMS ApplicationStateObj in topics.py.
    """

    def __init__(self, role: str) -> None:
        self._role = role  # "sensor" | "effector" | "command_control"

        # Active threats keyed by threat.id
        self._threats: Dict[int, shipConstants.Threat] = {}

        # Latest detection per sensor_id (populated by SensorDetectionRdr)
        self._sensor_detections: Dict[int, shipConstants.SensorDetection] = {}

        # Latest effector action per effector_id (populated by EffectorActionRdr)
        self._effector_actions: Dict[int, shipConstants.EffectorAction] = {}

        # Set of threat IDs already engaged by the effector (prevents duplicates)
        self._engaged: Set[int] = set()

    # ------------------------------------------------------------------
    # Threat management
    # ------------------------------------------------------------------

    def update_threat(self, threat: shipConstants.Threat) -> None:
        self._threats[threat.id] = threat

    def remove_threat(self, threat_id: int) -> None:
        self._threats.pop(threat_id, None)

    def get_threats(self) -> Dict[int, shipConstants.Threat]:
        return self._threats

    # ------------------------------------------------------------------
    # Sensor and effector tracking
    # ------------------------------------------------------------------

    def update_sensor_detection(self, detection: shipConstants.SensorDetection) -> None:
        self._sensor_detections[detection.sensor_id] = detection

    def update_effector_action(self, action: shipConstants.EffectorAction) -> None:
        self._effector_actions[action.effector_id] = action

    # ------------------------------------------------------------------
    # Engagement de-duplication (effector app)
    # ------------------------------------------------------------------

    def is_engaged(self, threat_id: int) -> bool:
        return threat_id in self._engaged

    def mark_engaged(self, threat_id: int) -> None:
        self._engaged.add(threat_id)


# ===========================================================================
# Command & Control  –  Threat  (writer)
# ===========================================================================

class ThreatWtr(shipEntities.Writer):
    """Publishes Threat position updates from the command_control app.

    command_control originates threats (simulated spawning replaces the
    SDL mouse-click from the C++ app) and republishes their updated positions
    every REPUBLISH_INTERVAL so sensor and effector apps can check range.
    """

    def __init__(self, publisher: dds.Publisher, topic: dds.Topic,
                 app_state_obj: ApplicationStateObj) -> None:
        shipEntities.Writer.__init__(
            self, publisher, topic, shipConstants.Threat,
            periodic=False, period=1.0)
        self._app_state_obj = app_state_obj

    def write_threat(self, threat: shipConstants.Threat) -> None:
        """Publish a specific Threat sample directly (not the shared _sample)."""
        print(f"[C2] Publishing Threat id={threat.id} "
              f"at ({threat.x:.1f}, {threat.y:.1f})")
        self._writer.write(threat)


# ===========================================================================
# Sensor  –  Threat  (reader)
# ===========================================================================

class ThreatRdr(shipEntities.Reader):
    """Sensor app: receives Threat updates and fires detection reports.

    Mirrors the C++ ThreatListener::on_data_available() in sensor/main.cpp:
    for each received Threat, each sensor in the Aegis suite checks whether
    the threat is inside its detection range and, if so, publishes a
    SensorDetection with a random confidence value drawn from that sensor's
    accuracy range.
    """

    def __init__(self, subscriber: dds.Subscriber, topic: dds.Topic,
                 app_state_obj: ApplicationStateObj,
                 detection_wtr: SensorDetectionWtr) -> None:
        shipEntities.Reader.__init__(
            self, subscriber, topic, shipConstants.Threat)
        self._app_state_obj = app_state_obj
        self._detection_wtr = detection_wtr

    def handler(self, data: Any) -> None:
        threat: shipConstants.Threat = data
        logging.info("Received Threat id=%d at (%.1f, %.1f)",
                     threat.id, threat.x, threat.y)
        self._app_state_obj.update_threat(threat)

        # Each sensor in the Aegis suite checks range and reports a detection
        for sensor in shipConstants.SENSOR_DEFS:
            dx = threat.x - shipConstants.SHIP_X_PX
            dy = threat.y - shipConstants.SHIP_Y_PX
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > sensor.range_px:
                continue
            confidence = random.randint(sensor.conf_min, sensor.conf_max)
            self._detection_wtr.write_detection(
                sensor.sensor_id, threat.id,
                threat.x, threat.y, confidence)


# ===========================================================================
# Sensor  –  SensorDetection  (writer)
# ===========================================================================

class SensorDetectionWtr(shipEntities.Writer):
    """Publishes SensorDetection reports from the sensor app.

    Mirrors the C++ g_detection_writer->write() call in sensor/main.cpp.
    """

    def __init__(self, publisher: dds.Publisher, topic: dds.Topic,
                 app_state_obj: ApplicationStateObj) -> None:
        shipEntities.Writer.__init__(
            self, publisher, topic, shipConstants.SensorDetection,
            periodic=False, period=1.0)
        self._app_state_obj = app_state_obj

    def write_detection(self, sensor_id: int, threat_id: int,
                        x: float, y: float, confidence: int) -> None:
        """Populate and publish one SensorDetection sample."""
        self._sample.sensor_id  = sensor_id
        self._sample.threat_id  = threat_id
        self._sample.x          = x
        self._sample.y          = y
        self._sample.confidence = confidence
        sensor_name = next(
            (s.name for s in shipConstants.SENSOR_DEFS
             if s.sensor_id == sensor_id), f"SENSOR-{sensor_id}")
        print(f"[SENSOR] {sensor_name:<12} detected T#{threat_id} "
              f"at ({x:.1f},{y:.1f})  conf={confidence}%")
        self._writer.write(self._sample)


# ===========================================================================
# Command & Control  –  SensorDetection  (reader)
# ===========================================================================

class SensorDetectionRdr(shipEntities.Reader):
    """Command & Control: receives sensor detection reports for display.

    Stores the latest detection per sensor_id in the shared ApplicationStateObj.
    The command_control print_status() function reads these for the status panel.
    """

    def __init__(self, subscriber: dds.Subscriber, topic: dds.Topic,
                 app_state_obj: ApplicationStateObj) -> None:
        shipEntities.Reader.__init__(
            self, subscriber, topic, shipConstants.SensorDetection)
        self._app_state_obj = app_state_obj

    def handler(self, data: Any) -> None:
        detection: shipConstants.SensorDetection = data
        logging.info(
            "Received SensorDetection sensor=%d threat=%d conf=%d%%",
            detection.sensor_id, detection.threat_id, detection.confidence)
        self._app_state_obj.update_sensor_detection(detection)
        sensor_name = next(
            (s.name for s in shipConstants.SENSOR_DEFS
             if s.sensor_id == detection.sensor_id),
            f"SENSOR-{detection.sensor_id}")
        print(f"[C2] Sensor track: {sensor_name:<12} "
              f"T#{detection.threat_id}  conf={detection.confidence}%")


# ===========================================================================
# Effector  –  Threat  (reader)
# ===========================================================================

class EffectorThreatRdr(shipEntities.Reader):
    """Effector app: receives Threat updates and fires weapon engagements.

    Mirrors the C++ ThreatListener::on_data_available() in effector/main.cpp:
    - Engages a threat only once (de-duplicated via ApplicationStateObj._engaged)
    - Only fires when the threat has crossed inside EFFECTOR_ENGAGEMENT_RANGE_PX
      (same 380 px radius as the C++ source)
    - Applies layered defence: all weapon systems engage; MK 45/62 only when
      threat.severity >= 3 (surface threat), mirroring the C++ surface_only check
    """

    def __init__(self, subscriber: dds.Subscriber, topic: dds.Topic,
                 app_state_obj: ApplicationStateObj,
                 action_wtr: EffectorActionWtr) -> None:
        shipEntities.Reader.__init__(
            self, subscriber, topic, shipConstants.Threat)
        self._app_state_obj = app_state_obj
        self._action_wtr    = action_wtr

    def handler(self, data: Any) -> None:
        threat: shipConstants.Threat = data
        logging.info("Received Threat id=%d at (%.1f, %.1f)",
                     threat.id, threat.x, threat.y)
        self._app_state_obj.update_threat(threat)

        # Engage only when threat has closed to engagement range
        dx   = threat.x - shipConstants.SHIP_X_PX
        dy   = threat.y - shipConstants.SHIP_Y_PX
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > shipConstants.EFFECTOR_ENGAGEMENT_RANGE_PX:
            return

        # Only engage each threat once to avoid duplicate engagement reports
        if self._app_state_obj.is_engaged(threat.id):
            return
        self._app_state_obj.mark_engaged(threat.id)

        # Layered defence: all weapon systems evaluate the threat
        for efx in shipConstants.EFFECTOR_DEFS:
            if efx.surface_only and threat.severity < 3:
                continue
            destroyed = (random.randint(1, 100) <= efx.pk)
            self._action_wtr.write_action(
                efx.effector_id, threat.id,
                destroyed, threat.x, threat.y)


# ===========================================================================
# Effector  –  EffectorAction  (writer)
# ===========================================================================

class EffectorActionWtr(shipEntities.Writer):
    """Publishes EffectorAction engagement reports from the effector app.

    Mirrors the C++ g_action_writer->write() call in effector/main.cpp.
    """

    def __init__(self, publisher: dds.Publisher, topic: dds.Topic,
                 app_state_obj: ApplicationStateObj) -> None:
        shipEntities.Writer.__init__(
            self, publisher, topic, shipConstants.EffectorAction,
            periodic=False, period=1.0)
        self._app_state_obj = app_state_obj

    def write_action(self, effector_id: int, threat_id: int,
                     destroyed: bool, x: float, y: float) -> None:
        """Populate and publish one EffectorAction sample."""
        self._sample.effector_id = effector_id
        self._sample.threat_id   = threat_id
        self._sample.destroyed   = destroyed
        self._sample.x           = x
        self._sample.y           = y
        efx_name = next(
            (e.name for e in shipConstants.EFFECTOR_DEFS
             if e.effector_id == effector_id), f"EFX-{effector_id}")
        status = "KILL " if destroyed else "FIRED"
        print(f"[EFFECTOR] {efx_name:<10} → T#{threat_id:<3}  [{status}]")
        self._writer.write(self._sample)


# ===========================================================================
# Command & Control  –  EffectorAction  (reader)
# ===========================================================================

class EffectorActionRdr(shipEntities.Reader):
    """Command & Control: receives effector engagement reports for display.

    Stores the latest action per effector_id in the shared ApplicationStateObj.
    The command_control print_status() function reads these for the status panel.
    """

    def __init__(self, subscriber: dds.Subscriber, topic: dds.Topic,
                 app_state_obj: ApplicationStateObj) -> None:
        shipEntities.Reader.__init__(
            self, subscriber, topic, shipConstants.EffectorAction)
        self._app_state_obj = app_state_obj

    def handler(self, data: Any) -> None:
        action: shipConstants.EffectorAction = data
        logging.info(
            "Received EffectorAction effector=%d threat=%d destroyed=%s",
            action.effector_id, action.threat_id, action.destroyed)
        self._app_state_obj.update_effector_action(action)
        efx_name = next(
            (e.name for e in shipConstants.EFFECTOR_DEFS
             if e.effector_id == action.effector_id),
            f"EFX-{action.effector_id}")
        status = "KILL " if action.destroyed else "FIRED"
        print(f"[C2] Weapon report: {efx_name:<10} → T#{action.threat_id:<3}  [{status}]")
