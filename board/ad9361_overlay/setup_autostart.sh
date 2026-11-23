#!/bin/bash
# Setup sekali: AD9361 overlay + CAN0 otomatis aktif saat boot (antSDR E200, PYNQ)
# Jalankan sebagai root (terminal Jupyter):  bash setup_autostart.sh
# Ganti bitrate CAN di sini kalau OBC memakai kecepatan lain:
CAN_BITRATE=500000
set -e
cd "$(dirname "$0")"

# ---------- 1. Overlay AD9361 ----------
command -v dtc >/dev/null || { apt update && apt install -y device-tree-compiler; }
if [ -f ad9361_e200.dts ]; then
  dtc -@ -q -I dts -O dtb -o /lib/firmware/ad9361_e200.dtbo ad9361_e200.dts
fi
[ -f /lib/firmware/ad9361_e200.dtbo ] || { echo "ERROR: ad9361_e200.dtbo tidak ada"; exit 1; }

cat > /usr/local/sbin/load-ad9361-overlay.sh <<'EOF'
#!/bin/bash
CFG=/sys/kernel/config
mountpoint -q $CFG || mount -t configfs none $CFG
OV=$CFG/device-tree/overlays/ad9361
[ -d $OV ] && exit 0
mkdir $OV
cat /lib/firmware/ad9361_e200.dtbo > $OV/dtbo
# beri waktu driver AD9361 selesai probe
for i in $(seq 1 20); do
  grep -qs ad9361-phy /sys/bus/iio/devices/*/name && exit 0
  sleep 0.5
done
echo "ad9361 belum muncul setelah overlay" >&2
EOF
chmod 755 /usr/local/sbin/load-ad9361-overlay.sh

cat > /etc/systemd/system/ad9361-overlay.service <<'EOF'
[Unit]
Description=Muat device tree overlay AD9361 (antSDR E200)
After=local-fs.target sys-kernel-config.mount
Before=iiod.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/load-ad9361-overlay.sh

[Install]
WantedBy=multi-user.target
EOF

mkdir -p /etc/systemd/system/iiod.service.d
cat > /etc/systemd/system/iiod.service.d/after-ad9361.conf <<'EOF'
[Unit]
Wants=ad9361-overlay.service
After=ad9361-overlay.service
EOF

# ---------- 2. CAN0 ----------
cat > /etc/systemd/system/can0.service <<EOF
[Unit]
Description=Aktifkan CAN0 (SocketCAN) saat boot
BindsTo=sys-subsystem-net-devices-can0.device
After=sys-subsystem-net-devices-can0.device

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=-/usr/sbin/ip link set can0 down
ExecStart=/usr/sbin/ip link set can0 up type can bitrate ${CAN_BITRATE} loopback off restart-ms 100
ExecStop=/usr/sbin/ip link set can0 down

[Install]
WantedBy=multi-user.target
EOF

# ---------- aktifkan ----------
systemctl daemon-reload
systemctl enable ad9361-overlay.service can0.service iiod.service
systemctl start ad9361-overlay.service
systemctl restart can0.service iiod.service

echo
echo "===== STATUS ====="
systemctl is-active ad9361-overlay can0 iiod
ip -details link show can0 | grep -E "state|bitrate|loopback"
iio_info -u local: 2>/dev/null | grep "iio:device"
echo "Selesai. Coba reboot untuk memastikan semuanya otomatis: sudo reboot"
