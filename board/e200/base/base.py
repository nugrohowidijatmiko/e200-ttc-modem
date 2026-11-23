import pynq

__all__ = ['BaseOverlay']


class BaseOverlay(pynq.Overlay):
    """Overlay dasar antSDR E200 (AD9361 + Ethernet PL + CAN0 via EMIO)."""

    def __init__(self, bitfile_name='base.bit', **kwargs):
        super().__init__(bitfile_name, **kwargs)
