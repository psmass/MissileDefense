"""
VectorNav_Publisher.py — VectorNav Component (Publisher)
=========================================================
Mirrors pyCompiledTypes/device.py from the TMS example.

This is the VectorNav Component shown in VectorNavBlockDiagram.drawio.
It publishes two UMAA SA topics at 1 Hz using the WaitSet-based Writer
threads from ddsEntities.py and concrete topic classes from vn_topics.py.

Topics published (SpeedStatus + GlobalPoseStatus Providers):
  UMAA::SA::SpeedStatus::SpeedReportType
  UMAA::SA::GlobalPoseStatus::GlobalPoseReportType

Usage:
  python VectorNav_Publisher.py [-d DOMAIN_ID]     (default 0)

No state machine is needed — the VectorNav sensor streams data continuously.
The writer threads run independently at 1 Hz using WaitSet timeouts.
"""

import argparse
import logging
from time import sleep

import rti.connextdds as dds

import application
import ddsEntities
import vn_constants
import vn_topics


def vecnav_main(domain_id: int) -> None:
    print("VectorNav Component Starting Up")
    logging.info('VectorNav Component Starting Up')

    # *** CREATE PARTICIPANT  (named so Admin Console shows "VectorNav_Publisher")
    qos = dds.DomainParticipantQos()
    qos.participant_name.name = "VectorNav_Publisher"
    participant = dds.DomainParticipant(domain_id=domain_id, qos=qos)

    # *** DECLARE SENSOR STATE OBJECT
    # VectorNavState holds / computes all simulated USV sensor values.
    # Both writer threads share the same instance (no locking needed —
    # all values are computed from time.monotonic()).
    vn_state = vn_topics.VectorNavState()

    # *** INSTANTIATE TOPIC WRITER OBJECTS
    speed_wtr = vn_topics.SpeedReport_Wtr(participant, vn_state)
    pose_wtr  = vn_topics.GlobalPoseReport_Wtr(participant, vn_state)

    # *** SUBSCRIBE TO SPEED MULTIPLIER COMMANDS (from Dashboard slider)
    speed_cmd_r = vn_topics.SpeedCommand_Rdr(participant, vn_state)

    # *** SUBSCRIBE TO ORBIT COMMANDS (from Dashboard orbit button)
    orbit_cmd_r = vn_topics.OrbitCommand_Rdr(participant, vn_state)

    # *** ATTACH WRITER LISTENERS (optional publication-match logging)
    speed_wtr.writer.set_listener(
        ddsEntities.DefaultWriterListener(), dds.StatusMask.ALL)
    pose_wtr.writer.set_listener(
        ddsEntities.DefaultWriterListener(), dds.StatusMask.ALL)

    # *** START WRITER AND READER THREADS
    speed_wtr.start()
    pose_wtr.start()
    speed_cmd_r.start()
    orbit_cmd_r.start()

    sleep(1)  # allow threads to begin their first WaitSet wait

    print("=" * 70)
    print(" VectorNav Component — Publisher")
    print(f" Domain  : {domain_id}")
    print(f" Speed   : {vn_constants.SPEED_TOPIC}")
    print(f" Pose    : {vn_constants.POSE_TOPIC}")
    print(f" Rate    : {vn_constants.PUBLISH_RATE_HZ} Hz")
    print(" Press Ctrl-C to stop.")
    print("=" * 70)

    # *** MAIN LOOP
    # The writer threads do all the work.  The main thread simply keeps the
    # process alive and monitors application.run_flag for a clean shutdown.
    # No state machine is required — the VectorNav sensor streams continuously.
    while application.run_flag:
        sleep(1)

    # *** SHUTDOWN WRITER THREADS
    logging.info('Shutting down writer threads')
    speed_wtr.join(timeout=3)
    pose_wtr.join(timeout=3)
    speed_cmd_r.join(timeout=3)
    orbit_cmd_r.join(timeout=3)

    print("VectorNav Component Exiting")
    logging.info('VectorNav Component Exiting')


if __name__ == "__main__":
    logging.basicConfig(
        handlers=[logging.FileHandler(
            filename="vecnav.log", encoding="utf-8", mode="a+")],
        format="%(asctime)s %(name)s:%(levelname)s:%(message)s",
        datefmt="%F %A %T",
        level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="UMAA VectorNav Component — Publisher (compiled types)")
    parser.add_argument("-d", "--domain", type=int, default=vn_constants.DOMAIN_ID,
                        help="DDS Domain ID  (default: %(default)s)")
    args = parser.parse_args()
    assert 0 <= args.domain < 233

    vecnav_main(args.domain)
