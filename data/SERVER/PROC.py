import time
import itertools

class ProcessTable:
    def __init__(self):
        self.procs = {}
        self.pid_counter = itertools.count(100)

    def spawn(self, name, user):
        pid = next(self.pid_counter)
        self.procs[pid] = {
            "pid": pid,
            "name": name,
            "user": user,
            "cpu": 0,
            "mem": 0,
            "state": "RUN",
            "start": time.time()
        }
        self.allocate_cpu()
        return pid


    def kill(self, pid):
        if pid in self.procs:
            del self.procs[pid]
            self.allocate_cpu()
            return True
        return False

    def list(self):
        return list(self.procs.values())

    def update_cpu(self, pid, value):
        if pid in self.procs:
            self.procs[pid]["cpu"] = value

    def update_mem(self, pid, value):
        if pid in self.procs:
            self.procs[pid]["mem"] = value

    def active_users(self):
        return len({p["user"] for p in self.procs.values()})
    
    def allocate_cpu(self):
        users = list({p["user"] for p in self.procs.values()})
        if not users:
            return

        share = 100 / len(users)

        for p in self.procs.values():
            p["cpu"] = round(share, 1)

        


