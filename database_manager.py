import os
import json

BASE = "data/users"

def list_accounts(user_id):
    path = os.path.join(BASE, str(user_id), "accounts")
    if not os.path.exists(path):
        return None, f"No such user directory: {path}"

    accounts = []
    for name in os.listdir(path):
        acc_path = os.path.join(path, name, "fs")
        if os.path.isdir(acc_path):
            accounts.append(name)

    return accounts, None


class AdminSession:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.cwd = "/"

    def _real(self, path):
        path = path.replace("..", "")
        if not path.startswith("/"):
            path = "/" + path
        return os.path.join(self.root, path.lstrip("/"))

    def ls(self, path=None):
        if path is None:
            path = self.cwd
        rp = self._real(path)
        if not os.path.exists(rp):
            return f"no such file or directory: {path}"
        if os.path.isfile(rp):
            return path
        try:
            items = os.listdir(rp)
        except Exception as e:
            return f"error: {e}"
        return "  ".join(sorted(items))

    def cd(self, path):
        if path == "/":
            self.cwd = "/"
            return self.cwd
        if not path.startswith("/"):
            path = os.path.join(self.cwd, path)
        norm = os.path.normpath(path).replace("\\", "/")
        if not norm.startswith("/"):
            norm = "/" + norm
        rp = self._real(norm)
        if not os.path.isdir(rp):
            return f"no such directory: {norm}"
        self.cwd = norm
        return self.cwd

    def pwd(self):
        return self.cwd

    def cat(self, path):
        if not path.startswith("/"):
            path = os.path.join(self.cwd, path)
        norm = os.path.normpath(path).replace("\\", "/")
        if not norm.startswith("/"):
            norm = "/" + norm
        rp = self._real(norm)
        if not os.path.exists(rp):
            return f"no such file: {norm}"
        if os.path.isdir(rp):
            return f"{norm}: is a directory"
        try:
            with open(rp, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"error: {e}"

    def show_passwd(self):
        return self.cat("/etc/passwd")

    def show_shadow(self):
        return self.cat("/etc/shadow")


def repl(session):
    print(f"\nMounted VM root: {session.root}")
    print("Type 'help' for commands.\n")
    while True:
        try:
            line = input(f"{session.pwd()}# ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue
        if line in ("exit", "quit"):
            break

        parts = line.split()
        cmd = parts[0]
        args = parts[1:]

        if cmd == "help":
            print("Commands:")
            print("  ls [path]")
            print("  cd <path>")
            print("  pwd")
            print("  cat <path>")
            print("  passwd      (show /etc/passwd)")
            print("  shadow      (show /etc/shadow)")
            print("  exit")
        elif cmd == "ls":
            print(session.ls(args[0] if args else None))
        elif cmd == "cd":
            print(session.cd(args[0] if args else "/"))
        elif cmd == "pwd":
            print(session.pwd())
        elif cmd == "cat":
            if not args:
                print("cat: missing file")
            else:
                print(session.cat(args[0]))
        elif cmd == "passwd":
            print(session.show_passwd())
        elif cmd == "shadow":
            print(session.show_shadow())
        else:
            print(f"{cmd}: unknown command")


def main():
    print("ArchCord Server Admin CLI")
    user_id = input("User ID: ").strip()

    accounts, err = list_accounts(user_id)
    if err:
        print(err)
        return

    if not accounts:
        print("No accounts found for this user.")
        return

    print("\nSelect an account:")
    for i, acc in enumerate(accounts, 1):
        print(f"{i}) {acc}")

    choice = input("\nEnter number: ").strip()
    if not choice.isdigit() or not (1 <= int(choice) <= len(accounts)):
        print("Invalid selection.")
        return

    account = accounts[int(choice) - 1]

    vm_root = os.path.join(BASE, str(user_id), "accounts", account, "fs")
    if not os.path.exists(vm_root):
        print(f"VM root does not exist: {vm_root}")
        return

    session = AdminSession(vm_root)
    repl(session)


if __name__ == "__main__":
    main()
