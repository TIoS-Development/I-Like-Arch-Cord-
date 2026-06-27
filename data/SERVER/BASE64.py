
class BASE64:
    _alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

    def __init__(self, session):
        self.session = session

    def encode(self, data: bytes) -> str:
        bits = ""
        for b in data:
            bits += f"{b:08b}"

        while len(bits) % 6 != 0:
            bits += "0"

        out = ""
        for i in range(0, len(bits), 6):
            chunk = bits[i:i+6]
            idx = int(chunk, 2)
            out += self._alphabet[idx]

        return out

    def decode(self, s: str) -> bytes:
        bits = ""
        for ch in s:
            idx = self._alphabet.find(ch)
            if idx == -1:
                continue
            bits += f"{idx:06b}"

        while len(bits) % 8 != 0:
            bits = bits[:-1]

        out = bytearray()
        for i in range(0, len(bits), 8):
            byte = bits[i:i+8]
            out.append(int(byte, 2))

        return bytes(out)
