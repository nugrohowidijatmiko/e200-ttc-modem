"""
CSP 1.x di atas CAN (CFP - CAN Fragmentation Protocol) memakai Linux SocketCAN.
Tanpa dependensi luar (pakai socket.AF_CAN bawaan Python).

Format sesuai libcsp 1.x (csp_if_can.c):
  CAN ID 29-bit extended:
    SRC    5 bit  [28..24]
    DST    5 bit  [23..19]
    TYPE   1 bit  [18]      0 = BEGIN, 1 = MORE
    REMAIN 8 bit  [17..10]  jumlah frame tersisa
    IDENT 10 bit  [9..0]    penghitung paket
  Frame BEGIN : [CSP header 4 byte BE][length 2 byte BE][data 0..2 byte]
  Frame MORE  : [data 1..8 byte]

  CSP 1.x header 32-bit:
    PRI 2 | SRC 5 | DST 5 | DPORT 6 | SPORT 6 | RES 4 | HMAC | XTEA | RDP | CRC
"""
from __future__ import annotations

import socket
import struct
import threading
import time
from dataclasses import dataclass, field

CAN_EFF_FLAG = 0x80000000
CAN_EFF_MASK = 0x1FFFFFFF
CAN_FRAME_FMT = "=IB3x8s"
CAN_FRAME_SIZE = struct.calcsize(CAN_FRAME_FMT)

CFP_SRC_SHIFT = 24
CFP_DST_SHIFT = 19
CFP_TYPE_SHIFT = 18
CFP_REMAIN_SHIFT = 10
CFP_BEGIN = 0
CFP_MORE = 1

CSP_FCRC32 = 0x01
CSP_FRDP = 0x02
CSP_FXTEA = 0x04
CSP_FHMAC = 0x08

CSP_PRIO_CRITICAL, CSP_PRIO_HIGH, CSP_PRIO_NORM, CSP_PRIO_LOW = 0, 1, 2, 3


# ---------------------------------------------------------------- CRC32C
def _make_crc32c_table():
    tbl = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ 0x82F63B78 if c & 1 else c >> 1
        tbl.append(c)
    return tbl


_CRC32C_TABLE = _make_crc32c_table()


