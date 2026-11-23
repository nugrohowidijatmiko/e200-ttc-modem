# Tutorial antSDR E200 TT&C Modem: PYNQ + CAN0 + AD9361 di WSL (Hasil Praktik)

**Bahasa Indonesia** · [English](tutorial_en.md)

Nov 23, 2026 · @nugroho

## Pendahuluan

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

## Bagian A: Siapkan Windows dan WSL2 Ubuntu 18.04

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

## Bagian B: Instal Vivado/Vitis 2021.1 dan PetaLinux 2022.1

Versi harus persis: repo HDL ADI meminta Vivado **2021.1**, dan antsdr-pynq memakai PetaLinux **2022.1**.

### B1. Unduh installer

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

### B2. Instal Vitis 2021.1 (hanya Zynq-7000)

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

### B3. Instal PetaLinux 2022.1

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

## Bagian C: Siapkan repo antsdr-pynq dan host PYNQ

Kita butuh dua repo di `~/antsdr`, rootfs PYNQ prebuilt, lalu menyiapkan host dengan `setup_host.sh`.

### C1. Ambil repo

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

### C2. Rootfs dan sdist PYNQ 3.0.1 (prebuilt)

Unduh `pynq_rootfs.arm.tar.gz` (± 1,9 GB) dan `pynq_sdist.tar.gz` (± 61 MB) versi 3.0.1 dari halaman unduhan PYNQ, lalu taruh di:

```bash
mkdir -p ~/antsdr/antsdr-pynq/PYNQ/sdbuild/prebuilt
# salin kedua file ke folder itu
ls -lh ~/antsdr/antsdr-pynq/PYNQ/sdbuild/prebuilt/
```

Makefile otomatis memakai keduanya (`PYNQ_ROOTFS` dan `PYNQ_SDIST`), sehingga rootfs Ubuntu tidak perlu dibangun dari nol.

### C3. Tambal pengecekan versi Vivado di Makefile PYNQ

Makefile PYNQ meminta Vivado/Vitis dengan versi sama seperti kernel (2022.1). Kita pakai 2021.1, jadi pengecekannya diganti:

```bash
cd ~/antsdr/antsdr-pynq/PYNQ/sdbuild
cp Makefile Makefile.asli
sed -i 's/vivado -version | fgrep ${KERNEL_VERSION}/vivado -version | fgrep 2021.1/; s/vitis -version | fgrep ${KERNEL_VERSION}/vitis -version | fgrep 2021.1/' Makefile
diff Makefile.asli Makefile      # 2 baris berubah
```

### C4. Jalankan setup\_host.sh (dengan perbaikan URL QEMU)

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

## Bagian D: Tambah CAN0 via EMIO di HDL dan build bitstream

Controller CAN0 ada di PS (ARM) Zynq. Kita aktifkan lewat EMIO, yaitu jalur yang melewati FPGA, lalu menyambungkannya ke pin **V5** (TX) dan **U7** (RX) yang keluar di header J30.

### D1. Pin dan tegangan

| Sinyal | Pin FPGA | Net skematik | Header J30 |
| --- | --- | --- | --- |
| `can0_tx` | V5 | GPIO\_00 | pin 3 |
| `can0_rx` | U7 | GPIO\_01 | pin 4 |
| 3,3 V | – | VCC\_3V3 | pin 1 |
| GND | – | GND | pin 2 (cek dengan multimeter) |

Di skematik (halaman 4), **VCCO bank 13 = 3,3 V**. XDC bawaan menulis empat pin bank 13 (V6, W6, V10, V11) sebagai LVCMOS18. Kalau CAN dipasang LVCMOS33 di bank yang sama, Vivado menolak karena standar tegangan bentrok. Jadi keempat pin itu ikut diubah ke **LVCMOS33**, sesuai kondisi fisik board. Dengan bank 3,3 V, SN65HVD230 bisa langsung disambung tanpa level shifter.

### D2. Jalankan script add\_can0.sh

Script (isi lengkap di Lampiran) mengubah tiga file dan menyimpan aslinya sebagai `*.asli`:

- `system_bd.tcl`: `PCW_CAN0_PERIPHERAL_ENABLE 1`, `PCW_CAN0_CAN0_IO EMIO`, clock CAN 100 MHz, port `can0_tx/can0_rx` ke `CAN0_PHY_TX/RX`.
- `system_top.v`: port top-level `can0_tx` (output) dan `can0_rx` (input), disambung ke `system_wrapper`.
- `system.xdc`: bank 13 jadi LVCMOS33, plus `can0_tx` di V5 dan `can0_rx` di U7 (pull-up).

