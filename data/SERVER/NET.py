# network module, you can fix it.
import json, time, random, asyncio


class Packet:
    def __init__(self, proto, src_ip, src_port, dst_ip, dst_port, flags=None, payload=""):
        self.proto    = proto
        self.src_ip   = src_ip
        self.src_port = src_port
        self.dst_ip   = dst_ip
        self.dst_port = dst_port
        self.flags    = flags or []
        self.payload  = payload
        self.ts       = time.time()

    def __repr__(self):
        f = "+".join(self.flags) if self.flags else "-"
        return (f"[{self.proto}] {self.src_ip}:{self.src_port}"
                f" -> {self.dst_ip}:{self.dst_port} [{f}] {repr(self.payload[:60])}")


class Connection:
    """
    One end of a bidirectional pipe.
    send() on one side puts into the other's inbox.

    Usage:
        conn, err = NET.connect(target_session, port)
        if err: return err
        conn.send("hello")
        reply = await conn.recv()
        conn.close()
    """
    def __init__(self, local_ip, local_port, remote_ip, remote_port, proto="TCP"):
        self.local_ip    = local_ip
        self.local_port  = local_port
        self.remote_ip   = remote_ip
        self.remote_port = remote_port
        self.proto       = proto
        self.state       = "ESTABLISHED"
        self._inbox      = asyncio.Queue()
        self._peer       = None

    def _link(self, peer):
        self._peer = peer

    def send(self, data):
        if self.state != "ESTABLISHED":
            return False
        if self._peer:
            self._peer._inbox.put_nowait(data)
        return True

    async def recv(self, timeout=30):
        """Returns None on timeout or when connection is closed."""
        try:
            return await asyncio.wait_for(self._inbox.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def recv_nowait(self):
        try:
            return self._inbox.get_nowait()
        except:
            return None

    def closed(self):
        return self.state == "CLOSED"

    def close(self):
        self.state = "CLOSED"
        if self._peer:
            self._peer.state = "CLOSED"
            try:
                self._peer._inbox.put_nowait(None)
            except:
                pass

    def __repr__(self):
        return (f"<Connection {self.local_ip}:{self.local_port}"
                f" <-> {self.remote_ip}:{self.remote_port} [{self.state}]>")


class Listener:
    """
    Returned by NET.listen(port).
    await listener.accept() blocks until a client connects.

    Usage (inside a background task):
        listener = NET.listen(9000, "myserver", banner="Welcome!")

        async def server_loop():
            while True:
                conn = await listener.accept()
                if conn is None:
                    break
                data = await conn.recv()
                conn.send("echo: " + str(data))
                conn.close()

        session.PROC.spawn_background("myserver", session.user_id, server_loop())
    """
    def __init__(self, port, net):
        self.port   = port
        self._net   = net
        self._queue = asyncio.Queue()
        self.open   = True

    async def accept(self, timeout=None):
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def accept_nowait(self):
        try:
            return self._queue.get_nowait()
        except:
            return None

    def close(self):
        self.open = False
        self._net.close_port(self.port)


class Service:
    def __init__(self, port, name, proto="TCP", banner=""):
        self.port     = port
        self.name     = name
        self.proto    = proto
        self.banner   = banner
        self.open     = True
        self.listener = None

    def to_dict(self):
        return {"port": self.port, "name": self.name,
                "proto": self.proto, "banner": self.banner, "open": self.open}


class NET:
    _registry = {}

    def __init__(self, session):
        self.session    = session
        self.ip         = self._init_ip()
        self.services   = {}
        self.packet_log = []
        self.firewall   = []
        NET._registry[self.ip] = session
        self._load_services()

    def _init_ip(self):
        raw = self.session.OS.read("/etc/net/ip")
        if raw and raw.strip():
            return raw.strip()
        uid = self.session.user_id
        ip  = f"10.{(uid >> 16) & 0xFF}.{(uid >> 8) & 0xFF}.{uid & 0xFF}"
        self.session.OS.mkdir("/etc/net", parents=True)
        self.session.OS.write("/etc/net/ip", ip)
        return ip

    def get_ip(self):
        return self.ip

    def resolve(self, host):
        """IP or /etc/hosts hostname -> session. None if not online."""
        if host in NET._registry:
            return NET._registry[host]
        for line in (self.session.OS.read("/etc/hosts") or "").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1] == host:
                return NET._registry.get(parts[0])
        return None

    def add_host(self, ip, hostname):
        cur = self.session.OS.read("/etc/hosts") or ""
        self.session.OS.write("/etc/hosts", cur + f"{ip} {hostname}\n")

    def who(self):
        """All online VMs: {ip: user_id}"""
        return {ip: s.user_id for ip, s in NET._registry.items()}

    def fw_add(self, action, proto="*", port="*"):
        """action: ACCEPT | DROP. First match wins."""
        self.firewall.append({"action": action, "proto": proto, "port": port})

    def fw_clear(self):
        self.firewall.clear()

    def fw_list(self):
        return list(self.firewall)

    def _fw_allow(self, proto, port):
        for rule in self.firewall:
            if (rule["port"]  in ("*", port, str(port))) and \
               (rule["proto"] in ("*", proto)):
                return rule["action"] == "ACCEPT"
        return True

    def open_port(self, port, name, proto="TCP", banner=""):
        """Register port as open. Returns Service object."""
        svc = Service(port, name, proto, banner)
        self.services[port] = svc
        self._save_services()
        return svc

    def close_port(self, port):
        svc = self.services.pop(port, None)
        if svc:
            self._save_services()
            return True
        return False

    def port_open(self, port):
        svc = self.services.get(port)
        return svc is not None and svc.open

    def list_ports(self):
        return list(self.services.values())

    def _save_services(self):
        self.session.OS.mkdir("/etc/net", parents=True)
        self.session.OS.write("/etc/net/services.json",
            json.dumps([s.to_dict() for s in self.services.values()], indent=2))

    def _load_services(self):
        raw = self.session.OS.read("/etc/net/services.json")
        if not raw:
            return
        try:
            for e in json.loads(raw):
                svc = Service(e["port"], e["name"], e.get("proto","TCP"), e.get("banner",""))
                svc.open = e.get("open", True)
                self.services[e["port"]] = svc
        except:
            pass

    def listen(self, port, name="service", proto="TCP", banner=""):
        """Open port and return Listener. Use with PROC.spawn_background()."""
        svc = self.open_port(port, name, proto, banner)
        listener = Listener(port, self)
        svc.listener = listener
        return listener

    def connect(self, target_session, port, proto="TCP"):
        """
        Connect to target_session:port.
        Returns (Connection, None) or (None, error_string).
        Logs full TCP handshake to both packet logs.
        """
        t_net = target_session.NET

        if not t_net.port_open(port):
            self._log(Packet(proto, self.ip, 0, t_net.ip, port, ["RST"]))
            return (None, f"Connection refused: {t_net.ip}:{port}")

        if not t_net._fw_allow(proto, port):
            return (None, f"Firewall DROP: {t_net.ip}:{port}")

        ep = random.randint(49152, 65535)

        self._log(Packet(proto,  self.ip,  ep,   t_net.ip, port, ["SYN"]))
        t_net._log(Packet(proto, self.ip,  ep,   t_net.ip, port, ["SYN"]))
        t_net._log(Packet(proto, t_net.ip, port, self.ip,  ep,   ["SYN","ACK"]))
        self._log(Packet(proto,  t_net.ip, port, self.ip,  ep,   ["SYN","ACK"]))
        self._log(Packet(proto,  self.ip,  ep,   t_net.ip, port,  ["ACK"]))
        t_net._log(Packet(proto, self.ip,  ep,   t_net.ip, port,  ["ACK"]))

        client_conn = Connection(self.ip,   ep,   t_net.ip, port, proto)
        server_conn = Connection(t_net.ip,  port, self.ip,  ep,   proto)
        client_conn._link(server_conn)
        server_conn._link(client_conn)

        svc = t_net.services.get(port)
        if svc and svc.listener:
            svc.listener._queue.put_nowait(server_conn)
        if svc and svc.banner:
            client_conn._inbox.put_nowait(svc.banner)

        return (client_conn, None)

    def udp_send(self, target_session, port, payload):
        """Fire-and-forget. Arrives at target listener as a single-recv Connection."""
        t_net = target_session.NET
        if not t_net._fw_allow("UDP", port):
            return False
        pkt = Packet("UDP", self.ip, 0, t_net.ip, port, [], payload)
        self._log(pkt)
        t_net._log(pkt)
        svc = t_net.services.get(port)
        if svc and svc.listener:
            fake = Connection(self.ip, 0, t_net.ip, port, "UDP")
            fake._inbox.put_nowait(payload)
            svc.listener._queue.put_nowait(fake)
        return True

    def ping(self, host, count=4):
        target = self.resolve(host)
        dst = target.NET.ip if target else host
        lines = []
        for i in range(count):
            self._log(Packet("ICMP", self.ip, 0, dst, 0, ["ECHO"]))
            rtt = round(random.uniform(0.4, 80.0), 2)
            lines.append(f"64 bytes from {dst}: icmp_seq={i+1} ttl=64 time={rtt} ms")
        return "\n".join(lines)

    def scan(self, target_session, ports=None, proto="TCP"):
        """Probe target's open ports. Returns list of Service objects."""
        t_net = target_session.NET
        if ports is None:
            ports = list(range(1, 1025))
        results = []
        for port in ports:
            svc = t_net.services.get(port)
            if svc and svc.open and t_net._fw_allow(proto, port):
                self._log(Packet(proto,  self.ip,  0,    t_net.ip, port, ["SYN"]))
                t_net._log(Packet(proto, self.ip,  0,    t_net.ip, port, ["SYN"]))
                self._log(Packet(proto,  t_net.ip, port, self.ip,  0,    ["RST","ACK"]))
                results.append(svc)
        return results

    def _log(self, pkt):
        self.packet_log.append(pkt)
        if len(self.packet_log) > 512:
            self.packet_log.pop(0)

    def get_log(self, n=20, proto=None, host=None):
        log = self.packet_log
        if proto:
            log = [p for p in log if p.proto == proto.upper()]
        if host:
            log = [p for p in log if host in (p.src_ip, p.dst_ip)]
        return log[-n:]

    def check_shadow(self, username, password):
        """Check /etc/shadow on this VM. Use this inside custom SSH servers."""
        shadow = self.session.OS.read("/etc/shadow") or ""
        HASH   = self.session.HASH
        for line in shadow.strip().splitlines():
            parts = line.split(":")
            if len(parts) < 2 or parts[0] != username:
                continue
            stored = parts[1]
            if "$" not in stored:
                continue
            salt, hashed = stored.split("$", 1)
            _, check = HASH.hash(password, salt)
            if check == hashed:
                return True
        return False
