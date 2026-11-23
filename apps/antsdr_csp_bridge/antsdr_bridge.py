#!/usr/bin/env python3
"""
Bridge antSDR: RF GMSK 9600 bps (frame CCSDS) <-> CSP 1.x di CAN bus <-> OBC

  Uplink  : RF -> GMSK demod -> ASM sync -> derandomize -> frame CCSDS (cek FECF)
            -> payload CSP (antSDR -> OBC:uplink_port) -> CAN
  Downlink: CAN -> paket CSP ke antSDR:downlink_port (payload = frame CCSDS)
            -> randomize -> [preamble][ASM][frame] -> GMSK mod -> RF
  Bonus   : antSDR menjawab CSP ping (port 1), jadi OBC bisa csp_ping(alamat_antSDR).

Contoh (jalan di antSDR):
  python3 antsdr_bridge.py --can can0 --addr 5 --obc 1 \
      --rx-freq 437.5e6 --tx-freq 437.5e6 --uri local:

Uji tanpa hardware RF (loopback internal + CAN asli/vcan):
  python3 antsdr_bridge.py --can vcan0 --sim
"""
from __future__ import annotations

import argparse
import logging
import queue
import signal
import threading
import time

import numpy as np

from ccsds import fecf_ok, parse_tm_header
from csp1_can import CSP_FCRC32, CspCanInterface, CspPacket
from gmsk import GmskReceiver, GmskTransmitter

log = logging.getLogger("bridge")

CSP_PING_PORT = 1


# ======================================================================= SDR
class AdiSdr:
    """AD9361 di antSDR lewat pyadi-iio (libiio)."""

    def __init__(self, uri, fs, rx_freq, tx_freq, rx_gain, tx_gain, rf_bw, buf_size):
        import adi  # pip install pyadi-iio
        self.fs = fs
        self.tx_gain = tx_gain
        s = self.sdr = adi.ad9361(uri=uri)
        s.sample_rate = int(fs)
        s.rx_rf_bandwidth = int(rf_bw)
        s.tx_rf_bandwidth = int(rf_bw)
        s.rx_lo = int(rx_freq)
        s.tx_lo = int(tx_freq)
        s.rx_enabled_channels = [0]
        s.tx_enabled_channels = [0]
        if rx_gain is None:
            s.gain_control_mode_chan0 = "slow_attack"
        else:
            s.gain_control_mode_chan0 = "manual"
            s.rx_hardwaregain_chan0 = float(rx_gain)
        s.rx_buffer_size = int(buf_size)
        s.tx_cyclic_buffer = False
        self._idle_tx()

    def _idle_tx(self):
        # redam TX semaksimal mungkin saat tidak mengirim (kurangi bocoran LO)
        self.sdr.tx_hardwaregain_chan0 = -89.0

    def rx(self) -> np.ndarray:
        return np.asarray(self.sdr.rx(), dtype=np.complex64)

    def tx(self, iq: np.ndarray):
        self.sdr.tx_hardwaregain_chan0 = float(self.tx_gain)
        self.sdr.tx((iq * 2 ** 14 * 0.7).astype(np.complex64))
        time.sleep(len(iq) / self.fs + 0.02)   # tunggu burst habis terkirim
        self.sdr.tx_destroy_buffer()
        self._idle_tx()


class SimSdr:
    """Loopback: burst yang di-TX muncul lagi di RX (+ noise & offset frekuensi)."""

    def __init__(self, fs, buf_size, ebn0_db=20.0, cfo_hz=1000.0, bitrate=9600):
        self.fs = fs
        self.n = int(buf_size)
        self.cfo = cfo_hz
        self.amp = 0.3
        self.sigma = np.sqrt(self.amp ** 2 * (fs / bitrate) / 10 ** (ebn0_db / 10) / 2)
        self.pending = np.zeros(0, dtype=np.complex64)
        self.lock = threading.Lock()
        self.t = 0
        self.rng = np.random.default_rng()

    def tx(self, iq):
        with self.lock:
            self.pending = np.concatenate([self.pending, iq.astype(np.complex64)])
        time.sleep(len(iq) / self.fs)

    def rx(self):
        time.sleep(self.n / self.fs)
        with self.lock:
            sig = self.pending[:self.n]
            self.pending = self.pending[self.n:]
        out = np.zeros(self.n, dtype=np.complex64)
        out[:len(sig)] = sig * self.amp
        k = np.arange(self.t, self.t + self.n)
        self.t += self.n
        out *= np.exp(2j * np.pi * self.cfo / self.fs * k).astype(np.complex64)
        out += (self.sigma * (self.rng.standard_normal(self.n) +
                              1j * self.rng.standard_normal(self.n))).astype(np.complex64)
        return out


