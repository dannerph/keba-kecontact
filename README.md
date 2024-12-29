# KEBA KeContact

This is python module to control KEBA charging stations, in specific the P20 and P30 (including different branding like BMW wallbox and SolarEdge).
Commands were taken from the [UDP Programming Manual](https://www.keba.com/download/x/4a925c4c61/kecontactp30udp_pgen.pdf).
The module was written for the usage in [Home Assistant](https://www.home-assistant.io/) and is based on asyncio.

## Install

You can install the module from pypi.org

```bash
pip install keba_kecontact
```

or from source

```bash
git clone https://github.com/dannerph/keba-kecontact
cd keba-kecontact
pip install .
```

## Command Line Interface

The module contains a command line interface to connect and send UDP commands, discover charging stations in your local networks and emulate a KEBA charging station for testing purposes. Run
```bash
python -m keba_kecontact
```
and follow the instructions.

## Use the module in your code

The module is written using asyncio and creates a UDP socket to listen for incoming packets on port 7090 (cannot be changed).

```python
from keba_kecontact import create_keba_connection
from keba_kecontact.connection import ChargingStation, SetupError

async def connect(ip: str) -> None:
    keba = await create_keba_connection()
    try:
        charging_station = await keba.setup_charging_station(ip, periodic_request=False)
    except SetupError as ex:
        print(f"Charging station at {ip} could not be set up: {ex}")
```

## Support Development

### Paypal

[![](https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=848P2G8EA68PJ)