"""Test charging station info."""

import pytest

from keba_kecontact.charging_station_info import ChargingStationInfo
from keba_kecontact.const import KebaService


def test_charging_station_info_invalid() -> None:
    """Test charging station info parsing."""
    report_1 = {
        "ID_not_here": "1",
        "Product": "BMW-10-EC240522-E1R",
        "Serial": "123456789",
        "Firmware": "some firmware string",
        "COM-module": 0,
        "Sec": 123,
    }
    with pytest.raises(ValueError):
        ChargingStationInfo("localhost", report_1)

    report_1 = {
        "ID": "2",
        "Product": "BMW-10-EC240522-E1R",
        "Serial": "123456789",
        "Firmware": "some firmware string",
        "COM-module": 0,
        "Sec": 123,
    }
    with pytest.raises(ValueError):
        ChargingStationInfo("localhost", report_1)

    report_1 = {
        "ID": "1",
        "Serial": "123456789",
        "Firmware": "some firmware string",
        "COM-module": 0,
        "Sec": 123,
    }
    with pytest.raises(ValueError):
        ChargingStationInfo("localhost", report_1)
    report_1 = {
        "ID": "1",
        "Product": "BMW-10-EC240522-E1R",
        "Firmware": "some firmware string",
        "COM-module": 0,
        "Sec": 123,
    }
    with pytest.raises(ValueError):
        ChargingStationInfo("localhost", report_1)

    report_1 = {
        "ID": "1",
        "Product": "BMW-10-EC240522-E1R",
        "Serial": "123456789",
        "COM-module": 0,
        "Sec": 123,
    }
    with pytest.raises(ValueError):
        ChargingStationInfo("localhost", report_1)

    report_1 = {
        "ID": "1",
        "Product": "BMW-10",
        "Serial": "123456789",
        "Firmware": "some firmware string",
        "COM-module": 0,
        "Sec": 123,
    }
    with pytest.raises(ValueError):
        ChargingStationInfo("localhost", report_1)


def test_charging_station_info_valid() -> None:
    """Test charging station info parsing."""
    # General info
    report_1 = {
        "ID": "1",
        "Product": "BMW-10-EC240522-E1R",
        "Serial": "123456789",
        "Firmware": "some firmware string",
        "COM-module": 0,
        "Sec": 123,
    }
    info = ChargingStationInfo("localhost", report_1)
    assert info.device_id == "123456789"
    assert info.sw_version == "some firmware string"
    assert info.host == "localhost"
    assert info.webconfigurl == "http://localhost"


def test_charging_station_info_valid_BMW() -> None:  # noqa: N802
    """Test charging station info parsing for BMW."""
    # BMW Wallbox Plus
    for product in ["BMW-10-EC240522-E1R", "BMW-10-ESS40022-E1R"]:
        report_1 = {
            "ID": "1",
            "Product": product,
            "Serial": "123456789",
            "Firmware": "some firmware string",
            "COM-module": 0,
            "Sec": 123,
        }
        info = ChargingStationInfo("localhost", report_1)
        assert info.manufacturer == "BMW"
        assert info.model == "Wallbox Plus"
        assert not info.has_display()
        assert info.is_data_logger_integrated()
        assert info.is_meter_integrated()
        assert KebaService.START in info.services
        assert KebaService.STOP in info.services

    # BMW Wallbox Connect
    report_1 = {
        "ID": "1",
        "Product": "BMW-10-EC2405B2-E1R",
        "Serial": "123456789",
        "Firmware": "some firmware string",
        "COM-module": 0,
        "Sec": 123,
    }
    info = ChargingStationInfo("localhost", report_1)
    assert info.manufacturer == "BMW"
    assert info.model == "Wallbox Connect"
    assert not info.has_display()
    assert info.is_data_logger_integrated()
    assert info.is_meter_integrated()
    assert KebaService.START in info.services
    assert KebaService.STOP in info.services


