# KEBA KeContact

This is python library to control KEBA charging stations, in specific the P20, P30 and the BMW wallbox.
Commands were taken from the [UDP Programming Manual](https://www.keba.com/web/downloads/e-mobility/KeContact_P20_P30_UDP_ProgrGuide_en.pdf).
The library was written for the usage in [Home Assistant](https://www.home-assistant.io/).

## Commands
The following commands are implemented so far:

### request_data

### set_failsafe
The failsafe function is a way to detect a failure of the network communication between the UDP application and the charging station.
In this case, the charging station will fall into a state with a definable current limitation.
By default, the failsafe function is disabled and must be enabled by the application.

Parameters:
- timeout in seconds (default = 30 s)
- fallback_value in ampere (default = 6 A) 
- persist (default = 0)

### set_energy
The command setenergy can be used to set an energy limit for an already running or the next charging session.
If the energy limit is greater than or equal to the value in the E pres field of report 3 the charging session will be stopped and the device will be deactivated (similar to ena 0).
All settings caused by setenergy are not permanent and are reset at the next time the device registers that the EV plug is pulled from a vehicle inlet or the charging station is restarted.

Parameters:
- energy in kWh (default = 0 kWh)

### set_current
This command sets the current limit of the running charging process.

Parameters:
- current in ampere (default = 0 A)

### set_text
This command displays a text on the display of the charger.

Parameters:
- text to show on the display
- min time to show the text before next text is shown (default = 2 s)
- max time to show the text (default = 10 s)

### start
This command authorizes a charging process with the given RFID tag and RFID class.

Parameters:
- rfid tag as 8 byte hex string, identifier of RFID card
- rfid class as 10 byte hex string, classifier of RFID card 

### stop
This command stops a charging process with the given RFID tag.

Parameters:
- rfid tag as 8 byte hex string, identifier of RFID card

### enable
The enable command can be used to permanently disable the system by using the parameter 0.
After receiving ena 0 the device will be disabled until it is rebooted or ena 1 or currtime are used.
The execution of ena 0 will take approximately 1 second.
If ena 0 is used, then no other command should be sent for 2 seconds to ensure an undisturbed execution of the disable command.

Parameters:
- ena in [0,1]

### unlock_socket
(not tested yet)