# Tutorial: antSDR E200 TT&C Modem — PYNQ + CAN0 + AD9361 on WSL (hands-on build)

[Bahasa Indonesia](tutorial_id.md) · **English**

## Introduction

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

## Part A: Prepare Windows and WSL2 Ubuntu 18.04

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

## Part B: Install Vivado/Vitis 2021.1 and PetaLinux 2022.1

The versions must match exactly: the ADI HDL repo requires Vivado **2021.1**, and antsdr-pynq uses PetaLinux **2022.1**.

### B1. Download the installers

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

### B2. Install Vitis 2021.1 (Zynq-7000 only)

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

### B3. Install PetaLinux 2022.1

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

## Part C: Prepare the antsdr-pynq repo and the PYNQ host

We need two repos in `~/antsdr`, the prebuilt PYNQ rootfs, and a host prepared with `setup_host.sh`.

### C1. Get the repos

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

### C2. PYNQ 3.0.1 rootfs and sdist (prebuilt)

Download `pynq_rootfs.arm.tar.gz` (≈ 1.9 GB) and `pynq_sdist.tar.gz` (≈ 61 MB) for version 3.0.1 from the PYNQ download page and put them in:
```bash
mkdir -p ~/antsdr/antsdr-pynq/PYNQ/sdbuild/prebuilt
# copy both files into that folder
ls -lh ~/antsdr/antsdr-pynq/PYNQ/sdbuild/prebuilt/
```
The Makefile uses both automatically (`PYNQ_ROOTFS` and `PYNQ_SDIST`), so the Ubuntu rootfs does not have to be built from scratch.

### C3. Patch the Vivado version check in the PYNQ Makefile

The PYNQ Makefile expects Vivado/Vitis with the same version as the kernel (2022.1). We use 2021.1, so the check is changed:
```bash
cd ~/antsdr/antsdr-pynq/PYNQ/sdbuild
cp Makefile Makefile.asli
sed -i 's/vivado -version | fgrep ${KERNEL_VERSION}/vivado -version | fgrep 2021.1/; s/vitis -version | fgrep ${KERNEL_VERSION}/vitis -version | fgrep 2021.1/' Makefile
diff Makefile.asli Makefile      # 2 lines changed
```

### C4. Run setup_host.sh (with the QEMU URL fix)

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

## Part D: Add CAN0 via EMIO in the HDL and build the bitstream

The CAN0 controller lives in the Zynq PS (ARM). We enable it through EMIO, the path through the FPGA fabric, and connect it to pins **V5** (TX) and **U7** (RX), which come out on header J30.

### D1. Pins and voltage

| Signal | FPGA pin | Schematic net | Header J30 |
| --- | --- | --- | --- |
| `can0_tx` | V5 | GPIO_00 | pin 3 |
| `can0_rx` | U7 | GPIO_01 | pin 4 |
| 3.3 V | – | VCC_3V3 | pin 1 |
| GND | – | GND | pin 2 (check with a multimeter) |

On the schematic (page 4), **bank 13 VCCO = 3.3 V**. The stock XDC declares four bank-13 pins (V6, W6, V10, V11) as LVCMOS18. Putting CAN on LVCMOS33 in the same bank makes Vivado refuse the design because of conflicting I/O standards. So those four pins are changed to **LVCMOS33** too, matching the real board. With a 3.3 V bank, the SN65HVD230 connects directly with no level shifter.

### D2. Run add_can0.sh

The script ([`hdl/add_can0.sh`](../hdl/add_can0.sh)) changes three files and keeps the originals as `*.asli`:

- `system_bd.tcl`: `PCW_CAN0_PERIPHERAL_ENABLE 1`, `PCW_CAN0_CAN0_IO EMIO`, CAN clock 100 MHz, ports `can0_tx/can0_rx` to `CAN0_PHY_TX/RX`.
- `system_top.v`: top-level ports `can0_tx` (output) and `can0_rx` (input), wired to `system_wrapper`.
- `system.xdc`: bank 13 to LVCMOS33, plus `can0_tx` on V5 and `can0_rx` on U7 (pull-up).

```bash
bash /mnt/d/antsdr_download/add_can0.sh      # prints a diff summary
```

The same change is also available as a patch: [`hdl/antsdre200/can0_emio.patch`](../hdl/antsdre200/can0_emio.patch).

### D3. Build

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

## Part E: Put the new hardware into board e200 and build the PYNQ image

Three hardware files are replaced, one CAN kernel config is added, then the image is built with `make`.

### E1. XSA, bitstream and hwh

