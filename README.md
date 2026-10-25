# lenovo-fanboost

Proactive Linux fan control utility for Lenovo laptops. 

On many modern Lenovo laptops, the Embedded Controller (EC) manages thermal curves automatically, but reacts with a noticeable delay of around 20 to 25 seconds when a heavy workload hits the CPU. During bursty compiles or demanding tasks, temperatures can spike straight to 100 °C and trigger thermal throttling long before the fans spin up to full speed.

This project addresses that gap by coupling an out-of-tree kernel module with a lightweight userspace daemon. The driver calls Lenovo's ACPI firmware methods directly to request higher fan speeds ahead of time, then smoothly restores automatic EC control once the CPU cools down.

Initial testing was done on a **ThinkBook 14 G7 ARP** (`21MV`, BIOS `P6CN38WW`), dropping peak compile temperatures from 100 °C (throttling) to a stable 92.9 °C. The goal is to extend support to additional Lenovo laptops (other ThinkBook, Yoga, and IdeaPad models) sharing compatible ACPI/WMI thermal interfaces.

## How it works

The project is split into three main parts:

- `kernel/lenovo_fanboost.c`: Kernel driver exposing a standard `hwmon` interface. Writing a target RPM (between 0 and 4000) to `fan1_target` invokes the ACPI method `\_SB.WMI5.WMLA(0, 0x12, {0x04030001, rpm})`. Writing `0` immediately hands fan control back to the EC. It also exposes `fan1_raw` to read EC register `0x95`.
- `daemon/lenovo-fanboostd`: Background daemon that reads CPU temperature (`Tctl` via `k10temp`) and applies configurable hysteresis (`on`, `off`, `hold`) across predefined fan levels (`low`, `medium`, `high`).
- `daemon/lenovo-fanboost`: CLI utility to check live telemetry, switch fan levels on the fly, and manage the systemd service.

## Compatibility and roadmap

Writing arbitrary values to unfamiliar ACPI methods or EC registers can lock up laptop firmware. Because of this, the driver will not load generically: it enforces a strict DMI whitelist and checks for the required ACPI method before registering hardware.

### Verified models
- **Lenovo ThinkBook 14 G7 ARP** (`21MV`, BIOS `P6CN38WW`)

### Adding more models
Lenovo uses different ACPI IDs and EC offsets across model generations. Adding a new chassis safely requires:
1. **DSDT table verification**: Examining `acpidump` tables to see if the machine exposes `WMLA` or the `VPC2004` device with matching thermal IDs (`0x04030001`).
2. **Reverse engineering ITS**: Inspecting Lenovo's Windows Intelligent Thermal Solution (ITS) driver packages to verify the command payloads and EC status registers for that model.
3. **Hardware validation**: Adding the verified DMI identity to the driver and confirming that stopping the service (`0`) reliably returns control to the EC without unexpected behavior.

If you have a different Lenovo laptop and want to help test compatibility, feel free to open an issue with your `acpidump` and `dmidecode` output.

## Usage

```sh
lenovo-fanboost                 # View service status, profile, temperature, and fan state
lenovo-fanboost watch           # Live view, refreshes every second
sudo lenovo-fanboost level high # Switch profile: low (60%), medium (80%), high (100%)
sudo lenovo-fanboost off        # Stop service and return fan control to the EC
sudo lenovo-fanboost on         # Enable service now and at system boot
```

## Configuration

Configuration lives at `/etc/lenovo-fanboost.toml`:

```toml
[fanboost]
on = 65.0       # Temperature to trigger fan boost (°C)
off = 55.0      # Temperature threshold to begin cooldown (°C)
hold = 15.0     # Seconds temperature must stay below 'off' before returning control to EC
level = "high"  # Fan profile: low, medium, or high
interval = 0.5  # Polling interval in seconds
```

## Safety and recovery

- The kernel module caps fan requests between 0 and 4000 RPM.
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
