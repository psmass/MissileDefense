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
 Differences from python/controller.py:
   - ddsEntities.register_tms_types() is called BEFORE
     qos_provider.create_participant_from_config() so that the RTI Python
     runtime associates each XML <register_type> entry with the corresponding
     compiled @idl.struct class.
   - All other controller logic is identical to the dynamic-types version.
"""

import sys
import logging
import argparse
from os import path as osPath
from time import sleep
import rti.connextdds as dds
import application
import constants
import tmsConstants
import topics
import ddsEntities

filepath = osPath.dirname(osPath.realpath(__file__))


def controller_main(domain_id):
    print("Controller Powering Up")
    logging.info('Controller Powering Up')

    shutdown = False

    # *** REGISTER COMPILED TYPES before XML App Creation ***
    # This must happen before qos_provider.create_participant_from_config() so
    # the DDS runtime can bind the XML <register_type name="tms::XYZ"> entries
    # to the Python @idl.struct classes defined in tmsConstants.py.
    ddsEntities.register_tms_types()

    # *** STAND UP PARTICIPANT WITH READERS AND WRITERS (XML App Creation)
    qos_provider = dds.QosProvider(constants.QOS_URL)
    participant   = qos_provider.create_participant_from_config(
        tmsConstants.master_controller.MASTER_CONTROLLER1)

    # *** DECLARE APP STATE AND TOPIC OBJECTS
    # (creates: readers, writers, and threads).  XML app create means the DDS
    # entities already exist; the topic classes simply look up handles.
    app_state_obj = topics.ApplicationStateObj(
        tmsConstants.tms_DeviceRole.ROLE_MICROGRID_CONTROLLER)

    controller_di_w         = topics.DeviceInfoMC_Wtr(participant, app_state_obj)
    controller_di_r         = topics.DeviceInfoMC_Rdr(participant, app_state_obj,
                                                       controller_di_w.writer.instance_handle)
    controller_hb_w         = topics.HeartbeatMC_Wtr(participant, app_state_obj)
    controller_hb_r         = topics.HeartbeatMC_Rdr(participant, app_state_obj,
                                                       controller_hb_w.writer.instance_handle)
    controller_amc_state_r  = topics.AMCStateMC_Rdr(participant, app_state_obj)
    controller_ate_rep_w    = topics.ATERepMC_Wtr(participant, app_state_obj)
    controller_ate_req_r    = topics.ATEReqMC_Rdr(participant, app_state_obj,
                                                    controller_ate_rep_w)
    controller_ate_result_r = topics.ATEResultMC_Rdr(participant, app_state_obj)
    controller_ess_req_w    = topics.ESSReqMC_Wtr(participant, app_state_obj)
    controller_reply_r      = topics.ReplyMC_Rdr(participant, app_state_obj)
    controller_ess_state_r  = topics.ESSStateMC_Rdr(participant, app_state_obj)

    # *** ATTACH WRITER LISTENER (optional – use instead of thread monitor)
    controller_di_w.writer.set_listener(
        ddsEntities.DefaultWriterListener(), dds.StatusMask.ALL)

    # *** START READER THREADS
    controller_di_r.start()
    controller_hb_r.start()
    controller_amc_state_r.start()
    controller_ate_req_r.start()
    controller_ate_result_r.start()
    controller_reply_r.start()
    controller_ess_state_r.start()

    sleep(5)  # let threads spin up

    # =====================================================================
    # CONTROLLER STATE MACHINE
    # =====================================================================
    print("\n\n **** Starting State Machine")
    logging.info('Starting State Machine')

    while not shutdown:
        if not application.run_flag:
            app_state_obj.setAppState(constants.ControllerState.SHUT_DOWN)

        if app_state_obj.appState() == constants.ControllerState.INIT:
            print("\nCONTROLLER STATE: INIT")
            app_state_obj._thisMCSelected         = False
            app_state_obj._authorizedForEnergizing = False
            controller_di_w.write()
            if not controller_hb_w.is_alive():
                controller_hb_w.start()
            app_state_obj.setAppState(constants.ControllerState.DISCOVERY)

        elif app_state_obj.appState() == constants.ControllerState.DISCOVERY:
            print("D ", end="", flush=True)
            if app_state_obj._deviceIdSet:
                app_state_obj.setAppState(constants.ControllerState.FOUND_NEW_DEVICE)

        elif app_state_obj.appState() == constants.ControllerState.FOUND_NEW_DEVICE:
            print("F ", end="", flush=True)
            if app_state_obj._thisMCSelected and app_state_obj._authorizedForEnergizing:
                app_state_obj.setAppState(constants.ControllerState.ENERGIZE)

        elif app_state_obj.appState() == constants.ControllerState.ENERGIZE:
            print("\nCONTROLLER STATE: ENERGIZE")
            print("Controller Energizing device {d_id}, current State: {e_state}".format(
                d_id=app_state_obj._deviceId,
                e_state=app_state_obj._deviceStartStopPresentLevel))

            if app_state_obj._deviceStartStopPresentLevel == \
               tmsConstants.tms_EnergyStartStopLevel.ESSL_OFF:
                controller_ess_req_w.write(
                    app_state_obj._deviceId,
                    tmsConstants.tms_EnergyStartStopLevel.ESSL_OPERATIONAL)
            app_state_obj.setAppState(constants.ControllerState.WAIT_CMD_IDLE)

        elif app_state_obj.appState() == constants.ControllerState.WAIT_CMD_IDLE:
            print(".", end="", flush=True)

        elif app_state_obj.appState() == constants.ControllerState.SHUT_DOWN:
            print("\nCONTROLLER STATE: SHUTDOWN")
            shutdown = True

        elif app_state_obj.appState() == constants.ControllerState.ERROR:
            print("\nCONTROLLER STATE: ERROR - Unexpected Event, resetting Target Device")
            app_state_obj.setAppState(constants.ControllerState.SHUT_DOWN)

        else:
            print("Else")
            logging.error('State Machine hit default(impossible?) else clause')

        sleep(1)

    # *** SHUTDOWN READER THREADS
    print("Controller Exiting")
    logging.info('Controller Exiting')

    if controller_hb_w.is_alive():
        controller_hb_w.join()
    controller_hb_r.join()
    controller_di_r.join()
    controller_amc_state_r.join()
    controller_ate_req_r.join()
    controller_ate_result_r.join()
    controller_reply_r.join()
    controller_ess_state_r.join()


if __name__ == "__main__":
    logging.basicConfig(
        handlers=[logging.FileHandler(
            filename="./controller.log", encoding='utf-8', mode='a+')],
        format="%(asctime)s %(name)s:%(levelname)s:%(message)s",
        datefmt="%F %A %T",
        level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="RTI Connext DDS Example: TMS Controller (compiled types)")
    parser.add_argument("-d", "--domain", type=int, default=0,
                        help="DDS Domain ID")
    args = parser.parse_args()
    assert 0 <= args.domain < 233

    controller_main(args.domain)
