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
 This file mirrors python/topics.py but uses compiled @idl.struct types rather
 than DynamicData.

 Key differences from the dynamic python/ version:
   - Each Writer/Reader passes its compiled type class to the base constructor
     (e.g. tmsConstants.tms_Heartbeat) instead of a type-name string.
   - Data sample fields are accessed via Python attribute syntax:
         self._sample.deviceId = "abc"       (was self._sample["deviceId"])
         self._sample.requestId.sequenceId   (was self._sample["requestId.sequenceId"])
   - Received data in handler() methods uses the same attribute syntax:
         data.deviceId                       (was data["deviceId"])
   - dds.ContentFilteredTopic.find() replaces the DynamicData-namespaced form.

 INSTANTIATE YOUR TOPICS IN THIS FILE

 Your topics must inherit either a ddsEntities.Reader or ddsEntities.Writer.
 They MUST implement / override the handler() member function to deal with
 topic specific fields (read/write) and will likely need extended member
 functions and data members to do specific functions based on application and
 specific topic status/state.
"""

import application
import ddsEntities
import constants
import tmsConstants
import rti.connextdds as dds
from time import sleep
import logging


# ---------------------------------------------------------------------------
# ApplicationStateObj  (unchanged from python/ version)
# ---------------------------------------------------------------------------

class ApplicationStateObj():
    """Holds per-device / per-controller runtime state.

    A single instance is shared across all topic Writers and Readers so they
    can coordinate the application state machine.
    """
    def __init__(self, role):
        self._role = role
        self._deviceId = ''
        self._masterControllerId = ''
        self._thisMCSelected = False
        self._authorizedForEnergizing = False
        self._deviceStartStopPresentLevel = tmsConstants.tms_EnergyStartStopLevel.ESSL_UNKNOWN
        self._deviceStartStopFutureLevel  = tmsConstants.tms_EnergyStartStopLevel.ESSL_UNKNOWN

        self._application_state = constants.ControllerState.INIT
        self._deviceIdSet       = False
        self._mcIdSet           = False
        self._sequenceNumber    = 0
        self._rrSequenceNumber  = self._sequenceNumber
        self._outstandingRequest = False

        if self._role == tmsConstants.tms_DeviceRole.ROLE_MICROGRID_CONTROLLER:
            self._masterControllerId = constants.CONTROLLER1_ID
            self._mcIdSet = True
            print("Master Controller ID set: ", self._masterControllerId)
        else:
            self._deviceId = constants.DEVICE1_ID
            self._deviceIdSet = True
            print("Generator Device ID set: ", self._deviceId)

    def appState(self):
        return self._application_state

    def setAppState(self, state):
        self._application_state = state

    def sequenceNumber(self):
        self._sequenceNumber += 1
        return self._sequenceNumber

    def rrSequenceNumber(self):
        if not self._outstandingRequest:
            self._rrSequenceNumber  = self.sequenceNumber()
            self._outstandingRequest = True
        return self._rrSequenceNumber

    def outstandingRequest(self):
        return self._outstandingRequest

    def clearOutstandingRequest(self):
        self._outstandingRequest = False

    def setDevId(self, deviceId):
        self._deviceId = deviceId
        self._deviceIdSet = True
        print("Found Device Id: ", self._deviceId)

    def setMCId(self, mcId):
        self._masterControllerId = mcId
        self._mcIdSet = True
        print("Found Controller Id: ", self._masterControllerId)

    def deviceId(self):
        return self._deviceId

    def deviceIdSet(self):
        return self._deviceIdSet

    # ------------------------------------------------------------------
    # Helpers for setting IDs in compiled-type samples.
    # Simple (non-dotted) field names use setattr directly.
    # Dotted names (e.g. "requestId.requestingDeviceId") are traversed
    # one component at a time.
    # ------------------------------------------------------------------

    @staticmethod
    def _set_nested_attr(obj, dotted_name, value):
        parts = dotted_name.split('.')
        for part in parts[:-1]:
            obj = getattr(obj, part)
        setattr(obj, parts[-1], value)

    def setDevIdInSample(self, sample, field_name):
        self._set_nested_attr(sample, field_name, self._deviceId)

    def setMCIdInSample(self, sample, field_name):
        self._set_nested_attr(sample, field_name, self._masterControllerId)


# ===========================================================================
# Generator Device  –  Heartbeat
# ===========================================================================

class HeartbeatGD_Wtr(ddsEntities.Writer):
    def __init__(self, participant, app_state_obj):
        ddsEntities.Writer.__init__(
            self, participant, True, constants.HEARTBEAT_PERIOD,
            tmsConstants.tms_Heartbeat,                      # compiled type
            tmsConstants.generator_device.HEARTBEAT_WRITER)

        self._thread_started = False
        self._app_state_obj  = app_state_obj
        # Preload static field using attribute access
        self._sample.deviceId = app_state_obj._deviceId

    def write(self):  # override to add sequence number
        self._thread_started = True
        self._sample.sequenceNumber = self._app_state_obj.sequenceNumber()
        self._writer.write(self._sample)


class HeartbeatGD_Rdr(ddsEntities.Reader):
    def __init__(self, participant, app_state_obj, ignore_wtr_instance_hndl):
        ddsEntities.Reader.__init__(
            self, participant,
            tmsConstants.tms_Heartbeat,                      # compiled type
            tmsConstants.generator_device.HEARTBEAT_READER)

        self._app_state_obj = app_state_obj
        participant.ignore_datawriter(ignore_wtr_instance_hndl)

    def handler(self, data):
        print("HB", end="", flush=True)


# ===========================================================================
# Master Controller  –  Heartbeat
# ===========================================================================

class HeartbeatMC_Wtr(ddsEntities.Writer):
    def __init__(self, participant, app_state_obj):
        ddsEntities.Writer.__init__(
            self, participant, True, constants.HEARTBEAT_PERIOD,
            tmsConstants.tms_Heartbeat,
            tmsConstants.master_controller.HEARTBEAT_WRITER)

        self._app_state_obj = app_state_obj
        self._sample.deviceId = app_state_obj._masterControllerId

    def write(self):
        self._sample.sequenceNumber = self._app_state_obj.sequenceNumber()
        self._writer.write(self._sample)


class HeartbeatMC_Rdr(ddsEntities.Reader):
    def __init__(self, participant, app_state_obj, ignore_wtr_instance_hndl):
        ddsEntities.Reader.__init__(
            self, participant,
            tmsConstants.tms_Heartbeat,
            tmsConstants.master_controller.HEARTBEAT_READER)

        self._app_state_obj = app_state_obj
        participant.ignore_datawriter(ignore_wtr_instance_hndl)

    def handler(self, data):
        print("HB", end="", flush=True)


# ===========================================================================
# Generator Device  –  DeviceInfo
# ===========================================================================

class DeviceInfoGD_Wtr(ddsEntities.Writer):
    def __init__(self, participant, app_state_obj):
        ddsEntities.Writer.__init__(
            self, participant, False, 0.0,
            tmsConstants.tms_DeviceInfo,
            tmsConstants.generator_device.DEVICE_INFO_WRITER)

        self._app_state_obj = app_state_obj
        # Preload static fields using attribute access
        self._sample.deviceId       = app_state_obj._deviceId
        self._sample.role           = tmsConstants.tms_DeviceRole.ROLE_SOURCE
        self._sample.product.modelName = "MyGeneratorDevice"

    def get_data_sample(self):
        return self._sample


class DeviceInfoGD_Rdr(ddsEntities.Reader):
    def __init__(self, participant, app_state_obj, ignore_wtr_instance_hndl):
        ddsEntities.Reader.__init__(
            self, participant,
            tmsConstants.tms_DeviceInfo,
            tmsConstants.generator_device.DEVICE_INFO_READER)

        self._app_state_obj = app_state_obj
        participant.ignore_datawriter(ignore_wtr_instance_hndl)

    def handler(self, data):
        print("\nReceived sample for topic {r_name}".format(r_name=self._reader_name))
        mcId = data.deviceId          # compiled-type attribute access
        self._app_state_obj.setMCId(mcId)
        if self._app_state_obj.appState() != constants.DeviceState.DISCOVERY:
            self._app_state_obj.setAppState(constants.DeviceState.INIT)


# ===========================================================================
# Master Controller  –  DeviceInfo
# ===========================================================================

class DeviceInfoMC_Wtr(ddsEntities.Writer):
    def __init__(self, participant, app_state_obj):
        ddsEntities.Writer.__init__(
            self, participant, False, 0.0,
            tmsConstants.tms_DeviceInfo,
            tmsConstants.master_controller.DEVICE_INFO_WRITER)

        self._app_state_obj = app_state_obj
        self._sample.deviceId          = app_state_obj._masterControllerId
        self._sample.role              = tmsConstants.tms_DeviceRole.ROLE_MICROGRID_CONTROLLER
        self._sample.product.modelName = "MyMasterController"

    def get_data_sample(self):
        return self._sample


class DeviceInfoMC_Rdr(ddsEntities.Reader):
    def __init__(self, participant, app_state_obj, ignore_wtr_instance_hndl):
        ddsEntities.Reader.__init__(
            self, participant,
            tmsConstants.tms_DeviceInfo,
            tmsConstants.master_controller.DEVICE_INFO_READER)

        self._app_state_obj = app_state_obj
        participant.ignore_datawriter(ignore_wtr_instance_hndl)

    def handler(self, data):
        print("\nReceived sample for topic {r_name}".format(r_name=self._reader_name))
        devId = data.deviceId         # compiled-type attribute access
        self._app_state_obj.setDevId(devId)
        if self._app_state_obj.appState() != constants.ControllerState.DISCOVERY:
            self._app_state_obj.setAppState(constants.ControllerState.INIT)


# ===========================================================================
# Generator Device  –  ActiveMicrogridControllerState  (writer only)
# ===========================================================================

class AMCStateGD_Wtr(ddsEntities.Writer):
    def __init__(self, participant, app_state_obj):
        ddsEntities.Writer.__init__(
            self, participant, False, 0.0,
            tmsConstants.tms_ActiveMicrogridControllerState,
            tmsConstants.generator_device.AMC_STATE_WRITER)

        self._app_state_obj = app_state_obj
        self._sample.deviceId = app_state_obj._deviceId

    def set_mc_in_sample(self, mcId):
        self._sample.masterId = mcId


# ===========================================================================
# Master Controller  –  ActiveMicrogridControllerState  (reader only)
# ===========================================================================

class AMCStateMC_Rdr(ddsEntities.Reader):
    def __init__(self, participant, app_state_obj):
        ddsEntities.Reader.__init__(
            self, participant,
            tmsConstants.tms_ActiveMicrogridControllerState,
            tmsConstants.master_controller.AMC_STATE_READER)

        self._app_state_obj = app_state_obj

    def handler(self, data):
        print("\nReceived sample for topic {r_name}".format(r_name=self._reader_name))
        print("\nThis Master Controller ID: {id} has been selected".format(
            id=self._app_state_obj._masterControllerId))
        self._app_state_obj._thisMCSelected = True


# ===========================================================================
# Generator Device  –  AuthorizationToEnergizeRequest  (writer)
# ===========================================================================

class ATEReqGD_Wtr(ddsEntities.Writer):
    def __init__(self, participant, app_state_obj):
        ddsEntities.Writer.__init__(
            self, participant, False, 0.0,
            tmsConstants.tms_AuthorizationToEnergizeRequest,
            tmsConstants.generator_device.ATE_REQUEST_WRITER)

        self._app_state_obj = app_state_obj
        # Nested field access: requestId.requestingDeviceId
        self._sample.requestId.requestingDeviceId = app_state_obj._deviceId
        self._sample.energizeRequestingDeviceId   = app_state_obj._deviceId

    def write(self):  # override to update sequenceId and gate on outstanding requests
        print("\nWriting ", self._topic_type_name)
        if not self._app_state_obj.outstandingRequest():
            self._sample.sequenceId        = self._app_state_obj.rrSequenceNumber()
            self._sample.energizeSequenceId = self._sample.sequenceId
            self._writer.write(self._sample)
        else:
            print("\n** Application Error - Attempting to send a request while one is outstanding")


# ===========================================================================
# Master Controller  –  AuthorizationToEnergizeRequest  (reader)
# ===========================================================================

class ATEReqMC_Rdr(ddsEntities.Reader):
    def __init__(self, participant, app_state_obj, ATE_reply_wtr):
        ddsEntities.Reader.__init__(
            self, participant,
            tmsConstants.tms_AuthorizationToEnergizeRequest,
            tmsConstants.master_controller.ATE_REQUEST_READER)

        self._app_state_obj  = app_state_obj
        self._ate_reply_wtr  = ATE_reply_wtr

    def handler(self, data):
        print("\nReceived sample for topic {r_name}".format(r_name=self._reader_name))

        # Copy request info into the ATE reply sample using attribute access
        self._ate_reply_wtr._sample.relatedRequestId.requestingDeviceId = \
            data.requestId.requestingDeviceId
        self._ate_reply_wtr._sample.relatedSequenceId          = data.sequenceId
        self._ate_reply_wtr._sample.energizeRequestingDeviceId = data.energizeRequestingDeviceId
        self._ate_reply_wtr._sample.energizeSequenceId         = data.energizeSequenceId
        self._ate_reply_wtr._sample.accept                     = True
        self._ate_reply_wtr._sample.deny                       = False
        self._ate_reply_wtr._sample.userId                     = \
            self._app_state_obj._masterControllerId
        self._ate_reply_wtr._sample.timeOfReview.epoch         = 2
        self._ate_reply_wtr._sample.timeOfReview.seconds       = 35
        self._ate_reply_wtr._sample.timeOfReview.nanoseconds   = 55
        self._app_state_obj._authorizedForEnergizing = True
        self._ate_reply_wtr.write()


# ===========================================================================
# Master Controller  –  AuthorizationToEnergizeReply  (writer)
# ===========================================================================

class ATERepMC_Wtr(ddsEntities.Writer):
    def __init__(self, participant, app_state_obj):
        ddsEntities.Writer.__init__(
            self, participant, False, 0.0,
            tmsConstants.tms_AuthorizationToEnergizeReply,
            tmsConstants.master_controller.ATE_REPLY_WRITER)

        self._app_state_obj = app_state_obj
        self._sample.deviceId = app_state_obj._masterControllerId


# ===========================================================================
# Generator Device  –  AuthorizationToEnergizeReply  (reader)
# ===========================================================================

class ATERepGD_Rdr(ddsEntities.Reader):
    def __init__(self, participant, app_state_obj, ate_result_wtr):
        ddsEntities.Reader.__init__(
            self, participant,
            tmsConstants.tms_AuthorizationToEnergizeReply,
            tmsConstants.generator_device.ATE_REPLY_READER)

        self._app_state_obj  = app_state_obj
        self._ate_result_wtr = ate_result_wtr

        # Install the content-filtered topic for this device's ATE replies.
        # With compiled types, use dds.ContentFilteredTopic (not the
        # DynamicData-namespaced form).
        cft_topic = dds.ContentFilteredTopic.find(
            self._participant,
            tmsConstants.generator_device.ATE_REPLY_CFT)
        param = "\'" + self._app_state_obj._deviceId + "\'"
        cft_topic.filter_parameters = [param]
        logging.info("ATE_REPLY_RDR CFT ID installed")

    def handler(self, data):
        print("\nReceived sample for topic {r_name}".format(r_name=self._reader_name))
        if data.accept:
            print("\nAuthorized to Energize by Master Controller: ", data.userId)
            self._app_state_obj._authorizedForEnergizing = True

            # Copy reply fields into the ATE result sample
            self._ate_result_wtr._sample.relatedRequestId.requestingDeviceId = \
                data.relatedRequestId.requestingDeviceId
            self._ate_result_wtr._sample.relatedSequenceId          = data.relatedSequenceId
            self._ate_result_wtr._sample.authorizationDeviceId      = data.deviceId
            self._ate_result_wtr._sample.energizeRequestingDeviceId = data.energizeRequestingDeviceId
            self._ate_result_wtr._sample.energizeSequenceId         = data.energizeSequenceId
            self._ate_result_wtr._sample.userId                     = data.userId
            self._ate_result_wtr._sample.accepted                   = True
            self._ate_result_wtr._sample.responseReceived           = True
            self._ate_result_wtr._sample.energizeRequestValid       = \
                self._app_state_obj._authorizedForEnergizing
            self._ate_result_wtr._sample.authorizationReviewValid   = True
            self._ate_result_wtr.write()


# ===========================================================================
# Generator Device  –  AuthorizationToEnergizeResult  (writer)
# ===========================================================================

class ATEResultGD_Wtr(ddsEntities.Writer):
    def __init__(self, participant, app_state_obj):
        ddsEntities.Writer.__init__(
            self, participant, False, 0.0,
            tmsConstants.tms_AuthorizationToEnergizeResult,
            tmsConstants.generator_device.ATE_RESULT_WRITER)

        self._app_state_obj = app_state_obj
        # Initialize boolean flags
        self._sample.responseReceived        = False
        self._sample.authorizationReviewValid = False


# ===========================================================================
# Master Controller  –  AuthorizationToEnergizeResult  (reader)
# ===========================================================================

class ATEResultMC_Rdr(ddsEntities.Reader):
    def __init__(self, participant, app_state_obj):
        ddsEntities.Reader.__init__(
            self, participant,
            tmsConstants.tms_AuthorizationToEnergizeResult,
            tmsConstants.master_controller.ATE_RESULT_READER)

        self._app_state_obj = app_state_obj

    def handler(self, data):
        print("\nReceived sample for topic {r_name}".format(r_name=self._reader_name))


# ===========================================================================
# Master Controller  –  EnergyStartStopRequest  (writer)
# ===========================================================================

class ESSReqMC_Wtr(ddsEntities.Writer):
    def __init__(self, participant, app_state_obj):
        ddsEntities.Writer.__init__(
            self, participant, False, 0.0,
            tmsConstants.tms_EnergyStartStopRequest,
            tmsConstants.master_controller.ESS_REQUEST_WRITER)

        self._app_state_obj = app_state_obj
        # Nested field
        self._sample.requestId.requestingDeviceId = app_state_obj._masterControllerId

    def write(self, target_dev_id, new_state):  # override for ESS-specific fields
        print("\nWriting ", self._topic_type_name)
        self._sample.requestId.targetDeviceId = target_dev_id
        self._sample.sequenceId = self._app_state_obj.rrSequenceNumber()
        self._sample.fromLevel  = self._app_state_obj._deviceStartStopPresentLevel
        self._sample.toLevel    = new_state
        self._writer.write(self._sample)


# ===========================================================================
# Generator Device  –  EnergyStartStopRequest  (reader)
# ===========================================================================

class ESSReqGD_Rdr(ddsEntities.Reader):
    def __init__(self, participant, app_state_obj, reply_wtr):
        ddsEntities.Reader.__init__(
            self, participant,
            tmsConstants.tms_EnergyStartStopRequest,
            tmsConstants.generator_device.ESS_REQUEST_READER)

        self._app_state_obj = app_state_obj
        self._reply_wtr     = reply_wtr

        # Install the content-filtered topic for this device's ESS requests
        cft_topic = dds.ContentFilteredTopic.find(
            self._participant,
            tmsConstants.generator_device.ESS_REQUEST_CFT)
        param = "\'" + self._app_state_obj._deviceId + "\'"
        cft_topic.filter_parameters = [param]
        logging.info("ESS_REQUEST_RDR CFT ID installed")

    def handler(self, data):
        print("\nReceived sample for topic {r_name}".format(r_name=self._reader_name))
        self._app_state_obj._deviceStartStopFutureLevel = data.toLevel

        # Populate the reply sample using attribute access
        self._reply_wtr._sample.requestingDeviceId = data.requestId.requestingDeviceId
        # targetDeviceId is pre-filled in ReplyGD_Wtr
        self._reply_wtr._sample.requestSequenceId  = data.sequenceId
        self._reply_wtr._sample.status.code        = tmsConstants.tms_ReplyCode.REPLY_OK
        self._reply_wtr._sample.status.reason      = "MC Requested it"
        self._reply_wtr.write()


# ===========================================================================
# Generator Device  –  Reply  (writer)
# ===========================================================================

class ReplyGD_Wtr(ddsEntities.Writer):
    def __init__(self, participant, app_state_obj):
        ddsEntities.Writer.__init__(
            self, participant, False, 0.0,
            tmsConstants.tms_Reply,
            tmsConstants.generator_device.REPLY_WRITER)

        self._app_state_obj = app_state_obj
        # targetDeviceId identifies the device sending this reply
        self._sample.targetDeviceId = app_state_obj._deviceId


# ===========================================================================
# Master Controller  –  Reply  (reader)
# ===========================================================================

class ReplyMC_Rdr(ddsEntities.Reader):
    def __init__(self, participant, app_state_obj):
        ddsEntities.Reader.__init__(
            self, participant,
            tmsConstants.tms_Reply,
            tmsConstants.master_controller.REPLY_READER)

        self._app_state_obj = app_state_obj

    def handler(self, data):
        print("\nReceived sample for topic {r_name}".format(r_name=self._reader_name))


# ===========================================================================
# Generator Device  –  EnergyStartStopState  (writer)
# ===========================================================================

class ESSStateGD_Wtr(ddsEntities.Writer):
    def __init__(self, participant, app_state_obj):
        ddsEntities.Writer.__init__(
            self, participant, False, 0.0,
            tmsConstants.tms_EnergyStartStopState,
            tmsConstants.generator_device.ESS_STATE_WRITER)

        self._app_state_obj = app_state_obj

        # Initialise internal state
        self._app_state_obj._deviceStartStopPresentLevel = \
            tmsConstants.tms_EnergyStartStopLevel.ESSL_OFF
        self._app_state_obj._deviceStartStopFutureLevel  = \
            tmsConstants.tms_EnergyStartStopLevel.ESSL_OFF

        # Load static sample fields using attribute access
        self._sample.deviceId          = app_state_obj._deviceId
        self._sample.presentLevel      = tmsConstants.tms_EnergyStartStopLevel.ESSL_OFF
        self._sample.futureLevel       = tmsConstants.tms_EnergyStartStopLevel.ESSL_OFF
        self._sample.requestLock       = False
        self._sample.presentLevelReason = tmsConstants.tms_PowerSwitchReason.PSR_STARTUP
        self._sample.presentLevelActor  = app_state_obj._deviceId  # Optional[str]
        self._sample.futureLevelReason  = \
            tmsConstants.tms_PowerSwitchTransitionCode.PSTC_COMPLETE


# ===========================================================================
# Master Controller  –  EnergyStartStopState  (reader)
# ===========================================================================

class ESSStateMC_Rdr(ddsEntities.Reader):
    def __init__(self, participant, app_state_obj):
        ddsEntities.Reader.__init__(
            self, participant,
            tmsConstants.tms_EnergyStartStopState,
            tmsConstants.master_controller.ESS_STATE_READER)

        self._app_state_obj = app_state_obj

    def handler(self, data):
        print("\nReceived sample for topic {r_name}".format(r_name=self._reader_name))
        # Save relevant fields in our app state object
        self._app_state_obj._deviceId                    = data.deviceId
        self._app_state_obj._deviceStartStopPresentLevel = data.presentLevel
        self._app_state_obj._deviceStartStopFutureLevel  = data.futureLevel

        print("\nDevice {d_id} Energy State: {e_state}".format(
            d_id=self._app_state_obj._deviceId,
            e_state=self._app_state_obj._deviceStartStopPresentLevel))