def crc32c(data: bytes, crc: int = 0xFFFFFFFF, final: bool = True) -> int:
    """CRC32 Castagnoli seperti csp_crc32_memory() di libcsp."""
    for b in data:
        crc = _CRC32C_TABLE[(crc ^ b) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF if final else crc


# ---------------------------------------------------------------- Packet
@dataclass
class CspPacket:
    src: int
    dst: int
    dport: int
    sport: int
    data: bytes = b""
    pri: int = CSP_PRIO_NORM
    flags: int = 0
    timestamp: float = field(default_factory=time.time)

    def header(self) -> int:
        return (((self.pri & 0x3) << 30) | ((self.src & 0x1F) << 25) |
                ((self.dst & 0x1F) << 20) | ((self.dport & 0x3F) << 14) |
                ((self.sport & 0x3F) << 8) | (self.flags & 0xFF))

    @classmethod
    def from_header(cls, h: int, data: bytes = b""):
        return cls(pri=(h >> 30) & 0x3, src=(h >> 25) & 0x1F,
                   dst=(h >> 20) & 0x1F, dport=(h >> 14) & 0x3F,
                   sport=(h >> 8) & 0x3F, flags=h & 0xFF, data=data)

    def __repr__(self):
        return (f"CspPacket({self.src}:{self.sport} -> {self.dst}:{self.dport}, "
                f"pri={self.pri}, flags=0x{self.flags:02x}, len={len(self.data)})")


def cfp_make_id(src, dst, typ, remain, ident):
    return (((src & 0x1F) << CFP_SRC_SHIFT) | ((dst & 0x1F) << CFP_DST_SHIFT) |
            ((typ & 0x1) << CFP_TYPE_SHIFT) | ((remain & 0xFF) << CFP_REMAIN_SHIFT) |
            (ident & 0x3FF))


def cfp_parse_id(cid):
    return ((cid >> CFP_SRC_SHIFT) & 0x1F, (cid >> CFP_DST_SHIFT) & 0x1F,
            (cid >> CFP_TYPE_SHIFT) & 0x1, (cid >> CFP_REMAIN_SHIFT) & 0xFF,
            cid & 0x3FF)


# ---------------------------------------------------------------- Fragmentasi
def cfp_fragment(pkt: CspPacket, ident: int, mac: int | None = None,
                 crc_include_header: bool = False):
    """Ubah satu paket CSP menjadi list (can_id, data) persis seperti libcsp 1.x."""
    data = bytes(pkt.data)
    hdr = pkt.header()
    if pkt.flags & CSP_FCRC32:
        if crc_include_header:
            crc = crc32c(struct.pack(">I", hdr) + data)
        else:
            crc = crc32c(data)
        data += struct.pack(">I", crc)
    length = len(data)
    if length > 0xFFFF:
        raise ValueError("paket terlalu panjang")
    dst_mac = pkt.dst if mac is None else mac

    frames = []
    avail = 8 - 6
    nbytes = min(length, avail)
    remain = (length - nbytes + 7) // 8
    cid = cfp_make_id(pkt.src, dst_mac, CFP_BEGIN, remain, ident)
    frames.append((cid, struct.pack(">IH", hdr, length) + data[:nbytes]))
    tx = nbytes
    while tx < length:
        nbytes = min(8, length - tx)
        remain = (length - tx - nbytes + 7) // 8
        cid = cfp_make_id(pkt.src, dst_mac, CFP_MORE, remain, ident)
        frames.append((cid, data[tx:tx + nbytes]))
        tx += nbytes
    return frames


class CfpReassembler:
    """Menyusun ulang frame CAN menjadi paket CSP."""

    def __init__(self, timeout=1.0, crc_include_header=False):
        self.buf = {}
        self.timeout = timeout
        self.crc_include_header = crc_include_header
        self.dropped = 0

    def feed(self, can_id: int, data: bytes):
        src, dst, typ, remain, ident = cfp_parse_id(can_id)
        key = (src, ident)
        now = time.monotonic()
        # bersihkan buffer kedaluwarsa
        for k in [k for k, v in self.buf.items() if now - v["t"] > self.timeout]:
            del self.buf[k]
            self.dropped += 1

        if typ == CFP_BEGIN:
            if len(data) < 6:
                self.dropped += 1
                return None
            hdr, length = struct.unpack(">IH", data[:6])
            entry = {"hdr": hdr, "len": length, "data": bytearray(data[6:]),
                     "remain": remain, "t": now}
            self.buf[key] = entry
        else:
            entry = self.buf.get(key)
            if entry is None or remain != entry["remain"] - 1:
                if entry is not None:
                    del self.buf[key]
                self.dropped += 1
                return None
            entry["data"] += data
            entry["remain"] = remain
            entry["t"] = now

        if len(entry["data"]) >= entry["len"]:
            del self.buf[key]
            payload = bytes(entry["data"][:entry["len"]])
            pkt = CspPacket.from_header(entry["hdr"])
            if pkt.flags & CSP_FCRC32:
                if len(payload) < 4:
                    self.dropped += 1
                    return None
                body, rx_crc = payload[:-4], struct.unpack(">I", payload[-4:])[0]
                calc = crc32c((struct.pack(">I", entry["hdr"]) if self.crc_include_header else b"") + body)
                if calc != rx_crc:
                    self.dropped += 1
                    return None
                payload = body
            pkt.data = payload
            return pkt
        return None


# ---------------------------------------------------------------- Interface
class CspCanInterface:
    """
    Node CSP 1.x di SocketCAN.
      iface = CspCanInterface("can0", my_addr=5)
      iface.start(callback)     # callback(CspPacket) untuk paket ke alamat ini
      iface.send(CspPacket(...))
    """

    def __init__(self, ifname="can0", my_addr=5, promisc=False,
                 crc_include_header=False, sock=None):
        self.ifname = ifname
        self.addr = my_addr & 0x1F
        self.promisc = promisc
        self.crc_include_header = crc_include_header
        self._ident = 0
        self._lock = threading.Lock()
        self._rx = CfpReassembler(crc_include_header=crc_include_header)
        self._running = False
        self.sock = sock if sock is not None else self._open()

    def _open(self):
        s = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        if not self.promisc:
            # hanya terima frame extended yang DST-nya = alamat kita
            can_id = (self.addr << CFP_DST_SHIFT) | CAN_EFF_FLAG
            mask = (0x1F << CFP_DST_SHIFT) | CAN_EFF_FLAG
            s.setsockopt(socket.SOL_CAN_RAW, socket.CAN_RAW_FILTER,
                         struct.pack("=II", can_id, mask))
        s.bind((self.ifname,))
        return s

    def send(self, pkt: CspPacket, mac=None):
        with self._lock:
            ident = self._ident
            self._ident = (self._ident + 1) & 0x3FF
            for cid, data in cfp_fragment(pkt, ident, mac, self.crc_include_header):
                frame = struct.pack(CAN_FRAME_FMT, cid | CAN_EFF_FLAG, len(data),
                                    data.ljust(8, b"\x00"))
                for _ in range(100):
                    try:
                        self.sock.send(frame)
                        break
                    except OSError:  # ENOBUFS: antrian TX penuh, tunggu sebentar
                        time.sleep(0.001)
                else:
                    raise OSError("CAN TX gagal (bus off / tidak ada ACK?)")

    def start(self, callback):
        self._running = True
        t = threading.Thread(target=self._rx_loop, args=(callback,), daemon=True)
        t.start()
        return t

    def stop(self):
        self._running = False

    def _rx_loop(self, callback):
        self.sock.settimeout(0.5)
        while self._running:
            try:
                frame = self.sock.recv(CAN_FRAME_SIZE)
            except socket.timeout:
                continue
            cid, dlc, data = struct.unpack(CAN_FRAME_FMT, frame)
            if not cid & CAN_EFF_FLAG:
                continue
            pkt = self._rx.feed(cid & CAN_EFF_MASK, data[:dlc])
            if pkt is not None and (self.promisc or pkt.dst == self.addr):
                callback(pkt)
