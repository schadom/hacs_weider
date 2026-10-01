# Weider WT16 integration

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]

> [!IMPORTANT]
> This integration is not affiliated with Weider Wärmepumpen GmbH and is provided as-is and without warranty.

Component to integrate with [Weider](https://www.weider.co.at) WT16 heat pumps.

The device library is vendorized below `custom_components/weider/vendor`.

## Installation with HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=schadom&repository=hacs_weider&category=integration)

1. Add this repository as a custom repository of category **Integration**.
2. Install **Weider WT16** and restart Home Assistant.
3. In **Settings > Devices & services > Add integration**, add **Weider WT16**.
4. Enter the heat pump or gateway's host/IP, TCP port (default **502**), and
	Modbus unit ID (default **1**).

For a manual install, copy `custom_components/weider` into Home Assistant's
`custom_components` directory and restart Home Assistant.

Requires Home Assistant **2026.9.0 or newer**; tested with **2026.9.4**.
The integration uses Home Assistant's shared `modbus` connection API. No separate
connection integration or Modbus YAML configuration is needed. Units acquired
through this API with identical connection parameters share a connection.

### Upgrading an old configuration

Entries created with a **Modbus Connection** selector must be reconfigured:
open the Weider integration entry's menu, choose **Reconfigure**, and supply its
host, port, and unit ID. The old connection reference does not contain enough
information to convert automatically. Reconfiguration preserves the entry and
entity IDs; do not delete the entry just to change its connection details.

## Local Docker testing

Install and start Docker Desktop on macOS, or Docker Engine with Compose on Linux.
From this repository, start the pinned Home Assistant **2026.9.4** image with
the optional synthetic WT16 server:

```sh
docker compose --profile simulator up -d
```

Open <http://localhost:8123>, complete Home Assistant onboarding, then add
**Weider WT16** with host **simulator**, port **5020**, and unit ID **1**.
The simulator is only accessible inside the Compose network. It supplies fixed
measurements and accepts target-temperature writes in memory; it does not model
heat-pump physics, firmware behavior, or temperature limits.

Expect 27 sensors, 20 binary sensors, and two temperature controls. The sample
hot-water temperature is 42.5 C and its target is 45 C. Change a target and check
that the target sensor updates. To test recovery, stop and restart the simulator:

```sh
docker compose stop simulator
docker compose --profile simulator start simulator
```

Allow a polling cycle (30 seconds, plus connection timeouts) for availability to
change. The connection should recover without reloading the integration.

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

The existing register addresses, unsigned temperature format, and default
multi-register byte/word order are retained. Confirm these against your WT16
documentation, especially for negative temperatures. The simulator checks the
software against this map, not the map against a real heat pump. Reads do not
span undocumented gaps. Optional or firmware-specific registers that return an
error can still make a full polling cycle fail; report the failing address and
firmware version rather than suppressing it silently.

The climate entities expose temperature targets only. Their `heat` mode denotes
the supported control mode, not compressor activity; the compressor binary
sensor reports that separately. On/off and heating/cooling mode changes are not
implemented.

[hacs_weider]: https://github.com/schadom/hacs_weider
[commits-shield]: https://img.shields.io/github/commit-activity/y/schadom/hacs_weider.svg?style=for-the-badge
[commits]: https://github.com/schadom/hacs_weider/commits/master
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/schadom/hacs_weider.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/schadom/hacs_weider.svg?style=for-the-badge
[releases]: https://github.com/schadom/hacs_weider/releases
