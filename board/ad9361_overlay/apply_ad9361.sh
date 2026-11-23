#!/bin/bash
# Muat device tree overlay AD9361 di antSDR E200 (PYNQ) tanpa memprogram ulang FPGA.
# Jalankan sebagai root (terminal Jupyter sudah root):  bash apply_ad9361.sh
set -e
cd "$(dirname "$0")"

command -v dtc >/dev/null || { apt update && apt install -y device-tree-compiler; }

dtc -@ -q -I dts -O dtb -o /lib/firmware/ad9361_e200.dtbo ad9361_e200.dts
echo "OK: /lib/firmware/ad9361_e200.dtbo dibuat"

CFG=/sys/kernel/config
mountpoint -q $CFG || mount -t configfs none $CFG
OV=$CFG/device-tree/overlays/ad9361
if [ -d $OV ]; then
  echo "Overlay ad9361 sudah dimuat sebelumnya (status: $(cat $OV/status))"
else
  mkdir $OV
  cat /lib/firmware/ad9361_e200.dtbo > $OV/dtbo
  echo "Status overlay: $(cat $OV/status)"
fi

sleep 3
echo "--- dmesg ---"
dmesg | grep -i -E "ad9361|cf_axi|axi-dmac|dmac" | tail -15
echo "--- perangkat IIO ---"
iio_info -u local: 2>/dev/null | grep -E "iio:device" || ls /sys/bus/iio/devices/
