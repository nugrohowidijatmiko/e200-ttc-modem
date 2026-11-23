#!/bin/bash
# Siapkan BSP + paket PYNQ supaya image e200 langsung siap saat power on:
#   - node AD9361 + DMA dimasukkan ke device tree utama (tanpa overlay)
#   - paket rootfs: iiod, can-utils, jaringan systemd-networkd (192.168.2.99 + DHCP), can0.service
# Jalankan di WSL:  bash /mnt/d/antsdr_download/image_final/siapkan_image_final.sh
# BELUM DIUJI. Semua file yang diubah disimpan dulu sebagai *.asli
CAN_BITRATE=500000
set -e
B=~/antsdr/antsdr-pynq/boards/e200
SD=~/antsdr/antsdr-pynq/PYNQ/sdbuild
DTS=$B/petalinux_bsp/meta-user/recipes-bsp/device-tree/files/system-user.dtsi

# ---------- 1. Device tree: aktifkan blok AD9361 yang di-comment ----------
[ -f "$DTS.asli" ] || cp "$DTS" "$DTS.asli"
cp "$DTS.asli" "$DTS"
python3 - "$DTS" <<'PY'
import re, sys
p = sys.argv[1]
L = open(p).read().split('\n')
def find(prefix):
    for i, l in enumerate(L):
        if l.startswith(prefix):
            return i
    raise SystemExit('tidak ketemu: ' + prefix)
s_phy = find('// \tadc0_ad9361: ad9361-phy@0 {')
e_phy = next(i for i in range(s_phy, len(L)) if L[i].startswith('// \t};'))
s_amba = find('// \t&amba {')
e_amba = next(i for i in range(s_amba + 1, len(L)) if L[i].startswith('// \t};'))
unc = lambda a, b: '\n'.join(re.sub(r'^// ?', '', l) for l in L[a:b + 1])
phy = unc(s_phy, e_phy)
phy = phy.replace('clocks = <&ad9361_clkin 0>;', 'clocks = <&ad9361_clkin>;')
phy = phy.replace('enable-gpios = <&gpio0 69 0>;', 'enable-gpios = <&gpio0 101 0>;')
phy = phy.replace('txnrx-gpios = <&gpio0 70 0>;', 'txnrx-gpios = <&gpio0 102 0>;')
amba = unc(s_amba + 1, e_amba - 1).replace('IRQ_TYPE_LEVEL_HIGH', '4').replace('<&clkc 16>', '<&clkc 15>')
amba = re.sub(r'\s*compatible = "simple-bus";\s*#address-cells = <0x1>;\s*#size-cells = <0x1>;\s*ranges;', '', amba)
amba = re.sub(r'\taxi_i2c0: i2c@41600000 \{.*?\n\t\t\};\n', '', amba, flags=re.S)
amba = re.sub(r'\tmwipcore@43c00000 \{.*?\};\n', '', amba, flags=re.S)
add = f'''

/* ===== AD9361 antSDR E200 (ditambahkan oleh siapkan_image_final.sh) ===== */
/ {{
	ad9361_clkin: ad9361-clkin {{
		compatible = "fixed-clock";
		#clock-cells = <0>;
		clock-frequency = <40000000>;
		clock-output-names = "ad9361_ext_refclk";
	}};
}};

&spi0 {{
	#address-cells = <1>;
	#size-cells = <0>;
	status = "okay";
{phy}
}};

&amba {{
{amba}
}};
'''
open(p, 'a').write(add)
print('OK: node AD9361 ditambahkan ke', p)
PY

# ---------- 2. Paket rootfs: autostart jaringan + CAN + iiod ----------
PKG=$SD/packages/antsdr_e200_autostart
mkdir -p $PKG
cat > $PKG/qemu.sh <<EOF
#!/bin/bash
# Dijalankan di dalam chroot rootfs saat build PYNQ
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y iiod libiio-utils can-utils device-tree-compiler

# Jaringan: systemd-networkd, DHCP + alamat tetap 192.168.2.99
mkdir -p /etc/systemd/network
cat > /etc/systemd/network/10-eth0.network <<'EON'
[Match]
Name=eth0

[Network]
DHCP=ipv4
Address=192.168.2.99/24
EON
rm -f /etc/network/interfaces.d/eth0
systemctl enable systemd-networkd
systemctl disable systemd-networkd-wait-online.service || true

# CAN0 otomatis UP
cat > /etc/systemd/system/can0.service <<'EOC'
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
EOC
systemctl enable can0.service iiod.service
EOF
chmod 755 $PKG/qemu.sh
echo "OK: paket $PKG dibuat"

# ---------- 3. Daftarkan paket di e200.spec ----------
[ -f "$B/e200.spec.asli" ] || cp "$B/e200.spec" "$B/e200.spec.asli"
grep -q antsdr_e200_autostart $B/e200.spec || \
  sed -i 's/^STAGE4_PACKAGES_e200 := \(.*\)$/STAGE4_PACKAGES_e200 := \1 antsdr_e200_autostart/' $B/e200.spec
grep STAGE4 $B/e200.spec

echo
echo "Selesai. Langkah berikutnya: hapus hasil build lama lalu make ulang (lihat tutorial Bagian M)."