```bash
bash /mnt/d/antsdr_download/add_can0.sh      # tampilkan ringkasan diff
```

### D3. Build

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

## Bagian E: Pasang hardware baru ke board e200 dan build image PYNQ

Tiga file hardware diganti, satu konfigurasi kernel CAN ditambahkan, lalu image dibangun dengan `make`.

### E1. XSA, bitstream, dan hwh

```bash
cd ~/antsdr/antsdr-pynq/boards/e200
cp -n base/base.bit base/base.bit.asli
cp -n petalinux_bsp/hardware_project/system.xsa petalinux_bsp/hardware_project/system.xsa.asli
cp ~/antsdr/hdl/projects/antsdre200/antsdre200.sdk/system_top.xsa petalinux_bsp/hardware_project/system.xsa
cp /tmp/xsa/system_top.bit base/base.bit
cp /tmp/xsa/system.hwh base/base.hwh
```

`base.bit` baru (± 2,4 MB) lebih kecil dari yang lama karena bitstream ADI dikompresi; Zynq tetap memuatnya normal. `base.hwh` dibutuhkan PYNQ untuk `Overlay("base.bit")`.

### E2. Paket overlay Python (wajib bila ada base.hwh)

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

### E3. Driver CAN di kernel

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

### E4. Build image

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

## Bagian F: Buat BOOT.BIN berisi bitstream

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

## Bagian G: Tulis SD card dan boot pertama

Gunakan kartu **16–32 GB**. Kartu 256 GB terbukti membuat Linux gagal membaca partisi root (`I/O error, dev mmcblk0`).

### G1. Tulis image

1. Kalau isi kartu masih dibutuhkan, backup dulu dengan Rufus: pilih kartu di **Device**, klik ikon disket di sebelahnya, simpan sebagai `.vhd`. balenaEtcher tidak bisa backup ke file.
2. Buka **balenaEtcher** (etcher.balena.io): **Flash from file** → `D:\antsdr_download\e200-3.0.1.img` (bukan BOOT.BIN), **Select target** → SD card, **Flash!** Tunggu sampai *Validating* selesai. Rufus mode DD juga bisa, tapi tidak memverifikasi hasil tulis.
3. Cabut dan colokkan lagi kartu. Muncul drive **BOOT** berisi `BOOT.BIN`, `boot.scr`, `image.ub`. Kalau Windows menawarkan format partisi lain, pilih **Cancel**.
4. **Timpa `BOOT.BIN`** di drive BOOT dengan `D:\antsdr_download\BOOT.BIN` (3,4 MB). Pastikan ukurannya 3,4 MB, bukan 1,1 MB. Lalu **Eject**.

### G2. Boot pertama lewat UART

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

## Bagian H: Jaringan stabil di 192.168.2.99 dengan systemd-networkd

Konfigurasi bawaan PYNQ (ifupdown: `eth0` DHCP + `eth0:1` = 192.168.2.99) tidak stabil kalau antSDR disambung langsung ke laptop. Tanpa router, `dhclient` terus mencoba ulang, memakai lagi lease lama (misalnya 192.168.0.143), dan setiap kali menghapus alamat 192.168.2.99. Solusinya, `eth0` diserahkan ke systemd-networkd, yang menjalankan DHCP dan alamat tetap bersamaan.

### H1. Sisi laptop

Tambahkan IP 192.168.2.1 di adapter Ethernet laptop, tanpa menghapus IP lain (PowerShell **Administrator**):

```powershell
netsh interface ipv4 add address "Ethernet" 192.168.2.1 255.255.255.0
```

### H2. Sisi antSDR (lewat PuTTY, sekali saja)

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

## Bagian I: Aktifkan AD9361 lewat device tree overlay

Di BSP antsdr-pynq, semua node AD9361 di `system-user.dtsi` sengaja di-comment, dan opsi FPGA Manager (`FPGA_MANAGER_e200 := 1`) memisahkan perangkat PL dari device tree utama. Akibatnya IIO hanya menemukan `xadc`. Kita tambahkan node AD9361 saat Linux berjalan dengan overlay `.dtbo`, **tanpa** memprogram ulang FPGA, jadi Ethernet tetap aman.

### I1. Isi overlay `ad9361_e200.dts`

Overlay diambil dari blok yang di-comment di BSP, dengan perbaikan:

