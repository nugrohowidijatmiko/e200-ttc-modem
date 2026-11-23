#!/usr/bin/env python3
"""
Simulator OBC (CSP 1.x di CAN) untuk menguji bridge tanpa OBC asli.
  - ping antSDR (CSP port 1)
  - kirim frame CCSDS TM ke antSDR:downlink_port secara periodik
  - tampilkan frame uplink yang masuk di port uplink_port

  python3 obc_sim.py --can vcan0 --addr 1 --antsdr 5
"""
from __future__ import annotations

import argparse
import time

from ccsds import build_tm_frame, fecf_ok, parse_tm_header
from csp1_can import CspCanInterface, CspPacket

PING_SPORT = 33


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--can", default="vcan0")
    p.add_argument("--addr", type=int, default=1)
    p.add_argument("--antsdr", type=int, default=5)
    p.add_argument("--uplink-port", type=int, default=10)
    p.add_argument("--downlink-port", type=int, default=11)
    p.add_argument("--scid", type=lambda s: int(s, 0), default=0x123)
    p.add_argument("--frame-len", type=int, default=223)
    p.add_argument("--period", type=float, default=2.0)
    p.add_argument("--count", type=int, default=0, help="0 = terus-menerus")
    a = p.parse_args(argv)

    csp = CspCanInterface(a.can, a.addr)
    ping_t = {}
    rx_frames = []

    def on_pkt(pkt: CspPacket):
        if pkt.dport == PING_SPORT and pkt.sport == 1:
            t0 = ping_t.pop(pkt.data, None)
            if t0:
                print(f"[OBC] ping antSDR OK {1e3 * (time.time() - t0):.1f} ms")
        elif pkt.dport == a.uplink_port:
            fr = pkt.data
            h = parse_tm_header(fr) if len(fr) >= 6 else {}
            print(f"[OBC] uplink {len(fr)} B dari {pkt.src}:{pkt.sport} "
                  f"FECF={'OK' if fecf_ok(fr) else 'SALAH'} scid={hex(h['scid']) if h else '?'} "
                  f"mcfc={h.get('mcfc')} data={fr[6:22].hex()}")
            rx_frames.append(fr)

    csp.start(on_pkt)
    payload = b"\x00" * 4
    ping_t[payload] = time.time()
    csp.send(CspPacket(src=a.addr, dst=a.antsdr, dport=1, sport=PING_SPORT, data=payload))

    i = 0
    while a.count == 0 or i < a.count:
        time.sleep(a.period)
        msg = f"TM dari OBC #{i} t={time.time():.0f}".encode()
        fr = build_tm_frame(msg, scid=a.scid, mcfc=i & 0xFF, vcfc=i & 0xFF, frame_len=a.frame_len)
        csp.send(CspPacket(src=a.addr, dst=a.antsdr, dport=a.downlink_port, sport=34, data=fr))
        print(f"[OBC] downlink frame #{i} {len(fr)} B -> {a.antsdr}:{a.downlink_port}")
        i += 1
    time.sleep(3)
    return rx_frames


if __name__ == "__main__":
    main()
