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

 Ship Threat Defense – Command & Control Application  (Python / RTI Connext DDS)

 Python equivalent of apps/command_control/main.cpp.

 The C++ source uses SDL for a real-time graphical display.  This Python
 equivalent replaces the SDL render loop with a terminal-based state machine
 and periodic status panel, keeping the same DDS interactions and threat
 movement logic.

 Role:
   - Originates inbound threats (simulated spawning replaces the SDL
     mouse-click mechanic from the C++ app)
   - Moves threats toward the ship position each 100 ms loop cycle and
     republishes updated positions every REPUBLISH_INTERVAL (0.5 s) so that
     sensor and effector apps can evaluate range, exactly as the C++ app does
   - Subscribes to SensorDetectionTopic and EffectorActionTopic
   - Prints a periodic terminal status panel showing:
       • active threats with type, distance, and time-to-impact
       • latest sensor tracks per sensor
       • latest effector engagements per weapon system
   - Removes threats that have reached the hull (< 70 px radius)

 State Machine (mirrors C++ main loop structure):
   INIT  → ACTIVE  → SHUT_DOWN

 Programming patterns mirror the TMS device.py application:
   - Compiled IDL types registered via ddsEntities.register_ship_types()
   - Writer / Reader base classes from ddsEntities.py
   - Topic-specific business logic in ship_topics.py (handler() overrides)
   - WaitSet-based threading for all DDS I/O
   - Application state machine in the main loop (same as TMS device_main())
   - Ctrl-C handled via application.RUN_FLAG

 Usage:
   python command_control.py [-d <domain_id>]

 Validated with RTI Connext Python API mypy checker (2026-07-02).
