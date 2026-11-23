"""
Modem GMSK (BT=0.5, h=0.5) dengan numpy/scipy + frame sync ASM CCSDS.

TX : frame CCSDS -> randomize -> [preamble 0x55][ASM][frame][postamble] -> GMSK -> upsample
RX : IQ -> decimasi -> diskriminator FM -> cari ASM di semua fase sampel -> frame CCSDS
"""
from __future__ import annotations

from collections import deque

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import firwin, lfilter, resample_poly, upfirdn

from ccsds import ASM, randomize, tc_frame_length

ASM_BITS = np.unpackbits(np.frombuffer(ASM, dtype=np.uint8))
ASM_PM = (2.0 * ASM_BITS - 1.0).astype(np.float32)


# --------------------------------------------------------------------- TX
def gaussian_taps(bt: float, sps: int, span: int = 4) -> np.ndarray:
    t = np.arange(-span * sps / 2, span * sps / 2 + 1) / sps
    sigma = np.sqrt(np.log(2)) / (2 * np.pi * bt)
    g = np.exp(-t ** 2 / (2 * sigma ** 2))
    return g / g.sum()


def gmsk_modulate(bits: np.ndarray, sps: int, bt: float = 0.5, ramp_symbols: int = 2) -> np.ndarray:
    nrz = 2.0 * bits.astype(np.float32) - 1.0
    freq = np.convolve(np.repeat(nrz, sps), gaussian_taps(bt, sps))
    phase = (np.pi / 2 / sps) * np.cumsum(freq)
    iq = np.exp(1j * phase).astype(np.complex64)
    # ramp amplitudo di awal & akhir burst supaya spektrum tidak melebar
    n = ramp_symbols * sps
    if n > 0 and len(iq) > 2 * n:
        r = (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, n))).astype(np.float32)
        iq[:n] *= r
        iq[-n:] *= r[::-1]
    return iq


def build_burst_bits(frame: bytes, randomized: bool = True,
                     preamble_bytes: int = 32, postamble_bytes: int = 4) -> np.ndarray:
    body = randomize(frame) if randomized else frame
    raw = b"\x55" * preamble_bytes + ASM + body + b"\x55" * postamble_bytes
    return np.unpackbits(np.frombuffer(raw, dtype=np.uint8))


class GmskTransmitter:
    def __init__(self, bitrate=9600, sps=10, fs=2.4e6, bt=0.5, randomized=True,
                 preamble_bytes=32, postamble_bytes=4):
        self.sps = sps
        self.up = int(round(fs / (bitrate * sps)))
        if abs(self.up * bitrate * sps - fs) > 1e-6:
            raise ValueError("fs harus kelipatan bulat dari bitrate*sps")
        self.bt = bt
        self.randomized = randomized
        self.pre = preamble_bytes
        self.post = postamble_bytes

    def burst(self, frame: bytes) -> np.ndarray:
        """Kembalikan IQ complex64 di laju fs (amplitudo <= 1)."""
        bits = build_burst_bits(frame, self.randomized, self.pre, self.post)
        bb = gmsk_modulate(bits, self.sps, self.bt)
        if self.up == 1:
            return bb
        return resample_poly(bb, self.up, 1).astype(np.complex64)


# --------------------------------------------------------------------- RX
class StreamDecimator:
    """Decimator FIR polyphase yang kontinu antar-blok (tanpa glitch di batas buffer)."""

    def __init__(self, decim: int, taps_per_phase: int = 10):
        self.D = decim
        self.L = decim * taps_per_phase + 1          # (L-1) kelipatan D
        self.h = firwin(self.L, 0.5 / decim) if decim > 1 else np.array([1.0])
        self.buf = np.zeros(0, dtype=np.complex64)

    def process(self, x: np.ndarray) -> np.ndarray:
        if self.D == 1:
            return x.astype(np.complex64)
        buf = np.concatenate([self.buf, x.astype(np.complex64)])
        if len(buf) < self.L:
            self.buf = buf
            return np.zeros(0, dtype=np.complex64)
        y = upfirdn(self.h, buf, 1, self.D)
        m0 = (self.L - 1) // self.D
        m_last = (len(buf) - 1) // self.D
        out = y[m0:m_last + 1]
        n_next = (m_last + 1) * self.D
        self.buf = buf[n_next - (self.L - 1):]
        return out.astype(np.complex64)