# ===================================================================== Bridge
class Bridge:
    def __init__(self, args, csp: CspCanInterface, sdr):
        self.a = args
        self.csp = csp
        self.sdr = sdr
        self.txq: queue.Queue[bytes] = queue.Queue(maxsize=args.tx_queue)
        self.tx_busy = threading.Event()
        self.running = True
        self.stats = dict(rf_rx=0, rf_rx_bad=0, can_tx=0, can_rx=0, rf_tx=0, tx_drop=0, ping=0)
        self.mod = GmskTransmitter(bitrate=args.bitrate, sps=args.sps, fs=args.fs,
                                   randomized=not args.no_randomize,
                                   preamble_bytes=args.preamble)
        self.demod = GmskReceiver(bitrate=args.bitrate, sps=args.sps, fs=args.fs,
                                  mode=args.frame_mode, frame_len=args.frame_len,
                                  max_len=args.max_len, randomized=not args.no_randomize,
                                  chan_cutoff_hz=args.chan_bw)

    # ---------------------------------------------------- CAN -> RF (downlink)
    def on_csp(self, pkt: CspPacket):
        self.stats["can_rx"] += 1
        if pkt.dport == CSP_PING_PORT:
            self.stats["ping"] += 1
            self.csp.send(CspPacket(src=self.a.addr, dst=pkt.src, dport=pkt.sport,
                                    sport=CSP_PING_PORT, data=pkt.data, pri=pkt.pri,
                                    flags=pkt.flags & CSP_FCRC32))
            return
        if pkt.dport != self.a.downlink_port:
            log.debug("abaikan %r", pkt)
            return
        frame = pkt.data
        if self.a.frame_mode == "tm" and len(frame) != self.a.frame_len:
            log.warning("frame downlink %d B, bukan %d B (frame-len)", len(frame), self.a.frame_len)
        if self.a.check_fecf and not fecf_ok(frame):
            log.warning("frame downlink dari OBC FECF salah, tetap dikirim")
        try:
            self.txq.put_nowait(frame)
        except queue.Full:
            self.stats["tx_drop"] += 1
            log.warning("antrian TX penuh, frame dibuang")

    def tx_loop(self):
        while self.running:
            try:
                frame = self.txq.get(timeout=0.5)
            except queue.Empty:
                continue
            iq = self.mod.burst(frame)
            self.tx_busy.set()
            try:
                self.sdr.tx(iq)
            finally:
                time.sleep(self.a.tx_guard)
                self.tx_busy.clear()
            self.stats["rf_tx"] += 1
            log.info("RF TX %d B (%.0f ms)", len(frame), 1e3 * len(iq) / self.a.fs)

    # ---------------------------------------------------- RF -> CAN (uplink)
    def rx_loop(self):
        while self.running:
            iq = self.sdr.rx()
            if self.a.half_duplex and self.tx_busy.is_set():
                continue
            for frame in self.demod.feed(iq):
                if self.a.check_fecf and not fecf_ok(frame):
                    self.stats["rf_rx_bad"] += 1
                    continue
                if self.a.scid is not None and self.a.frame_mode == "tm":
                    if parse_tm_header(frame)["scid"] != self.a.scid:
                        self.stats["rf_rx_bad"] += 1
                        continue
                self.stats["rf_rx"] += 1
                pkt = CspPacket(src=self.a.addr, dst=self.a.obc, dport=self.a.uplink_port,
                                sport=self.a.sport, data=frame,
                                flags=CSP_FCRC32 if self.a.csp_crc else 0)
                self.csp.send(pkt)
                self.stats["can_tx"] += 1
                log.info("RF RX frame %d B -> CSP %d:%d", len(frame), self.a.obc, self.a.uplink_port)

    def stats_loop(self):
        while self.running:
            time.sleep(self.a.stats_every)
            log.info("stat %s | asm=%d", self.stats, self.demod.stats["asm"])

    def run(self):
        self.csp.start(self.on_csp)
        for fn in (self.tx_loop, self.rx_loop, self.stats_loop):
            threading.Thread(target=fn, daemon=True).start()
        log.info("bridge jalan: CSP addr %d, OBC %d, uplink->port %d, downlink<-port %d",
                 self.a.addr, self.a.obc, self.a.uplink_port, self.a.downlink_port)
        while self.running:
            time.sleep(0.2)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="antSDR GMSK/CCSDS <-> CSP 1.x CAN bridge")
    g = p.add_argument_group("CSP / CAN")
    g.add_argument("--can", default="can0")
    g.add_argument("--addr", type=int, default=5, help="alamat CSP antSDR (0-31)")
    g.add_argument("--obc", type=int, default=1, help="alamat CSP OBC")
    g.add_argument("--uplink-port", type=int, default=10, help="port di OBC tujuan frame uplink")
    g.add_argument("--downlink-port", type=int, default=11, help="port di antSDR untuk frame downlink")
    g.add_argument("--sport", type=int, default=40, help="source port paket uplink")
    g.add_argument("--csp-crc", action="store_true", help="pakai CSP CRC32 di paket uplink")
    g = p.add_argument_group("RF / modem")
    g.add_argument("--uri", default="local:", help="libiio URI, mis. local: atau ip:192.168.1.10")
    g.add_argument("--rx-freq", type=float, default=437.5e6)
    g.add_argument("--tx-freq", type=float, default=437.5e6)
    g.add_argument("--rx-gain", type=float, default=None, help="dB, kosong = AGC")
    g.add_argument("--tx-gain", type=float, default=-10.0, help="dB (0 = maksimum, -89 = minimum)")
    g.add_argument("--fs", type=float, default=2.4e6, help="sample rate AD9361")
    g.add_argument("--rf-bw", type=float, default=200e3)
    g.add_argument("--bitrate", type=int, default=9600)
    g.add_argument("--sps", type=int, default=10)
    g.add_argument("--chan-bw", type=float, default=7200.0, help="filter kanal satu sisi (Hz)")
    g.add_argument("--rx-buf", type=int, default=2 ** 16)
    g.add_argument("--preamble", type=int, default=32, help="byte preamble 0x55")
    g.add_argument("--half-duplex", action="store_true", help="abaikan RX saat sedang TX")
    g.add_argument("--tx-guard", type=float, default=0.01, help="jeda setelah TX (detik)")
    g.add_argument("--tx-queue", type=int, default=32)
    g = p.add_argument_group("CCSDS")
    g.add_argument("--frame-mode", choices=["tm", "tc"], default="tm",
                   help="tm = panjang tetap, tc = panjang dari header TC")
    g.add_argument("--frame-len", type=int, default=223)
    g.add_argument("--max-len", type=int, default=256, help="maks panjang frame (mode tc)")
    g.add_argument("--no-randomize", action="store_true")
    g.add_argument("--no-fecf", dest="check_fecf", action="store_false", help="jangan cek CRC FECF")
    g.add_argument("--scid", type=lambda s: int(s, 0), default=None, help="filter SCID (mode tm)")
    g = p.add_argument_group("lain-lain")
    g.add_argument("--sim", action="store_true", help="loopback RF internal tanpa AD9361")
    g.add_argument("--sim-ebn0", type=float, default=20.0)
    g.add_argument("--stats-every", type=float, default=10.0)
    g.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    if a.sim:
        sdr = SimSdr(a.fs, a.rx_buf, a.sim_ebn0, bitrate=a.bitrate)
    else:
        sdr = AdiSdr(a.uri, a.fs, a.rx_freq, a.tx_freq, a.rx_gain, a.tx_gain, a.rf_bw, a.rx_buf)
    csp = CspCanInterface(a.can, a.addr)
    br = Bridge(a, csp, sdr)

    def stop(*_):
        br.running = False
        csp.stop()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    br.run()


if __name__ == "__main__":
    main()
