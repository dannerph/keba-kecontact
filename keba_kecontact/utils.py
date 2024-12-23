"""Utils for keba kecontact."""

import json
import string

from .const import KebaResponse, ReportField


class SetupError(Exception):
    """Error to indicate we cannot connect."""


def get_response_type(payload: str) -> KebaResponse:  # noqa: PLR0911
    """Get the response type.

    Args:
        payload (str): payload of response from Keba charging station

    Returns:
        KebaResponseType: response type of the response

    """
    if payload.startswith("i"):
        return KebaResponse.BROADCAST

    if payload.startswith('"Firmware'):
        return KebaResponse.BASIC_INFO

    if KebaResponse.TCH_OK in payload:
        return KebaResponse.TCH_OK

    if KebaResponse.TCH_ERR in payload:
        return KebaResponse.TCH_ERR

    try:
        json_rcv = json.loads(payload)
    except json.decoder.JSONDecodeError:
        return KebaResponse.UNKNOWN

    if ReportField.ID in json_rcv:
        if int(json_rcv[ReportField.ID]) == 1:
            return KebaResponse.REPORT_1
        if int(json_rcv[ReportField.ID]) == 2:
            return KebaResponse.REPORT_2
        if int(json_rcv[ReportField.ID]) == 3:
            return KebaResponse.REPORT_3
        if int(json_rcv[ReportField.ID]) > 100:
            return KebaResponse.REPORT_1XX
    else:
        return KebaResponse.PUSH_UPDATE


def validate_current(current: int | float) -> None:
    """Validate current value.

    Args:
        current (int | float): current to be 0 or between 6 - 63 A.

    """
    if not isinstance(current, int | float) or (current < 6 and current != 0) or current > 63:
        raise ValueError(
            "Current must be int or float and value must be above 6 and below 63 A or 0 A."
        )


def validate_rfid_tag(rfid: str) -> None:
    """Validate rfid tag.

    Args:
        rfid (str): 8 byte long hex string

    """
    if not all(c in string.hexdigits for c in rfid) or len(rfid) > 16:
        raise ValueError("RFID tag must be a 8 byte hex string.")


def validate_rfid_class(rfid_class: str) -> None:
    """Validate rfid class.

    Args:
        rfid_class (str): 10 byte long hex string

    """
    if not all(c in string.hexdigits for c in rfid_class) or len(rfid_class) > 20:
        raise ValueError("RFID class tag must be a 10 byte hex string.")
