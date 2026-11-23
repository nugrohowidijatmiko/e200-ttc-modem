# E200 TT&C Modem: Modem Satelit Berbasis antSDR, PYNQ, dan CSP over CAN

**[Bahasa Indonesia](#bahasa-indonesia)** · **[English](#english)**

antSDR E200 (Zynq-7020 + AD9361) yang menjalankan **PYNQ Linux** dengan **CAN0** (CSP over CAN ke OBC lewat header J30), **Ethernet**, dan **AD9361** (IIO + `iiod` untuk GNU Radio), semuanya aktif otomatis saat power on. Build dilakukan di **Windows + WSL2 Ubuntu 18.04** dengan Vivado/Vitis 2021.1, PetaLinux 2022.1, dan PYNQ v3.0.1 ([antsdr-pynq](https://github.com/MicroPhase/antsdr-pynq)).

*An antSDR E200 (Zynq-7020 + AD9361) running **PYNQ Linux** with **CAN0** (CSP over CAN to the OBC on header J30), **Ethernet** and the **AD9361** (IIO + `iiod` for GNU Radio), all up automatically at power on. Built on **Windows + WSL2 Ubuntu 18.04**.*

| J30 | Sinyal / Signal | SN65HVD230 |
| --- | --- | --- |
| 1 | 3,3 V | 3V3 |
| 2 | GND | GND |
| 3 | `can0_tx` (V5) | CTX / D |
| 4 | `can0_rx` (U7) | CRX / R |

File HDL turunan dari repo HDL Analog Devices dan mengikuti lisensi aslinya (GPL-2.0 / ADI BSD). *HDL files are derived from the Analog Devices HDL repository and keep its license.*

---

<a name="bahasa-indonesia"></a>
## Bahasa Indonesia: Tutorial antSDR E200 TT&C Modem (Hasil Praktik)

### Pendahuluan

Tutorial ini membuat antSDR E200 menjalankan PYNQ Linux dengan CAN0 di header J30, Ethernet, dan AD9361 yang siap begitu dinyalakan. Semua build dikerjakan di laptop Windows lewat WSL2 Ubuntu 18.04, persis seperti yang sudah dipraktikkan dan diuji.

**Hasil akhir yang sudah terbukti:**

| Fungsi | Status setelah power on |
| --- | --- |
| PYNQ Linux (Ubuntu 22.04, kernel 5.15.19) + Jupyter | Boot otomatis, Jupyter di `http://192.168.2.99:9090` |
| Ethernet (PL, GEM0 + GMII-to-RGMII) | 1 Gbps langsung ke laptop, IP tetap 192.168.2.99 |
| CAN0 (PS Zynq via EMIO ke J30 pin 3/4) | UP otomatis, 500 kbps, driver `xilinx_can` |
| AD9361 (driver IIO ADI) + `iiod` | Siap dipakai GNU Radio dari laptop |

**Yang dibutuhkan:**

- Laptop Windows 10/11 dengan RAM 16 GB atau lebih dan ruang kosong sekitar 250 GB di satu drive (contoh di sini drive D).
- antSDR E200, adaptor power, kabel LAN, kabel USB-C untuk UART (konsol serial).
- SD card **16–32 GB**. Kartu SDXC 256 GB terbukti gagal dibaca Zynq (I/O error).
- Modul transceiver CAN 3,3 V **SN65HVD230** dan header 2,0 mm 1×10 untuk J30.
- Akun AMD/Xilinx untuk mengunduh installer.

**Gambaran alur:** HDL di Vivado (CAN0 lewat EMIO) → XSA dan bitstream → PetaLinux dan PYNQ sdbuild → image SD card → BOOT.BIN berisi bitstream → boot → konfigurasi jaringan, overlay AD9361, dan service autostart di board.

Perintah yang diawali `PS>` dijalankan di PowerShell Windows. Perintah lain dijalankan di dalam WSL Ubuntu (prompt `asus@LAPTOP...$`), kecuali disebut **di antSDR**.

### Bagian A: Siapkan Windows dan WSL2 Ubuntu 18.04

Vivado 2021.1 dan PetaLinux 2022.1 resmi mendukung Ubuntu 18.04, jadi kita memakai distro itu di WSL2 dan menaruh seluruh disk virtualnya di drive D.

1. **Aktifkan dan perbarui WSL** (PowerShell sebagai Administrator):

   ```powershell
   wsl --install --no-distribution
   wsl --update
   wsl --set-default-version 2
   ```
2. **Unduh Ubuntu 18.04 secara manual.** Di Microsoft Store versi ini sering "tidak tersedia di wilayah Anda". Unduh paket appx dari `https://aka.ms/wsl-ubuntu-1804`, ubah ekstensinya menjadi `.zip`, lalu ekstrak. Ambil file `install.tar.gz` dari dalamnya.
3. **Import ke drive D:**

   ```powershell
   mkdir D:\WSL\Ubuntu1804
   wsl --import Ubuntu-18.04 D:\WSL\Ubuntu1804 D:\antsdr_download\install.tar.gz --version 2
   wsl -d Ubuntu-18.04
   ```
4. **Buat user biasa** (contoh `asus`) dan jadikan default. Di dalam WSL (masih sebagai root):

   ```bash
   adduser asus
   usermod -aG sudo asus
   printf '[user]\ndefault=asus\n' > /etc/wsl.conf
   exit
   ```

   Lalu `PS> wsl --terminate Ubuntu-18.04` dan masuk lagi dengan `wsl`.
5. **Atur RAM, CPU, dan swap WSL.** Buat file `C:\Users\<nama>\.wslconfig` (lewat PowerShell, bukan Notepad dari WSL):

   ```ini
   [wsl2]
   memory=10GB
   processors=12
   swap=16GB
   ```

   Jalankan `PS> wsl --shutdown` supaya pengaturan berlaku. Sesuaikan angka dengan laptop Anda; build PetaLinux butuh RAM besar.
6. **Pasang paket dasar** dan jadikan `/bin/sh` mengarah ke bash (wajib untuk PetaLinux):

   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y build-essential git wget unzip xz-utils liblz4-tool \
     python3 python3-pip libncurses5 libtinfo5 locales x11-apps
   sudo dpkg-reconfigure dash      # pilih "No"
   ls -l /bin/sh                   # harus -> bash
   ```

   Di Ubuntu 18.04 paketnya bernama `liblz4-tool`, bukan `lz4`.
7. **Cek GUI WSLg** dengan `xeyes`. Kalau jendela mata muncul, installer grafis Xilinx bisa dibuka.

**Penting:** kerjakan semua build di folder Linux (`~/...`), bukan di `/mnt/c` atau `/mnt/d`. Akses ke drive Windows dari WSL jauh lebih lambat.

### Bagian B: Instal Vivado/Vitis 2021.1 dan PetaLinux 2022.1

Versi harus persis: repo HDL ADI meminta Vivado **2021.1**, dan antsdr-pynq memakai PetaLinux **2022.1**.

#### B1. Unduh installer

| File | Ukuran | Catatan |
| --- | --- | --- |
| `Xilinx_Unified_2021.1_0610_2318.tar.gz` (SFD, semua OS) | ± 52 GB | Web installer 2021.1 sudah "obsolete", pakai SFD |
| `petalinux-v2022.1-04191534-installer.run` | ± 2,6 GB | Dari halaman arsip Embedded Design Tools 2022.1 |

Simpan di `D:\antsdr_download\`, lalu cocokkan MD5 dengan angka di halaman unduhan:

```bash
cd /mnt/d/antsdr_download
md5sum Xilinx_Unified_2021.1_0610_2318.tar.gz
tar -xzf Xilinx_Unified_2021.1_0610_2318.tar.gz
```

#### B2. Instal Vitis 2021.1 (hanya Zynq-7000)

```bash
sudo mkdir -p /opt/Xilinx && sudo chown -R $USER:$USER /opt/Xilinx
cd /mnt/d/antsdr_download/Xilinx_Unified_2021.1_0610_2318
./xsetup
```

Di installer (jendela WSLg):

1. Saat ditawari versi lebih baru, pilih **Continue** dengan 2021.1.
2. Product: **Vitis** (sudah termasuk Vivado dan Vitis HLS).
3. Di layar Customize, **kosongkan**: Vitis Model Composer, DocNav, *Install devices for Alveo...*, 7 Series, UltraScale, UltraScale+, Versal ACAP, Engineering Sample. Di bawah **SoCs**, sisakan hanya **Zynq-7000** (kosongkan Zynq UltraScale+ MPSoC dan RFSoC). Disk Space Required turun dari 131 GB ke ± 75 GB (pemakaian akhir ± 57 GB).
4. Centang tiga lisensi sendiri, lokasi **`/opt/Xilinx`**, kosongkan dua opsi shortcut.
5. Angka "Disk Space Available 999 GB" adalah kapasitas maksimum disk virtual WSL, bukan sisa ruang drive D. Pastikan drive D masih punya ± 90 GB kosong.
6. Install butuh 1–3 jam. Matikan sleep saat dicolok charger: `PS> powercfg /change standby-timeout-ac 0`.
7. Kalau muncul **Xilinx Information Center** yang menawarkan update 2021.1.1 atau versi baru, klik **Dismiss**.

Verifikasi:

```bash
source /opt/Xilinx/Vivado/2021.1/settings64.sh
vivado -version     # Vivado v2021.1 (64-bit)
vitis -version      # Vitis v2021.1 (64-bit)
```

#### B3. Instal PetaLinux 2022.1

Buka terminal WSL baru (tanpa environment Vivado):

```bash
sudo apt install -y gawk xterm autoconf libtool texinfo zlib1g-dev gcc-multilib \
  build-essential libncurses5-dev libtinfo5 net-tools tftpd-hpa python3 python3-pip \
  python3-pexpect python3-git python3-jinja2 xz-utils debianutils iputils-ping \
  libegl1-mesa libsdl1.2-dev pylint3 cpio diffstat chrpath socat unzip locales
sudo locale-gen en_US.UTF-8
sudo dpkg --add-architecture i386 && sudo apt update && sudo apt install -y zlib1g:i386
sudo mkdir -p /opt/pkg/petalinux/2022.1 && sudo chown -R $USER:$USER /opt/pkg
mkdir -p ~/installers && cp /mnt/d/antsdr_download/petalinux-v2022.1-04191534-installer.run ~/installers/
cd ~/installers && chmod +x petalinux-v2022.1-04191534-installer.run
./petalinux-v2022.1-04191534-installer.run -d /opt/pkg/petalinux/2022.1   # tanpa sudo
```

Di teks lisensi tekan **q**, lalu ketik **y** bila setuju. Tanpa `zlib1g:i386`, installer berhenti dengan error *missing development libraries*.

Cek: `source /opt/pkg/petalinux/2022.1/settings.sh && echo $PETALINUX`. Peringatan *This is not a supported OS* (Ubuntu 18.04.6) dan *No tftp server found* aman diabaikan.

### Bagian C: Siapkan repo antsdr-pynq dan host PYNQ

Kita butuh dua repo di `~/antsdr`, rootfs PYNQ prebuilt, lalu menyiapkan host dengan `setup_host.sh`.

#### C1. Ambil repo

```bash
mkdir -p ~/antsdr && cd ~/antsdr
git clone --recursive https://github.com/MicroPhase/antsdr-pynq.git
```

Repo HDL antSDR (fork HDL ADI yang berisi `projects/antsdre200`) diletakkan di `~/antsdr/hdl`. Pastikan file berikut ada:

```bash
ls ~/antsdr/hdl/projects/antsdre200/      # Makefile system_bd.tcl system_top.v system.xdc ...
ls ~/antsdr/antsdr-pynq/boards/e200/      # e200.spec base/ petalinux_bsp/
grep -n "required_vivado_version" ~/antsdr/hdl/projects/scripts/adi_project_xilinx.tcl   # "2021.1"
```

#### C2. Rootfs dan sdist PYNQ 3.0.1 (prebuilt)

Unduh `pynq_rootfs.arm.tar.gz` (± 1,9 GB) dan `pynq_sdist.tar.gz` (± 61 MB) versi 3.0.1 dari halaman unduhan PYNQ, lalu taruh di:

```bash
mkdir -p ~/antsdr/antsdr-pynq/PYNQ/sdbuild/prebuilt
# salin kedua file ke folder itu
ls -lh ~/antsdr/antsdr-pynq/PYNQ/sdbuild/prebuilt/
```

Makefile otomatis memakai keduanya (`PYNQ_ROOTFS` dan `PYNQ_SDIST`), sehingga rootfs Ubuntu tidak perlu dibangun dari nol.

#### C3. Tambal pengecekan versi Vivado di Makefile PYNQ

Makefile PYNQ meminta Vivado/Vitis dengan versi sama seperti kernel (2022.1). Kita pakai 2021.1, jadi pengecekannya diganti:

```bash
cd ~/antsdr/antsdr-pynq/PYNQ/sdbuild
cp Makefile Makefile.asli
sed -i 's/vivado -version | fgrep ${KERNEL_VERSION}/vivado -version | fgrep 2021.1/; s/vitis -version | fgrep ${KERNEL_VERSION}/vitis -version | fgrep 2021.1/' Makefile
diff Makefile.asli Makefile      # 2 baris berubah
```

#### C4. Jalankan setup_host.sh (dengan perbaikan URL QEMU)

Script ini memasang crosstool-ng, meng-compile QEMU 5.2.0, dan paket Python. URL lama `wiki.qemu-project.org` gagal karena sertifikat HTTPS-nya kedaluwarsa, jadi arahkan ke `download.qemu.org` dulu:

```bash
cd ~/antsdr/antsdr-pynq/PYNQ/sdbuild
cp scripts/setup_host.sh scripts/setup_host.sh.asli
sed -i 's#http://wiki.qemu-project.org/download/#https://download.qemu.org/#' scripts/setup_host.sh
./scripts/setup_host.sh 2>&1 | tee ~/setup_host.log
```

Setelah selesai (± 30–60 menit), keluar lalu masuk lagi ke WSL supaya PATH baru aktif, kemudian cek:

```bash
which qemu-arm-static ct-ng      # /opt/qemu/bin/... dan /opt/crosstool-ng/bin/...
```

### Bagian D: Tambah CAN0 via EMIO di HDL dan build bitstream

Controller CAN0 ada di PS (ARM) Zynq. Kita aktifkan lewat EMIO, yaitu jalur yang melewati FPGA, lalu menyambungkannya ke pin **V5** (TX) dan **U7** (RX) yang keluar di header J30.

#### D1. Pin dan tegangan

| Sinyal | Pin FPGA | Net skematik | Header J30 |
| --- | --- | --- | --- |
| `can0_tx` | V5 | GPIO_00 | pin 3 |
| `can0_rx` | U7 | GPIO_01 | pin 4 |
| 3,3 V | – | VCC_3V3 | pin 1 |
| GND | – | GND | pin 2 (cek dengan multimeter) |

Di skematik (halaman 4), **VCCO bank 13 = 3,3 V**. XDC bawaan menulis empat pin bank 13 (V6, W6, V10, V11) sebagai LVCMOS18. Kalau CAN dipasang LVCMOS33 di bank yang sama, Vivado menolak karena standar tegangan bentrok. Jadi keempat pin itu ikut diubah ke **LVCMOS33**, sesuai kondisi fisik board. Dengan bank 3,3 V, SN65HVD230 bisa langsung disambung tanpa level shifter.

#### D2. Jalankan script add_can0.sh

Script [`hdl/add_can0.sh`](hdl/add_can0.sh) mengubah tiga file dan menyimpan aslinya sebagai `*.asli`:

- `system_bd.tcl`: `PCW_CAN0_PERIPHERAL_ENABLE 1`, `PCW_CAN0_CAN0_IO EMIO`, clock CAN 100 MHz, port `can0_tx/can0_rx` ke `CAN0_PHY_TX/RX`.
- `system_top.v`: port top-level `can0_tx` (output) dan `can0_rx` (input), disambung ke `system_wrapper`.
- `system.xdc`: bank 13 jadi LVCMOS33, plus `can0_tx` di V5 dan `can0_rx` di U7 (pull-up).

```bash
bash /mnt/d/antsdr_download/add_can0.sh      # tampilkan ringkasan diff
```

#### D3. Build

```bash
cd ~/antsdr/hdl/projects/antsdre200
source /opt/Xilinx/Vivado/2021.1/settings64.sh
make 2>&1 | tee ~/hdl_build.log      # ± 40 menit
```

Semua library dan project harus berakhir **OK**. Lalu cek tiga hal:

```bash
ls -lh antsdre200.sdk/                                   # system_top.xsa
grep -E "WNS|TNS" antsdre200_vivado.log | tail -2        # WNS dan WHS positif
mkdir -p /tmp/xsa && cd /tmp/xsa && unzip -o -q ~/antsdr/hdl/projects/antsdre200/antsdre200.sdk/system_top.xsa
grep -o 'PCW_CAN0_[A-Z_]*" VALUE="[A-Z0-9]*"' system.hwh | sort -u   # ENABLE=1, IO=EMIO
```

Hasil praktik: WNS = +0,248 ns, WHS = +0,032 ns (timing lolos), dan di dalam XSA ada `system_top.bit` dan `system.hwh`.

### Bagian E: Pasang hardware baru ke board e200 dan build image PYNQ

Tiga file hardware diganti, satu konfigurasi kernel CAN ditambahkan, lalu image dibangun dengan `make`.

#### E1. XSA, bitstream, dan hwh

```bash
cd ~/antsdr/antsdr-pynq/boards/e200
cp -n base/base.bit base/base.bit.asli
cp -n petalinux_bsp/hardware_project/system.xsa petalinux_bsp/hardware_project/system.xsa.asli
cp ~/antsdr/hdl/projects/antsdre200/antsdre200.sdk/system_top.xsa petalinux_bsp/hardware_project/system.xsa
cp /tmp/xsa/system_top.bit base/base.bit
cp /tmp/xsa/system.hwh base/base.hwh
```

`base.bit` baru (± 2,4 MB) lebih kecil dari yang lama karena bitstream ADI dikompresi; Zynq tetap memuatnya normal. `base.hwh` dibutuhkan PYNQ untuk `Overlay("base.bit")`.

#### E2. Paket overlay Python (wajib bila ada base.hwh)

Begitu `base.hwh` ada, script build menganggap `base/` overlay lengkap dan mencari file `*.py`. Tanpa itu build gagal di akhir dengan `cannot stat '.../base/*.py'`.

```bash
cd ~/antsdr/antsdr-pynq/boards/e200/base
cat > base.py <<'EOF'
import pynq

__all__ = ['BaseOverlay']


class BaseOverlay(pynq.Overlay):
    """Overlay dasar antSDR E200 (AD9361 + Ethernet PL + CAN0 via EMIO)."""

    def __init__(self, bitfile_name='base.bit', **kwargs):
        super().__init__(bitfile_name, **kwargs)
EOF
echo "from .base import BaseOverlay" > __init__.py
```

#### E3. Driver CAN di kernel

BSP bawaan belum menyertakan SocketCAN dan driver `xilinx_can`. Tanpa ini, `can0` tidak pernah muncul di Linux.

```bash
cd ~/antsdr/antsdr-pynq/boards/e200/petalinux_bsp/meta-user/recipes-kernel/linux
cat > linux-xlnx/can.cfg <<'EOF'
CONFIG_CAN=y
CONFIG_CAN_RAW=y
CONFIG_CAN_BCM=y
CONFIG_CAN_GW=y
CONFIG_CAN_DEV=y
CONFIG_CAN_CALC_BITTIMING=y
CONFIG_CAN_XILINXCAN=y
EOF
cp -n linux-xlnx_%.bbappend linux-xlnx_%.bbappend.asli
echo 'SRC_URI += "file://can.cfg"' >> linux-xlnx_%.bbappend
```

#### E4. Build image

Folder board e200 tidak ada di `PYNQ/boards/`, jadi harus ditunjuk dengan `BOARDDIR`. Gunakan terminal WSL baru:

```bash
source /opt/pkg/petalinux/2022.1/settings.sh
source /opt/Xilinx/Vitis/2021.1/settings64.sh      # sekaligus memuat Vivado
cd ~/antsdr/antsdr-pynq/PYNQ/sdbuild
sudo -v
make BOARDDIR=$HOME/antsdr/antsdr-pynq/boards BOARDS=e200 2>&1 | tee ~/pynq_build.log
```

Build praktik selesai sekitar 1,5 jam. Hasilnya `output/e200-3.0.1.img` (7,3 GB). Pastikan driver CAN dan device tree-nya ikut:

```bash
cd ~/antsdr/antsdr-pynq/PYNQ/sdbuild/build/e200/petalinux_project
grep -E "CONFIG_CAN=|CONFIG_CAN_XILINXCAN" build/tmp/work/*/linux-xlnx/*/linux-*-build/.config
grep -n -A2 "&can0" components/plnx_workspace/device-tree/device-tree/pcw.dtsi   # status = "okay"
```

Status `disabled` di `zynq-7000.dtsi` itu default; `pcw.dtsi` (dari XSA) yang mengubahnya menjadi `okay`.

Jangan membuka Vivado GUI saat build berjalan. GUI memakan 2–3 GB RAM, dan build PetaLinux bisa gagal kehabisan memori.

### Bagian F: Buat BOOT.BIN berisi bitstream

BOOT.BIN hasil build PYNQ (± 1,1 MB) hanya berisi FSBL, U-Boot, dan DTB, **tanpa bitstream**. Di E200, Ethernet dan pin CAN0 sama-sama lewat FPGA, jadi bitstream wajib termuat sejak boot. Folder `e200_boot_gen` membuat BOOT.BIN yang lengkap.

File bawaan di `e200_boot_gen` adalah versi lama tanpa CAN0, jadi keempatnya diganti dengan hasil build kita:

```bash
source /opt/Xilinx/Vitis/2021.1/settings64.sh      # untuk bootgen
cd ~/antsdr/antsdr-pynq/e200_boot_gen
mkdir -p asli && cp -n system.dtb system_top.bit u-boot.elf zynq_fsbl.elf asli/
IMG=~/antsdr/antsdr-pynq/PYNQ/sdbuild/build/e200/petalinux_project/images/linux
cp $IMG/zynq_fsbl.elf $IMG/u-boot.elf $IMG/system.dtb .
cp ~/antsdr/antsdr-pynq/boards/e200/base/base.bit system_top.bit
rm -rf build_sdimg && make sdimg
ls -lh build_sdimg/BOOT.bin                        # ± 3,4 MB
```

Salin hasil ke Windows supaya mudah ditulis ke SD card:

```bash
cp build_sdimg/BOOT.bin /mnt/d/antsdr_download/BOOT.BIN
cp ~/antsdr/antsdr-pynq/PYNQ/sdbuild/output/e200-3.0.1.img /mnt/d/antsdr_download/
```

Setelah itu WSL boleh dimatikan supaya RAM lega: `PS> wsl --shutdown`. Perintah ini dijalankan di PowerShell, bukan di dalam WSL.

### Bagian G: Tulis SD card dan boot pertama

Gunakan kartu **16–32 GB**. Kartu 256 GB terbukti membuat Linux gagal membaca partisi root (`I/O error, dev mmcblk0`).

#### G1. Tulis image

1. Kalau isi kartu masih dibutuhkan, backup dulu dengan Rufus: pilih kartu di **Device**, klik ikon disket di sebelahnya, simpan sebagai `.vhd`. balenaEtcher tidak bisa backup ke file.
2. Buka **balenaEtcher** (etcher.balena.io): **Flash from file** → `D:\antsdr_download\e200-3.0.1.img` (bukan BOOT.BIN), **Select target** → SD card, **Flash!** Tunggu sampai *Validating* selesai. Rufus mode DD juga bisa, tapi tidak memverifikasi hasil tulis.
3. Cabut dan colokkan lagi kartu. Muncul drive **BOOT** berisi `BOOT.BIN`, `boot.scr`, `image.ub`. Kalau Windows menawarkan format partisi lain, pilih **Cancel**.
4. **Timpa `BOOT.BIN`** di drive BOOT dengan `D:\antsdr_download\BOOT.BIN` (3,4 MB). Pastikan ukurannya 3,4 MB, bukan 1,1 MB. Lalu **Eject**.

#### G2. Boot pertama lewat UART

1. Pasang kartu, switch boot ke **SD**, sambungkan USB-C UART ke laptop.
2. Cari nomor COM di **Device Manager → Ports (COM & LPT)** (praktik: COM8).
3. **PuTTY**: Connection type **Serial**, Serial line `COM8`, Speed **115200** (bukan 11500), lalu **Open**.
4. Nyalakan antSDR. Log U-Boot dan kernel berjalan, lalu muncul `pynq login: xilinx (automatic login)`. User/password: `xilinx` / `xilinx`.
5. Cek:

   ```bash
   ip addr show eth0
   ip -details link show can0          # can0 muncul, state STOPPED (normal)
   dmesg | grep -i -E "xilinx_can|macb"
   ```

Di PuTTY, teks yang diblok otomatis tersalin dan klik kanan langsung menempel. Jangan tekan Ctrl+C untuk copy; itu menghentikan program. Pesan `TDC Offset value not in range` dari `xilinx_can` hanya relevan untuk CAN-FD dan aman diabaikan.

Matikan antSDR selalu dengan `sudo poweroff`, tunggu ± 10 detik, baru cabut power. Mencabut USB UART saja aman selama board diberi daya dari adaptor.

### Bagian H: Jaringan stabil di 192.168.2.99 dengan systemd-networkd

Konfigurasi bawaan PYNQ (ifupdown: `eth0` DHCP + `eth0:1` = 192.168.2.99) tidak stabil kalau antSDR disambung langsung ke laptop. Tanpa router, `dhclient` terus mencoba ulang, memakai lagi lease lama (misalnya 192.168.0.143), dan setiap kali menghapus alamat 192.168.2.99. Solusinya, `eth0` diserahkan ke systemd-networkd, yang menjalankan DHCP dan alamat tetap bersamaan.

#### H1. Sisi laptop

Tambahkan IP 192.168.2.1 di adapter Ethernet laptop, tanpa menghapus IP lain (PowerShell **Administrator**):

```powershell
netsh interface ipv4 add address "Ethernet" 192.168.2.1 255.255.255.0
```

#### H2. Sisi antSDR (lewat PuTTY, sekali saja)

```bash
sudo tee /etc/systemd/network/10-eth0.network >/dev/null <<'EOF'
[Match]
Name=eth0

[Network]
DHCP=ipv4
Address=192.168.2.99/24
EOF
sudo mv /etc/network/interfaces.d/eth0 /root/eth0.ifupdown.bak
sudo pkill -f "dhclient.*eth0"
sudo ip addr flush dev eth0
sudo rm -f /var/lib/dhcp/dhclient*.eth0.leases
sudo systemctl enable systemd-networkd
sudo systemctl disable systemd-networkd-wait-online.service
sudo systemctl restart systemd-networkd
sudo networkctl reconfigure eth0
ip -4 addr show eth0          # inet 192.168.2.99/24
```

`systemd-networkd-wait-online` dimatikan **setelah** enable networkd, karena enable ikut menyalakannya lagi; tanpa itu boot tertahan ± 2 menit saat tidak ada router.

Hasil:

| Kabel | Alamat antSDR |
| --- | --- |
| Langsung ke laptop (1 Gbps) | 192.168.2.99 |
| Ke router | IP dari DHCP router **dan** 192.168.2.99 |

Uji: `PS> ping 192.168.2.99`, lalu buka `http://192.168.2.99:9090` (password Jupyter `xilinx`). Nama `http://pynq:9090` tidak dikenali tanpa DNS router.

Lewat router port 100 Mbps, aliran IQ 2,4 MS/s (± 77 Mbps) membuat audio GNU Radio putus-putus. Sambungan langsung 1 Gbps ke laptop lebih stabil.

### Bagian I: Aktifkan AD9361 lewat device tree overlay

Di BSP antsdr-pynq, semua node AD9361 di `system-user.dtsi` sengaja di-comment, dan opsi FPGA Manager (`FPGA_MANAGER_e200 := 1`) memisahkan perangkat PL dari device tree utama. Akibatnya IIO hanya menemukan `xadc`. Kita tambahkan node AD9361 saat Linux berjalan dengan overlay `.dtbo`, **tanpa** memprogram ulang FPGA, jadi Ethernet tetap aman.

#### I1. Isi overlay `ad9361_e200.dts`

Overlay diambil dari blok yang di-comment di BSP, dengan perbaikan:

| Bagian | Nilai |
| --- | --- |
| Clock referensi (baru) | `fixed-clock` 40 MHz, `ad9361_ext_refclk` |
| `adi,ad9361` di `&spi0` | reg 0, LVDS, 2R2T, FDD, digital tune penuh |
| GPIO kontrol | en_agc 66, sync 67, reset 68, enable **101**, txnrx **102** (sesuai `gpio_o[47]`/`[48]` di `system_top.v`) |
| DMA RX / TX | `0x7C400000` irq 57 / `0x7C420000` irq 56, clock FCLK0 |
| Core ADC / DAC | `0x79020000` / `0x79024000` |
| sysid | `0x45000000` |

#### I2. Muat overlay dan pasang iiod

Upload `ad9361_e200.dts` dan `apply_ad9361.sh` lewat tombol **Upload** di Jupyter (folder `/home/xilinx/jupyter_notebooks`). Di terminal Jupyter (sudah root):

```bash
bind 'set enable-bracketed-paste off'     # ketik manual dulu, mencegah sisa ^[[200~ saat paste
apt update && apt install -y iiod libiio-utils
cd /home/xilinx/jupyter_notebooks
bash apply_ad9361.sh
systemctl restart iiod                    # iiod harus dimulai SETELAH overlay
```

Hasil yang benar:

```
Status overlay: applied
ad9361 spi1.0: ad9361_probe : AD936x Rev 0 successfully initialized
cf_axi_adc 79020000.cf-ad9361-lpc: ... probed ADC AD9361 as MASTER
iio:device1: ad9361-phy
iio:device2: cf-ad9361-lpc (buffer capable)
iio:device3: cf-ad9361-dds-core-lpc (buffer capable)
```

Peringatan `OF: overlay: WARNING: memory leak will occur if overlay removed` normal.

Cek dari laptop (Radioconda Prompt):

```
iio_info -u ip:192.168.2.99 | findstr "devices iio:device"
```

Jangan memanggil `Overlay("base.bit")` dengan download di Jupyter. Memprogram ulang FPGA me-reset Ethernet PL dan memutus Jupyter. Untuk membaca isi desain, pakai `BaseOverlay("base.bit", download=False)`.

### Bagian J: Autostart CAN0 + AD9361 dan uji reboot

Overlay AD9361 dan pengaturan `can0` hilang setiap restart. Script [`setup_autostart.sh`](board/ad9361_overlay/setup_autostart.sh) memasang dua service sekali jalan:

- **`ad9361-overlay.service`**: memuat `/lib/firmware/ad9361_e200.dtbo` saat boot, dan `iiod` diatur baru mulai setelahnya (drop-in `iiod.service.d/after-ad9361.conf`).
- **`can0.service`**: `ip link set can0 up type can bitrate 500000 loopback off restart-ms 100` begitu driver `can0` siap.

Ubah `CAN_BITRATE=500000` di awal script kalau OBC memakai kecepatan lain. Upload script ke Jupyter, lalu di terminal Jupyter:

```bash
cd /home/xilinx/jupyter_notebooks
bash setup_autostart.sh
```

Uji dengan reboot (Jupyter akan terputus sebentar):

```bash
reboot
```

Setelah ± 1–2 menit, buka lagi `http://192.168.2.99:9090`, buka terminal, lalu:

```bash
systemctl is-active ad9361-overlay can0 iiod      # active active active
ip -4 addr show eth0                               # 192.168.2.99/24
ip -details link show can0 | grep -E "state|bitrate"
iio_info -u local: | grep "iio:device"
```

Hasil praktik setelah reboot: ketiga service **active**, `eth0` di 192.168.2.99, `can0` **UP, ERROR-ACTIVE, bitrate 499999** (500 kbps; selisih 1 bit/s karena clock CAN 99,999999 MHz), dan `ad9361-phy` + `cf-ad9361-lpc` + `cf-ad9361-dds-core-lpc` tersedia. Artinya antSDR siap begitu dinyalakan.

### Bagian K: Tes CAN0 dan wiring SN65HVD230

Uji controller dulu dengan loopback internal (tanpa kabel), baru sambungkan transceiver ke OBC.

#### K1. Cek konfigurasi PS dari Jupyter

```python
from pynq.overlays.base import BaseOverlay
ol = BaseOverlay("base.bit", download=False)
print(list(ol.ip_dict))   # axi_gpreg, axi_iic_main, axi_sysid_0, axi_ad9361, ..._adc_dma, ..._dac_dma, sys_ps7
ps = ol.ip_dict["sys_ps7"]["parameters"]
print(ps.get("PCW_CAN0_PERIPHERAL_ENABLE"), ps.get("PCW_CAN0_CAN0_IO"), ps.get("PCW_CAN_PERIPHERAL_FREQMHZ"))   # 1 EMIO 100
```

#### K2. Loopback internal

Di terminal Jupyter:

```bash
ip link set can0 down
ip link set can0 type can bitrate 500000 loopback on
ip link set can0 up
```

Di notebook (hanya library bawaan Python, cara yang sama dengan `csp1_can.py`):

```python
import socket, struct
rx = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW); rx.bind(("can0",)); rx.settimeout(1.0)
tx = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW); tx.bind(("can0",))
data = bytes([0xDE, 0xAD, 0xBE, 0xEF])
tx.send(struct.pack("=IB3x8s", 0x123, len(data), data.ljust(8, b"\0")))
can_id, dlc, payload = struct.unpack("=IB3x8s", rx.recv(16))
print(f"ID=0x{can_id & 0x1FFFFFFF:X} DLC={dlc} DATA={payload[:dlc].hex(' ').upper()}")
```

Hasil praktik: `ID=0x123 DLC=4 DATA=DE AD BE EF`. Kembalikan ke mode normal dengan `systemctl restart can0`.

#### K3. Sambungkan SN65HVD230

Header J30 berjarak pin **2,0 mm** (header 2,54 mm tidak masuk). Matikan antSDR sebelum memasang kabel.

| J30 antSDR | Modul SN65HVD230 |
| --- | --- |
| pin 1 (3,3 V) | 3V3 |
| pin 2 (GND) | GND |
| pin 3 (`can0_tx`, V5) | CTX / D |
| pin 4 (`can0_rx`, U7) | CRX / R |

CANH dan CANL modul disambung ke CANH dan CANL OBC. Bus CAN butuh resistor 120 Ω di kedua ujung; banyak modul sudah membawanya. Bitrate OBC harus sama (500 kbps). Pantau lalu lintas bus dengan:

```bash
apt install -y can-utils
candump can0
```

### Bagian L: Tes receiver FM dengan GNU Radio

GNU Radio berjalan di laptop (Radioconda, GNU Radio 3.10.12) dan mengakses AD9361 lewat `iiod` di antSDR. Blok **UHD: USRP Source** tidak dipakai lagi; gantinya **FMComms2/3/4 Source** (gr-iio).

Flowgraph: `FMComms2/3/4 Source → Low Pass Filter → WBFM Receive → Multiply Const (volume) → Audio Sink`, dengan cabang ke **QT GUI Frequency Sink**. Generate Options: **QT GUI**.

| Blok | Pengaturan |
| --- | --- |
| Variabel `samp_rate` | 1 200 000 |
| QT GUI Range `freq` | 88e6–108e6, langkah 100e3 |
| QT GUI Range `vol` | 0–2, awal 0,5 |
| FMComms2/3/4 Source | URI `'ip:192.168.2.99'`, LO `int(freq)`, Sample Rate `int(samp_rate)`, RF BW 1 000 000, Buffer 131 072, RX1 saja, Gain `slow_attack`, Port `A_BALANCED`, Filter `Auto` |
| Low Pass Filter | Decimation 5, cutoff 100e3, transition 20e3 (1,2 MS/s → 240 kS/s) |
| WBFM Receive | Quadrature 240e3, Audio Decimation 5 (→ 48 kHz) |
| Audio Sink | 48 000, OK to Block = **No** |
| QT GUI Frequency Sink | Center `freq`, Bandwidth `samp_rate` |

File siap pakai: `D:\antsdr_download\fm_rx_antsdr.grc`. Buka di GNU Radio Companion, klik **Execute** (F6), lalu geser slider frekuensi ke stasiun terdekat.

Tips dari praktik:

- **Audio putus-putus** lewat router 100 Mbps. Turunkan sample rate ke 1,2 MS/s, perbesar buffer, set *OK to Block* = No, atau sambung langsung ke laptop.
- **`Unable to create context`**: URI tidak cocok dengan sambungan (0.143 vs 192.168.2.99) atau antSDR belum siap. Cek `ping` dan `iio_info -u ip:...`.
- Saat GRC masih membuka file, ia bisa menimpa file yang diubah dari luar. Tutup file tanpa menyimpan sebelum membuka versi baru.
- AD9361 hanya bisa dipakai satu program sekaligus. Matikan bridge GMSK/CSP saat GNU Radio jalan, dan sebaliknya. CAN0 tidak terpengaruh.

### Bagian M: Image final yang langsung siap di kartu mana pun

**Status: belum dipraktikkan.** Bagian H–J dipasang di SD card yang sedang dipakai, jadi kartu baru dari `e200-3.0.1.img` harus disetel ulang. Ada dua cara supaya kartu baru langsung siap saat power on.

#### M1. Cara cepat: golden image dari kartu yang sudah jalan

Cara ini menyalin kartu 16 GB yang sudah teruji apa adanya, jadi tidak perlu build ulang.

1. Matikan antSDR dengan `sudo poweroff`, tunggu ± 10 detik, cabut kartu, lalu colokkan ke laptop.
2. **Rufus**: pilih kartu di **Device**, klik ikon disket di sebelahnya, simpan sebagai `D:\antsdr_download\antsdr_e200_final.vhd`. Alternatif: **Win32 Disk Imager**, isi nama file `.img`, klik **Read**.
3. Untuk kartu baru, tulis file itu dengan Rufus (pilih `.vhd` di Boot selection) atau balenaEtcher.

Kartu tujuan harus **sama besar atau lebih besar** dari 16 GB. Kartu 16 GB merek lain kadang sedikit lebih kecil, jadi lebih aman pakai 32 GB.

#### M2. Cara bersih: build ulang dengan semua perbaikan tertanam

Script [`image_final/siapkan_image_final.sh`](image_final/siapkan_image_final.sh) menyiapkan tiga perubahan (file asli disimpan sebagai `*.asli`):

| Perubahan | File | Efek |
| --- | --- | --- |
| Node AD9361 + DMA + ADC/DAC dimasukkan ke device tree utama (dari blok yang di-comment, dengan perbaikan Bagian I1) | `petalinux_bsp/meta-user/recipes-bsp/device-tree/files/system-user.dtsi` | AD9361 aktif saat boot tanpa overlay |
| Paket rootfs baru: `iiod`, `libiio-utils`, `can-utils`, `device-tree-compiler`, `10-eth0.network`, `can0.service` | `PYNQ/sdbuild/packages/antsdr_e200_autostart/qemu.sh` | Jaringan 192.168.2.99 dan CAN0 500 kbps otomatis |
| Paket didaftarkan | `boards/e200/e200.spec` (`STAGE4_PACKAGES_e200`) | Paket ikut dipasang saat build |

Langkah di WSL:

```bash
bash /mnt/d/antsdr_download/image_final/siapkan_image_final.sh

# hapus hasil build lama supaya device tree dan rootfs dibangun ulang
cd ~/antsdr/antsdr-pynq/PYNQ/sdbuild
sudo rm -rf build/e200 build/e200.tar.gz output/e200-3.0.1.img output/boot/e200

source /opt/pkg/petalinux/2022.1/settings.sh
source /opt/Xilinx/Vitis/2021.1/settings64.sh
sudo -v
make BOARDDIR=$HOME/antsdr/antsdr-pynq/boards BOARDS=e200 2>&1 | tee ~/pynq_build_final.log
```

Setelah build selesai (perkiraan 1,5–2 jam), buat lagi BOOT.BIN berisi bitstream seperti Bagian F, karena `system.dtb` ikut berubah. Lalu tulis image baru ke kartu dan timpa BOOT.BIN seperti Bagian G.

Cek setelah boot pertama, **tanpa** menjalankan script apa pun:

```bash
ip -4 addr show eth0                                  # 192.168.2.99/24
ip -details link show can0 | grep -E "state|bitrate"  # UP, 500000
systemctl is-active can0 iiod                         # active active
iio_info -u local: | grep "iio:device"                # ad9361-phy, cf-ad9361-lpc, cf-ad9361-dds-core-lpc
```

Yang perlu diperhatikan saat mencoba M2 pertama kali:

- Kalau device tree gagal di-compile, error-nya muncul di log PetaLinux (`do_compile` device-tree). Kirim potongan log itu, karena node hasil konversi otomatis bisa butuh penyesuaian kecil.
- Kalau `ad9361-phy` tidak muncul, cek `dmesg | grep ad9361`. Sebagai cadangan, overlay Bagian I dan `setup_autostart.sh` tetap bisa dipakai di image baru.
- Paket `qemu.sh` memasang paket dari internet di dalam chroot, jadi WSL harus terhubung ke internet selama build.

### Troubleshooting

Masalah yang benar-benar muncul selama praktik, berurutan sesuai tahap.

| Gejala | Penyebab | Solusi |
| --- | --- | --- |
| Perintah Linux error di PowerShell | Diketik di Windows, bukan di WSL | Ketik `wsl` dulu; prompt `asus@...$` = Linux, `PS C:\>` = Windows |
| Ubuntu 18.04 "tidak tersedia" di Store | Pembatasan wilayah | Appx dari aka.ms/wsl-ubuntu-1804 + `wsl --import` (Bagian A) |
| `E: Unable to locate package lz4` | Nama paket berbeda di 18.04 | `liblz4-tool` |
| Web installer 2021.1 "obsolete" | Sudah ditarik AMD | Pakai SFD 52 GB |
| Installer meminta 131 GB | Semua device tercentang | Sisakan hanya Zynq-7000 (± 75 GB) |
| PetaLinux: missing `zlib1g:i386` | Arsitektur i386 belum aktif | `dpkg --add-architecture i386` lalu install |
| `setup_host.sh` gagal unduh QEMU | Sertifikat wiki.qemu-project.org kedaluwarsa | Ganti URL ke download.qemu.org (C4) |
| Vivado ditolak versi oleh Makefile PYNQ | Makefile meminta 2022.1 | Patch pengecekan ke 2021.1 (C3) |
| Build PYNQ: `cannot stat base/*.py` | Ada `base.hwh` tanpa file Python | Tambah `base.py` + `__init__.py` (E2) |
| `I/O error, dev mmcblk0` saat boot | SD card 256 GB tidak cocok dengan Zynq | Pakai kartu 16–32 GB, tulis dengan balenaEtcher |
| Etcher: *Missing partition table* | Salah pilih file (BOOT.BIN) | Pilih `e200-3.0.1.img` |
| PuTTY menampilkan karakter acak | Speed salah (11500) | 115200 |
| `ping 192.168.2.99` timeout, IP berpindah-pindah | `dhclient` memakai lease lama dan menghapus alamat tetap | systemd-networkd (Bagian H) |
| `http://pynq:9090` tidak terbuka | Tidak ada DNS tanpa router | Pakai alamat IP |
| IIO hanya menemukan `xadc` | Node AD9361 di-comment di BSP | Overlay AD9361 (Bagian I) |
| `iio_info` dari laptop: 2 devices | `iiod` dimulai sebelum overlay | `systemctl restart iiod` (atau autostart J) |
| `^[[200~` saat paste di terminal Jupyter | Bracketed paste | `bind 'set enable-bracketed-paste off'` |
| `apt install iiod` tidak ditemukan | `apt update` belum berjalan | Jalankan `apt update` dulu |
| Audio FM putus-putus | Data IQ terlalu besar untuk port 100 Mbps | 1,2 MS/s, buffer besar, sambung langsung 1 Gbps |
| `Unable to create context` di GNU Radio | URI salah | Sesuaikan URI dengan sambungan |

Kalau antSDR tidak bisa dihubungi sama sekali, buka PuTTY (COM, 115200). Log boot dan `ip addr show eth0` hampir selalu menunjukkan penyebabnya.

### File di repo ini

| File | Dipakai di |
| --- | --- |
| [`hdl/add_can0.sh`](hdl/add_can0.sh), [`hdl/antsdre200/`](hdl/antsdre200/) | Bagian D (WSL) |
| [`petalinux/recipes-kernel/can.cfg`](petalinux/recipes-kernel/can.cfg) | Bagian E3 |
| [`board/e200/base/`](board/e200/base/) | Bagian E2 |
| [`board/network/10-eth0.network`](board/network/10-eth0.network) | Bagian H (antSDR) |
| [`board/ad9361_overlay/`](board/ad9361_overlay/) | Bagian I dan J (antSDR) |
| [`image_final/siapkan_image_final.sh`](image_final/siapkan_image_final.sh) | Bagian M2 (belum diuji) |
| [`apps/gnuradio/fm_rx_antsdr.grc`](apps/gnuradio/fm_rx_antsdr.grc) | Bagian L (laptop) |
| [`apps/antsdr_csp_bridge/`](apps/antsdr_csp_bridge/) | Bridge CSP ↔ CCSDS ↔ GMSK (fase berikutnya) |

File besar (image SD card, BOOT.BIN, bitstream, installer) tidak disimpan di repo ini.

---

<a name="english"></a>
## English: antSDR E200 TT&C Modem Tutorial (hands-on build)

### Introduction

This tutorial makes the antSDR E200 run PYNQ Linux with CAN0 on header J30, Ethernet, and the AD9361, all ready the moment it is powered on. Every build step runs on a Windows laptop through WSL2 Ubuntu 18.04, exactly as it was built and tested.

**Verified end result:**

| Function | State after power on |
| --- | --- |
| PYNQ Linux (Ubuntu 22.04, kernel 5.15.19) + Jupyter | Boots automatically, Jupyter at `http://192.168.2.99:9090` |
| Ethernet (PL, GEM0 + GMII-to-RGMII) | 1 Gbps direct to the laptop, fixed IP 192.168.2.99 |
| CAN0 (Zynq PS via EMIO to J30 pins 3/4) | UP automatically, 500 kbps, `xilinx_can` driver |
| AD9361 (ADI IIO driver) + `iiod` | Ready for GNU Radio on the laptop |

**What you need:**

- A Windows 10/11 laptop with 16 GB RAM or more and about 250 GB free on one drive (drive D in this guide).
- antSDR E200, power adapter, LAN cable, USB-C cable for the UART console.
- A **16–32 GB** SD card. A 256 GB SDXC card failed to be read by the Zynq (I/O errors).
- A 3.3 V CAN transceiver module **SN65HVD230** and a 2.0 mm 1×10 header for J30.
- An AMD/Xilinx account to download the installers.

**Flow:** HDL in Vivado (CAN0 via EMIO) → XSA and bitstream → PetaLinux and PYNQ sdbuild → SD card image → BOOT.BIN that contains the bitstream → boot → network setup, AD9361 overlay and autostart services on the board.

Commands starting with `PS>` run in Windows PowerShell. All other commands run inside WSL Ubuntu (prompt `user@LAPTOP...$`), unless marked **on the antSDR**.

### Part A: Prepare Windows and WSL2 Ubuntu 18.04

Vivado 2021.1 and PetaLinux 2022.1 officially support Ubuntu 18.04, so we use that distro in WSL2 and keep its virtual disk on drive D.

1. **Enable and update WSL** (PowerShell as Administrator):
    ```powershell
    wsl --install --no-distribution
    wsl --update
    wsl --set-default-version 2
    ```
2. **Download Ubuntu 18.04 manually.** The Microsoft Store often says it is "not available in your market". Download the appx package from `https://aka.ms/wsl-ubuntu-1804`, rename it to `.zip`, extract it and take `install.tar.gz` from inside.
3. **Import it to drive D:**
    ```powershell
    mkdir D:\WSL\Ubuntu1804
    wsl --import Ubuntu-18.04 D:\WSL\Ubuntu1804 D:\antsdr_download\install.tar.gz --version 2
    wsl -d Ubuntu-18.04
    ```
4. **Create a normal user** (example `asus`) and make it the default. Inside WSL (still root):
    ```bash
    adduser asus
    usermod -aG sudo asus
    printf '[user]\ndefault=asus\n' > /etc/wsl.conf
    exit
    ```
    Then `PS> wsl --terminate Ubuntu-18.04` and enter again with `wsl`.
5. **Set WSL RAM, CPU and swap.** Create `C:\Users\<name>\.wslconfig` (from PowerShell, not from Notepad inside WSL):
    ```ini
    [wsl2]
    memory=10GB
    processors=12
    swap=16GB
    ```
    Run `PS> wsl --shutdown` to apply. Adjust to your laptop; the PetaLinux build needs a lot of RAM.
6. **Install base packages** and point `/bin/sh` to bash (required by PetaLinux):
    ```bash
    sudo apt update && sudo apt upgrade -y
    sudo apt install -y build-essential git wget unzip xz-utils liblz4-tool \
      python3 python3-pip libncurses5 libtinfo5 locales x11-apps
    sudo dpkg-reconfigure dash      # choose "No"
    ls -l /bin/sh                   # must point to bash
    ```
    On Ubuntu 18.04 the package is `liblz4-tool`, not `lz4`.
7. **Check the WSLg GUI** with `xeyes`. If the eyes window appears, the graphical Xilinx installer will work.

**Important:** do all builds in Linux folders (`~/...`), not in `/mnt/c` or `/mnt/d`. Accessing Windows drives from WSL is much slower.

### Part B: Install Vivado/Vitis 2021.1 and PetaLinux 2022.1

The versions must match exactly: the ADI HDL repo requires Vivado **2021.1**, and antsdr-pynq uses PetaLinux **2022.1**.

#### B1. Download the installers

| File | Size | Note |
| --- | --- | --- |
| `Xilinx_Unified_2021.1_0610_2318.tar.gz` (SFD, all OS) | ≈ 52 GB | The 2021.1 web installer is "obsolete"; use the SFD |
| `petalinux-v2022.1-04191534-installer.run` | ≈ 2.6 GB | From the Embedded Design Tools 2022.1 archive |

Save them in `D:\antsdr_download\` and check the MD5 against the download page:
```bash
cd /mnt/d/antsdr_download
md5sum Xilinx_Unified_2021.1_0610_2318.tar.gz
tar -xzf Xilinx_Unified_2021.1_0610_2318.tar.gz
```

#### B2. Install Vitis 2021.1 (Zynq-7000 only)

```bash
sudo mkdir -p /opt/Xilinx && sudo chown -R $USER:$USER /opt/Xilinx
cd /mnt/d/antsdr_download/Xilinx_Unified_2021.1_0610_2318
./xsetup
```

In the installer (WSLg window):

1. When offered a newer version, choose **Continue** with 2021.1.
2. Product: **Vitis** (includes Vivado and Vitis HLS).
3. On the Customize screen, **uncheck**: Vitis Model Composer, DocNav, *Install devices for Alveo...*, 7 Series, UltraScale, UltraScale+, Versal ACAP, Engineering Sample. Under **SoCs**, keep only **Zynq-7000** (uncheck Zynq UltraScale+ MPSoC and RFSoC). Disk Space Required drops from 131 GB to ≈ 75 GB (≈ 57 GB final).
4. Accept the three licenses yourself, location **`/opt/Xilinx`**, uncheck both shortcut options.
5. "Disk Space Available 999 GB" is the maximum size of the WSL virtual disk, not the free space on drive D. Make sure drive D still has ≈ 90 GB free.
6. Installation takes 1–3 hours. Disable sleep while on AC power: `PS> powercfg /change standby-timeout-ac 0`.
7. If the **Xilinx Information Center** offers 2021.1.1 or a newer release, click **Dismiss**.

Verify:
```bash
source /opt/Xilinx/Vivado/2021.1/settings64.sh
vivado -version     # Vivado v2021.1 (64-bit)
vitis -version      # Vitis v2021.1 (64-bit)
```

#### B3. Install PetaLinux 2022.1

Open a new WSL terminal (without the Vivado environment):
```bash
sudo apt install -y gawk xterm autoconf libtool texinfo zlib1g-dev gcc-multilib \
  build-essential libncurses5-dev libtinfo5 net-tools tftpd-hpa python3 python3-pip \
  python3-pexpect python3-git python3-jinja2 xz-utils debianutils iputils-ping \
  libegl1-mesa libsdl1.2-dev pylint3 cpio diffstat chrpath socat unzip locales
sudo locale-gen en_US.UTF-8
sudo dpkg --add-architecture i386 && sudo apt update && sudo apt install -y zlib1g:i386
sudo mkdir -p /opt/pkg/petalinux/2022.1 && sudo chown -R $USER:$USER /opt/pkg
mkdir -p ~/installers && cp /mnt/d/antsdr_download/petalinux-v2022.1-04191534-installer.run ~/installers/
cd ~/installers && chmod +x petalinux-v2022.1-04191534-installer.run
./petalinux-v2022.1-04191534-installer.run -d /opt/pkg/petalinux/2022.1   # no sudo
```

In the license text press **q**, then type **y** if you agree. Without `zlib1g:i386`, the installer stops with *missing development libraries*.

Check: `source /opt/pkg/petalinux/2022.1/settings.sh && echo $PETALINUX`. The warnings *This is not a supported OS* (Ubuntu 18.04.6) and *No tftp server found* are safe to ignore.

### Part C: Prepare the antsdr-pynq repo and the PYNQ host

We need two repos in `~/antsdr`, the prebuilt PYNQ rootfs, and a host prepared with `setup_host.sh`.

#### C1. Get the repos

```bash
mkdir -p ~/antsdr && cd ~/antsdr
git clone --recursive https://github.com/MicroPhase/antsdr-pynq.git
```

Place the antSDR HDL repo (the ADI HDL fork that contains `projects/antsdre200`) in `~/antsdr/hdl`. Check:
```bash
ls ~/antsdr/hdl/projects/antsdre200/      # Makefile system_bd.tcl system_top.v system.xdc ...
ls ~/antsdr/antsdr-pynq/boards/e200/      # e200.spec base/ petalinux_bsp/
grep -n "required_vivado_version" ~/antsdr/hdl/projects/scripts/adi_project_xilinx.tcl   # "2021.1"
```

#### C2. PYNQ 3.0.1 rootfs and sdist (prebuilt)

Download `pynq_rootfs.arm.tar.gz` (≈ 1.9 GB) and `pynq_sdist.tar.gz` (≈ 61 MB) for version 3.0.1 from the PYNQ download page and put them in:
```bash
mkdir -p ~/antsdr/antsdr-pynq/PYNQ/sdbuild/prebuilt
# copy both files into that folder
ls -lh ~/antsdr/antsdr-pynq/PYNQ/sdbuild/prebuilt/
```
The Makefile uses both automatically (`PYNQ_ROOTFS` and `PYNQ_SDIST`), so the Ubuntu rootfs does not have to be built from scratch.

#### C3. Patch the Vivado version check in the PYNQ Makefile

The PYNQ Makefile expects Vivado/Vitis with the same version as the kernel (2022.1). We use 2021.1, so the check is changed:
```bash
cd ~/antsdr/antsdr-pynq/PYNQ/sdbuild
cp Makefile Makefile.asli
sed -i 's/vivado -version | fgrep ${KERNEL_VERSION}/vivado -version | fgrep 2021.1/; s/vitis -version | fgrep ${KERNEL_VERSION}/vitis -version | fgrep 2021.1/' Makefile
diff Makefile.asli Makefile      # 2 lines changed
```

#### C4. Run setup_host.sh (with the QEMU URL fix)

The script installs crosstool-ng, compiles QEMU 5.2.0 and installs Python packages. The old URL `wiki.qemu-project.org` fails because its HTTPS certificate has expired, so point it to `download.qemu.org` first:
```bash
cd ~/antsdr/antsdr-pynq/PYNQ/sdbuild
cp scripts/setup_host.sh scripts/setup_host.sh.asli
sed -i 's#http://wiki.qemu-project.org/download/#https://download.qemu.org/#' scripts/setup_host.sh
./scripts/setup_host.sh 2>&1 | tee ~/setup_host.log
```

When it finishes (≈ 30–60 minutes), exit and re-enter WSL so the new PATH is active, then check:
```bash
which qemu-arm-static ct-ng      # /opt/qemu/bin/... and /opt/crosstool-ng/bin/...
```

### Part D: Add CAN0 via EMIO in the HDL and build the bitstream

The CAN0 controller lives in the Zynq PS (ARM). We enable it through EMIO, the path through the FPGA fabric, and connect it to pins **V5** (TX) and **U7** (RX), which come out on header J30.

#### D1. Pins and voltage

| Signal | FPGA pin | Schematic net | Header J30 |
| --- | --- | --- | --- |
| `can0_tx` | V5 | GPIO_00 | pin 3 |
| `can0_rx` | U7 | GPIO_01 | pin 4 |
| 3.3 V | – | VCC_3V3 | pin 1 |
| GND | – | GND | pin 2 (check with a multimeter) |

On the schematic (page 4), **bank 13 VCCO = 3.3 V**. The stock XDC declares four bank-13 pins (V6, W6, V10, V11) as LVCMOS18. Putting CAN on LVCMOS33 in the same bank makes Vivado refuse the design because of conflicting I/O standards. So those four pins are changed to **LVCMOS33** too, matching the real board. With a 3.3 V bank, the SN65HVD230 connects directly with no level shifter.

#### D2. Run add_can0.sh

The script ([`hdl/add_can0.sh`](hdl/add_can0.sh)) changes three files and keeps the originals as `*.asli`:

- `system_bd.tcl`: `PCW_CAN0_PERIPHERAL_ENABLE 1`, `PCW_CAN0_CAN0_IO EMIO`, CAN clock 100 MHz, ports `can0_tx/can0_rx` to `CAN0_PHY_TX/RX`.
- `system_top.v`: top-level ports `can0_tx` (output) and `can0_rx` (input), wired to `system_wrapper`.
- `system.xdc`: bank 13 to LVCMOS33, plus `can0_tx` on V5 and `can0_rx` on U7 (pull-up).

```bash
bash /mnt/d/antsdr_download/add_can0.sh      # prints a diff summary
```

The same change is also available as a patch: [`hdl/antsdre200/can0_emio.patch`](hdl/antsdre200/can0_emio.patch).

#### D3. Build

```bash
cd ~/antsdr/hdl/projects/antsdre200
source /opt/Xilinx/Vivado/2021.1/settings64.sh
make 2>&1 | tee ~/hdl_build.log      # ≈ 40 minutes
```

All libraries and the project must end with **OK**. Then check three things:
```bash
ls -lh antsdre200.sdk/                                   # system_top.xsa
grep -E "WNS|TNS" antsdre200_vivado.log | tail -2        # WNS and WHS positive
mkdir -p /tmp/xsa && cd /tmp/xsa && unzip -o -q ~/antsdr/hdl/projects/antsdre200/antsdre200.sdk/system_top.xsa
grep -o 'PCW_CAN0_[A-Z_]*" VALUE="[A-Z0-9]*"' system.hwh | sort -u   # ENABLE=1, IO=EMIO
```

Result in practice: WNS = +0.248 ns, WHS = +0.032 ns (timing met), and the XSA contains `system_top.bit` and `system.hwh`.

### Part E: Put the new hardware into board e200 and build the PYNQ image

Three hardware files are replaced, one CAN kernel config is added, then the image is built with `make`.

#### E1. XSA, bitstream and hwh

```bash
cd ~/antsdr/antsdr-pynq/boards/e200
cp -n base/base.bit base/base.bit.asli
cp -n petalinux_bsp/hardware_project/system.xsa petalinux_bsp/hardware_project/system.xsa.asli
cp ~/antsdr/hdl/projects/antsdre200/antsdre200.sdk/system_top.xsa petalinux_bsp/hardware_project/system.xsa
cp /tmp/xsa/system_top.bit base/base.bit
cp /tmp/xsa/system.hwh base/base.hwh
```

The new `base.bit` (≈ 2.4 MB) is smaller than the old one because the ADI bitstream is compressed; the Zynq loads it normally. `base.hwh` is needed by PYNQ for `Overlay("base.bit")`.

#### E2. Python overlay package (required once base.hwh exists)

As soon as `base.hwh` exists, the build script treats `base/` as a full overlay and looks for `*.py` files. Without them the build fails at the end with `cannot stat '.../base/*.py'`. Copy [`board/e200/base/base.py`](board/e200/base/base.py) and [`__init__.py`](board/e200/base/__init__.py) into `~/antsdr/antsdr-pynq/boards/e200/base/`.

#### E3. CAN driver in the kernel

The stock BSP does not include SocketCAN or the `xilinx_can` driver. Without them, `can0` never appears in Linux.
```bash
cd ~/antsdr/antsdr-pynq/boards/e200/petalinux_bsp/meta-user/recipes-kernel/linux
cat > linux-xlnx/can.cfg <<'EOF'
CONFIG_CAN=y
CONFIG_CAN_RAW=y
CONFIG_CAN_BCM=y
CONFIG_CAN_GW=y
CONFIG_CAN_DEV=y
CONFIG_CAN_CALC_BITTIMING=y
CONFIG_CAN_XILINXCAN=y
EOF
cp -n linux-xlnx_%.bbappend linux-xlnx_%.bbappend.asli
echo 'SRC_URI += "file://can.cfg"' >> linux-xlnx_%.bbappend
```

#### E4. Build the image

The e200 board folder is not in `PYNQ/boards/`, so it must be passed with `BOARDDIR`. Use a fresh WSL terminal:
```bash
source /opt/pkg/petalinux/2022.1/settings.sh
source /opt/Xilinx/Vitis/2021.1/settings64.sh      # also loads Vivado
cd ~/antsdr/antsdr-pynq/PYNQ/sdbuild
sudo -v
make BOARDDIR=$HOME/antsdr/antsdr-pynq/boards BOARDS=e200 2>&1 | tee ~/pynq_build.log
```

The build took about 1.5 hours in practice. The result is `output/e200-3.0.1.img` (7.3 GB). Make sure the CAN driver and device tree made it in:
```bash
cd ~/antsdr/antsdr-pynq/PYNQ/sdbuild/build/e200/petalinux_project
grep -E "CONFIG_CAN=|CONFIG_CAN_XILINXCAN" build/tmp/work/*/linux-xlnx/*/linux-*-build/.config
grep -n -A2 "&can0" components/plnx_workspace/device-tree/device-tree/pcw.dtsi   # status = "okay"
```
`disabled` in `zynq-7000.dtsi` is the default; `pcw.dtsi` (from the XSA) turns it into `okay`.

Do not open the Vivado GUI during the build. It uses 2–3 GB of RAM and the PetaLinux build can fail with out-of-memory.

### Part F: Build a BOOT.BIN that contains the bitstream

The PYNQ BOOT.BIN (≈ 1.1 MB) only contains FSBL, U-Boot and the DTB, **no bitstream**. On the E200, Ethernet and the CAN0 pins both go through the FPGA, so the bitstream must be loaded at boot. The `e200_boot_gen` folder builds a complete BOOT.BIN.

The stock files in `e200_boot_gen` are old versions without CAN0, so all four are replaced with our build outputs:
```bash
source /opt/Xilinx/Vitis/2021.1/settings64.sh      # for bootgen
cd ~/antsdr/antsdr-pynq/e200_boot_gen
mkdir -p asli && cp -n system.dtb system_top.bit u-boot.elf zynq_fsbl.elf asli/
IMG=~/antsdr/antsdr-pynq/PYNQ/sdbuild/build/e200/petalinux_project/images/linux
cp $IMG/zynq_fsbl.elf $IMG/u-boot.elf $IMG/system.dtb .
cp ~/antsdr/antsdr-pynq/boards/e200/base/base.bit system_top.bit
rm -rf build_sdimg && make sdimg
ls -lh build_sdimg/BOOT.bin                        # ≈ 3.4 MB
```

Copy the results to Windows so they are easy to write to the SD card:
```bash
cp build_sdimg/BOOT.bin /mnt/d/antsdr_download/BOOT.BIN
cp ~/antsdr/antsdr-pynq/PYNQ/sdbuild/output/e200-3.0.1.img /mnt/d/antsdr_download/
```

WSL can then be shut down to free RAM: `PS> wsl --shutdown`. This command runs in PowerShell, not inside WSL.

### Part G: Write the SD card and first boot

Use a **16–32 GB** card. A 256 GB card made Linux fail to read the root partition (`I/O error, dev mmcblk0`).

#### G1. Write the image

1. If the card's content is still needed, back it up first with Rufus: select the card in **Device**, click the disk icon next to it, save as `.vhd`. balenaEtcher cannot back up to a file.
2. Open **balenaEtcher** (etcher.balena.io): **Flash from file** → `D:\antsdr_download\e200-3.0.1.img` (not BOOT.BIN), **Select target** → SD card, **Flash!** Wait until *Validating* finishes. Rufus in DD mode also works but does not verify the write.
3. Unplug and replug the card. A **BOOT** drive appears with `BOOT.BIN`, `boot.scr`, `image.ub`. If Windows offers to format another partition, choose **Cancel**.
4. **Overwrite `BOOT.BIN`** on the BOOT drive with `D:\antsdr_download\BOOT.BIN` (3.4 MB). Make sure it is 3.4 MB, not 1.1 MB. Then **Eject**.

#### G2. First boot over UART

1. Insert the card, set the boot switch to **SD**, connect the USB-C UART to the laptop.
2. Find the COM port in **Device Manager → Ports (COM & LPT)** (COM8 in practice).
3. **PuTTY**: Connection type **Serial**, Serial line `COM8`, Speed **115200** (not 11500), then **Open**.
4. Power on the antSDR. U-Boot and kernel logs scroll, then `pynq login: xilinx (automatic login)` appears. User/password: `xilinx` / `xilinx`.
5. Check:
    ```bash
    ip addr show eth0
    ip -details link show can0          # can0 present, state STOPPED (normal)
    dmesg | grep -i -E "xilinx_can|macb"
    ```

In PuTTY, selected text is copied automatically and right-click pastes it. Do not press Ctrl+C to copy; it stops the running program. The `TDC Offset value not in range` message from `xilinx_can` only matters for CAN-FD and is safe to ignore.

Always shut the antSDR down with `sudo poweroff`, wait ≈ 10 seconds, then remove power. Unplugging only the USB UART is safe as long as the board is powered from its adapter.

### Part H: Stable network on 192.168.2.99 with systemd-networkd

The stock PYNQ config (ifupdown: `eth0` DHCP + `eth0:1` = 192.168.2.99) is unstable when the antSDR is connected directly to the laptop. With no router, `dhclient` keeps retrying, reuses an old lease (for example 192.168.0.143), and removes 192.168.2.99 every time. The fix is to hand `eth0` to systemd-networkd, which runs DHCP and a fixed address side by side.

#### H1. Laptop side

Add 192.168.2.1 to the laptop's Ethernet adapter without removing other IPs (PowerShell **as Administrator**):
```powershell
netsh interface ipv4 add address "Ethernet" 192.168.2.1 255.255.255.0
```

#### H2. antSDR side (over PuTTY, once)

```bash
sudo tee /etc/systemd/network/10-eth0.network >/dev/null <<'EOF'
[Match]
Name=eth0

[Network]
DHCP=ipv4
Address=192.168.2.99/24
EOF
sudo mv /etc/network/interfaces.d/eth0 /root/eth0.ifupdown.bak
sudo pkill -f "dhclient.*eth0"
sudo ip addr flush dev eth0
sudo rm -f /var/lib/dhcp/dhclient*.eth0.leases
sudo systemctl enable systemd-networkd
sudo systemctl disable systemd-networkd-wait-online.service
sudo systemctl restart systemd-networkd
sudo networkctl reconfigure eth0
ip -4 addr show eth0          # inet 192.168.2.99/24
```

`systemd-networkd-wait-online` is disabled **after** enabling networkd, because enabling turns it back on; without that, boot waits ≈ 2 minutes when no router is present.

Result:

| Cable | antSDR address |
| --- | --- |
| Direct to the laptop (1 Gbps) | 192.168.2.99 |
| To a router | IP from the router's DHCP **and** 192.168.2.99 |

Test: `PS> ping 192.168.2.99`, then open `http://192.168.2.99:9090` (Jupyter password `xilinx`). The name `http://pynq:9090` does not resolve without a router's DNS.

Through a 100 Mbps router port, a 2.4 MS/s IQ stream (≈ 77 Mbps) makes GNU Radio audio stutter. A direct 1 Gbps link to the laptop is more stable.

### Part I: Enable the AD9361 with a device tree overlay

In the antsdr-pynq BSP, every AD9361 node in `system-user.dtsi` is commented out, and the FPGA Manager option (`FPGA_MANAGER_e200 := 1`) keeps PL devices out of the main device tree. As a result IIO only finds `xadc`. We add the AD9361 nodes at runtime with a `.dtbo` overlay, **without** reprogramming the FPGA, so Ethernet stays up.

#### I1. Contents of `ad9361_e200.dts`

The overlay ([`board/ad9361_overlay/ad9361_e200.dts`](board/ad9361_overlay/ad9361_e200.dts)) comes from the commented blocks in the BSP, with fixes:

| Part | Value |
| --- | --- |
| Reference clock (new) | `fixed-clock` 40 MHz, `ad9361_ext_refclk` |
| `adi,ad9361` on `&spi0` | reg 0, LVDS, 2R2T, FDD, full digital tune |
| Control GPIOs | en_agc 66, sync 67, reset 68, enable **101**, txnrx **102** (matching `gpio_o[47]`/`[48]` in `system_top.v`) |
| RX / TX DMA | `0x7C400000` irq 57 / `0x7C420000` irq 56, clock FCLK0 |
| ADC / DAC core | `0x79020000` / `0x79024000` |
| sysid | `0x45000000` |

#### I2. Load the overlay and install iiod

Upload `ad9361_e200.dts` and [`apply_ad9361.sh`](board/ad9361_overlay/apply_ad9361.sh) with the **Upload** button in Jupyter (folder `/home/xilinx/jupyter_notebooks`). In a Jupyter terminal (already root):
```bash
bind 'set enable-bracketed-paste off'     # type this by hand first; prevents ^[[200~ on paste
apt update && apt install -y iiod libiio-utils
cd /home/xilinx/jupyter_notebooks
bash apply_ad9361.sh
systemctl restart iiod                    # iiod must start AFTER the overlay
```

Expected output:
```
Status overlay: applied
ad9361 spi1.0: ad9361_probe : AD936x Rev 0 successfully initialized
cf_axi_adc 79020000.cf-ad9361-lpc: ... probed ADC AD9361 as MASTER
iio:device1: ad9361-phy
iio:device2: cf-ad9361-lpc (buffer capable)
iio:device3: cf-ad9361-dds-core-lpc (buffer capable)
```

The warning `OF: overlay: WARNING: memory leak will occur if overlay removed` is normal.

Check from the laptop (Radioconda Prompt):
```
iio_info -u ip:192.168.2.99 | findstr "devices iio:device"
```

Do not call `Overlay("base.bit")` with download in Jupyter. Reprogramming the FPGA resets the PL Ethernet and cuts off Jupyter. To read the design, use `BaseOverlay("base.bit", download=False)`.

### Part J: Autostart CAN0 + AD9361 and the reboot test

The AD9361 overlay and the `can0` settings are lost on every restart. [`setup_autostart.sh`](board/ad9361_overlay/setup_autostart.sh) installs two services in one go:

- **`ad9361-overlay.service`**: loads `/lib/firmware/ad9361_e200.dtbo` at boot, and `iiod` is made to start after it (drop-in `iiod.service.d/after-ad9361.conf`).
- **`can0.service`**: `ip link set can0 up type can bitrate 500000 loopback off restart-ms 100` as soon as the `can0` driver is ready.

Change `CAN_BITRATE=500000` at the top of the script if your OBC uses another bitrate. Upload the script to Jupyter, then in a Jupyter terminal:
```bash
cd /home/xilinx/jupyter_notebooks
bash setup_autostart.sh
```

Test with a reboot (Jupyter disconnects for a moment):
```bash
reboot
```

After ≈ 1–2 minutes, open `http://192.168.2.99:9090` again, open a terminal, then:
```bash
systemctl is-active ad9361-overlay can0 iiod      # active active active
ip -4 addr show eth0                               # 192.168.2.99/24
ip -details link show can0 | grep -E "state|bitrate"
iio_info -u local: | grep "iio:device"
```

Result in practice after a reboot: all three services **active**, `eth0` on 192.168.2.99, `can0` **UP, ERROR-ACTIVE, bitrate 499999** (500 kbps; the 1 bit/s difference comes from the 99.999999 MHz CAN clock), and `ad9361-phy` + `cf-ad9361-lpc` + `cf-ad9361-dds-core-lpc` present. The antSDR is ready the moment it is powered on.

### Part K: Test CAN0 and wire the SN65HVD230

Test the controller first with internal loopback (no cable), then connect the transceiver to the OBC.

#### K1. Check the PS configuration from Jupyter

```python
from pynq.overlays.base import BaseOverlay
ol = BaseOverlay("base.bit", download=False)
print(list(ol.ip_dict))   # axi_gpreg, axi_iic_main, axi_sysid_0, axi_ad9361, ..._adc_dma, ..._dac_dma, sys_ps7
ps = ol.ip_dict["sys_ps7"]["parameters"]
print(ps.get("PCW_CAN0_PERIPHERAL_ENABLE"), ps.get("PCW_CAN0_CAN0_IO"), ps.get("PCW_CAN_PERIPHERAL_FREQMHZ"))   # 1 EMIO 100
```

#### K2. Internal loopback

In a Jupyter terminal:
```bash
ip link set can0 down
ip link set can0 type can bitrate 500000 loopback on
ip link set can0 up
```

In the notebook (Python standard library only, the same approach as `csp1_can.py`):
```python
import socket, struct
rx = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW); rx.bind(("can0",)); rx.settimeout(1.0)
tx = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW); tx.bind(("can0",))
data = bytes([0xDE, 0xAD, 0xBE, 0xEF])
tx.send(struct.pack("=IB3x8s", 0x123, len(data), data.ljust(8, b"\0")))
can_id, dlc, payload = struct.unpack("=IB3x8s", rx.recv(16))
print(f"ID=0x{can_id & 0x1FFFFFFF:X} DLC={dlc} DATA={payload[:dlc].hex(' ').upper()}")
```
Result in practice: `ID=0x123 DLC=4 DATA=DE AD BE EF`. Return to normal mode with `systemctl restart can0`.

#### K3. Connect the SN65HVD230

Header J30 has a **2.0 mm** pitch (a 2.54 mm header does not fit). Power the antSDR off before wiring.

| J30 antSDR | SN65HVD230 module |
| --- | --- |
| pin 1 (3.3 V) | 3V3 |
| pin 2 (GND) | GND |
| pin 3 (`can0_tx`, V5) | CTX / D |
| pin 4 (`can0_rx`, U7) | CRX / R |

Connect the module's CANH and CANL to the OBC's CANH and CANL. A CAN bus needs a 120 Ω resistor at both ends; many modules already have one. The OBC bitrate must match (500 kbps). Watch bus traffic with:
```bash
apt install -y can-utils
candump can0
```

### Part L: FM receiver test with GNU Radio

GNU Radio runs on the laptop (Radioconda, GNU Radio 3.10.12) and reaches the AD9361 through `iiod` on the antSDR. The **UHD: USRP Source** block no longer applies; use **FMComms2/3/4 Source** (gr-iio) instead.

Flowgraph: `FMComms2/3/4 Source → Low Pass Filter → WBFM Receive → Multiply Const (volume) → Audio Sink`, with a branch to a **QT GUI Frequency Sink**. Generate Options: **QT GUI**.

| Block | Setting |
| --- | --- |
| Variable `samp_rate` | 1 200 000 |
| QT GUI Range `freq` | 88e6–108e6, step 100e3 |
| QT GUI Range `vol` | 0–2, default 0.5 |
| FMComms2/3/4 Source | URI `'ip:192.168.2.99'`, LO `int(freq)`, Sample Rate `int(samp_rate)`, RF BW 1 000 000, Buffer 131 072, RX1 only, Gain `slow_attack`, Port `A_BALANCED`, Filter `Auto` |
| Low Pass Filter | Decimation 5, cutoff 100e3, transition 20e3 (1.2 MS/s → 240 kS/s) |
| WBFM Receive | Quadrature 240e3, Audio Decimation 5 (→ 48 kHz) |
| Audio Sink | 48 000, OK to Block = **No** |
| QT GUI Frequency Sink | Center `freq`, Bandwidth `samp_rate` |

Ready-made file: [`apps/gnuradio/fm_rx_antsdr.grc`](apps/gnuradio/fm_rx_antsdr.grc). Open it in GNU Radio Companion, click **Execute** (F6) and move the frequency slider to a nearby station.

Tips from practice:

- **Choppy audio** through a 100 Mbps router: lower the sample rate to 1.2 MS/s, enlarge the buffer, set *OK to Block* = No, or connect directly to the laptop.
- **`Unable to create context`**: the URI does not match the connection (0.143 vs 192.168.2.99) or the antSDR is not ready yet. Check with `ping` and `iio_info -u ip:...`.
- While GRC still has a file open, it can overwrite changes made from outside. Close the file without saving before opening the new version.
- The AD9361 can only be used by one program at a time. Stop the GMSK/CSP bridge while GNU Radio runs, and vice versa. CAN0 is not affected.

### Part M: A final image that is ready on any card

**Status: not tested yet.** Parts H–J are installed on the SD card in use, so a new card made from `e200-3.0.1.img` has to be set up again. There are two ways to make a new card ready at power on.

#### M1. Quick way: golden image from the working card

This copies the tested 16 GB card as-is, with no rebuild.

1. Shut the antSDR down with `sudo poweroff`, wait ≈ 10 seconds, remove the card and plug it into the laptop.
2. **Rufus**: select the card in **Device**, click the disk icon next to it, save as `D:\antsdr_download\antsdr_e200_final.vhd`. Alternative: **Win32 Disk Imager**, enter an `.img` file name, click **Read**.
3. For a new card, write that file with Rufus (select the `.vhd` in Boot selection) or balenaEtcher.

The target card must be **the same size or larger** than 16 GB. Some 16 GB cards from other brands are slightly smaller, so 32 GB is safer.

#### M2. Clean way: rebuild with every fix built in

[`image_final/siapkan_image_final.sh`](image_final/siapkan_image_final.sh) prepares three changes (originals kept as `*.asli`):

| Change | File | Effect |
| --- | --- | --- |
| AD9361 + DMA + ADC/DAC nodes added to the main device tree (from the commented blocks, with the Part I1 fixes) | `petalinux_bsp/meta-user/recipes-bsp/device-tree/files/system-user.dtsi` | AD9361 active at boot without an overlay |
| New rootfs package: `iiod`, `libiio-utils`, `can-utils`, `device-tree-compiler`, `10-eth0.network`, `can0.service` | `PYNQ/sdbuild/packages/antsdr_e200_autostart/qemu.sh` | Network 192.168.2.99 and CAN0 500 kbps automatic |
| Package registered | `boards/e200/e200.spec` (`STAGE4_PACKAGES_e200`) | Package installed during the build |

Steps in WSL:
```bash
bash /mnt/d/antsdr_download/image_final/siapkan_image_final.sh

# remove old build outputs so the device tree and rootfs are rebuilt
cd ~/antsdr/antsdr-pynq/PYNQ/sdbuild
sudo rm -rf build/e200 build/e200.tar.gz output/e200-3.0.1.img output/boot/e200

source /opt/pkg/petalinux/2022.1/settings.sh
source /opt/Xilinx/Vitis/2021.1/settings64.sh
sudo -v
make BOARDDIR=$HOME/antsdr/antsdr-pynq/boards BOARDS=e200 2>&1 | tee ~/pynq_build_final.log
```

When the build is done (estimated 1.5–2 hours), rebuild the BOOT.BIN with the bitstream as in Part F, because `system.dtb` changed too. Then write the new image to a card and overwrite BOOT.BIN as in Part G.

Check after the first boot, **without** running any script:
```bash
ip -4 addr show eth0                                  # 192.168.2.99/24
ip -details link show can0 | grep -E "state|bitrate"  # UP, 500000
systemctl is-active can0 iiod                         # active active
iio_info -u local: | grep "iio:device"                # ad9361-phy, cf-ad9361-lpc, cf-ad9361-dds-core-lpc
```

Things to watch the first time M2 is tried:

- If the device tree fails to compile, the error shows in the PetaLinux log (`do_compile` device-tree). The automatically converted nodes may need small adjustments.
- If `ad9361-phy` does not appear, check `dmesg | grep ad9361`. As a fallback, the Part I overlay and `setup_autostart.sh` still work on the new image.
- `qemu.sh` installs packages from the internet inside the chroot, so WSL must be online during the build.

### Troubleshooting

Problems that actually came up during the build, in order of stage.

| Symptom | Cause | Fix |
| --- | --- | --- |
| Linux commands fail in PowerShell | Typed in Windows, not in WSL | Type `wsl` first; prompt `user@...$` = Linux, `PS C:\>` = Windows |
| Ubuntu 18.04 "not available" in the Store | Regional restriction | Appx from aka.ms/wsl-ubuntu-1804 + `wsl --import` (Part A) |
| `E: Unable to locate package lz4` | Different package name on 18.04 | `liblz4-tool` |
| 2021.1 web installer "obsolete" | Withdrawn by AMD | Use the 52 GB SFD |
| Installer asks for 131 GB | All devices selected | Keep only Zynq-7000 (≈ 75 GB) |
| PetaLinux: missing `zlib1g:i386` | i386 architecture not enabled | `dpkg --add-architecture i386`, then install |
| `setup_host.sh` fails to download QEMU | wiki.qemu-project.org certificate expired | Change the URL to download.qemu.org (C4) |
| PYNQ Makefile rejects the Vivado version | Makefile expects 2022.1 | Patch the check to 2021.1 (C3) |
| PYNQ build: `cannot stat base/*.py` | `base.hwh` present without Python files | Add `base.py` + `__init__.py` (E2) |
| `I/O error, dev mmcblk0` at boot | 256 GB SD card incompatible with the Zynq | Use a 16–32 GB card, write with balenaEtcher |
| Etcher: *Missing partition table* | Wrong file selected (BOOT.BIN) | Select `e200-3.0.1.img` |
| PuTTY shows garbage characters | Wrong speed (11500) | 115200 |
| `ping 192.168.2.99` times out, IP keeps changing | `dhclient` reuses an old lease and removes the fixed address | systemd-networkd (Part H) |
| `http://pynq:9090` does not open | No DNS without a router | Use the IP address |
| IIO only finds `xadc` | AD9361 nodes commented out in the BSP | AD9361 overlay (Part I) |
| `iio_info` from the laptop: 2 devices | `iiod` started before the overlay | `systemctl restart iiod` (or autostart, Part J) |
| `^[[200~` when pasting in the Jupyter terminal | Bracketed paste | `bind 'set enable-bracketed-paste off'` |
| `apt install iiod` not found | `apt update` has not run | Run `apt update` first |
| Choppy FM audio | IQ data too large for a 100 Mbps port | 1.2 MS/s, large buffer, direct 1 Gbps link |
| `Unable to create context` in GNU Radio | Wrong URI | Match the URI to the connection |

If the antSDR cannot be reached at all, open PuTTY (COM, 115200). The boot log and `ip addr show eth0` almost always show the cause.

### Files in this repo

| File | Used in |
| --- | --- |
| [`hdl/add_can0.sh`](hdl/add_can0.sh), [`hdl/antsdre200/`](hdl/antsdre200/) | Part D (WSL) |
| [`petalinux/recipes-kernel/can.cfg`](petalinux/recipes-kernel/can.cfg) | Part E3 |
| [`board/e200/base/`](board/e200/base/) | Part E2 |
| [`board/network/10-eth0.network`](board/network/10-eth0.network) | Part H (antSDR) |
| [`board/ad9361_overlay/`](board/ad9361_overlay/) | Parts I and J (antSDR) |
| [`image_final/siapkan_image_final.sh`](image_final/siapkan_image_final.sh) | Part M2 (not tested) |
| [`apps/gnuradio/fm_rx_antsdr.grc`](apps/gnuradio/fm_rx_antsdr.grc) | Part L (laptop) |
| [`apps/antsdr_csp_bridge/`](apps/antsdr_csp_bridge/) | CSP ↔ CCSDS ↔ GMSK bridge (next phase) |

Large files (SD card image, BOOT.BIN, bitstream, installers) are not stored in this repo.
