#!/bin/bash
# Tambah CAN0 (PS Zynq, via EMIO) ke project HDL antsdre200
#   can0_tx -> V5 (J30), can0_rx -> U7 (J30)
# Bank 13 di antSDR E200 diberi VCCO 3.3V (lihat skematik hal. 4),
# jadi pin bank 13 di XDC diseragamkan ke LVCMOS33.
set -e
cd ~/antsdr/hdl/projects/antsdre200

# --- backup (sekali saja) ---
for f in system_bd.tcl system_top.v system.xdc; do
  [ -f "$f.asli" ] || cp "$f" "$f.asli"
done

# kalau sudah pernah dijalankan, mulai lagi dari file asli
cp system_bd.tcl.asli system_bd.tcl
cp system_top.v.asli  system_top.v
cp system.xdc.asli    system.xdc

python3 - <<'PY'
import re

# 1) system_bd.tcl : aktifkan CAN0 lewat EMIO + port + koneksi
p = 'system_bd.tcl'
s = open(p).read()
anchor = 'ad_ip_parameter sys_ps7 CONFIG.PCW_SPI1_SPI1_IO EMIO\n'
assert anchor in s, 'anchor SPI1 tidak ditemukan'
s = s.replace(anchor, anchor +
    '# CAN0 via EMIO (ke header J30)\n'
    'ad_ip_parameter sys_ps7 CONFIG.PCW_CAN0_PERIPHERAL_ENABLE 1\n'
    'ad_ip_parameter sys_ps7 CONFIG.PCW_CAN0_CAN0_IO EMIO\n'
    'ad_ip_parameter sys_ps7 CONFIG.PCW_CAN_PERIPHERAL_FREQMHZ 100\n', 1)
anchor2 = '# system id\n'
assert anchor2 in s, 'anchor system id tidak ditemukan'
s = s.replace(anchor2,
    '# can0 connections\n\n'
    'create_bd_port -dir O can0_tx\n'
    'create_bd_port -dir I can0_rx\n'
    'ad_connect can0_tx sys_ps7/CAN0_PHY_TX\n'
    'ad_connect can0_rx sys_ps7/CAN0_PHY_RX\n\n' + anchor2, 1)
open(p, 'w').write(s)

# 2) system_top.v : port top-level + sambungan ke system_wrapper
p = 'system_top.v'
s = open(p).read()
a = '  output          tx_amp_en\n  );'
assert a in s, 'anchor tx_amp_en tidak ditemukan'
s = s.replace(a,
    '  // CAN0 (PS, via EMIO) ke header J30\n'
    '  output          can0_tx,\n'
    '  input           can0_rx,\n\n' + a, 1)
b = '    .ddr_addr (ddr_addr),'
assert b in s, 'anchor ddr_addr tidak ditemukan'
s = s.replace(b, '    .can0_tx (can0_tx),\n    .can0_rx (can0_rx),\n' + b, 1)
open(p, 'w').write(s)

# 3) system.xdc : bank 13 -> LVCMOS33, tambah pin CAN0
p = 'system.xdc'
s = open(p).read()
for pin in ['V6', 'W6', 'V10', 'V11']:
    s, n = re.subn(r'(PACKAGE_PIN\s+%s\s+IOSTANDARD\s+)LVCMOS18' % pin, r'\1LVCMOS33', s)
    assert n == 1, 'pin %s tidak ditemukan' % pin
s += ('\n# CAN0 (PS via EMIO) -> header J30, bank 13 (VCCO 3.3V)\n'
      'set_property -dict {PACKAGE_PIN V5 IOSTANDARD LVCMOS33} [get_ports can0_tx]\n'
      'set_property -dict {PACKAGE_PIN U7 IOSTANDARD LVCMOS33 PULLTYPE PULLUP} [get_ports can0_rx]\n')
open(p, 'w').write(s)
print('OK: system_bd.tcl, system_top.v, system.xdc sudah dimodifikasi')
PY

echo
echo "===== Ringkasan perubahan ====="
for f in system_bd.tcl system_top.v system.xdc; do
  echo "--- $f ---"
  diff "$f.asli" "$f" || true
done