"""

from __future__ import annotations

import argparse
import logging
import math
import random
from enum import IntEnum
from time import sleep, time

import rti.connextdds as dds

import application
import shipConstants
import ddsEntities
import ship_topics


# ---------------------------------------------------------------------------
# Timing constants
# ---------------------------------------------------------------------------

THREAT_SPAWN_INTERVAL = 8.0   # seconds between automatic threat spawns
REPUBLISH_INTERVAL    = 0.5   # seconds between threat-position republishes
STATUS_INTERVAL       = 5.0   # seconds between terminal status panel prints
LOOP_PERIOD           = 0.1   # seconds per main-loop cycle (10 Hz)
HULL_RADIUS_SQ        = 70.0 ** 2  # px² – threat removed when dist² < this

# Threat type labels (mirrors C++ type_str selection: id % 3)
_THREAT_TYPES = {0: "BALST", 1: "DRONE", 2: "ASCM "}


# ---------------------------------------------------------------------------
# Application state machine states
# ---------------------------------------------------------------------------

class C2State(IntEnum):
    INIT      = 0
    ACTIVE    = 1
    SHUT_DOWN = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spawn_threat(next_id: int) -> shipConstants.Threat:
    """Create a simulated inbound threat spawned outside SPY-1D range.

    Mirrors the SDL mouse-click threat creation in command_control/main.cpp.
    Spawns at a random position on a circle of radius 430–550 px centred on
    the ship.
    """
    t         = shipConstants.Threat()
    t.id      = next_id
    angle     = random.uniform(0.0, 2.0 * math.pi)
    radius    = random.uniform(430.0, 550.0)
    t.x       = shipConstants.SHIP_X_PX + radius * math.cos(angle)
    t.y       = shipConstants.SHIP_Y_PX + radius * math.sin(angle)
    t.heading = 180.0
    t.speed   = 22.0   # px / sec (same default as C++)
    t.severity = random.randint(1, 3)
    return t


def _update_position(t: shipConstants.Threat, dt: float) -> None:
    """Move threat toward the ship bow for one time-step dt (seconds).

    Mirrors the C++ per-frame threat-movement loop in command_control/main.cpp.
    """
    dx   = shipConstants.SHIP_X_PX - t.x
    dy   = (shipConstants.SHIP_Y_PX - 16.0) - t.y  # aim at main deck
    dist = math.sqrt(dx * dx + dy * dy)
    if dist > 1e-6:
        t.x += (dx / dist) * t.speed * dt
        t.y += (dy / dist) * t.speed * dt


def _at_hull(t: shipConstants.Threat) -> bool:
    """Return True when the threat has reached the hull (< 70 px from ship)."""
    dx = shipConstants.SHIP_X_PX - t.x
    dy = shipConstants.SHIP_Y_PX - t.y
    return (dx * dx + dy * dy) < HULL_RADIUS_SQ


def _print_status(
        app_state_obj: ship_topics.ApplicationStateObj,
        threats: dict[int, shipConstants.Threat]) -> None:
    """Print a terminal status panel.

    Replaces the SDL right-panel render in command_control/main.cpp, showing
    the same three sections: THREATS, SENSORS, EFFECTORS.
    """
    print("\n" + "=" * 62)
    print("  SHIP DEFENSE  –  COMMAND & CONTROL  –  STATUS REPORT")
    print("=" * 62)

    # ---- THREATS ----
    print(f"\n  THREATS  ({len(threats)} active)")
    if threats:
        print(f"  {'ID':<6}  {'TYPE':<6}  {'DIST (px)':>9}  {'TTI (s)':>8}")
        for t in threats.values():
            dx   = t.x - shipConstants.SHIP_X_PX
            dy   = t.y - shipConstants.SHIP_Y_PX
            dist = math.sqrt(dx * dx + dy * dy)
            tti  = dist / t.speed if t.speed > 0.01 else 999.0
            ttype = _THREAT_TYPES.get(t.id % 3, "UNK  ")
            print(f"  T#{t.id:<4}  {ttype:<6}  {dist:>9.1f}  {tti:>7.1f}s")
    else:
        print("  NO CONTACTS")

    # ---- SENSOR TRACKS ----
    sensor_names = {s.sensor_id: s.name for s in shipConstants.SENSOR_DEFS}
    print(f"\n  SENSOR TRACKS")
    if app_state_obj._sensor_detections:
        print(f"  {'SENSOR':<12}  {'THREAT':>7}  {'CONF':>5}")
        for sid, det in app_state_obj._sensor_detections.items():
            sname = sensor_names.get(sid, f"SENSOR-{sid}")
            print(f"  {sname:<12}  T#{det.threat_id:<5}  {det.confidence:>3}%")
    else:
        print("  NO TRACKS")

    # ---- EFFECTOR STATUS ----
    efx_names = {e.effector_id: e.name for e in shipConstants.EFFECTOR_DEFS}
    print(f"\n  EFFECTOR STATUS")
    if app_state_obj._effector_actions:
        print(f"  {'WEAPON':<10}  {'TARGET':>7}  {'STATUS':>7}")
        for eid, act in app_state_obj._effector_actions.items():
            ename  = efx_names.get(eid, f"EFX-{eid}")
            status = "KILL  " if act.destroyed else "FIRED "
            print(f"  {ename:<10}  T#{act.threat_id:<5}  {status}")
    else:
        print("  IDLE")

    print("=" * 62)


# ---------------------------------------------------------------------------
# Application entry point
# ---------------------------------------------------------------------------

def command_control_main(domain_id: int) -> None:
    print("Command & Control Powering Up")
    logging.info("Command & Control Powering Up")

    shutdown = False

    # *** REGISTER COMPILED TYPES before creating participant ***
    ddsEntities.register_ship_types()

    # *** CREATE PARTICIPANT (raw DDS API – default QoS) ***
    participant = dds.DomainParticipant(domain_id)

    # *** CREATE TOPICS ***
    threat_topic    = dds.Topic(participant, shipConstants.THREAT_TOPIC,
                                shipConstants.Threat)
    detection_topic = dds.Topic(participant, shipConstants.SENSOR_DETECTION_TOPIC,
                                shipConstants.SensorDetection)
    effector_topic  = dds.Topic(participant, shipConstants.EFFECTOR_ACTION_TOPIC,
                                shipConstants.EffectorAction)

    # *** CREATE PUBLISHER AND SUBSCRIBER ***
    publisher  = dds.Publisher(participant)
    subscriber = dds.Subscriber(participant)

    # *** DECLARE APP STATE ***
    app_state_obj = ship_topics.ApplicationStateObj("command_control")

    # *** DECLARE TOPIC OBJECTS ***
    threat_w       = ship_topics.ThreatWtr(
        publisher,  threat_topic,    app_state_obj)
    detection_r    = ship_topics.SensorDetectionRdr(
        subscriber, detection_topic, app_state_obj)
    effector_r     = ship_topics.EffectorActionRdr(
        subscriber, effector_topic,  app_state_obj)

    # *** ATTACH WRITER LISTENER ***
    threat_w.writer.set_listener(
        ddsEntities.DefaultWriterListener(), dds.StatusMask.ALL)

    # *** START READER THREADS ***
    detection_r.start()
    effector_r.start()

    sleep(2)  # let threads spin up

    # =====================================================================
    # APPLICATION STATE MACHINE
    # =====================================================================
    print("\n\n **** Command & Control Starting")
    logging.info("Command & Control Starting – domain %d", domain_id)

    c2_state: C2State = C2State.INIT
    threats:  dict[int, shipConstants.Threat] = {}
    next_id       = 1
    last_spawn    = time()
    last_republish = time()
    last_status   = time()
    last_update   = time()

    while not shutdown:
        if not application.RUN_FLAG:
            c2_state = C2State.SHUT_DOWN

        now = time()
        dt  = now - last_update
        last_update = now

        # ------------------------------------------------------------------
        # INIT  – one-time setup, transition immediately to ACTIVE
        # ------------------------------------------------------------------
        if c2_state == C2State.INIT:
            print("\nC2 STATE: INIT")
            logging.info("C2 STATE: INIT")
            c2_state = C2State.ACTIVE

        # ------------------------------------------------------------------
        # ACTIVE  – threat lifecycle + republish + status display
        # ------------------------------------------------------------------
        elif c2_state == C2State.ACTIVE:
            # Spawn a new simulated inbound threat periodically
            if now - last_spawn >= THREAT_SPAWN_INTERVAL:
                t = _spawn_threat(next_id)
                next_id += 1
                threats[t.id] = t
                threat_w.write_threat(t)
                last_spawn = now
                logging.info("Spawned Threat id=%d severity=%d at (%.1f, %.1f)",
                             t.id, t.severity, t.x, t.y)

            # Move all active threats toward the ship (mirrors C++ dt loop)
            for t in list(threats.values()):
                _update_position(t, dt)

            # Cull threats that have reached the hull
            hull_hits = [tid for tid, t in threats.items() if _at_hull(t)]
            for tid in hull_hits:
                print(f"\n[C2] *** ALERT: Threat T#{tid} REACHED THE HULL ***")
                logging.warning("Threat %d reached hull – removing", tid)
                threats.pop(tid)

            # Republish updated threat positions every REPUBLISH_INTERVAL
            # so sensor range-checks and effector engagement logic stay current
            if now - last_republish >= REPUBLISH_INTERVAL:
                for t in threats.values():
                    threat_w.write_threat(t)
                last_republish = now

            # Periodic terminal status display (replaces SDL render panel)
            if now - last_status >= STATUS_INTERVAL:
                _print_status(app_state_obj, threats)
                last_status = now

        # ------------------------------------------------------------------
        # SHUT_DOWN
        # ------------------------------------------------------------------
        elif c2_state == C2State.SHUT_DOWN:
            print("\nC2 STATE: SHUT_DOWN")
            logging.info("C2 STATE: SHUT_DOWN")
            shutdown = True

        sleep(LOOP_PERIOD)   # 10 Hz main loop

    # *** SHUTDOWN READER THREADS ***
    detection_r.join()
    effector_r.join()

    print("Command & Control Exiting")
    logging.info("Command & Control Exiting")


if __name__ == "__main__":
    logging.basicConfig(
        handlers=[logging.FileHandler(
            filename="./command_control.log", encoding="utf-8", mode="a+")],
        format="%(asctime)s %(name)s:%(levelname)s:%(message)s",
        datefmt="%F %A %T",
        level=logging.INFO,
    )

    parser = argparse.ArgumentParser(
        description="RTI Connext DDS: Ship Threat Defense – Command & Control")
    parser.add_argument(
        "-d", "--domain", type=int, default=0, help="DDS Domain ID (0-232)")
    args = parser.parse_args()
    assert 0 <= args.domain < 233

    command_control_main(args.domain)