```bash
cd ~/antsdr/antsdr-pynq/boards/e200
cp -n base/base.bit base/base.bit.asli
cp -n petalinux_bsp/hardware_project/system.xsa petalinux_bsp/hardware_project/system.xsa.asli
cp ~/antsdr/hdl/projects/antsdre200/antsdre200.sdk/system_top.xsa petalinux_bsp/hardware_project/system.xsa
cp /tmp/xsa/system_top.bit base/base.bit
cp /tmp/xsa/system.hwh base/base.hwh
```

The new `base.bit` (≈ 2.4 MB) is smaller than the old one because the ADI bitstream is compressed; the Zynq loads it normally. `base.hwh` is needed by PYNQ for `Overlay("base.bit")`.

### E2. Python overlay package (required once base.hwh exists)

As soon as `base.hwh` exists, the build script treats `base/` as a full overlay and looks for `*.py` files. Without them the build fails at the end with `cannot stat '.../base/*.py'`. Copy [`board/e200/base/base.py`](../board/e200/base/base.py) and [`__init__.py`](../board/e200/base/__init__.py) into `~/antsdr/antsdr-pynq/boards/e200/base/`.

### E3. CAN driver in the kernel

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

### E4. Build the image

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

## Part F: Build a BOOT.BIN that contains the bitstream

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

## Part G: Write the SD card and first boot

Use a **16–32 GB** card. A 256 GB card made Linux fail to read the root partition (`I/O error, dev mmcblk0`).

### G1. Write the image

1. If the card's content is still needed, back it up first with Rufus: select the card in **Device**, click the disk icon next to it, save as `.vhd`. balenaEtcher cannot back up to a file.
2. Open **balenaEtcher** (etcher.balena.io): **Flash from file** → `D:\antsdr_download\e200-3.0.1.img` (not BOOT.BIN), **Select target** → SD card, **Flash!** Wait until *Validating* finishes. Rufus in DD mode also works but does not verify the write.
3. Unplug and replug the card. A **BOOT** drive appears with `BOOT.BIN`, `boot.scr`, `image.ub`. If Windows offers to format another partition, choose **Cancel**.
4. **Overwrite `BOOT.BIN`** on the BOOT drive with `D:\antsdr_download\BOOT.BIN` (3.4 MB). Make sure it is 3.4 MB, not 1.1 MB. Then **Eject**.

### G2. First boot over UART

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

## Part H: Stable network on 192.168.2.99 with systemd-networkd

The stock PYNQ config (ifupdown: `eth0` DHCP + `eth0:1` = 192.168.2.99) is unstable when the antSDR is connected directly to the laptop. With no router, `dhclient` keeps retrying, reuses an old lease (for example 192.168.0.143), and removes 192.168.2.99 every time. The fix is to hand `eth0` to systemd-networkd, which runs DHCP and a fixed address side by side.

### H1. Laptop side

Add 192.168.2.1 to the laptop's Ethernet adapter without removing other IPs (PowerShell **as Administrator**):
```powershell
netsh interface ipv4 add address "Ethernet" 192.168.2.1 255.255.255.0
```

### H2. antSDR side (over PuTTY, once)

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

## Part I: Enable the AD9361 with a device tree overlay

In the antsdr-pynq BSP, every AD9361 node in `system-user.dtsi` is commented out, and the FPGA Manager option (`FPGA_MANAGER_e200 := 1`) keeps PL devices out of the main device tree. As a result IIO only finds `xadc`. We add the AD9361 nodes at runtime with a `.dtbo` overlay, **without** reprogramming the FPGA, so Ethernet stays up.

### I1. Contents of `ad9361_e200.dts`

The overlay ([`board/ad9361_overlay/ad9361_e200.dts`](../board/ad9361_overlay/ad9361_e200.dts)) comes from the commented blocks in the BSP, with fixes:

| Part | Value |
| --- | --- |
| Reference clock (new) | `fixed-clock` 40 MHz, `ad9361_ext_refclk` |
| `adi,ad9361` on `&spi0` | reg 0, LVDS, 2R2T, FDD, full digital tune |
| Control GPIOs | en_agc 66, sync 67, reset 68, enable **101**, txnrx **102** (matching `gpio_o[47]`/`[48]` in `system_top.v`) |
| RX / TX DMA | `0x7C400000` irq 57 / `0x7C420000` irq 56, clock FCLK0 |
| ADC / DAC core | `0x79020000` / `0x79024000` |
| sysid | `0x45000000` |

### I2. Load the overlay and install iiod

