"""
 * (c) Copyright, Real-Time Innovations, 2020.  All rights reserved.
 * RTI grants Licensee a license to use, modify, compile, and create derivative
 * works of the software solely for use with RTI Connext DDS. Licensee may
 * redistribute copies of the software provided that all such copies are subject
 * to this license. The software is provided "as is", with no warranty of any
 * type, including any warranty for fitness for any purpose. RTI is under no
 * obligation to maintain or support the software. RTI shall not be liable for
 * any incidental or consequential damages arising out of the use or inability
 * to use the software.

 Note: For other language bindings these constants are defined with the data
 module (in the idl). RtiCodeGenerator is used to create a project header file
 to ascertain these constants.

 This file contains common constants that are application specific (vs. 
 data model)
"""
from enum import IntEnum

QOS_URL = "file://../model_distroA/tmsExampleApp.xml"

# the state classes are used by both the device/controller and the app_state_object
DEVICE1_ID = "DGen1234"
CONTROLLER1_ID = "MC0001"

HEARTBEAT_PERIOD=1.0

class ControllerState(IntEnum):
    INIT = 0 # send DI and start HB
    DISCOVERY = 1
    FOUND_NEW_DEVICE = 2 
    WAIT_CMD_IDLE = 3
    POWER_UP_AUTH = 4
    ENERGIZE = 5
    SHUT_DOWN = 6
    ERROR = 7 # received an out of order request

class DeviceState(IntEnum):
    INIT = 0 # send DI and start HB
    DISCOVERY = 1
    FOUND_NEW_CONTROLLER = 2
    WAIT_CMD_IDLE = 3
    POWER_UP_AUTH = 4
    ENERGIZE = 5
    SHUT_DOWN = 6
    ERROR = 7 # received an out of order request
