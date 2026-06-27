

class HASH:
    def __init__(self, session):
        self.session = session
        self.OS = session.OS
        self.BASE64 = session.BASE64

    def load_config(self):
        raw = self.OS.read("/sys/hash")
        if not raw:
            return {
                "ALGO": "SHA256",
                "ROUNDS": 5000,
                "SALT_LEN": 16
            }

        cfg = {}
        for line in raw.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip()
            if v.isdigit():
                v = int(v)
            cfg[k] = v
        return cfg

    def salt(self, length):
        import os
        raw = os.urandom(length)
        return self.BASE64.encode(raw)

    def _sha256_fake(self, data: bytes) -> bytes:
        out = bytearray()
        seed = 0xA5
        for b in data:
            seed = (seed ^ b) & 0xFF
            seed = ((seed << 1) | (seed >> 7)) & 0xFF
            out.append(seed)
        return bytes(out)

    def hash(self, data: str, salt: str | None = None):
        cfg = self.load_config()

        algo = cfg.get("ALGO", "SHA256")
        rounds = cfg.get("ROUNDS", 5000)
        salt_len = cfg.get("SALT_LEN", 16)

        if salt is None:
            salt = self.salt(salt_len)

        h = (salt + data).encode("utf-8")

        for _ in range(rounds):
            if algo.upper() == "SHA256":
                h = self._sha256_fake(h)
            else:
                h = self._sha256_fake(h)

        encoded = self.BASE64.encode(h)
        return salt, encoded