| Bagian | Nilai |
| --- | --- |
| Clock referensi (baru) | `fixed-clock` 40 MHz, `ad9361_ext_refclk` |
| `adi,ad9361` di `&spi0` | reg 0, LVDS, 2R2T, FDD, digital tune penuh |
| GPIO kontrol | en\_agc 66, sync 67, reset 68, enable **101**, txnrx **102** (sesuai `gpio_o[47]`/`[48]` di `system_top.v`) |
| DMA RX / TX | `0x7C400000` irq 57 / `0x7C420000` irq 56, clock FCLK0 |
| Core ADC / DAC | `0x79020000` / `0x79024000` |
| sysid | `0x45000000` |

### I2. Muat overlay dan pasang iiod

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

## Bagian J: Autostart CAN0 + AD9361 dan uji reboot

Overlay AD9361 dan pengaturan `can0` hilang setiap restart. Script `setup_autostart.sh` (isi di Lampiran) memasang dua service sekali jalan:

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

## Bagian K: Tes CAN0 dan wiring SN65HVD230

Uji controller dulu dengan loopback internal (tanpa kabel), baru sambungkan transceiver ke OBC.

### K1. Cek konfigurasi PS dari Jupyter

```python
from pynq.overlays.base import BaseOverlay
ol = BaseOverlay("base.bit", download=False)
print(list(ol.ip_dict))   # axi_gpreg, axi_iic_main, axi_sysid_0, axi_ad9361, ..._adc_dma, ..._dac_dma, sys_ps7
ps = ol.ip_dict["sys_ps7"]["parameters"]
print(ps.get("PCW_CAN0_PERIPHERAL_ENABLE"), ps.get("PCW_CAN0_CAN0_IO"), ps.get("PCW_CAN_PERIPHERAL_FREQMHZ"))   # 1 EMIO 100
```

### K2. Loopback internal

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

### K3. Sambungkan SN65HVD230

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

## Bagian L: Tes receiver FM dengan GNU Radio

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

## Bagian M: Image final yang langsung siap di kartu mana pun

**Status: belum dipraktikkan.** Bagian H–J dipasang di SD card yang sedang dipakai, jadi kartu baru dari `e200-3.0.1.img` harus disetel ulang. Ada dua cara supaya kartu baru langsung siap saat power on.

### M1. Cara cepat: golden image dari kartu yang sudah jalan

Cara ini menyalin kartu 16 GB yang sudah teruji apa adanya, jadi tidak perlu build ulang.

1. Matikan antSDR dengan `sudo poweroff`, tunggu ± 10 detik, cabut kartu, lalu colokkan ke laptop.
2. **Rufus**: pilih kartu di **Device**, klik ikon disket di sebelahnya, simpan sebagai `D:\antsdr_download\antsdr_e200_final.vhd`. Alternatif: **Win32 Disk Imager**, isi nama file `.img`, klik **Read**.
3. Untuk kartu baru, tulis file itu dengan Rufus (pilih `.vhd` di Boot selection) atau balenaEtcher.

Kartu tujuan harus **sama besar atau lebih besar** dari 16 GB. Kartu 16 GB merek lain kadang sedikit lebih kecil, jadi lebih aman pakai 32 GB.

### M2. Cara bersih: build ulang dengan semua perbaikan tertanam

Script `D:\antsdr_download\image_final\siapkan_image_final.sh` menyiapkan tiga perubahan (file asli disimpan sebagai `*.asli`):

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

## Troubleshooting

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

## Lampiran: file dan script

Semua file hasil praktik tersimpan di `D:\antsdr_download\`.

| File | Lokasi | Dipakai di |
| --- | --- | --- |
| `add_can0.sh` | `D:\antsdr_download\` | Bagian D (WSL) |
| `e200-3.0.1.img` | `D:\antsdr_download\` | Bagian G |
| `BOOT.BIN` (3,4 MB, berisi bitstream) | `D:\antsdr_download\` | Bagian G |
| `ad9361_e200.dts`, `apply_ad9361.sh`, `setup_autostart.sh` | `D:\antsdr_download\ad9361_overlay\` | Bagian I dan J (antSDR) |
| `fm_rx_antsdr.grc` | `D:\antsdr_download\` | Bagian L (laptop) |
| `BOOT_pynq_tanpa_bitstream.BIN` | `D:\antsdr_download\` | Cadangan BOOT.BIN bawaan |

Untuk Bagian M2 (belum diuji): `D:\antsdr_download\image_final\siapkan_image_final.sh`.

### add\_can0.sh

```bash
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
```

### apply\_ad9361.sh

```bash
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
```

### setup\_autostart.sh

```bash
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
```

File `ad9361_e200.dts` (± 335 baris) berisi node dari Bagian I1; gunakan file aslinya karena terlalu panjang untuk ditulis ulang di sini.