class GmskReceiver:
    """
    Demodulator GMSK non-koheren + frame sync.
      mode="tm" : frame CCSDS TM panjang tetap `frame_len`
      mode="tc" : panjang dibaca dari header TC (maks `max_len`)
    feed(iq_fs) -> list[bytes] (frame CCSDS yang sudah di-derandomize)
    """

    def __init__(self, bitrate=9600, sps=10, fs=2.4e6, mode="tm", frame_len=223,
                 max_len=256, randomized=True, asm_threshold=3, chunk_s=0.25,
                 chan_cutoff_hz=7200.0):
        """chan_cutoff_hz: lebar filter kanal satu sisi. Default 0.75*bitrate.
        Offset frekuensi (Doppler) harus jauh lebih kecil dari ini (± ~2 kHz)."""
        self.sps = sps
        decim = int(round(fs / (bitrate * sps)))
        if abs(decim * bitrate * sps - fs) > 1e-6:
            raise ValueError("fs harus kelipatan bulat dari bitrate*sps")
        self.decim = StreamDecimator(decim)
        fs_bb = bitrate * sps
        self.chan_h = firwin(8 * sps + 1, min(chan_cutoff_hz / (fs_bb / 2), 0.99))
        self.chan_zi = np.zeros(len(self.chan_h) - 1, dtype=np.complex64)
        self.mode = mode
        self.frame_len = frame_len
        self.max_len = max_len if mode == "tc" else frame_len
        self.randomized = randomized
        self.thr = 32 - 2 * asm_threshold
        self.overlap = (32 + 8 * self.max_len + 64) * sps
        self.chunk = int(chunk_s * bitrate * sps)
        self.buf = np.zeros(0, dtype=np.complex64)
        self.buf_start = 0
        self.recent = deque(maxlen=128)
        self.stats = {"asm": 0, "frames": 0}

    def feed(self, iq: np.ndarray) -> list:
        bb = self.decim.process(iq)
        if len(bb):
            bb, self.chan_zi = lfilter(self.chan_h, 1.0, bb, zi=self.chan_zi)
            bb = bb.astype(np.complex64)
        self.buf = np.concatenate([self.buf, bb])
        frames = []
        while len(self.buf) >= self.overlap + self.chunk:
            frames += self._process(self.buf)
            keep = self.overlap
            self.buf_start += len(self.buf) - keep
            self.buf = self.buf[-keep:]
        return frames

    def flush(self) -> list:
        frames = self._process(self.buf) if len(self.buf) > 64 * self.sps else []
        return frames

    # ---------------------------------------------------------------
    def _process(self, x: np.ndarray) -> list:
        sps = self.sps
        d = np.angle(x[1:] * np.conj(x[:-1])).astype(np.float32)
        f_raw = uniform_filter1d(d, sps, mode="nearest")          # integrasi 1 simbol
        # buang DC kasar (offset frekuensi) hanya untuk deteksi ASM
        f = f_raw - uniform_filter1d(f_raw, 256 * sps, mode="nearest")

        cands = []
        for o in range(sps):
            s = f[o::sps]
            if len(s) < 32:
                continue
            hard = np.where(s > 0, 1.0, -1.0).astype(np.float32)
            c = np.correlate(hard, ASM_PM, mode="valid")
            for k in np.nonzero(c >= self.thr)[0]:
                seg = s[k:k + 32]
                score = float(np.dot(seg, ASM_PM))   # bukaan mata terbesar = fase terbaik
                cands.append((self.buf_start + o + k * sps, o, int(k), score))
        if not cands:
            return []

        # kelompokkan deteksi yang berdekatan (fase sampel berbeda, simbol sama)
        cands.sort()
        groups, cur = [], [cands[0]]
        for c in cands[1:]:
            if c[0] - cur[-1][0] < sps:
                cur.append(c)
            else:
                groups.append(cur)
                cur = [c]
        groups.append(cur)

        frames = []
        for g in groups:
            pos, o, k, _ = max(g, key=lambda c: c[3])
            if any(abs(pos - p) < 4 * sps for p in self.recent):
                continue
            # DC halus per-frame diestimasi dari preamble 0x55 (rata-rata nol)
            s = f_raw[o::sps]
            pre = s[max(0, k - 128):k]
            s = s - (float(np.mean(pre)) if len(pre) >= 32 else float(np.mean(f_raw) - np.mean(f)))
            start = k + 32
            n_bytes = self.frame_len
            if self.mode == "tc":
                if len(s) < start + 40:
                    continue
                hdr = np.packbits((s[start:start + 40] > 0).astype(np.uint8)).tobytes()
                if self.randomized:
                    hdr = randomize(hdr)
                n_bytes = tc_frame_length(hdr)
                if n_bytes < 7 or n_bytes > self.max_len:
                    self.recent.append(pos)
                    continue
            if len(s) < start + 8 * n_bytes:
                continue                     # belum lengkap; tunggu blok berikut
            self.stats["asm"] += 1
            bits = (s[start:start + 8 * n_bytes] > 0).astype(np.uint8)
            frame = np.packbits(bits).tobytes()
            if self.randomized:
                frame = randomize(frame)
            self.recent.append(pos)
            frames.append(frame)
        return frames
