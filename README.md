# lenovo-fanboost

Linux fan control utility for Lenovo laptops. It pairs an out-of-tree kernel module (exposing a standard `hwmon` interface via ACPI/WMI) with a lightweight userspace daemon that monitors CPU temperatures and spins up the fan during sustained workloads, before handing control back to the EC.

Initial hardware verification was done on the Lenovo ThinkBook 14 G7 ARP (`21MV`). Because Lenovo shares ACPI layouts and ITS (Intelligent Thermal Solution) logic across several families, the broader goal is to systematically support other ThinkBook, Yoga, and IdeaPad models.

## How it works

On modern Lenovo laptops, the Embedded Controller (EC) handles thermal curves in hardware, but often ramps fans up too late during sudden compute spikes.

This driver talks directly to Lenovo's ACPI methods (specifically `WMLA` over `\_SB.WMI5`) to set a target fan speed. Writing a target RPM engages the fan, while writing `0` hands control straight back to the EC. The daemon monitors `k10temp` (Tctl) and applies hysteresis: fans kick in early under heavy load and return to automatic control once temperatures drop and stay below the threshold for a cooldown period.

## Compatibility and roadmap

Writing blindly to ACPI methods or EC registers on unsupported laptops can cause firmware lockups or unexpected power states. For this reason, the kernel driver uses a strict DMI whitelist rather than binding generically.

### Verified models
- **Lenovo ThinkBook 14 G7 ARP** (DMI product `21MV`, BIOS `P6CN38WW`)

### Roadmap for other Lenovo laptops
Lenovo adjusts ACPI IDs and EC offsets across model generations. Adding new hardware safely requires:
1. **DSDT inspection**: Verifying whether the target laptop implements the `WMLA` ACPI method or `VPC2004` device with matching fan control IDs (such as `0x04030001`).
2. **Reverse engineering ITS**: Analyzing Lenovo's Windows ITS packages to confirm command payloads and EC status registers for each chassis.
3. **Quirk integration**: Adding tested DMI matches and chassis-specific quirks to the driver once validated with community `acpidump` data.

If you have a different Lenovo laptop and want to help test compatibility, feel free to open an issue with your `acpidump` and `dmidecode` output.

## Installation

On Arch Linux or CachyOS, you can install the package using DKMS:

```sh
cd packaging
makepkg -si
sudo lenovo-fanboost on
```

DKMS automatically picks clang/lld/llvm for clang-built kernels and gcc for standard kernels. If building manually on a clang-built kernel, run `make -C kernel LLVM=1`.

## Usage

```sh
lenovo-fanboost                 # Show service state, temperature, and current fan target
lenovo-fanboost watch           # Live view (refreshes every second)
sudo lenovo-fanboost level high # Set profile: low, medium, or high
sudo lenovo-fanboost off        # Stop service and return fan control to EC
sudo lenovo-fanboost on         # Enable service now and at system boot
```

The configuration file is installed at `/etc/lenovo-fanboost.toml`:

```toml
[fanboost]
on = 65.0
off = 55.0
hold = 15.0
level = "high"
interval = 0.5
```

The daemon reads Tctl from `k10temp`. When temperature reaches `on`, it boosts the fan. Once temperature drops below `off` and stays there for `hold` seconds, it returns the fan to automatic EC control. Low, medium, and high correspond to roughly 60%, 80%, and 100% of maximum fan speed (4000 RPM).

## Hardware interface

The kernel module registers a `hwmon` device named `lenovo_fanboost`:

- `fan1_target`: Accepts requests from 0 to 4000 RPM. Writing `0` restores automatic EC control. Reading it shows the last requested target.
- `fan1_raw`: Reads the raw EC value at register `0x95`.
- `fan1_input`: Optional attribute that converts the raw reading into estimated RPM if `rpm_per_unit` is configured.

## Safety and recovery

The module automatically requests EC control at load time and releases control before unload, shutdown, or suspend. The daemon does the same on exit or if the temperature sensor fails. Built-in CPU and EC thermal protections remain untouched and take priority at all times.

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

## Testing and license

Run tests with `python -I -m unittest`. The suite mocks the `hwmon` filesystem tree and does not interact with physical hardware.

Licensed under GPL-2.0-only. See [LICENSE](LICENSE).
