"""Minimal drivrutin för 128x64 OLED över I2C, SSD1306 eller SH1106.

Skärmar på 1,3 tum har ofta SH1106, som saknar SSD1306:ans horisontella
adressering och har bilden förskjuten två kolumner. Syns en smal rand med
skräp i högerkanten är det SH1106: sätt OLED_KIND = "sh1106" i profilen.
"""

import framebuf

ADDRESS = 0x3C


class OLED(framebuf.FrameBuffer):
    def __init__(self, i2c, kind="ssd1306", width=128, height=64, address=ADDRESS):
        self.i2c = i2c
        self.kind = kind
        self.width = width
        self.height = height
        self.address = address
        self.pages = height // 8
        self.buffer = bytearray(self.pages * width)
        super().__init__(self.buffer, width, height, framebuf.MONO_VLSB)
        self.init()

    def init(self):
        """Skicka startsekvensen. Anropas igen om skärmen har tappat ström."""
        width, height = self.width, self.height
        if self.kind == "sh1106":
            init = (0xAE, 0xD5, 0x80, 0xA8, height - 1, 0xD3, 0x00, 0x40,
                    0xAD, 0x8B, 0xA1, 0xC8, 0xDA, 0x12, 0x81, 0xCF,
                    0xD9, 0x1F, 0xDB, 0x40, 0xA4, 0xA6, 0xAF)
        else:
            init = (0xAE, 0x20, 0x00, 0x40, 0xA1, 0xA8, height - 1, 0xC8,
                    0xD3, 0x00, 0xDA, 0x02 if width > 2 * height else 0x12,
                    0xD5, 0x80, 0xD9, 0xF1, 0xDB, 0x30, 0x81, 0xCF,
                    0xA4, 0xA6, 0x8D, 0x14, 0xAF)
        for cmd in init:
            self.cmd(cmd)

    def cmd(self, c):
        self.i2c.writeto(self.address, bytes((0x80, c)))

    def show(self):
        if self.kind == "sh1106":
            for page in range(self.pages):
                self.cmd(0xB0 | page)
                self.cmd(0x02)   # kolumn 2: SH1106 har 132 kolumner, bilden börjar på 2
                self.cmd(0x10)
                start = page * self.width
                self.i2c.writevto(self.address,
                                  (b"\x40", memoryview(self.buffer)[start:start + self.width]))
        else:
            for c in (0x21, 0, self.width - 1, 0x22, 0, self.pages - 1):
                self.cmd(c)
            self.i2c.writevto(self.address, (b"\x40", self.buffer))
