# lenovo-fanboost

Proactive Linux fan control utility for Lenovo laptops. 

On many modern Lenovo laptops, the Embedded Controller (EC) manages thermal curves automatically, but reacts with a noticeable delay of around 20 to 25 seconds when a heavy workload hits the CPU. During bursty compiles or demanding tasks, temperatures can spike straight to 100 °C and trigger thermal throttling long before the fans spin up to full speed.

This project addresses that gap by coupling an out-of-tree kernel module with a lightweight userspace daemon. The driver calls Lenovo's ACPI firmware methods directly to request higher fan speeds ahead of time, then smoothly restores automatic EC control once the CPU cools down.

Initial testing was done on a **ThinkBook 14 G7 ARP** (`21MV`, BIOS `P6CN38WW`), dropping peak compile temperatures from 100 °C (throttling) to a stable 92.9 °C. The goal is to extend support to additional Lenovo laptops (other ThinkBook, Yoga, and IdeaPad models) sharing compatible ACPI/WMI thermal interfaces.

## How it works

The project is split into three main parts:

- `kernel/lenovo_fanboost.c`: Kernel driver exposing a standard `hwmon` interface. Writing a target RPM to `fan1_target` invokes the ACPI method `\_SB.WMI5.WMLA(0, 0x12, {0x04030001, rpm})`. Writing `0` immediately hands fan control back to the EC. It also exposes `fan1_max` (model-specific maximum RPM) and `fan1_raw` to read EC register `0x95`.
- `daemon/lenovo-fanboostd`: Background daemon that reads CPU temperature (`Tctl` via `k10temp`) and continuously interpolates percentage-based fan curves mapped to the laptop's hardware RPM range.
- `daemon/lenovo-fanboost`: CLI utility to check live telemetry, switch fan profiles (`Quiet`, `Balanced`, `Aggressive`), and control service state (`Active` / `Inactive (EC Mode)`).

## Compatibility and roadmap

Writing arbitrary values to unfamiliar ACPI methods or EC registers can lock up laptop firmware. Because of this, the driver will not load generically: it enforces a strict DMI whitelist and checks for the required ACPI method before registering hardware.

### Supported models
- **Lenovo ThinkBook 14 G7 ARP** (`21MV`, BIOS `P6CN38WW`)
- **Lenovo ThinkBook 16 G7 ARP** (`21NW`)

### Adding more models
Detailed model tiers and instructions for testing new hardware are documented in [ROADMAP.md](ROADMAP.md). If you have another Lenovo laptop (ThinkBook, IdeaPad Pro, or Yoga) and want to test compatibility, open an issue with your `acpidump` and `dmidecode` output.

## Usage

```sh
lenovo-fanboost                      # View state (Active / Inactive), profile, and fan telemetry
lenovo-fanboost watch                # Live telemetry stream, refreshes once per second
sudo lenovo-fanboost profile Quiet   # Switch curve profile: Quiet, Balanced, or Aggressive
sudo lenovo-fanboost off             # Stop service and return fan control to EC Mode
sudo lenovo-fanboost on              # Enable service now and at system boot
```

## Configuration

Configuration lives at `/etc/lenovo-fanboost.toml`:

```toml
[fanboost]
profile = "Balanced"
interval = 0.5

[profiles.Quiet]
# Temperature in °C vs fan speed in % (0% = EC automatic control)
points = [[40, 0], [60, 0], [70, 45], [80, 65], [90, 90], [95, 100]]

[profiles.Balanced]
points = [[40, 0], [50, 0], [60, 45], [70, 65], [80, 85], [90, 100]]

[profiles.Aggressive]
points = [[40, 0], [45, 40], [55, 60], [65, 80], [75, 100], [95, 100]]
```

Curves use percentages `[temperature_celsius, percent_0_to_100]`. The driver defines the maximum hardware RPM for each supported laptop model, so the same profile scales cleanly across different laptops.

## Safety and recovery

- The kernel module caps fan requests between 0 and the model's `max_rpm`.
- Automatic EC control (`0`) is requested when the driver loads, before it unloads, and during system shutdown or suspend.
- If the daemon crashes or the thermal sensor fails to read, control drops back to the EC immediately. The systemd unit also enforces an EC reset via `ExecStopPost`.
- Hardware thermal safety mechanisms built into the CPU and EC remain active at all times.

## Installation (Arch / CachyOS)

Install via DKMS:

```sh
cd packaging
makepkg -si
sudo lenovo-fanboost on
```

`dkms.conf` automatically chooses clang or gcc depending on how the installed kernel was built (standard in CachyOS vs Arch stock).

## Manual recovery & uninstallation

To manually restore automatic fan control at any time:

```sh
echo 0 | sudo tee /sys/class/hwmon/hwmon*/fan1_target
```

To uninstall:

```sh
sudo lenovo-fanboost off
sudo modprobe -r lenovo_fanboost
sudo pacman -R lenovo-fanboost
```

## Testing

Run unit tests with:

```sh
python -I -m unittest
```

Tests use a mocked `hwmon` sysfs hierarchy and do not touch real hardware.


## License

GPL-2.0-only. See [LICENSE](LICENSE).

**Disclaimer:** This is an independent, community-developed project and is not affiliated with, endorsed by, or supported by Lenovo. Lenovo® is a trademark of Lenovo.
