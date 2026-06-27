DEBUG_SHELL = False

def dbg(*a):
    if DEBUG_SHELL:
        print("[SHELL-DBG]", *a)

import shlex, itertools, os

async def run(message, session, args):
    OS = session.OS

    if not hasattr(session, "env"):
        session.env = {}
    if not hasattr(session, "JOBS"):
        session.JOBS = {}
    if not hasattr(session, "JOB_COUNTER"):
        session.JOB_COUNTER = itertools.count(1)
    if "PATH" not in session.env:
        session.env["PATH"] = "/usr/bin:/bin"

    session.env["INPUT"] = ""

    raw = message.content[1:].strip()
    dbg("RAW INPUT:", raw)

    if not raw:
        return ""

    if raw == ":(){ :|:& };:":
        return "shell: fork bomb blocked"

    tokens = (
        raw.replace("&&", " && ")
           .replace("||", " || ")
           .replace(";", " ; ")
           .replace("&", " & ")
           .split()
    )

    dbg("TOKENS:", tokens)

    commands = []
    current = []

    for t in tokens:
        if t in [";", "&", "&&", "||"]:
            commands.append((current, t))
            dbg("COMMAND SPLIT:", current, "SEP:", t)
            current = []
        else:
            current.append(t)
    if current:
        commands.append((current, None))
        dbg("FINAL COMMAND:", current)

    last_status = True
    outputs = []

    for parts, sep in commands:
        dbg("PROCESSING COMMAND:", parts, "SEP:", sep)

        if not parts:
            continue

        if sep == "&&" and not last_status:
            dbg("SKIP due to &&")
            continue
        if sep == "||" and last_status:
            dbg("SKIP due to ||")
            continue

        # background job? i think?
        background = False
        if parts[-1] == "&":
            background = True
            parts = parts[:-1]
            dbg("BACKGROUND JOB DETECTED")

        segment = " ".join(parts)
        dbg("SEGMENT:", segment)

        pipes = segment.split("|")
        dbg("PIPES:", pipes)

        output = None

        for i, seg in enumerate(pipes):
            seg = seg.strip()
            dbg("PIPE SEG:", seg)

            redirect = None
            target = None

            if ">>" in seg:
                p = seg.split(">>", 1)
                seg = p[0].strip()
                target = p[1].strip()
                redirect = ">>"
                dbg("REDIRECT >> to", target)
            elif ">" in seg:
                p = seg.split(">", 1)
                seg = p[0].strip()
                target = p[1].strip()
                redirect = ">"
                dbg("REDIRECT > to", target)

            if seg.startswith("echo "):
                cmd = "echo"
                arg_str = seg[len("echo "):]

                if arg_str.startswith(" "):
                    arg_str = arg_str[1:]

                cmd_args = [arg_str]
                dbg("ECHO ARGS:", cmd_args)

            else:
                try:
                    parts2 = shlex.split(seg)
                    dbg("SHLEX:", parts2)
                except:
                    dbg("SHLEX ERROR")
                    return "shell: parse error"

                if not parts2:
                    return ""

                cmd = parts2[0]
                cmd_args = parts2[1:]
                dbg("CMD:", cmd, "ARGS:", cmd_args)

            if "/" in cmd and not cmd.startswith("echo"):
                vm_path = OS.normalize(cmd, session)
                real_path = OS._real(vm_path)

                dbg("PATH EXEC:", cmd, "->", vm_path, real_path)

                if not os.path.exists(real_path):
                    return f"{cmd}: command not found"

                mode = None
                if hasattr(OS, "get_mode"):
                    mode = OS.get_mode(vm_path)

                if not mode or len(mode) != 3 or mode[2] not in ("1", "5", "7"):
                    return f"{cmd}: permission denied"

                content = OS.read(vm_path)
                first = content.splitlines()[0] if content else ""

                if first.startswith("#!"):
                    interpreter = first[2:].strip()
                else:
                    interpreter = "/usr/bin/sh"

                cmd = interpreter.split("/")[-1]
                cmd_args = [vm_path] + cmd_args
                dbg("EXECUTABLE FILE, INTERPRETER:", interpreter)

            if output is not None:
                session.env["INPUT"] = output
                dbg("PIPE INPUT SET:", output)

            if session.ssh_client:
                try:
                    stdin, stdout, stderr = session.ssh_client.exec_command(seg)
                    out = stdout.read().decode()
                    err = stderr.read().decode()
                    output = out + err
                    continue
                except Exception as e:
                    return f"ssh error: {e}"

            if cmd == "export":
                dbg("EXPORT:", cmd_args)
                for a in cmd_args:
                    if "=" in a:
                        k, v = a.split("=", 1)
                        session.env[k] = v
                output = ""
                continue




            cmd_path = session.command_manager.get(cmd)
            dbg("CMD PATH:", cmd_path)

            if cmd_path is None:
                path_dirs = session.env.get("PATH", "").split(":")
                dbg("SEARCH PATH:", path_dirs)
                found = None
                for d in path_dirs:
                    p = OS.normalize(d + "/" + cmd, session)
                    dbg("CHECK:", p)
                    if OS.read(p) is not None:
                        found = p
                        dbg("FOUND:", p)
                        break
                if found is None:
                    dbg("UNKNOWN CMD:", cmd)
                    return f"Unknown command: {cmd}"

                if found.startswith("/usr/bin/") and not found.startswith("/usr/bin/_sys_"):
                    return f"{cmd}: cannot execute Python commands from /usr/bin (security)"

                code = OS.read(found)

            else:
                if cmd_path.startswith("/usr/bin/") and not cmd_path.startswith("/usr/bin/_sys_"):
                    return f"{cmd}: cannot execute Python commands from /usr/bin (security)"

                code = OS.read(f"/usr/bin/{cmd}")

            pid = session.PROC.spawn(cmd, session.user_id)
            dbg("SPAWN PID:", pid)

            if background and i == len(pipes) - 1:
                jid = next(session.JOB_COUNTER)
                session.JOBS[jid] = {
                    "pid": pid,
                    "cmd": cmd,
                    "args": cmd_args,
                    "state": "RUN"
                }
                outputs.append(f"[{jid}] {pid} running in background")
                output = ""
                break

            env = {
                "session": session,
                "OS": session.OS,
                "NET": session.NET,
                "message": message,
                "args": cmd_args,
            }

            exec(code, env)

            if "run" not in env:
                session.PROC.kill(pid)
                dbg("NO RUN() IN CMD")
                return f"Command `{cmd}` missing run()"

            dbg("RUNNING CMD:", cmd, cmd_args)
            result = await env["run"](message, session, cmd_args)
            dbg("RESULT:", repr(result))

            if result is None:
                result = ""

            session.PROC.kill(pid)

            if redirect and target:
                dbg("WRITE TO:", target, "MODE:", redirect)
                vm_target = OS.normalize(target, session)

                if redirect == ">":
                    OS.write(vm_target, result)
                else:
                    OS.append(vm_target, result)

                result = ""

            output = result


        if output:
            outputs.append(output)
        last_status = (output != "")


    return "\n".join(o for o in outputs if o)
