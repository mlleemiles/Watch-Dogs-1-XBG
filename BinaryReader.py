import struct

class BinaryReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.size = len(data)

    def tell(self):
        return self.pos

    def eof(self):
        return self.pos >= self.size

    def align(self, alignment):
        mask = alignment - 1
        if self.pos & mask:
            self.pos = (self.pos + mask) & ~mask

    def skip(self, size):
        self.pos += size

    def u8(self):
        v = self.data[self.pos]
        self.pos += 1
        return v

    def u16(self):
        v = struct.unpack_from("<H", self.data, self.pos)[0]
        self.pos += 2
        return v

    def u32(self):
        v = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return v

    def f32(self):
        v = struct.unpack_from("<f", self.data, self.pos)[0]
        self.pos += 4
        return v

    def bytes(self, size):
        b = self.data[self.pos:self.pos+size]
        self.pos += size
        return b

    def string(self, size):
        return self.bytes(size).rstrip(b"\x00").decode("utf-8", errors="replace")
