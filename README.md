# E200 TT&C Modem: Modem Satelit Berbasis antSDR, PYNQ, dan CSP over CAN

**Bahasa Indonesia** · [English](#english)

File pendukung untuk menjalankan **PYNQ Linux** di **antSDR E200** (Zynq-7020 + AD9361) dengan:

- **CAN0** controller PS Zynq lewat EMIO ke header **J30** (pin 3 = TX/V5, pin 4 = RX/U7), driver `xilinx_can`, SocketCAN
- **Ethernet** PL (GEM0 + GMII-to-RGMII) dengan IP tetap `192.168.2.99`
- **AD9361** lewat driver IIO ADI + `iiod`, bisa dipakai GNU Radio dari laptop
- Semua aktif otomatis saat power on

Build dilakukan di **Windows + WSL2 Ubuntu 18.04** dengan Vivado/Vitis 2021.1, PetaLinux 2022.1, dan PYNQ v3.0.1 ([antsdr-pynq](https://github.com/MicroPhase/antsdr-pynq)).

Tutorial lengkap langkah demi langkah: [`docs/tutorial_id.md`](docs/tutorial_id.md) (Bahasa Indonesia) · [`docs/tutorial_en.md`](docs/tutorial_en.md) (English)

## Isi repo

| Folder | Isi | Dipakai di |
| --- | --- | --- |
| `hdl/` | `add_can0.sh`, file HDL `antsdre200` yang sudah dimodifikasi, `can0_emio.patch` | Build bitstream (Vivado) |
| `petalinux/` | `can.cfg` (SocketCAN + `xilinx_can`) | Build kernel |
| `board/e200/base/` | `base.py`, `__init__.py` (overlay PYNQ) | Build image PYNQ |
| `board/ad9361_overlay/` | `ad9361_e200.dts`, `apply_ad9361.sh`, `setup_autostart.sh` | Di antSDR |
| `board/network/` | `10-eth0.network` (systemd-networkd) | Di antSDR |
| `image_final/` | `siapkan_image_final.sh` (belum diuji) | Build ulang image final |
| `apps/antsdr_csp_bridge/` | Bridge CSP 1.x (CAN) ↔ CCSDS ↔ GMSK 9600 bps | Di antSDR |
| `apps/gnuradio/` | `fm_rx_antsdr.grc` receiver FM (GNU Radio 3.10) | Di laptop |

File besar (image SD card, BOOT.BIN, bitstream, installer) **tidak** disimpan di repo ini.

## Pin J30

| J30 | Sinyal | SN65HVD230 |
| --- | --- | --- |
| 1 | 3,3 V | 3V3 |
| 2 | GND | GND |
| 3 | `can0_tx` (V5) | CTX / D |
| 4 | `can0_rx` (U7) | CRX / R |

Header J30 berjarak pin 2,0 mm. Bank 13 Zynq di E200 memakai VCCO 3,3 V.

## Catatan

- Gunakan SD card 16–32 GB. Kartu SDXC 256 GB terbukti gagal dibaca (I/O error).
- Bitrate CAN default 500 kbps (ubah `CAN_BITRATE` di `setup_autostart.sh`).
- File HDL turunan dari repo HDL Analog Devices dan mengikuti lisensi aslinya (GPL-2.0 / ADI BSD).

---

<a name="english"></a>
## English

Support files for running **PYNQ Linux** on the **antSDR E200** (Zynq-7020 + AD9361) with:

- **CAN0** (Zynq PS controller) routed through EMIO to header **J30** (pin 3 = TX/V5, pin 4 = RX/U7), `xilinx_can` driver, SocketCAN
- PL **Ethernet** (GEM0 + GMII-to-RGMII) with a fixed IP `192.168.2.99`
- **AD9361** through the ADI IIO driver + `iiod`, usable from GNU Radio on a laptop
- Everything comes up automatically at power on

Built on **Windows + WSL2 Ubuntu 18.04** with Vivado/Vitis 2021.1, PetaLinux 2022.1 and PYNQ v3.0.1 ([antsdr-pynq](https://github.com/MicroPhase/antsdr-pynq)).

Full step-by-step tutorial: [`docs/tutorial_en.md`](docs/tutorial_en.md) (English) · [`docs/tutorial_id.md`](docs/tutorial_id.md) (Bahasa Indonesia)

### Quick overview

1. HDL: run `hdl/add_can0.sh` (or apply `hdl/antsdre200/can0_emio.patch`), build `projects/antsdre200` with Vivado 2021.1.
2. Copy the XSA, bitstream and `.hwh` into `antsdr-pynq/boards/e200`, add `board/e200/base/*.py` and `petalinux/recipes-kernel/can.cfg`.
3. Build the PYNQ image: `make BOARDDIR=$HOME/antsdr/antsdr-pynq/boards BOARDS=e200`.
4. Build a BOOT.BIN that contains the bitstream with `e200_boot_gen` (Ethernet and the CAN0 pins live in the PL).
5. On the board: install `board/network/10-eth0.network`, then run `board/ad9361_overlay/setup_autostart.sh`.

### Notes

- Use a 16–32 GB SD card; a 256 GB SDXC card failed with I/O errors.
- Default CAN bitrate is 500 kbps (`CAN_BITRATE` in `setup_autostart.sh`).
- HDL files are derived from the Analog Devices HDL repository and keep its license (GPL-2.0 / ADI BSD).
