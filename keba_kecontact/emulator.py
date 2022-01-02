import asyncio
import logging
import asyncio_dgram

_LOGGER = logging.getLogger(__name__)

UDP_PORT = 7090


class Emulator:
    def __init__(self, loop=None):
        """Constructor."""
        self._loop = asyncio.get_event_loop() if loop is None else loop
        self._stream = None

    async def start(self):
        """Start emulator."""

        self._stream = await asyncio_dgram.bind(("0.0.0.0", UDP_PORT))
        self._loop.create_task(self._listen())

    async def _listen(self):
        data, remote_addr = await self._stream.recv()  # Listen until something received
        self._loop.create_task(self._listen())  # Listen again
        self._loop.create_task(self._internal_callback(data, remote_addr))  # Callback

    async def _internal_callback(self, raw_data, remote_addr):

        data = raw_data.decode()
        _LOGGER.debug(f"Datagram recvied from {remote_addr}: {data}")

        payload = ""
        matches_OK = [
            "unlock",
            "stop",
            "setenergy",
            "output",
            "currtime",
            "curr",
            "ena",
            "failsafe",
        ]

        try:
            if data == "i":
                payload = '"Firmware":"Emulator v 2.0.0"\n'

            elif any(x in data for x in matches_OK):
                payload = "TCH-OK :done"

            elif "start" in data:
                split = data.split(" ")
                payload = (
                    '"RFID tag": "' + split[1] + '"\n' + '"RFID class": "' + split[2]
                )

            elif "report" in data:
                split = data.split(" ")
                i = int(split[1])
                if i == 1:
                    payload = '{"ID": "1","Product": "Keba-Emulator","Serial": "123456789","Firmware":"Emulator v 2.0.0","COM-module": 0,"Sec": 0}'
                elif i == 2:
                    payload = '{"ID": "2","State": 2,"Error1": 99,"Error2": 99,"Plug": 1,"Enable sys": 1,"Enable user": 1,"Max curr": 32000,"Max curr %": 1000,"Curr HW": 32000,"Curr user": 63000,"Curr FS": 63000,"Tmo FS": 0,"Curr timer": 0,"Tmo CT": 0,"Setenergy": 0,"Output": 0,"Input": 0,"Serial": "15017355","Sec": 4294967296}'
                elif i == 3:
                    payload = '{"ID": "3","U1": 230,"U2": 230,"U3": 230,"I1": 99999,"I2": 99999,"I3": 99999,"P": 99999999,"PF": 1000,"E pres": 999999,"E total": 9999999999,"Serial": "15017355","Sec": 4294967296}'

                elif i >= 100:
                    payload = (
                        '{"ID": "'
                        + str(i)
                        + '","Session ID": 35,"Curr HW ": 20000,"E Start ": 29532,"E Pres ": 0,"started[s]": 1698,"ended[s] ": 0,"reason ": 0,"RFID tag": "e3f76b8d00000000","RFID class": "01010400000000000000","Serial": "16914905","Sec": 1704}'
                    )
        except Exception as e:
            payload = "TCH-ERR"

        _LOGGER.debug("Send %s to %s", payload, remote_addr)
        await self._stream.send(payload.encode("cp437", "ignore"), remote_addr)
