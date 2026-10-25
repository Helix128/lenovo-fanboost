#!/usr/bin/env bash
# Install lenovo-fanboost package, build module via dkms hooks, enable the service.
set -uo pipefail
pkg="$(ls -t "$(cd "$(dirname "$0")" && pwd)"/lenovo-fanboost-*-any.pkg.tar.zst | head -1)"
step() { echo "STEP $*"; }
step "pacman -U"; pacman -U --noconfirm --needed "$pkg" || { echo "ERROR pacman"; exit 1; }
step "dkms status"; dkms status lenovo-fanboost
modinfo lenovo_fanboost >/dev/null 2>&1 || { echo "ERROR module not built"; exit 1; }
step "modprobe"; dkms status lenovo-fanboost; modprobe lenovo_fanboost || { echo "ERROR modprobe"; exit 1; }
for d in /sys/class/hwmon/hwmon*; do
    [ "$(cat "$d/name")" = lenovo_fanboost ] && echo "HWMON $d target=$(cat "$d/fan1_target") raw=$(cat "$d/fan1_raw")"
done
step "enable service"; systemctl enable lenovo-fanboost.service; systemctl restart lenovo-fanboost.service || { echo "ERROR service"; exit 1; }
sleep 3; systemctl --no-pager --lines=8 status lenovo-fanboost.service
echo "DONE"