Upload `ad9361_e200.dts` and [`apply_ad9361.sh`](../board/ad9361_overlay/apply_ad9361.sh) with the **Upload** button in Jupyter (folder `/home/xilinx/jupyter_notebooks`). In a Jupyter terminal (already root):
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

## Part J: Autostart CAN0 + AD9361 and the reboot test

The AD9361 overlay and the `can0` settings are lost on every restart. [`setup_autostart.sh`](../board/ad9361_overlay/setup_autostart.sh) installs two services in one go:

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

## Part K: Test CAN0 and wire the SN65HVD230

Test the controller first with internal loopback (no cable), then connect the transceiver to the OBC.

### K1. Check the PS configuration from Jupyter

```python
from pynq.overlays.base import BaseOverlay
ol = BaseOverlay("base.bit", download=False)
print(list(ol.ip_dict))   # axi_gpreg, axi_iic_main, axi_sysid_0, axi_ad9361, ..._adc_dma, ..._dac_dma, sys_ps7
ps = ol.ip_dict["sys_ps7"]["parameters"]
print(ps.get("PCW_CAN0_PERIPHERAL_ENABLE"), ps.get("PCW_CAN0_CAN0_IO"), ps.get("PCW_CAN_PERIPHERAL_FREQMHZ"))   # 1 EMIO 100
```

### K2. Internal loopback

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

### K3. Connect the SN65HVD230

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

## Part L: FM receiver test with GNU Radio

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

Ready-made file: [`apps/gnuradio/fm_rx_antsdr.grc`](../apps/gnuradio/fm_rx_antsdr.grc). Open it in GNU Radio Companion, click **Execute** (F6) and move the frequency slider to a nearby station.

Tips from practice:

- **Choppy audio** through a 100 Mbps router: lower the sample rate to 1.2 MS/s, enlarge the buffer, set *OK to Block* = No, or connect directly to the laptop.
- **`Unable to create context`**: the URI does not match the connection (0.143 vs 192.168.2.99) or the antSDR is not ready yet. Check with `ping` and `iio_info -u ip:...`.
- While GRC still has a file open, it can overwrite changes made from outside. Close the file without saving before opening the new version.
- The AD9361 can only be used by one program at a time. Stop the GMSK/CSP bridge while GNU Radio runs, and vice versa. CAN0 is not affected.

## Part M: A final image that is ready on any card

**Status: not tested yet.** Parts H–J are installed on the SD card in use, so a new card made from `e200-3.0.1.img` has to be set up again. There are two ways to make a new card ready at power on.

### M1. Quick way: golden image from the working card

This copies the tested 16 GB card as-is, with no rebuild.

1. Shut the antSDR down with `sudo poweroff`, wait ≈ 10 seconds, remove the card and plug it into the laptop.
2. **Rufus**: select the card in **Device**, click the disk icon next to it, save as `D:\antsdr_download\antsdr_e200_final.vhd`. Alternative: **Win32 Disk Imager**, enter an `.img` file name, click **Read**.
3. For a new card, write that file with Rufus (select the `.vhd` in Boot selection) or balenaEtcher.

The target card must be **the same size or larger** than 16 GB. Some 16 GB cards from other brands are slightly smaller, so 32 GB is safer.

### M2. Clean way: rebuild with every fix built in

[`image_final/siapkan_image_final.sh`](../image_final/siapkan_image_final.sh) prepares three changes (originals kept as `*.asli`):

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

## Troubleshooting

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

## Files in this repo

| File | Used in |
| --- | --- |
| [`hdl/add_can0.sh`](../hdl/add_can0.sh), [`hdl/antsdre200/`](../hdl/antsdre200/) | Part D (WSL) |
| [`petalinux/recipes-kernel/can.cfg`](../petalinux/recipes-kernel/can.cfg) | Part E3 |
| [`board/e200/base/`](../board/e200/base/) | Part E2 |
| [`board/network/10-eth0.network`](../board/network/10-eth0.network) | Part H (antSDR) |
| [`board/ad9361_overlay/`](../board/ad9361_overlay/) | Parts I and J (antSDR) |
| [`image_final/siapkan_image_final.sh`](../image_final/siapkan_image_final.sh) | Part M2 (not tested) |
| [`apps/gnuradio/fm_rx_antsdr.grc`](../apps/gnuradio/fm_rx_antsdr.grc) | Part L (laptop) |
| [`apps/antsdr_csp_bridge/`](../apps/antsdr_csp_bridge/) | CSP ↔ CCSDS ↔ GMSK bridge (next phase) |

Large files (SD card image, BOOT.BIN, bitstream, installers) are not stored in this repo.
