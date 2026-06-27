#archcord os module bc i like  my pc
import os

import json

class OS:
    def __init__(self, session):
        self.session = session
        self.user_id = session.user_id
        self.account_id = session.account_id
        self.fs_root = session.fs_root
        

    def sanitize(self, path):
        # Replace characters Windows hates (alot of them)
        bad = '<>:"\\|?*'
        for c in bad:
            path = path.replace(c, "_")
        return path


    def _real(self, path):
        path = path.replace("\\", "/")

        if ":" in path:
            path = "/" + path.split(":", 1)[1].lstrip("/")

        path = self.sanitize(path)

        return os.path.join(self.fs_root, path.lstrip("/"))

    def ssh_login(self, uid, account, password):
        from bot import account_root, fs_root, load_config
        import os

        acc_path = account_root(uid, account)
        if not os.path.exists(acc_path):
            return (False, f"ssh: account '{account}' not found for user {uid}")

        cfg = load_config(uid, account)
        if "password" in cfg and cfg["password"] != password:
            return (False, "ssh: authentication failed")

        self.fs_root = fs_root(uid, account)

        return (True, cfg)


    def ssh_logout(self, uid, account):
        from bot import fs_root, load_config

        self.fs_root = fs_root(uid, account)

        return load_config(uid, account)



     # fs api that works if you dont look at it

    def listdir(self, path="/"):
        """Return list of files in a directory."""
        if path.startswith("/repo/"):
            host_path = os.path.join("data", path.lstrip("/"))
            if os.path.isdir(host_path):
                return os.listdir(host_path)
            return []
        rp = self._real(path)
        if not os.path.exists(rp):
            return []
        try:
            return os.listdir(rp)
        except:
            return []

    def raw_read(self, path):
        rp = self._real(path)
        if not os.path.exists(rp):
            return None
        with open(rp, "r", encoding="utf-8", errors="replace") as f:
            return f.read()


    def raw_write(self, path, data):
        rp = self._real(path)
        os.makedirs(os.path.dirname(rp), exist_ok=True)
        with open(rp, "w", encoding="utf-8", errors="replace") as f:
            f.write(data)



    def read(self, path):
        links = self.load_links()
        if path in links and links[path]["type"] == "hard":
            path = links[path]["target"]

        if path.startswith("/repo/"):
            host_path = os.path.join("data", path.lstrip("/"))
            if os.path.exists(host_path):
                with open(host_path, "r", encoding="utf-8") as f:
                    return f.read()
            return None

        path = self.normalize(path)

        rp = self._real(path)
        if os.path.isdir(rp):
            return ""
        try:
            with open(rp, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except (FileNotFoundError, PermissionError, OSError):
            return ""



    def write(self, path, data, session=None):
        quotas = self.get_quotas()
        limit = quotas.get(self.user_id, 5 * 1024 * 1024 * 1024)

        used = 0
        for root, dirs, files in os.walk(self.fs_root):
            for f in files:
                try:
                    fp = os.path.join(root, f)
                    used += os.path.getsize(fp)
                except:
                    pass

        new_size = len(data.encode("utf-8")) if isinstance(data, str) else len(data)
        if used + new_size > limit:
            return "ERROR: quota exceeded"

        links = self.load_links()
        if path in links and links[path]["type"] == "hard":
            path = links[path]["target"]

        path = self.normalize(path, session)

        self.raw_write(path, data)
        return True


    def _perm_path(self):
        """
        permissions.json lives INSIDE the VM filesystem at:
        /etc/permissions.json
        """
        return self._real("/etc/permissions.json")

    def load_permissions(self):
        path = self._perm_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

    def save_permissions(self, perms):
        path = self._perm_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(perms, f, indent=2)

    def get_mode(self, vm_path):
        perms = self.load_permissions()
        return perms.get(vm_path, {}).get("mode")

    def set_mode(self, vm_path, mode, owner):
        perms = self.load_permissions()
        if vm_path not in perms:
            perms[vm_path] = {}
        perms[vm_path]["mode"] = mode
        perms[vm_path]["owner"] = owner
        self.save_permissions(perms)





    def append(self, path, data, session=None):
        links = self.load_links()
        if path in links and links[path]["type"] == "hard":
            path = links[path]["target"]
    
        path = self.normalize(path, session)
    
        rp = self._real(path)
    
        os.makedirs(os.path.dirname(rp), exist_ok=True)
    
        with open(rp, "a", encoding="utf-8") as f:
            f.write(data)
    
        return True




    def delete(self, path):
        """Delete file or directory recursively."""
        links = self.load_links()
        if path in links:
            del links[path]
            self.save_links(links)
            return True

        rp = self._real(path)
        if not os.path.exists(rp):
            return False

        if os.path.isdir(rp):
            for root, dirs, files in os.walk(rp, topdown=False):
                for name in files:
                    try:
                        os.remove(os.path.join(root, name))
                    except:
                        pass
                for name in dirs:
                    try:
                        os.rmdir(os.path.join(root, name))
                    except:
                        pass
            try:
                os.rmdir(rp)
            except:
                pass
        else:
            try:
                os.remove(rp)
            except:
                pass

        return True

    def get_quotas(self):
        path = "data/SERVER/user/quotas.json"
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

    def save_quotas(self, quotas):
        path = "data/SERVER/user/quotas.json"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(quotas, f)

    
    def run_command(self, raw):
        if raw.startswith(">"):
            raw = raw[1:]

        raw = raw.strip()

        if raw == "":
            return ""

        parts = raw.split()
        cmd = parts[0]
        args = parts[1:]

        path = f"/usr/bin/{cmd}"

        if not self.exists(path):
            return f"{cmd}: command not found"

        code = self.read(path)
        if code is None:
            return f"{cmd}: failed to load"

        env = {}
        exec(code, env)

        if "run" not in env:
            return f"{cmd}: invalid command file"

        




    #get os bc im lazy
    def os_latest(self):
        """
        Replace /usr/bin with the server's master commands
        located at data/SERVER/commands.
        """

        import os

        server_cmds = "data/SERVER/commands"

        if not os.path.isdir(server_cmds):
            return "Server commands folder missing."

        for f in self.listdir("/usr/bin"):
            self.delete(f"/usr/bin/" + f)

        for fname in os.listdir(server_cmds):
            full = os.path.join(server_cmds, fname)

            try:
                with open(full, "r", encoding="utf-8") as fp:
                    data = fp.read()
            except:
                continue

            self.write(f"/usr/bin/{fname}", data)

        return "ArchCord OS updated from server commands."





    def exists(self, path):
        if path.startswith("/repo/"):
            host_path = os.path.join("data", path.lstrip("/"))
            return os.path.exists(host_path)

        rp = self._real(path)
        return os.path.exists(rp)



    def mkdir(self, path):
        """Create directory."""
        rp = self._real(path)
        os.makedirs(rp, exist_ok=True)

    def get_perms(self):
        raw = self.read("/etc/perms.json")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except:
            return {}

    def save_perms(self, perms):
        self.write("/etc/perms.json", json.dumps(perms))

    def get_owners(self):
        raw = self.read("/etc/owners.json")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except:
            return {}

    def save_owners(self, owners):
        self.write("/etc/owners.json", json.dumps(owners))

    def load_links(self):
        raw = self.raw_read("/etc/links.json")
        if not raw:
            return {}
        import json
        return json.loads(raw)

    def save_links(self, links):
        import json
        self.raw_write("/etc/links.json", json.dumps(links))


    def resolve(self, path, depth=0, session=None):
        links = self.load_links()
        if path in links and links[path]["type"] == "symlink":
            target = links[path]["target"]
            if depth > 10:
                return None
            return self.resolve(target, depth+1)
        return self.normalize(path, session)

    def join(self, a, b):
        return os.path.normpath(os.path.join(a, b)).replace("\\", "/")

    def normalize(self, path, session=None):
        path = path.replace("\\", "/")

        if ":" in path:
            path = "/" + path.split(":", 1)[1].lstrip("/")

        if path.startswith("/"):
            p = path
        else:
            cwd = self.getCWD()
            cwd = cwd.replace("\\", "/")
            p = cwd.rstrip("/") + "/" + path

        p = os.path.normpath(p).replace("\\", "/")

        if not p.startswith("/"):
            p = "/" + p

        return p







    def basename(self, path):
        return os.path.basename(path)

    def dirname(self, path):
        return os.path.dirname(path)
    
    def is_dir(self, path):
        rp = self._real(path)
        return os.path.isdir(rp)

    def mkdir(self, path, parents=False):
        rp = self._real(path)
        if parents:
            os.makedirs(rp, exist_ok=True)
        else:
            os.mkdir(rp)

    def rm(self, path):
        rp = self._real(path)
        os.remove(rp)

    def rmdir(self, path):
        rp = self._real(path)
        os.rmdir(rp)

    def chmod(self, path, mode):
        rp = self._real(path)
        os.chmod(rp, mode)

    def mv(self, src, dst):
        rp_src = self._real(src)
        rp_dst = self._real(dst)
        os.rename(rp_src, rp_dst)

    def cp(self, src, dst):
        import shutil
        rp_src = self._real(src)
        rp_dst = self._real(dst)
        shutil.copy2(rp_src, rp_dst)

    def touch(self, path, atime=None, mtime=None, create=True):
        rp = self._real(path)

        exists = os.path.exists(rp)

        if not exists and not create:
            return
        if not exists:
            with open(rp, "a"):
                pass

        if atime is None or mtime is None:
            os.utime(rp, None)
        else:
            os.utime(rp, (atime, mtime))

    def read_file(self, path):
        rp = self._real(path)
        with open(rp, "r", encoding="utf-8", errors="replace") as f:
            return f.read()


    def stat(self, path):
        links = self.load_links()
        t = "file"
        if self.is_dir(path):
            t = "dir"
        if path in links:
            if links[path]["type"] == "symlink":
                t = "symlink"
            if links[path]["type"] == "hard":
                t = "hardlink"
        size = len(self.read(path) or "")
        return {"type": t, "size": size}
    

    #user env

    def getCWD(self):
        cwd = self.read("/etc/cwd")
        if not cwd:
            return "/"
        return cwd.strip()


    def setCWD(self, path):
        if not self.exists(path):
            return False
        self.write("/etc/cwd", path)
        return True


    def getHome(self):
        return "/home/admin"

    def reset(self):
        """Wipe the entire VM filesystem."""
        root = self.fs_root
        for rootdir, dirs, files in os.walk(root, topdown=False):
            for f in files:
                try:
                    os.remove(os.path.join(rootdir, f))
                except:
                    pass
            for d in dirs:
                try:
                    os.rmdir(os.path.join(rootdir, d))
                except:
                    pass
        return True
