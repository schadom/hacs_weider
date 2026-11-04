# Weider integration

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]

> [!IMPORTANT]
> This integration is not affiliated with Weider Wärmepumpen GmbH and is provided as-is and without warranty.

Component to integrate with [Weider](https://www.weider.co.at) heat pumps over Modbus TCP or Modbus RTU.

## Supported controllers

| Controller | RS232 | RS485 | Ethernet | Modbus RTU | Modbus TCP | Status |
| --- | --- | --- | --- | --- | --- | --- |
| WeiTronic WT16 | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | Supported |
| WeiTronic WT08 | ✅ Yes | ✅ Yes | ❌ No | ✅ Yes | ❌ No | Not supported |

The integration reads the controller as a Modbus slave, over Modbus TCP or Modbus
RTU. Only the WT16 supports the slave role.

Device communication is handled by the [weider-modbus](https://pypi.org/project/weider-modbus/)
library ([source](https://github.com/schadom/weider-modbus)), which Home Assistant
installs automatically.

## Screenshot

![demo]

## Installation with HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=schadom&repository=hacs_weider&category=integration)

1. Add this repository as a custom repository of category **Integration**.
2. Install **Weider** and restart Home Assistant.
3. In **Settings > Devices & services > Add integration**, add **Weider**.
4. Choose how Home Assistant connects to the heat pump:
   - **Network (Modbus TCP):** the heat pump's Ethernet port. Enter its host or IP
     address, TCP port (default **502**) and Modbus unit ID (default **1**).
   - **Serial port (Modbus RTU):** the RS485 port X9 through a USB-RS485 adapter.
     See [Connecting over RS485](#connecting-over-rs485-modbus-rtu).
   - **RS485 converter on the network (Modbus RTU over TCP):** the RS485 port X9
     through an RS485-to-Ethernet converter in transparent mode. Enter the
     converter's host or IP address, TCP port and the Modbus unit ID.

For a manual install, copy `custom_components/weider` into Home Assistant's
`custom_components` directory and restart Home Assistant.

Requires Home Assistant **2026.10.0 or newer**; tested with **2026.10.3**. On older
versions, HACS offers 1.2.3 at most.

Installations from before 1.4.0 keep their device name "Weider WT16" and their
entity IDs (for example `sensor.weider_wt16_hot_water_temperature`). New
installations are named "Weider" (for example `sensor.weider_hot_water_temperature`).
Rename the device in Home Assistant if you prefer the other name.
The integration uses Home Assistant's shared `modbus` connection API. No separate
connection integration or Modbus YAML configuration is needed. Units acquired
through this API with identical connection parameters share a connection.

Installations from before 1.6.0 use Modbus TCP and keep working without changes.

### Connecting over RS485 (Modbus RTU)

The RS485 port X9 ("Modbus 1") connects directly to the controller. It is not
affected by the Ethernet board's hourly network resets (see
[Known limitations](#known-limitations)), and Weider recommends it for
connecting other systems.

1. **Enable Modbus 1 on the controller** as **Slave** in **RTU** mode, and note
   its Modbus address, baud rate, parity and stop bits. These settings need the
   service code; ask Weider to set them up.
2. **Wire X9 to the adapter:** A to A, B to B, and GND to GND. If the heat pump
   does not answer, swap A and B. X9 already has a terminating resistor.
3. **Connect the adapter** to the Home Assistant host, or use an RS485-to-Ethernet
   converter in transparent mode next to the heat pump.
4. **Add the integration** with **Serial port (Modbus RTU)** or **RS485 converter
   on the network**, and enter the same settings as on the controller. The
   integration suggests 19200 baud, no parity and 2 stop bits.

The RS485 port has its own register map. Most values exist on both connections
and keep their entity, so switching with **Reconfigure** keeps their history.
Some values exist on only one connection:

- **Modbus TCP only:** refrigerant circuit temperatures (superheat, evaporation,
  condensation, evaporator, suction gas, hot gas, defrost), flow target and mixer
  temperature, volume flow, flow switches, 4-way valve, SG Ready inputs and mode,
  last pump runtime and the active error text.
- **Modbus RTU only:** hot water hysteresis, heating limit temperature, average
  outdoor temperature, operating season, heating circuit 1 flow target and flow
  temperature, mixer 2 position, operating hours, heating hours, last heating
  runtime, heat energy, the active error number and the manual SG Ready mode.

The heat energy sensor can be used in the Energy dashboard. Not connected
temperature sensors show as unknown.

### Upgrading an old configuration

Entries created with a **Modbus Connection** selector must be reconfigured:
open the Weider integration entry's menu, choose **Reconfigure**, and supply its
host, port, and unit ID. The old connection reference does not contain enough
information to convert automatically. Reconfiguration preserves the entry and
entity IDs; do not delete the entry just to change its connection details.

## Removal

1. In **Settings > Devices & services**, open **Weider**, open the entry's menu
   and choose **Delete**. This removes the device and all its entities. Settings
   stored on the heat pump are not changed.
2. To remove the integration completely, uninstall **Weider** in HACS (or delete
   `custom_components/weider`) and restart Home Assistant.

## Local Docker testing

Install and start Docker Desktop on macOS, or Docker Engine with Compose on Linux.
From this repository, start the pinned Home Assistant **2026.10.3** image with
the optional synthetic WT16 server:

```sh
docker compose --profile simulator up -d
```

Open <http://localhost:8123>, complete Home Assistant onboarding, then add
**Weider** with host **simulator**, port **5020**, and unit ID **1**.
The simulator is only accessible inside the Compose network. It supplies fixed
measurements and accepts target-temperature writes in memory; it does not model
heat-pump physics, firmware behavior, or temperature limits.

Expect 28 sensors, 20 binary sensors, and two temperature controls. The sample
hot-water temperature is 42.5 C and its target is 45 C. Change a target and check
that the target sensor updates. To test recovery, stop and restart the simulator:

```sh
docker compose stop simulator
docker compose --profile simulator start simulator
```

A failed poll is retried once immediately, because the shared connection reopens
on the next request. Entities keep their last values until three consecutive polls
have failed, so allow about three minutes (plus connection timeouts) for
availability to change. The connection should recover without reloading the integration.

To test a real device instead, start only Home Assistant:

```sh
docker compose up -d homeassistant
```

Use the device's LAN IP and TCP port in the integration form. For a Modbus server
running on your Mac, use `host.docker.internal`, not `localhost`. Avoid concurrent
connections from a production HA instance or other clients to a single-client
gateway. Temperature changes against a real device are real writes.

The UI binds only to `127.0.0.1`. If port 8123 is occupied, use
`HA_PORT=8124 docker compose --profile simulator up -d` and open port 8124.
HA state is retained in a Docker volume; the integration source is mounted
read-only from this checkout. No HACS installation is needed inside this test HA.

```sh
docker compose logs --tail=100 homeassistant simulator
docker compose restart homeassistant
docker compose --profile simulator down
```

Restart Home Assistant after Python changes. `down` retains your test
configuration; adding `--volumes` permanently deletes it.

## Development checks

Use Python 3.14. The test dependencies pin Home Assistant to the same version as
the Docker image.

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check custom_components tests dev
docker compose --profile simulator config --quiet
```

Tests exercise HA config flows, legacy reconfiguration, shared-connection cleanup,
polling recovery, service errors, register decoding, and FC16 writes. A loopback
TCP test uses the same `tmodbus` backend as HA against the PyModbus simulator.

## Hardware verification

The existing register addresses and default multi-register byte/word order are
retained. Temperatures are read as signed values, so readings below 0 °C decode
correctly. Confirm these against your WT16 documentation. The simulator checks the
software against this map, not the map against a real heat pump. Reads do not
span undocumented gaps. Some firmware versions do not provide every register.
The room temperature is read from input register 12 (`BET.T.A.1`, the measured
sensor value) of the standard Modbus map. Some heat pumps have a custom Modbus
map that Weider configures on request. Such a map answers 0 at register 12 and
provides the room temperature at register 724 instead. The integration then uses
register 724. If both registers answer 0, the room temperature shows as unknown.
The integration skips these optional registers if the device rejects them: room
temperature and room target, mixer position, runtimes and the active error text.
The integration creates no entities for registers and digital inputs that the
device does not provide. It logs each skipped field at info level when it starts.

The reserve entities are disabled by default, because they are only connected on
some installations: the three reserve sensor temperatures and the inputs Reserve
1–3, Reserve 4 cooling output (optional cooling add-on), Reserve 5 and Reserve.
Enable them on the device page in Home Assistant if your installation uses them.
Installations from before 1.5.0 keep these entities as they are.
A rejected core register still makes the polling cycle fail; report the failing
address and firmware version.

The climate entities expose temperature targets only. Their `heat` mode denotes
the supported control mode, not compressor activity. Their action shows
`heating` while the compressor and the circuit's pump both run: the hot water
pump for hot water, the heating pump for the room. Otherwise it shows `idle`.
On/off and heating/cooling mode changes are not implemented.

The integration polls the heat pump every 60 seconds. The heat pump refreshes its
Modbus values about once a minute, so polling more often only repeats the same
values.

> [!WARNING]
> The controller stores the target temperatures in flash memory. Flash memory
> tolerates only a limited number of write cycles (typically around 100,000), and
> exceeding it can damage the controller. Change targets only when needed, and do
> not let automations or scripts set them on a short schedule or in a fast control
> loop.

## Known limitations

- **Connection resets about once per hour.** The controller's Ethernet board keeps
  a connection to the manufacturer's cloud service. Whenever that connection ends,
  which happens roughly every 64 minutes, the board restarts its network and drops
  the Modbus TCP connection as well
  ([#24](https://github.com/schadom/hacs_weider/issues/24)). The integration
  reconnects on its own and keeps the last values, so entities stay available.
  Home Assistant still logs each reset as an error:

  ```text
  ERROR (MainThread) [tmodbus.transport.async_tcp] Async TCP connection lost due to error: [Errno 104] Connection reset by peer
  ```

  To hide this message, add to `configuration.yaml`:

  ```yaml
  logger:
    logs:
      tmodbus.transport.async_tcp: critical
  ```

- **Use Modbus RTU to avoid the resets.** The RS485 port is not affected by the
  Ethernet board's network restarts. See
  [Connecting over RS485](#connecting-over-rs485-modbus-rtu).
- **No heating on/off or mode changes.** Only the hot water and room target
  temperatures can be changed.

## Troubleshooting

- **Entities become unavailable.** Check that the heat pump answers on its IP
  address and port 502. The Ethernet board requests a new DHCP lease after every
  network restart, so give it a fixed IP address (a DHCP reservation in your
  router). The board can also create a new MAC address on each start, which
  breaks a DHCP reservation. To keep the MAC address, enable expert mode in the
  weiRemote app's settings, then choose **Settings > Functions > Fix MAC
  address**. To change the address in the integration, open its entry menu and
  choose **Reconfigure**; this keeps all entities.
- **No answer over RS485.** Check that Modbus 1 is enabled as slave in RTU mode,
  that the baud rate, parity, stop bits and Modbus address match the
  controller, and that GND is connected. Then swap A and B.
- **Values are missing.** Some firmware versions do not provide every register.
  The integration skips them and logs each skipped field at info level when it
  starts. If the device rejects a register the integration needs, polling fails
  and the entities become unavailable; please report the register address and
  firmware version.
- **Room temperature shows 0 or unknown.** See the room temperature notes under
  [Hardware verification](#hardware-verification).
- **Enable debug logging** to see failed polls and how the integration recovers:

  ```yaml
  logger:
    logs:
      custom_components.weider: debug
      weider_modbus: debug
  ```

[hacs_weider]: https://github.com/schadom/hacs_weider
[commits-shield]: https://img.shields.io/github/commit-activity/y/schadom/hacs_weider.svg?style=for-the-badge
[commits]: https://github.com/schadom/hacs_weider/commits/master
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/schadom/hacs_weider.svg?style=for-the-badge
[demo]: https://raw.githubusercontent.com/schadom/hacs_weider/refs/heads/main/demo.png
[releases-shield]: https://img.shields.io/github/release/schadom/hacs_weider.svg?style=for-the-badge
[releases]: https://github.com/schadom/hacs_weider/releases
