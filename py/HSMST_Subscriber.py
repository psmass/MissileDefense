"""
HSMST_Subscriber.py — HSMST Control Component (Subscriber, Partial)
=====================================================================
Mirrors pyCompiledTypes/controller.py from the TMS example.

This is the HSMST Control Component shown in VectorNavBlockDiagram.drawio.
It subscribes to two UMAA SA topics using WaitSet-based Reader threads from
ddsEntities.py and concrete topic classes from vn_topics.py.

Topics subscribed (SpeedStatus + GlobalPoseStatus Consumers):
  UMAA::SA::SpeedStatus::SpeedReportType
  UMAA::SA::GlobalPoseStatus::GlobalPoseReportType

Usage:
  python HSMST_Subscriber.py [-d DOMAIN_ID]     (default 0)

  Run VectorNav_Publisher.py on the same domain to generate data.

No state machine is needed for the HSMST consumer — each received sample
is handled immediately in the reader thread's handler() method.
"""

import argparse
import logging
from time import sleep

import rti.connextdds as dds

import application
import ddsEntities
import vn_constants
import vn_topics


def hsmst_main(domain_id: int) -> None:
    print("HSMST Control Component Starting Up")
    logging.info('HSMST Control Component Starting Up')

    # *** CREATE PARTICIPANT  (named so Admin Console shows "HSMST_Subscriber")
    qos = dds.DomainParticipantQos()
    qos.participant_name.name = "HSMST_Subscriber"
    participant = dds.DomainParticipant(domain_id=domain_id, qos=qos)

    # *** INSTANTIATE TOPIC READER OBJECTS
    # Each reader creates its own Topic + Subscriber + DataReader +
    # WaitSet and runs as an independent thread.
    speed_rdr = vn_topics.SpeedReport_Rdr(participant)
    pose_rdr  = vn_topics.GlobalPoseReport_Rdr(participant)

    # *** START READER THREADS
    speed_rdr.start()
    pose_rdr.start()

    sleep(2)  # allow threads to settle and begin waiting for data

    print("=" * 70)
    print(" HSMST Control Component — Subscriber  (Partial)")
    print(f" Domain  : {domain_id}")
    print(f" Speed   : {vn_constants.SPEED_TOPIC}")
    print(f" Pose    : {vn_constants.POSE_TOPIC}")
    print(" Waiting for VectorNav data…")
    print(" Press Ctrl-C to stop.")
    print("=" * 70)

    # *** MAIN LOOP
    # All data handling occurs in the reader threads via handler().
    # The main thread simply keeps the process alive.
    while application.run_flag:
        sleep(1)

    # *** SHUTDOWN READER THREADS
    logging.info('Shutting down reader threads')
    speed_rdr.join(timeout=6)   # reader timeout is 4 s; allow a little extra
    pose_rdr.join(timeout=6)

    print("HSMST Control Component Exiting")
    logging.info('HSMST Control Component Exiting')


if __name__ == "__main__":
    logging.basicConfig(
        handlers=[logging.FileHandler(
            filename="hsmst.log", encoding="utf-8", mode="a+")],
        format="%(asctime)s %(name)s:%(levelname)s:%(message)s",
        datefmt="%F %A %T",
        level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="UMAA HSMST Control Component — Subscriber (compiled types)")
    parser.add_argument("-d", "--domain", type=int, default=vn_constants.DOMAIN_ID,
                        help="DDS Domain ID  (default: %(default)s)")
    args = parser.parse_args()
    assert 0 <= args.domain < 233

    hsmst_main(args.domain)
