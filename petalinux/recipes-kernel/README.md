# Kernel CAN config / Konfigurasi kernel CAN

Copy `can.cfg` to / Salin `can.cfg` ke:
`antsdr-pynq/boards/e200/petalinux_bsp/meta-user/recipes-kernel/linux/linux-xlnx/`

Then add this line to / Lalu tambahkan baris ini ke `linux-xlnx_%.bbappend`:

```
SRC_URI += "file://can.cfg"
```
