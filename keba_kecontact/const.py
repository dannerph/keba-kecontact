"""Consts for keba kecontact."""

from enum import StrEnum

UDP_PORT = 7090


class ReportField(StrEnum):
    """Enum to represent report fields."""

    ID = "ID"
    SERIAL = "Serial"
    FIRMWARE = "Firmware"
    PRODUCT = "Product"
    MAX_CURR_PERCENT = "Max curr %"
    MAX_CURR = "Max curr"
    CURR_HW = "Curr HW"
    CURR_USER = "Curr user"
    CURR_FS = "Curr FS"
    CURR_TIMER = "Curr timer"
    I1 = "I1"
    I2 = "I2"
    I3 = "I3"
    U1 = "U1"
    U2 = "U2"
    U3 = "U3"
    PF = "PF"
    SETENERGY = "Setenergy"
    E_PRES = "E pres"
    E_TOTAL = "E total"
    E_START = "E start"
    PLUG = "Plug"
    PLUG_CS = "Plug_charging_station"
    PLUG_LOCKED = "Plug_locked"
    PLUG_EV = "Plug_EV"
    STATE = "State"
    STATE_ON = "State_on"
    STATE_DETAILS = "State_details"
    TMO_FS = "Tmo FS"
    FS_ON = "FS_on"
    P = "P"
    AUTHREQ = "Authreq"


class KebaService(StrEnum):
    """Enum to represent implemented services."""

    SET_FAILSAFE = "set_failsafe"
    SET_CURRENT = "set_current"
    SET_CHARGING_POWER = "set_charging_power"
    SET_ENERGY = "set_energy"
    SET_OUTPUT = "set_output"
    DISPLAY = "display"
    START = "start"
    STOP = "stop"


class KebaResponse(StrEnum):
    """Enum to define different keba responses."""

    BASIC_INFO = "i"
    REPORT_1 = "report 1"
    REPORT_2 = "report 2"
    REPORT_3 = "report 3"
    REPORT_1XX = "report 1xx"
    TCH_OK = "TCH-OK"
    TCH_ERR = "TCH-ERR"
    PUSH_UPDATE = "push update"
    BROADCAST = "broadcast"
    UNKNOWN = "unknown"
