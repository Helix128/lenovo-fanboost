# lenovo-fanboost

Linux fan control for the Lenovo ThinkBook 14 G7 ARP (DMI product `21MV`). The daemon reads CPU temperature and requests a fan level through the laptop's firmware.

## Scope and status

The fan-control path has been verified on DMI product `21MV` (Lenovo ThinkBook 14 G7 ARP) with BIOS `P6CN38WW`. The kernel module enforces strict DMI matching and verifies the required ACPI method before binding to prevent unintended writes to unsupported hardware.

## Compatibility roadmap

Expanding support to additional Lenovo laptops (ThinkBook, Yoga, and IdeaPad lines) follows a strict reverse-engineering and validation workflow:

1. **Safety-first DMI whitelist**: Writing arbitrary registers on the Embedded Controller (EC) can disrupt platform firmware. Every newly supported chassis will be gated behind verified DMI match entries.
2. **Firmware analysis (ACPI/WMI & ITS)**:
   - Correlating vendor Windows Intelligent Thermal Solution (ITS) drivers with Linux platform interfaces.
   - Disassembling DSDT/SSDT tables to verify WMI method availability (`WMLA`, `VPC2004`) and fan control capability bits.
3. **Community diagnostics**:
   - Diagnostic tools and instructions to capture `acpidump`, DMI identifiers, and `hwmon` sensor topology without risk to hardware.
4. **Target models under evaluation**:
   - ThinkBook 14 / 16 G6 & G7 series (AMD / Intel).
   - Yoga Slim and IdeaPad models sharing compatible ACPI/EC thermal hooks.

## Install

On Arch or CachyOS, install the package with DKMS, kernel headers, and the compiler tools for the installed kernel:

```sh
cd packaging
makepkg -si
sudo lenovo-fanboost on
```

DKMS selects clang/lld/llvm for clang-built kernels and gcc for gcc-built kernels. For a manual build on a clang-built kernel, run `make -C kernel LLVM=1`.

## Use

```sh
lenovo-fanboost                 # show service, level, temperature, and fan status
lenovo-fanboost watch           # refresh status every second
sudo lenovo-fanboost level high # choose low, medium, or high
sudo lenovo-fanboost off        # disable the service and return control to the EC
sudo lenovo-fanboost on         # enable the service now and at boot
```

The installed configuration is `/etc/lenovo-fanboost.toml`:

```toml
[fanboost]
on = 65.0
off = 55.0
hold = 15.0
level = "high"
interval = 0.5
```

The daemon reads Tctl from `k10temp`. It requests a fan boost when Tctl reaches `on`, then returns to automatic control after Tctl stays below `off` for `hold` seconds. `interval` sets the polling interval. Low, medium, and high request 60%, 80%, and 100% of 4000 rpm. Change the level with the CLI; restart the service after editing the file.

## Hardware interface

The kernel module exposes a hwmon device named `lenovo_fanboost`:

- `fan1_target` accepts requests from 0 to 4000 rpm. A value of 0 returns control to the EC. Reading the file shows the last successful request, not measured fan speed.
- `fan1_raw` reads the raw EC value at `0x95`; its rpm scale is not confirmed.
- Optional `fan1_input` converts the raw value with `rpm_per_unit=N`. The result is an estimate, not a verified tachometer reading.

## Lenovo ITS

Lenovo publishes separate Windows Intelligent Thermal Solution (ITS) packages for models including the [S340](https://support.lenovo.com/gb/en/downloads/ds506314), [Yoga Slim 7](https://support.lenovo.com/gb/en/downloads/ds549491), and [Yoga 6](https://support.lenovo.com/kr/ko/downloads/ds551850). These listings do not establish compatibility with this Linux driver.

Static analysis of ITS 5.0.2510.1 on the `21MV` found thermal and power mode changes, but no fan command. The fan request used by this project was checked separately through WMI/ACPI: EC readback changed after a request, and `0` returned control to the EC.

## Recovery and removal

The module requests automatic control at startup and before removal, shutdown, or suspend. The daemon does the same on exit or sensor failure, and the systemd service attempts a reset when it stops. EC and CPU firmware thermal protections remain active.

To restore automatic control manually, write `0` to `fan1_target` on the hwmon device named `lenovo_fanboost`.

To uninstall:

```sh
sudo lenovo-fanboost off
sudo modprobe -r lenovo_fanboost
sudo pacman -R lenovo-fanboost
```

## Tests and license

Run `python -I -m unittest`. Tests use a temporary fake hwmon tree and do not access hardware.

Licensed under GPL-2.0-only. See [LICENSE](LICENSE).
