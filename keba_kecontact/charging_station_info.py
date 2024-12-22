"""Keba charging station info."""

import logging

from .const import KebaService, ReportField

_LOGGER = logging.getLogger(__name__)


class ChargingStationInfo:
    """Keba charging station information object to identify features and available services."""

    def __init__(self, host: str, report_1: dict[str, str]) -> None:
        """Initialize charging station info.

        Args:
            host (str): host address
            report_1_json (dict[str, str]): dict of report 1 data to extract

        """
        self.host: str = host
        self.webconfigurl: str = f"http://{host}"

        # Default features
        self.services: list[KebaService] = [
            KebaService.SET_FAILSAFE,
            KebaService.SET_CURRENT,
            KebaService.SET_CHARGING_POWER,
        ]
        self.meter_integrated = False
        self.data_logger_integrated = False

        # Check if report is of expected structure
        assert isinstance(report_1, dict), "Report is not of type dict."
        assert ReportField.ID in report_1, "Report does not contain an ID."
        assert report_1[ReportField.ID] == "1", "Report is not the expected report 1."
        assert ReportField.SERIAL in report_1, "Report does not contain SERIAL."
        assert ReportField.FIRMWARE in report_1, "Report does not contain FIRMWARE."
        assert ReportField.PRODUCT in report_1, "Report does not contain PRODUCT."

        self.device_id: str = report_1[ReportField.SERIAL]
        self.sw_version: str = report_1[ReportField.FIRMWARE]

        # Friendly name mapping
        product: str = report_1[ReportField.PRODUCT]
        if "KC" in product:
            self.manufacturer = "KEBA"
            self.services.append(KebaService.SET_OUTPUT)

            if "KC-P30-EC220112-000-DE" in product:
                self.model = "P30-DE"
                self.meter_integrated = False
                self.data_logger_integrated = True
            elif "P30" in product:
                self.model = "P30"

                # Add available services
                self.services.append(KebaService.DISPLAY)
                self.services.append(KebaService.SET_ENERGY)
                self.services.append(KebaService.START)
                self.services.append(KebaService.STOP)

                self.meter_integrated = True
                self.data_logger_integrated = True

            elif "P20" in product:
                self.model = "P20"
                self.meter_integrated = False
                self.data_logger_integrated = False

        elif "BMW" in product:
            self.manufacturer = "BMW"
            if "BMW-10-EC2405B2-E1R" in product:
                self.model = "Wallbox Connect"
            elif "BMW-10-EC240522-E1R" in product:
                self.model = "Wallbox Plus"

            # Add available services
            self.services.append(KebaService.SET_ENERGY)
            self.services.append(KebaService.START)
            self.services.append(KebaService.STOP)

            self.meter_integrated = True
            self.data_logger_integrated = True
        else:
            _LOGGER.warning(
                "Not able to identify the model type. Please report to"
                + "https://github.com/dannerph/keba-kecontact/issues"
            )
            self.manufacturer: str = "unknown"
            self.model = product.split("-")[1:]

    def __str__(self) -> str:
        """Print device info."""
        return (
            f"{self.manufacturer} {self.model} ({self.device_id}, {self.sw_version}) at {self.host}"
        )

    def __eq__(self, other):
        """Equal if device_id is equal."""
        if isinstance(other, ChargingStationInfo):
            return self.device_id == other.device_id
        return False

    def available_services(self) -> list[KebaService]:
        """Get available services as a list of method name strings.

        Returns:
            list[KebaService]: list of services

        """
        return self.services

    def is_meter_integrated(self) -> bool:
        """Check if a metering device is integrated into the charging station.

        Returns:
            bool: True if metering is integrated, False otherwise

        """
        return self.meter_integrated

    def is_data_logger_integrated(self) -> bool:
        """Check if logging functionality is integrated into the charging station.

        Returns:
            bool: True if report 1XX is available, False otherwise

        """
        return self.data_logger_integrated

    def has_display(self) -> bool:
        """Check if a display is integrated into the charging station.

        Returns:
            bool: True if a display is integrated, False otherwise

        """
        return KebaService.DISPLAY in self.services