def test_charging_station_info_valid_P20() -> None:  # noqa: N802
    """Test charging station info parsing for keba P20."""
    # Keba P20 e-series
    for product in ["KC-P20-ES230001-000", "KC-P20-EC230101-000", "KC-P20-EC130101-000"]:
        report_1 = {
            "ID": "1",
            "Product": product,
            "Serial": "123456789",
            "Firmware": "some firmware string",
            "COM-module": 0,
            "Sec": 123,
        }
        info = ChargingStationInfo("localhost", report_1)
        assert info.manufacturer == "KEBA"
        assert info.model == "P20"
        assert not info.has_display()
        assert not info.is_data_logger_integrated()
        assert not info.is_meter_integrated()

    # Keba P20 b-series
    for product in ["KC-P20-ES240010-000", "KC-P20-EC220110-000", "KC-P20-EC240110-000"]:
        report_1 = {
            "ID": "1",
            "Product": product,
            "Serial": "123456789",
            "Firmware": "some firmware string",
            "COM-module": 0,
            "Sec": 123,
        }
        info = ChargingStationInfo("localhost", report_1)
        assert info.manufacturer == "KEBA"
        assert info.model == "P20"
        assert not info.has_display()
        assert not info.is_data_logger_integrated()
        assert info.is_meter_integrated()

    # Keba P20 c-series
    for product in ["KC-P20-ES240020-000", "KC-P20-ES240030-000", "KC-P20-EC220120-000"]:
        report_1 = {
            "ID": "1",
            "Product": product,
            "Serial": "123456789",
            "Firmware": "some firmware string",
            "COM-module": 0,
            "Sec": 123,
        }
        info = ChargingStationInfo("localhost", report_1)
        assert info.manufacturer == "KEBA"
        assert info.model == "P20"
        assert not info.has_display()
        assert not info.is_data_logger_integrated()
        assert info.is_meter_integrated()

    # P20 R
    report_1 = {
        "ID": "1",
        "Product": "KC-P20-ES240020-00R",
        "Serial": "123456789",
        "Firmware": "some firmware string",
        "COM-module": 0,
        "Sec": 123,
    }
    info = ChargingStationInfo("localhost", report_1)
    assert KebaService.START in info.services
    assert KebaService.STOP in info.services


def test_charging_station_info_valid_P30() -> None:  # noqa: N802
    """Test charging station info parsing for keba P30."""
    # P30
    report_1 = {
        "ID": "1",
        "Product": "KC-P30-XXXXXXXX-000",
        "Serial": "123456789",
        "Firmware": "some firmware string",
        "COM-module": 0,
        "Sec": 123,
    }
    info = ChargingStationInfo("localhost", report_1)
    assert info.manufacturer == "KEBA"
    assert info.model == "P30"
    assert info.has_display()
    assert info.is_data_logger_integrated()
    assert info.is_meter_integrated()
    assert KebaService.START in info.services
    assert KebaService.STOP in info.services

    # P30 DE
    report_1 = {
        "ID": "1",
        "Product": "KC-P30-EC220112-000-DE",
        "Serial": "123456789",
        "Firmware": "some firmware string",
        "COM-module": 0,
        "Sec": 123,
    }
    info = ChargingStationInfo("localhost", report_1)
    assert info.manufacturer == "KEBA"
    assert info.model == "P30-DE"
    assert not info.has_display()
    assert info.is_data_logger_integrated()
    assert not info.is_meter_integrated()
    assert KebaService.START in info.services
    assert KebaService.STOP in info.services


def test_charging_station_info_eq() -> None:
    """Test equality."""
    a_report_1 = {
        "ID": "1",
        "Product": "BMW-10-EC240522-E1R",
        "Serial": "123456789",
        "Firmware": "some firmware string",
        "COM-module": 0,
        "Sec": 123,
    }
    a_info = ChargingStationInfo("localhost", a_report_1)

    b_report_1 = {
        "ID": "1",
        "Product": "BMW-10-EC240522-E1R",
        "Serial": "123456789",
        "Firmware": "some firmware string",
        "COM-module": 0,
        "Sec": 123,
    }
    b_info = ChargingStationInfo("localhost", b_report_1)

    assert a_info == b_info

    c_report_1 = {
        "ID": "1",
        "Product": "BMW-10-EC240522-E1R",
        "Serial": "5",
        "Firmware": "some firmware string",
        "COM-module": 0,
        "Sec": 123,
    }
    c_info = ChargingStationInfo("localhost", c_report_1)

    assert a_info != c_info
