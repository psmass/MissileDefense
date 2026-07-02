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

 COMPILED TYPES VERSION
 ----------------------
 Differences from python/device.py:
   - ddsEntities.register_tms_types() is called BEFORE
     qos_provider.create_participant_from_config() so that the RTI Python
     runtime associates each XML <register_type> entry with the corresponding
     compiled @idl.struct class.
   - Typed sample field access uses Python attributes instead of dict-style
     subscripts:
         device_ess_state_w._sample.presentLevel = ...
         (was device_ess_state_w._sample["presentLevel"] = ...)
   - All other device logic is identical to the dynamic-types version.
"""

import sys
import logging
import tmsConstants
import constants
import argparse
from os import path as osPath
from enum import IntEnum
from time import sleep
import rti.connextdds as dds
import application
import topics
import ddsEntities

filepath = osPath.dirname(osPath.realpath(__file__))


def device_main(domain_id):
    print("Device Powering Up")
    logging.info('Device Powering Up')

    shutdown = False

    # *** REGISTER COMPILED TYPES before XML App Creation ***
    # Must happen before qos_provider.create_participant_from_config().
    ddsEntities.register_tms_types()

    # *** STAND UP PARTICIPANT WITH READERS AND WRITERS (XML App Creation)
    qos_provider = dds.QosProvider(constants.QOS_URL)
    participant   = qos_provider.create_participant_from_config(
        tmsConstants.generator_device.DEVICE1)

    # *** DECLARE APP STATE AND TOPIC OBJECTS
    app_state_obj       = topics.ApplicationStateObj(tmsConstants.tms_DeviceRole.ROLE_SOURCE)

    device_di_w         = topics.DeviceInfoGD_Wtr(participant, app_state_obj)
    device_di_r         = topics.DeviceInfoGD_Rdr(participant, app_state_obj,
                                                    device_di_w.writer.instance_handle)
    device_hb_w         = topics.HeartbeatGD_Wtr(participant, app_state_obj)
    device_hb_r         = topics.HeartbeatGD_Rdr(participant, app_state_obj,
                                                   device_hb_w.writer.instance_handle)
    device_amc_state_w  = topics.AMCStateGD_Wtr(participant, app_state_obj)
    device_ate_req_w    = topics.ATEReqGD_Wtr(participant, app_state_obj)
    device_ate_res_w    = topics.ATEResultGD_Wtr(participant, app_state_obj)
    device_ate_rep_r    = topics.ATERepGD_Rdr(participant, app_state_obj, device_ate_res_w)
    device_reply_w      = topics.ReplyGD_Wtr(participant, app_state_obj)
    device_ess_req_r    = topics.ESSReqGD_Rdr(participant, app_state_obj, device_reply_w)
    device_ess_state_w  = topics.ESSStateGD_Wtr(participant, app_state_obj)

    # *** ATTACH WRITER LISTENER (optional)
    device_di_w.writer.set_listener(
        ddsEntities.DefaultWriterListener(), dds.StatusMask.ALL)

    # *** START READER THREADS
    device_di_r.start()
    device_hb_r.start()
    device_ate_rep_r.start()
    device_ess_req_r.start()

    sleep(5)  # let threads spin up

    # =====================================================================
    # DEVICE STATE MACHINE
    # =====================================================================
    print("\n\n **** Starting State Machine")
    logging.info('Starting State Machine')

    count_in_state = 0

    while not shutdown:
        if not application.run_flag:
            app_state_obj.setAppState(constants.DeviceState.SHUT_DOWN)

        if app_state_obj.appState() == constants.DeviceState.INIT:
            print("\nDEVICE STATE: INIT")
            app_state_obj._authorizedForEnergizing = False
            app_state_obj._masterControllerId      = ''
            # Re-initialise the ESS state writer (creates fresh typed sample)
            device_ess_state_w.__init__(participant, app_state_obj)
            device_di_w.write()
            if not device_hb_w.is_alive():
                device_hb_w.start()
            device_ess_state_w.write()
            app_state_obj.setAppState(constants.DeviceState.DISCOVERY)

        elif app_state_obj.appState() == constants.DeviceState.DISCOVERY:
            print("D ", end="", flush=True)
            if app_state_obj._mcIdSet:
                app_state_obj.setAppState(constants.DeviceState.FOUND_NEW_CONTROLLER)

        elif app_state_obj.appState() == constants.DeviceState.FOUND_NEW_CONTROLLER:
            print("\nDEVICE STATE: FOUND NEW CONTROLLER")
            device_amc_state_w.set_mc_in_sample(app_state_obj._masterControllerId)
            device_amc_state_w.write()
            app_state_obj.setAppState(constants.DeviceState.POWER_UP_AUTH)

        elif app_state_obj.appState() == constants.DeviceState.POWER_UP_AUTH:
            print("P ", end="", flush=True)
            count_in_state += 1
            if count_in_state % 10 == 0:
                app_state_obj.clearOutstandingRequest()
                device_ate_req_w.write()
            if app_state_obj._authorizedForEnergizing:
                app_state_obj.setAppState(constants.DeviceState.WAIT_CMD_IDLE)

        elif app_state_obj.appState() == constants.DeviceState.WAIT_CMD_IDLE:
            print(".", end="", flush=True)
            if app_state_obj._deviceStartStopPresentLevel != \
               app_state_obj._deviceStartStopFutureLevel:
                app_state_obj.setAppState(constants.DeviceState.ENERGIZE)

        elif app_state_obj.appState() == constants.DeviceState.ENERGIZE:
            print("\nDEVICE STATE: ENERGIZE")
            # Assume the device transitioned to the future level
            app_state_obj._deviceStartStopPresentLevel = \
                app_state_obj._deviceStartStopFutureLevel
            # Update the sample using compiled-type attribute access
            device_ess_state_w._sample.presentLevel = \
                app_state_obj._deviceStartStopPresentLevel
            device_ess_state_w.write()
            app_state_obj.setAppState(constants.DeviceState.WAIT_CMD_IDLE)

        elif app_state_obj.appState() == constants.DeviceState.SHUT_DOWN:
            print("\nDEVICE STATE: SHUT_DOWN")
            shutdown = True

        elif app_state_obj.appState() == constants.DeviceState.ERROR:
            print("\nDEVICE STATE: ERROR - Unexpected Event, resetting Device")
            app_state_obj.setAppState(constants.DeviceState.SHUT_DOWN)

        else:
            logging.error("State Machine else clause hit - Device in undefined state")

        sleep(1)

    # *** SHUTDOWN READER THREADS
    if device_hb_w.is_alive():
        device_hb_w.join()
    device_di_r.join()
    device_ate_rep_r.join()
    device_ess_req_r.join()

    print("Device Exiting")
    logging.info('Device Exiting')


if __name__ == "__main__":
    logging.basicConfig(
        handlers=[logging.FileHandler(
            filename="./device.log", encoding='utf-8', mode='a+')],
        format="%(asctime)s %(name)s:%(levelname)s:%(message)s",
        datefmt="%F %A %T",
        level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="RTI Connext DDS Example: TMS Device (compiled types)")
    parser.add_argument("-d", "--domain", type=int, default=0,
                        help="DDS Domain ID")
    args = parser.parse_args()
    assert 0 <= args.domain < 233

    device_main(args.domain)
