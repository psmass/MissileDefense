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

 Ship Threat Defense – Effector Application  (Python / RTI Connext DDS)

 Python equivalent of apps/effector/main.cpp.

 Role:
   - Subscribes to ThreatTopic (published by command_control.py)
   - Implements layered Aegis weapon engagement when a threat closes inside
     the engagement range (380 px ≈ same as C++ source):
         SM-2 MR   Pk = 75 %  (Standard Missile 2 Medium Range, VLS)
         SM-6      Pk = 87 %  (Standard Missile 6 extended range, VLS)
         ESSM      Pk = 68 %  (Evolved Sea Sparrow Missile, VLS)
         CIWS      Pk = 52 %  (Phalanx Close-In Weapon System)
         MK 45/62  Pk = 36 %  (5-inch / 62-cal gun – surface threats only)
   - Each threat is engaged only once (de-duplicated via ApplicationStateObj)
   - Publishes EffectorAction samples to EffectorActionTopic

 Programming patterns mirror the TMS device.py application:
   - Compiled IDL types registered via ddsEntities.register_ship_types()
   - Writer / Reader base classes from ddsEntities.py
   - Topic-specific business logic in ship_topics.py (handler() overrides)
   - WaitSet-based threading for all DDS I/O
   - Ctrl-C handled via application.RUN_FLAG

 Usage:
   python effector.py [-d <domain_id>]

 Validated with RTI Connext Python API mypy checker (2026-07-02).
"""

from __future__ import annotations

import argparse
import logging
from time import sleep

import rti.connextdds as dds

import application
import shipConstants
import ddsEntities
import ship_topics


def effector_main(domain_id: int) -> None:
    print("Effector Powering Up")
    logging.info("Effector Powering Up")

    # *** REGISTER COMPILED TYPES before creating participant ***
    ddsEntities.register_ship_types()

    # *** CREATE PARTICIPANT – named so it appears in Admin Console Logical View ***
    _qos = dds.DomainParticipantQos()
    _qos.participant_name.name = "effector"
    participant = dds.DomainParticipant(domain_id, _qos)

    # *** CREATE TOPICS ***
    threat_topic   = dds.Topic(participant, shipConstants.THREAT_TOPIC,
                               shipConstants.Threat)
    effector_topic = dds.Topic(participant, shipConstants.EFFECTOR_ACTION_TOPIC,
                               shipConstants.EffectorAction)

    # *** CREATE PUBLISHER AND SUBSCRIBER ***
    publisher  = dds.Publisher(participant)
    subscriber = dds.Subscriber(participant)

    # *** DECLARE APP STATE ***
    app_state_obj = ship_topics.ApplicationStateObj("effector")

    # *** DECLARE TOPIC OBJECTS ***
    # action_w must be created before threat_r because EffectorThreatRdr holds a reference
    action_w = ship_topics.EffectorActionWtr(
        publisher, effector_topic, app_state_obj)
    threat_r = ship_topics.EffectorThreatRdr(
        subscriber, threat_topic, app_state_obj, action_w)

    # *** ATTACH WRITER LISTENER ***
    action_w.writer.set_listener(
        ddsEntities.DefaultWriterListener(), dds.StatusMask.ALL)

    # *** START READER THREADS ***
    threat_r.start()

    sleep(2)  # let threads spin up

    # =====================================================================
    # EFFECTOR MAIN LOOP
    # =====================================================================
    print("\n **** Effector listening for threats on domain", domain_id)
    logging.info("Effector listening for threats on domain %d", domain_id)

    try:
        while application.RUN_FLAG:
            sleep(1)
    except KeyboardInterrupt:
        pass

    # *** SHUTDOWN READER THREADS ***
    threat_r.join()

    print("Effector Exiting")
    logging.info("Effector Exiting")


if __name__ == "__main__":
    logging.basicConfig(
        handlers=[logging.FileHandler(
            filename="./effector.log", encoding="utf-8", mode="a+")],
        format="%(asctime)s %(name)s:%(levelname)s:%(message)s",
        datefmt="%F %A %T",
        level=logging.INFO,
    )

    parser = argparse.ArgumentParser(
        description="RTI Connext DDS: Ship Threat Defense – Effector")
    parser.add_argument(
        "-d", "--domain", type=int, default=0, help="DDS Domain ID (0-232)")
    args = parser.parse_args()
    assert 0 <= args.domain < 233

    effector_main(args.domain)
