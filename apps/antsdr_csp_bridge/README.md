# antSDR ⇄ OBC: GMSK 9600 + CCSDS + CSP 1.x di CAN bus

```
            RF 9600 bps GMSK                      CAN bus (CSP 1.x / CFP)
 Ground ⇄ [preamble|ASM|frame CCSDS] ⇄ antSDR ⇄ paket CSP (payload = frame CCSDS) ⇄ OBC
```

- **Uplink:** RF → demod GMSK → sinkronisasi ASM `1ACFFC1D` → derandomize → cek FECF → CSP `antSDR(5) → OBC(1):10`
- **Downlink:** OBC kirim CSP ke `antSDR(5):11`, payload = frame CCSDS → randomize → ASM → GMSK → RF
- antSDR juga menjawab **CSP ping (port 1)**, jadi OBC bisa `csp_ping(5, ...)`.

## Isi folder

| File | Fungsi |
|---|---|
| `csp1_can.py` | CSP 1.x di atas SocketCAN (CFP, CRC32C), tanpa library tambahan |
| `ccsds.py` | ASM, randomizer CCSDS, FECF CRC-16, pembuat frame TM/TC |
| `gmsk.py` | Modulator dan demodulator GMSK (BT=0.5) dengan numpy/scipy |
| `antsdr_bridge.py` | Program utama bridge |
| `obc_sim.py` | Simulator OBC untuk uji tanpa OBC asli |
| `test_bridge.py` | Uji otomatis tanpa hardware (`python3 test_bridge.py`) |

## 1. Persiapan di antSDR (Linux SD card, Kuiper/Debian)

```bash
pip3 install numpy scipy pyadi-iio     # Python 3.9+
sudo ip link set can0 type can bitrate 1000000
sudo ip link set can0 up
candump can0                            # cek ada trafik dari OBC
```

## 2. Uji tanpa RF dan tanpa OBC (vcan + loopback)

```bash
sudo modprobe vcan
sudo ip link add vcan0 type vcan && sudo ip link set vcan0 up
python3 antsdr_bridge.py --can vcan0 --sim       # terminal 1
python3 obc_sim.py --can vcan0                   # terminal 2
```
Di terminal 2 akan muncul `ping antSDR OK`, lalu setiap frame downlink kembali sebagai uplink dengan `FECF=OK`.

## 3. Jalan dengan AD9361 dan OBC asli

```bash
python3 antsdr_bridge.py --can can0 --addr 5 --obc 1 \
    --rx-freq 437.5e6 --tx-freq 437.5e6 --tx-gain -10 \
    --frame-mode tm --frame-len 223 --uri local:
```

Opsi penting:
- `--frame-mode tc`: panjang frame dibaca dari header TC (untuk uplink telecommand)
- `--scid 0x123`: hanya teruskan frame dengan SCID ini
- `--no-randomize`: matikan randomizer kalau ground station tidak memakainya
- `--half-duplex`: abaikan RX selama TX (satu antena atau frekuensi sama)
- `--csp-crc`: tambahkan CRC32 CSP pada paket uplink (OBC juga harus mengecek CRC)

**Performa CPU:** di PC x86, 1 detik sinyal pada 2,4 MSPS butuh sekitar 0,08 detik proses. Di ARM Cortex-A9 bisa 15–25 kali lebih lambat, jadi pada 2,4 MSPS mungkin tidak terkejar. Kalau log menunjukkan RX tertinggal:
- turunkan `--fs 480000` (atau 960000), dengan **FIR AD9361 aktif**. Di bawah 2,083 MSPS AD9361 butuh filter FIR, yang bisa dimuat lewat file `.ftr` (properti `filter` di pyadi-iio, atau Filter Wizard di IIO Oscilloscope); atau
- jalankan bridge dulu di PC dengan `--uri ip:192.168.1.10` selama pengembangan.

## 4. Sisi OBC (libcsp 1.x, C)

```c
/* terima frame uplink dari antSDR */
csp_socket_t *sock = csp_socket(CSP_SO_CONN_LESS);
csp_bind(sock, 10);
for (;;) {
    csp_packet_t *p = csp_recvfrom(sock, 1000);
    if (p) { proses_ccsds(p->data, p->length); csp_buffer_free(p); }
}

/* kirim frame CCSDS untuk didownlink */
csp_packet_t *p = csp_buffer_get(223);
memcpy(p->data, frame, 223);
p->length = 223;
if (csp_sendto(CSP_PRIO_NORM, 5, 11, 34, CSP_O_NONE, p, 100) != CSP_ERR_NONE)
    csp_buffer_free(p);
```
- Bridge memakai CSP **connectionless** (tanpa RDP), jadi OBC harus memakai socket `CSP_SO_CONN_LESS`.
- Ukuran buffer CSP di OBC harus ≥ panjang frame (223 B, ditambah 4 B kalau memakai CRC).
- Bitrate CAN harus sama di kedua sisi (default 1 Mbps).
- Alamat antSDR (default 5) tidak boleh sama dengan node lain di bus.

## Hasil uji (`test_bridge.py`)

- CFP CSP 1.x: fragmentasi/penyusunan ulang 0–252 byte, dengan dan tanpa CRC32 ✔
- GMSK: 20/20 frame 223 B benar pada Eb/N0 16 dB dengan offset frekuensi ±1,5 kHz ✔
- End-to-end OBC → CAN → GMSK → RF → GMSK → CAN → OBC: 5/5 frame utuh, ping dijawab ✔

## Keterbatasan dan langkah berikutnya

- **Belum ada FEC.** Tanpa FEC, frame 223 B butuh Eb/N0 sekitar 15–16 dB supaya hampir selalu lolos. Tambahkan Reed-Solomon (255,223) atau convolutional untuk link margin.
- **Toleransi offset frekuensi sekitar ±2 kHz.** Doppler LEO di UHF bisa ±10 kHz, jadi koreksi Doppler harus dilakukan dengan mengatur `rx_lo`/`tx_lo` dari TLE, atau perlebar `--chan-bw` dengan konsekuensi sensitivitas turun.
- Belum diuji dengan hardware AD9361 dan OBC asli. Uji pertama sebaiknya dengan `--sim` dan `obc_sim.py`.
- Varian libcsp 1.x tertentu menghitung CRC32 dengan menyertakan header. Kalau memakai `--csp-crc` dan CRC ditolak, ubah `crc_include_header=True` di `CspCanInterface`.
