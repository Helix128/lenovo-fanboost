# Compatibility Roadmap

This document outlines the planned hardware support expansion for `lenovo-fanboost`.

Because writing unverified values to laptop ACPI methods or Embedded Controller (EC) registers risks firmware lockups, models are added through a strict DMI whitelist after verifying their ACPI tables and fan control interfaces.

---

## Supported Hardware

| Model | DMI Product | Platform | Status |
|---|---|---|---|
| ThinkBook 14 G7 ARP | `21MV` | AMD Zen 3+ / Zen 4 (Barcelo/Rembrandt) | Verified & Tested |
| ThinkBook 16 G7 ARP | `21NW` | AMD Zen 3+ / Zen 4 (Barcelo/Rembrandt) | Added (Shared LCFC board) |

---

## Target Tiers

### Tier 1: Modern ThinkBooks (2023–2025)
High priority. These models share the same motherboard ODM platform (LCFC), the `\_SB.WMI5.WMLA` ACPI method, and the `IDEA2008` ITS 5.x firmware structure:

- **ThinkBook 14 / 16 G6** (AMD Ryzen 7030/7035/7040 and Intel 13th gen)
- **ThinkBook 14+ / 16+ Gen 5** (Ryzen 7040/8040 and Intel 13th gen)
- **ThinkBook 14 G7 / 16 G7 IAH / IMH** (Intel 13th gen / Core Ultra)

### Tier 2: Consumer Sister Platforms (IdeaPad Pro & Yoga)
These devices use the same `VPC2004` device node and similar EC firmware logic:

- **IdeaPad Pro 5 (14" & 16", Gen 8 / Gen 9)**: Same 25W–45W thermal design and identical thermal throttling behavior under Linux.
- **Yoga Slim 7 & Yoga Pro 7 (Gen 8 / Gen 9)**: Ultrabooks with identical fan latency issues in the EC curve.

### Tier 3: Older ThinkBooks (2021–2022)
- **ThinkBook 14+ / 16+ Gen 4** (Ryzen 6000 Rembrandt / Intel 12th gen)
- **ThinkBook 14 / 15 G4 & G5**

### Dual-Fan Hardware (Requires Driver Extension)
- **ThinkBook 16p (Gen 4, Gen 5)**: High-performance creator laptops with discrete RTX graphics. These feature two independent fans and will require extending the driver to handle a secondary channel (`fan2_target`).

---

## How to Help Add a Model

If your Lenovo laptop has thermal lag or runs hot under Linux and you want to verify compatibility:

1. Extract the DSDT table:
   ```sh
   sudo cp /sys/firmware/acpi/tables/DSDT ./dsdt.dat
   ```
   *(Extracting only the DSDT table avoids dumping unrelated tables like MSDM, which contains the preinstalled Windows license key).*
2. Get the DMI product strings:
   ```sh
   sudo dmidecode -s system-product-name
   sudo dmidecode -s system-version
   ```
3. Open an issue on GitHub attaching `dsdt.dat` and the DMI product name. The DSDT will be checked for the `WMLA` method and matching fan SID (`0x04030001`) before adding the DMI entry.
