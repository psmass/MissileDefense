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

 Ship Threat Defense – Sensor Application  (Python / RTI Connext DDS)

 Python equivalent of apps/sensor/main.cpp.

 Role:
   - Subscribes to ThreatTopic (published by command_control.py)
   - For each incoming Threat position update the Aegis sensor suite evaluates
     range and reports a SensorDetection if the threat is inside sensor coverage:
         AN/SPY-1D  220 nm  (412 px)  – primary phased-array radar
         AN/SPQ-9B   40 nm  ( 75 px)  – horizon search / gun FC radar
         AN/SPS-67   25 nm  ( 47 px)  – surface search radar
         AN/SLQ-32  100 nm  (187 px)  – electronic warfare / ESM
   - Publishes SensorDetection samples to SensorDetectionTopic

 Programming patterns mirror the TMS device.py application:
   - Compiled IDL types registered via ddsEntities.register_ship_types()
   - Writer / Reader base classes from ship_ddsEntities.py
   - Topic-specific business logic in ship_topics.py (handler() overrides)
   - WaitSet-based threading for all DDS I/O
   - Ctrl-C handled via application.run_flag

 Usage:
   python sensor.py [-d <domain_id>]

 Validated with RTI Connext Python API mypy checker (2026-07-02).
"""

from __future__ import annotations

import argparse
import logging
from time import sleep

import rti.connextdds as dds

import application
import shipConstants
import ship_ddsEntities as ddsEntities
import ship_topics


def sensor_main(domain_id: int) -> None:
    print("Sensor Powering Up")
    logging.info("Sensor Powering Up")

    # List the active Aegis sensor suite (mirrors C++ SENSOR_DEFS[] in sensor/main.cpp)
    print("\n Aegis Sensor Suite:")
    for s in shipConstants.SENSOR_DEFS:
        print(f"   [{s.sensor_id}] {s.name:<12}  range={s.range_px:>5.0f} px  "
              f"conf={s.conf_min}–{s.conf_max}%")
    print()

    # *** REGISTER COMPILED TYPES before creating participant ***
    ddsEntities.register_ship_types()

    # *** CREATE PARTICIPANT – named so it appears in Admin Console Logical View ***
    _qos = dds.DomainParticipantQos()
    _qos.participant_name.name = "sensor"
    participant = dds.DomainParticipant(domain_id, _qos)

    # *** CREATE TOPICS ***
    threat_topic    = dds.Topic(participant, shipConstants.THREAT_TOPIC,
                                shipConstants.Threat)
    detection_topic = dds.Topic(participant, shipConstants.SENSOR_DETECTION_TOPIC,
                                shipConstants.SensorDetection)

    # *** CREATE PUBLISHER AND SUBSCRIBER ***
    publisher  = dds.Publisher(participant)
    subscriber = dds.Subscriber(participant)

    # *** DECLARE APP STATE ***
    app_state_obj = ship_topics.ApplicationStateObj("sensor")

    # *** DECLARE TOPIC OBJECTS ***
    # detection_w must be created before threat_r because ThreatRdr holds a reference
    detection_w = ship_topics.SensorDetectionWtr(
        publisher, detection_topic, app_state_obj)
    threat_r    = ship_topics.ThreatRdr(
        subscriber, threat_topic, app_state_obj, detection_w)

    # *** ATTACH WRITER LISTENER ***
    detection_w.writer.set_listener(
        ddsEntities.DefaultWriterListener(), dds.StatusMask.ALL)

    # *** START READER THREADS ***
    threat_r.start()

    sleep(2)  # let threads spin up

    # =====================================================================
    # SENSOR MAIN LOOP
    # =====================================================================
    print("\n **** Sensor listening for threats on domain", domain_id)
    logging.info("Sensor listening for threats on domain %d", domain_id)

    try:
        while application.run_flag:
            sleep(1)
    except KeyboardInterrupt:
        pass

    # *** SHUTDOWN READER THREADS ***
    threat_r.join()

    print("Sensor Exiting")
    logging.info("Sensor Exiting")


if __name__ == "__main__":
    logging.basicConfig(
        handlers=[logging.FileHandler(
            filename="./sensor.log", encoding="utf-8", mode="a+")],
        format="%(asctime)s %(name)s:%(levelname)s:%(message)s",
        datefmt="%F %A %T",
        level=logging.INFO,
    )

    parser = argparse.ArgumentParser(
        description="RTI Connext DDS: Ship Threat Defense – Sensor")
    parser.add_argument(
        "-d", "--domain", type=int, default=0, help="DDS Domain ID (0-232)")
    args = parser.parse_args()
    assert 0 <= args.domain < 233

    sensor_main(args.domain)
