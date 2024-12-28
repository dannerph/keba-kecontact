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
        self.authorization_integrated = False
        self.data_logger_integrated = False
        self.phase_switch_x2 = False

        # Check if report is of expected structure
        if not isinstance(report_1, dict):
            raise ValueError("Report is not of type dict")
        if ReportField.ID not in report_1:
            raise ValueError("Report does not contain an ID")
        if report_1[ReportField.ID] != "1":
            raise ValueError("Report is not the expected report 1")
        if ReportField.SERIAL not in report_1:
            raise ValueError("Report does not contain SERIAL")
        if ReportField.FIRMWARE not in report_1:
            raise ValueError("Report does not contain FIRMWARE")
        if ReportField.PRODUCT not in report_1:
            raise ValueError("Report does not contain PRODUCT")

        self.device_id: str = report_1[ReportField.SERIAL]
        self.sw_version: str = report_1[ReportField.FIRMWARE]

        # Friendly name mapping
        product: str = report_1[ReportField.PRODUCT]
        p_split = product.split("-")
        if len(p_split) < 4:
            raise ValueError("Product string is not valid")
        self.manufacturer = p_split[0]  # "KC" or "BMW"
        self.model = p_split[1]  # "P20", "P30" or custom for none Keba branding
        product_version = p_split[2]  # e.g. "ES230001" or "EC220110"
        product_features = p_split[3]  # e.g. "00R" for RFID (P20)
        if self.manufacturer == "KC":
            self.manufacturer = "KEBA"
            self.services.append(KebaService.SET_OUTPUT)  # not sure if available for all?
            self.phase_switch_x2 = True

            if self.model == "P30":
                self.authorization_integrated = True
                self.data_logger_integrated = True
                if "KC-P30-EC220112-000-DE" in product:  # Special case DE-Wallbox
                    self.model = "P30-DE"
                    self.meter_integrated = False
                else:
                    self.services.append(KebaService.DISPLAY)
                    self.meter_integrated = True

            if self.model == "P20":
                # https://media.expleo.hu/documents/katalogusok/keba/kecontact_smart-charging-solutions_en_interactive.pdf
                if product_version.endswith("01"):  # e-series
                    self.meter_integrated = False
                    self.data_logger_integrated = False
                elif product_version.endswith("10"):  # b-series
                    self.meter_integrated = True
                    self.data_logger_integrated = False
                elif product_version.endswith("20") or product_version.endswith("30"):  # c-series
                    self.meter_integrated = True
                    self.data_logger_integrated = False  # not sure about this one

                if "R" in product_features:  # not sure maybe "K" might also work
                    self.authorization_integrated = True

        elif self.manufacturer == "BMW":
            self.manufacturer = "BMW"
            # Absolutely no idea, how the models are identified. The following is based on examples
            # available during development
            if "BMW-10-EC2405B2-E1R" in product:
                self.model = "Wallbox Connect"
            elif "BMW-10-EC240522-E1R" in product or "BMW-10-ESS40022-E1R" in product:
                self.model = "Wallbox Plus"

            # Features
            self.meter_integrated = True
            self.authorization_integrated = True
            self.data_logger_integrated = True
        else:
            _LOGGER.warning(
                "Not able to identify the model type. Please report to"
                + "https://github.com/dannerph/keba-kecontact/issues"
            )

        if self.meter_integrated:
            self.services.append(KebaService.SET_ENERGY)
        if self.authorization_integrated:
            self.services.append(KebaService.START)
            self.services.append(KebaService.STOP)

    def __str__(self) -> str:
        """Print device info."""
        return (
            f"{self.manufacturer} {self.model} ({self.device_id}, {self.sw_version}) at {self.host}"
        )

    def __eq__(self, other) -> bool:
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

    def has_phase_switch_x2(self) -> bool:
        """Check if x2 is possible to be used as phase switch output.

        Returns:
            bool: True if x2 output can be used for phase switching, False otherwise.

        """
        return self.phase_switch_x2
