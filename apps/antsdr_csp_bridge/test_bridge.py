#!/usr/bin/env python3
"""
Uji tanpa hardware:
  1. CFP: fragmentasi/penyusunan ulang CSP 1.x (+CRC32)
  2. CCSDS: randomizer, FECF
  3. GMSK: loopback dengan noise & offset frekuensi
  4. End-to-end: OBC-sim <-CAN palsu-> bridge <-RF loopback-> bridge -> OBC-sim
"""
from __future__ import annotations

import queue
import struct
import threading
import time

import numpy as np

import antsdr_bridge as ab
from ccsds import build_tm_frame, fecf_ok, randomize, _PN
from csp1_can import (CAN_FRAME_FMT, CSP_FCRC32, CfpReassembler, CspCanInterface,
                      CspPacket, cfp_fragment, cfp_parse_id, crc32c)
from gmsk import GmskReceiver, GmskTransmitter


class FakeCanBus:
    """Bus CAN di memori: frame dari satu node diterima semua node lain."""

    def __init__(self):
        self.nodes = []

    def socket(self):
        s = _FakeSock(self)
        self.nodes.append(s)
        return s


class _FakeSock:
    def __init__(self, bus):
        self.bus, self.q, self.to = bus, queue.Queue(), None

    def send(self, frame):
        for n in self.bus.nodes:
            if n is not self:
                n.q.put(frame)

    def settimeout(self, t):
        self.to = t

    def recv(self, n):
        try:
            return self.q.get(timeout=self.to)
        except queue.Empty:
            import socket
            raise socket.timeout


def test_cfp():
    rng = np.random.default_rng(0)
    for n in [0, 1, 2, 3, 10, 100, 223, 252]:
        for flags in (0, CSP_FCRC32):
            pkt = CspPacket(src=5, dst=1, dport=10, sport=40, flags=flags,
                            data=bytes(rng.integers(0, 256, n, dtype=np.uint8)))
            frames = cfp_fragment(pkt, ident=77)
            # cek struktur seperti libcsp 1.x
            src, dst, typ, remain, ident = cfp_parse_id(frames[0][0])
            assert (src, dst, typ, ident) == (5, 1, 0, 77)
            assert remain == len(frames) - 1
            assert struct.unpack(">I", frames[0][1][:4])[0] == pkt.header()
            r = CfpReassembler()
            out = None
            for cid, d in frames:
                out = r.feed(cid, d) or out
            assert out is not None and out.data == pkt.data and out.dport == 10, n
    assert crc32c(b"123456789") == 0xE3069283        # nilai cek standar CRC32C
    print("OK  CFP / CSP 1.x")


def test_ccsds():
    assert _PN[:8].hex() == "ff480ec09a0d70bc"
    fr = build_tm_frame(b"halo", scid=0x123)
    assert len(fr) == 223 and fecf_ok(fr) and randomize(randomize(fr)) == fr
    print("OK  CCSDS (PN, FECF)")


def test_gmsk():
    rng = np.random.default_rng(1)
    tx, fs = GmskTransmitter(), 2.4e6
    frames = [build_tm_frame(bytes(rng.integers(0, 256, 100, dtype=np.uint8)), scid=0x123, mcfc=i)
              for i in range(20)]
    parts = []
    for fr in frames:
        parts += [np.zeros(int(rng.integers(1000, 50000)), np.complex64), tx.burst(fr)]
    x = np.concatenate(parts + [np.zeros(100000, np.complex64)]) * 0.3
    for cfo, ebn0 in [(0, 20), (1500, 16), (-1500, 16)]:
        sigma = np.sqrt(0.09 * (fs / 9600) / 10 ** (ebn0 / 10) / 2)
        y = (x * np.exp(1j * (2 * np.pi * cfo / fs * np.arange(len(x)) + 0.7)) +
             sigma * (rng.standard_normal(len(x)) + 1j * rng.standard_normal(len(x)))).astype(np.complex64)
        rx, out = GmskReceiver(), []
        t0 = time.time()
        for i in range(0, len(y), 65536):
            out += rx.feed(y[i:i + 65536])
        good = sum(1 for o in out if fecf_ok(o) and o in frames)
        print(f"OK  GMSK cfo={cfo:+5d} Hz Eb/N0={ebn0} dB: {good}/20 frame benar "
              f"(proses {time.time() - t0:.2f}s untuk {len(y) / fs:.1f}s sinyal)")
        assert good >= 19


def test_end_to_end():
    bus = FakeCanBus()
    args = ab.parse_args(["--sim", "--sim-ebn0", "18", "--stats-every", "100"])
    bridge_if = CspCanInterface(my_addr=args.addr, sock=bus.socket())
    obc_if = CspCanInterface(my_addr=args.obc, sock=bus.socket())
    sdr = ab.SimSdr(args.fs, args.rx_buf, ebn0_db=18, cfo_hz=800)
    br = ab.Bridge(args, bridge_if, sdr)
    threading.Thread(target=br.run, daemon=True).start()

    got, pong = [], []
    obc_if.start(lambda p: (got if p.dport == args.uplink_port else pong).append(p))
    time.sleep(0.3)

    obc_if.send(CspPacket(src=1, dst=5, dport=1, sport=33, data=b"ping"))
    sent = []
    for i in range(5):
        fr = build_tm_frame(f"TM #{i}".encode(), scid=0x123, mcfc=i)
        sent.append(fr)
        obc_if.send(CspPacket(src=1, dst=5, dport=args.downlink_port, sport=34, data=fr))
    t0 = time.time()
    while len(got) < 5 and time.time() - t0 < 15:
        time.sleep(0.1)
    br.running = False
    ok = sum(1 for p in got if p.data in sent)
    print(f"OK  end-to-end: ping={'balas' if pong and pong[0].data == b'ping' else 'GAGAL'}, "
          f"{ok}/5 frame OBC->CAN->GMSK->RF->GMSK->CAN->OBC kembali utuh")
    assert pong and ok >= 4


if __name__ == "__main__":
    test_cfp()
    test_ccsds()
    test_gmsk()
    test_end_to_end()
    print("SEMUA UJI LULUS")
