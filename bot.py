import os
import json
import uuid
import traceback
import time
import discord
from discord.ext import commands
from discord import app_commands
import importlib
import importlib.util
from discord.ui import View, Button
from data.SERVER.SHELL import run as SHELL


ROLE_NAME = "Banished"
CHANNEL_NAME = "plead-your-case"

VOTE_DURATION = 24 * 60 * 60      ## 24 hrs rn
UPDATE_INTERVAL = 10 * 60  

#replace with your id to get dev only shi
DEV_ID = "idhere"


TOKEN = "TokenHERE"

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.dm_messages = True
INTENTS.guilds = True

BASE = os.path.dirname(__file__)
DATA = os.path.join(BASE, "data")
USERS = os.path.join(DATA, "users")
SERVER = os.path.join(DATA, "SERVER")
ADDCOMMANDS = os.path.join(DATA, "ADDCOMMANDS")
COMMANDS = os.path.join(SERVER, "commands")


# util


def ensure_dirs():
    os.makedirs(USERS, exist_ok=True)
    os.makedirs(SERVER, exist_ok=True)


def user_root(uid):
    path = os.path.join(USERS, str(uid))
    os.makedirs(path, exist_ok=True)
    return path


def account_root(uid, accid):
    path = os.path.join(user_root(uid), "accounts", accid)
    os.makedirs(path, exist_ok=True)
    return path


def fs_root(uid, accid):
    path = os.path.join(account_root(uid, accid), "fs")
    os.makedirs(path, exist_ok=True)
    return path


def config_path(uid, accid):
    return os.path.join(account_root(uid, accid), "config.json")


def load_config(uid, accid):
    p = config_path(uid, accid)
    if not os.path.exists(p):
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(uid, accid, cfg):
    p = config_path(uid, accid)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

#Mini fake os for hashing passwords
def load_server_hash_for_fs(fs_path):
    class FakeSession:
        def __init__(self, fs_root):
            self.fs_root = fs_root
            self.user_id = 0
            self.account_id = "server"

            class FakeOS:
                def __init__(self, root):
                    self.fs_root = root
                def _real(self, path):
                    if path.startswith("/"):
                        path = path[1:]
                    return os.path.join(self.fs_root, path)
                def read(self, path):
                    rp = self._real(path)
                    if not os.path.exists(rp):
                        return None
                    with open(rp, "r", encoding="utf-8") as f:
                        return f.read()
                def write(self, path, data):
                    rp = self._real(path)
                    os.makedirs(os.path.dirname(rp), exist_ok=True)
                    with open(rp, "w", encoding="utf-8") as f:
                        f.write(data)

            b64_spec = importlib.util.spec_from_file_location(
                "BASE64", os.path.join(SERVER, "BASE64.py")
            )
            b64_mod = importlib.util.module_from_spec(b64_spec)
            b64_spec.loader.exec_module(b64_mod)

            self.OS = FakeOS(fs_root)
            self.BASE64 = b64_mod.BASE64(self)

    hash_spec = importlib.util.spec_from_file_location(
        "HASH", os.path.join(SERVER, "HASH.py")
    )
    hash_mod = importlib.util.module_from_spec(hash_spec)
    hash_spec.loader.exec_module(hash_mod)

    fake_session = FakeSession(fs_path)
    return hash_mod.HASH(fake_session)


class CommandManager:
    def __init__(self, session):
        self.session = session
        self.root = session.OS._real("/usr/bin")
        self.commands = {}



    def get(self, name):
        return self.commands.get(name)

    def load_all(self):
        self.commands.clear()

        os.makedirs(self.root, exist_ok=True)

        for fname in os.listdir(self.root):
            full_path = os.path.join(self.root, fname)

            if not os.path.isfile(full_path):
                continue

            code = open(full_path, "r", encoding="utf-8").read()

            cname = None
            for line in code.splitlines():
                if line.startswith("COMMAND_NAME"):
                    cname = line.split("=")[1].strip().strip('"\'')
                    break

            if cname:
                self.commands[cname] = full_path

class ArchCordSession:
    def __init__(self, user, account_id, server):
        self.user = user
        self.user_id = user.id
        self.account_id = account_id

        self.fs_root = fs_root(self.user_id, self.account_id)
        self.config = load_config(self.user_id, self.account_id)
        # ADD MORE MODULES HERE
        self.OS = self.load_module("OS")
        self.NET = self.load_module("NET")
        self.ROUTER = self.load_module("ROUTER")
        self.DOMAIN = self.load_module("DOMAIN")
        self.BASE64 = self.load_module("BASE64")
        self.HASH = self.load_module("HASH")

        self.command_manager = CommandManager(self)
        self.command_manager.load_all()
        #need for shi
        from data.SERVER.PROC import ProcessTable
        self.PROC = ProcessTable()
        self.server = server

        self.ssh_session  = None
        self.ssh_host     = None
        self.ssh_user     = None
        self.ftp_session  = None
        self.ftp_host     = None
        self.ssh_client = None

        


    def get_vm(self, host):
        return self.vms.get(host)



    def load_module(self, name):
        path = os.path.join(SERVER, f"{name}.py")
        if not os.path.exists(path):
            return None

        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        if hasattr(mod, name):
            return getattr(mod, name)(self)
        return mod

    def save(self):
        save_config(self.user_id, self.account_id, self.config)



# DISCORD BOT SHI

class ArchCordBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS)

    async def setup_hook(self):
        ensure_dirs()
        await self.tree.sync()


bot = ArchCordBot()


import shutil
import asyncio

@bot.tree.command(name="bootsys", description="Boot your ArchCord VM.")
async def bootsys(interaction: discord.Interaction):
    user = interaction.user
    uid = user.id

    try:
        dm = await user.create_dm()
    except:
        await interaction.response.send_message(
            "Enable DMs and try again.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "Booting ArchCord VM... Check your DMs.",
        ephemeral=True
    )

    accounts_dir = os.path.join(user_root(uid), "accounts")
    os.makedirs(accounts_dir, exist_ok=True)
    accounts = os.listdir(accounts_dir)

    if accounts:
        accid = accounts[0]
        await dm.send(f"VM `{accid}` already exists. No reinstall.")
        return

    accid = uuid.uuid4().hex[:16]
    os.makedirs(account_root(uid, accid), exist_ok=True)
    await dm.send(f"Creating new VM `{accid}`...")

    await dm.send("Enter username (e.g. `admin`):")

    def check(m):
        return m.author.id == uid and m.channel.id == dm.id

    try:
        uname_msg = await bot.wait_for("message", check=check, timeout=120)
    except asyncio.TimeoutError:
        await dm.send("Timed out. Run `/bootsys` again.")
        return

    username = uname_msg.content.strip() or "admin"

    await dm.send(f" Enter password for `{username}`:")
    try:
        pwd_msg = await bot.wait_for("message", check=check, timeout=120)
    except asyncio.TimeoutError:
        await dm.send("Timed out. Run `/bootsys` again.")
        return

    password = pwd_msg.content.strip()
    if not password:
        await dm.send("Empty password not allowed. Run `/bootsys` again.")
        return

    fs = fs_root(uid, accid)

    await dm.send("Building filesystem...")
    shutil.copytree(
        os.path.join(DATA, "SERVER", "defaultos"),
        fs,
        dirs_exist_ok=True
    )

    sysdir = os.path.join(fs, "sys")
    os.makedirs(sysdir, exist_ok=True)
    hashfile = os.path.join(sysdir, "hash")
    if not os.path.exists(hashfile):
        with open(hashfile, "w", encoding="utf-8") as f:
            f.write("ALGO: SHA256\nROUNDS: 5000\nSALT_LEN: 16\n")

    await dm.send("Setting CWD...")
    cwd_path = os.path.join(fs, "etc", "cwd")
    os.makedirs(os.path.dirname(cwd_path), exist_ok=True)
    with open(cwd_path, "w", encoding="utf-8") as f:
        f.write(f"/home/{username}")

    await dm.send("Writing /etc/passwd and /etc/shadow...")
    etc_dir = os.path.join(fs, "etc")
    os.makedirs(etc_dir, exist_ok=True)

    passwd_path = os.path.join(etc_dir, "passwd")
    shadow_path = os.path.join(etc_dir, "shadow")

    uid_num = 1000
    gid_num = 1000
    shell = "/usr/bin/sh"
    home = f"/home/{username}"

    with open(passwd_path, "w", encoding="utf-8") as f:
        f.write(f"{username}:x:{uid_num}:{gid_num}:{username}:{home}:{shell}\n")

    HASH_srv = load_server_hash_for_fs(fs)
    salt, hashed = HASH_srv.hash(password)

    with open(shadow_path, "w", encoding="utf-8") as f:
        f.write(f"{username}:{salt}${hashed}\n")

    await dm.send("Installing commands...")
    usrbin = os.path.join(fs, "usr", "bin")
    os.makedirs(usrbin, exist_ok=True)

    server_cmds = os.path.join(DATA, "SERVER", "commands")
    for fname in os.listdir(server_cmds):
        src = os.path.join(server_cmds, fname)

        if os.path.isdir(src):
            continue

        if not fname.endswith(""):
            continue

        dst = os.path.join(usrbin, fname)
        shutil.copy2(src, dst)


    cfg = {
        "initialized": True,
        "username": username,
        "is_admin": False,
        "godmode": False
    }
    save_config(uid, accid, cfg)

    await dm.send(
        "**ArchCord VM boot complete.**\n"
        f"User: `{username}`\n"
        "This is a fully simulated OS, check welcome.txt in the /home/admin folder. (this is running modified linux)\n\n"
        "Run commands with `>` (e.g. `>ls`)."
    )

async def run_user_script(message, session, cmd_name, args):
    OS = session.OS
    HASH = session.HASH
    BASE64 = session.BASE64

    script_path = f"/usr/bin/{cmd_name}"
    code = OS.read(script_path)
    if not code:
        await message.channel.send(f"Unknown command `{cmd_name}`")
        return

    if "__" in code:
        await message.channel.send(f"security: command `{cmd_name}` blocked")
        return

    g = {
        "__builtins__": {},
        "OS": OS,
        "HASH": HASH,
        "BASE64": BASE64,
        "ARGS": args,
        "SESSION": session,
        "MESSAGE": message,
    }
    l = {}

    try:
        exec(code, g, l)
    except Exception as e:
        await message.channel.send(f"Script `{cmd_name}` crashed:\n```{e}```")
        return

    run = g.get("run") or l.get("run")
    if not callable(run):
        await message.channel.send(f"Script `{cmd_name}` has no run()")
        return

    try:
        result = await run(message, session, args)
        if result:
            await message.channel.send(str(result))
    except Exception as e:
        await message.channel.send(f"Script `{cmd_name}` crashed in run():\n```{e}```")

@bot.tree.command(name="mkvm", description="Admin: create a VM for any user.")
async def mkvm(interaction: discord.Interaction, target_user_id: str, account_id: str, username: str, password: str):


    if interaction.user.id != DEV_ID:
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return

    try:
        uid = int(target_user_id)
    except:
        await interaction.response.send_message("Invalid user ID.", ephemeral=True)
        return

    acc_path = account_root(uid, account_id)
    os.makedirs(acc_path, exist_ok=True)

    fs = fs_root(uid, account_id)

    shutil.copytree(
        os.path.join(DATA, "SERVER", "defaultos"),
        fs,
        dirs_exist_ok=True
    )

    cwd_path = os.path.join(fs, "etc", "cwd")
    os.makedirs(os.path.dirname(cwd_path), exist_ok=True)
    with open(cwd_path, "w", encoding="utf-8") as f:
        f.write(f"/home/{username}")


    etc_dir = os.path.join(fs, "etc")
    os.makedirs(etc_dir, exist_ok=True)

    passwd_path = os.path.join(etc_dir, "passwd")
    shadow_path = os.path.join(etc_dir, "shadow")

    uid_num = 1000
    gid_num = 1000
    shell = "/usr/bin/sh"
    home = f"/home/{username}"

    with open(passwd_path, "w", encoding="utf-8") as f:
        f.write(f"{username}:x:{uid_num}:{gid_num}:{username}:{home}:{shell}\n")

    HASH_srv = load_server_hash_for_fs(fs)
    salt, hashed = HASH_srv.hash(password)

    with open(shadow_path, "w", encoding="utf-8") as f:
        f.write(f"{username}:{salt}${hashed}\n")


    usrbin = os.path.join(fs, "usr", "bin")
    os.makedirs(usrbin, exist_ok=True)

    server_cmds = os.path.join(DATA, "SERVER", "commands")
    for fname in os.listdir(server_cmds):
        src = os.path.join(server_cmds, fname)
        if os.path.isdir(src):
            continue
        dst = os.path.join(usrbin, fname)
        shutil.copy2(src, dst)


    cfg = {
        "initialized": True,
        "username": username,
        "is_admin": False,
        "godmode": False
    }
    save_config(uid, account_id, cfg)

    await interaction.response.send_message(
        f"VM created for user `{uid}` with account `{account_id}`.\n"
        f"Username: `{username}`\nPassword: `{password}`",
        ephemeral=True
    )



@bot.tree.command(name="docs", description="Look at API docs for ArchCord")
async def docs_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="ArchCord Developer Documentation",
        description="Select a module below to view its API reference.",
        color=0x00AEEF
    )

    view = View()
    view.add_item(Button(label="OS", style=discord.ButtonStyle.primary, custom_id="docs_os"))
    view.add_item(Button(label="BASE64", style=discord.ButtonStyle.primary, custom_id="docs_base64"))
    view.add_item(Button(label="HASH", style=discord.ButtonStyle.primary, custom_id="docs_hash"))
    view.add_item(Button(label="SESSION", style=discord.ButtonStyle.primary, custom_id="docs_session"))
    view.add_item(Button(label="ENV", style=discord.ButtonStyle.primary, custom_id="docs_env"))
    view.add_item(Button(label="NET", style=discord.ButtonStyle.primary, custom_id="docs_net"))
    view.add_item(Button(label="SECURITY", style=discord.ButtonStyle.danger, custom_id="docs_security"))

    await interaction.response.send_message(embed=embed, view=view)



@bot.event
async def on_interaction(interaction: discord.Interaction):
    cid = interaction.data.get("custom_id")

    if cid == "docs_os":
        text = "\n".join([
            "**OS MODULE**",
            "OS.read(path)",
            "OS.write(path, data)",
            "OS.append(path, data)",
            "OS.exists(path)",
            "OS.is_dir(path)",
            "OS.is_file(path)",
            "OS.listdir(path)",
            "OS.mkdir(path)",
            "OS.rm(path)",
            "OS.rmdir(path)",
            "OS.mv(a, b)",
            "OS.cp(a, b)",
            "OS.touch(path)",
            "OS.stat(path)",
            "OS.size(path)",
            "OS.normalize(path)",
            "OS.join(a, b)",
            "OS.getCWD()",
            "OS.setCWD(path)",
            "OS.getHome()",
            "OS.get_quotas()",
            "OS.get_mode(path)",
            "OS.set_mode(path, mode, uid)",
            "OS.run_command(command)",
        ])
        await interaction.response.send_message(f"```\n{text}\n```", ephemeral=True)

    elif cid == "docs_base64":
        text = "\n".join([
            "**BASE64 MODULE**",
            "BASE64.encode(text)",
            "BASE64.decode(text)",
        ])
        await interaction.response.send_message(f"```\n{text}\n```", ephemeral=True)

    elif cid == "docs_hash":
        text = "\n".join([
            "**HASH MODULE**",
            "HASH.sha256(text)",
            "HASH.md5(text)",
            "HASH.sha1(text)",
        ])
        await interaction.response.send_message(f"```\n{text}\n```", ephemeral=True)

    elif cid == "docs_session":
        text = "\n".join([
            "**SESSION FIELDS**",
            "session.user_id",
            "session.account_id",
            "session.env",
            "session.ssh_client",
            "session.ssh_host",
            "session.ssh_user",
        ])
        await interaction.response.send_message(f"```\n{text}\n```", ephemeral=True)

    elif cid == "docs_net":
        text = "\n".join([
            "**NET MODULE**",
            "NET.get_ip()",
            "NET.add_host(hostname, ip)",
            "NET.socket(proto=\"TCP\")",
            "NET.open_port(port, name, proto=\"TCP\", banner=\"\", handler=None)",
            "NET.close_port(port)",
            "NET.port_open(port)",
            "NET.list_ports()",
            "NET.fw_add(action, proto=\"*\", port=\"*\")",
            "NET.fw_clear()",
            "NET.get_log(n=20)",
            "NET.ping(dst_ip, count=4)",
            "NET.scan(target_session, ports=None)",
            "NET.connect(target_session, port)",
            "NET.ssh_connect(target_session, username, password)",
            "NET.ftp_connect(target_session, username, password)",
    
            "",
            "**SOCKET OBJECT**",
            "sock.connect(dst_ip, dst_port)",
            "sock.bind(port)",
            "sock.listen_on()",
            "sock.accept()",
            "sock.send(data)",
            "sock.recv()",
            "sock.recv_all()",
            "sock.close()",
    
            "",
            "**PACKET FIELDS**",
            "Packet.proto",
            "Packet.src_ip",
            "Packet.src_port",
            "Packet.dst_ip",
            "Packet.dst_port",
            "Packet.flags",
            "Packet.payload",
            "Packet.ts",
        ])
        await interaction.response.send_message(f"```\n{text}\n```", ephemeral=True)


    elif cid == "docs_env":
        text = "\n".join([
            "**ENVIRONMENT VARIABLES**",
            "PATH",
            "INPUT",
        ])
        await interaction.response.send_message(f"```\n{text}\n```", ephemeral=True)

    elif cid == "docs_security":
        text = "\n".join([
            "**SECURITY RULES**",
            "• No '__' allowed in VM command source",
            "• No attribute access on SESSION or OS",
            "• No imports except json/math/string",
            "• No real filesystem access",
            "• Commands run in a sandboxed exec()",
        ])
        await interaction.response.send_message(f"```\n{text}\n```", ephemeral=True)

@bot.tree.command(name="vote", description="Put a user on trial for 24 hours.")
@app_commands.describe(user="User to put on trial")
async def vote(interaction: discord.Interaction, user: discord.Member):

    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message(
            "Only the **server owner** can run this command.",
            ephemeral=True
        )
        return

    guild = interaction.guild

    role = discord.utils.get(guild.roles, name=ROLE_NAME)
    if role is None:
        role = await guild.create_role(
            name=ROLE_NAME,
            reason="Banished role for vote trial"
        )

    channel = discord.utils.get(guild.channels, name=CHANNEL_NAME)
    if channel is None:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False),
            role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        channel = await guild.create_text_channel(
            CHANNEL_NAME,
            overwrites=overwrites,
            reason="Plead-for-stay channel"
        )

    await user.add_roles(role, reason="User put on trial")

    await interaction.response.send_message(
        f"**{user.mention} has been put on trial for 24 hours!**\n"
        f"They may speak only in {channel.mention}. The server will vote.",
        ephemeral=False
    )

    await channel.send(
        f"{user.mention}, you have been selected for judgment.\n"
        f"You have **24 hours** to plead your case.\n"
        f"Every 10 minutes, the remaining time will be updated."
    )

    vote_msg = await interaction.channel.send(
        f"**Server Vote: Should {user.mention} stay?**\n"
        f"👍 = Stay\n"
        f"👎 = Ban\n"
        f"Voting ends in **24 hours**."
    )

    await vote_msg.add_reaction("👍")
    await vote_msg.add_reaction("👎")

    remaining = VOTE_DURATION
    while remaining > 0:
        await asyncio.sleep(UPDATE_INTERVAL)
        remaining -= UPDATE_INTERVAL

        hours = remaining // 3600
        minutes = (remaining % 3600) // 60

        await channel.send(
            f"**Time remaining:** {hours}h {minutes}m"
        )

    vote_msg = await interaction.channel.fetch_message(vote_msg.id)

    up = down = 0
    for reaction in vote_msg.reactions:
        if str(reaction.emoji) == "👍":
            up = reaction.count - 1
        elif str(reaction.emoji) == "👎":
            down = reaction.count - 1

    if up > down:
        decision = f"**{user.mention} is allowed to stay.**"
        await user.remove_roles(role, reason="Vote passed")
    elif down > up:
        decision = f"**{user.mention} has been banned by server vote.**"
        await guild.ban(user, reason="Vote failed")
    else:
        decision = f"**Tie vote. {user.mention} stays, but remains watched.**"
        await user.remove_roles(role, reason="Tie vote")

    await interaction.channel.send(decision)




@bot.event
async def on_message(msg: discord.Message):
    if msg.author.bot:
        return

    content = msg.content.strip()
    if not content:
        return

    if isinstance(msg.channel, discord.TextChannel) and content.startswith(">"):
        allowed = get_allowed_channel(msg.guild.id)

        if not allowed:
            return

        if msg.channel.id != allowed:
            return

        uid = msg.author.id
        accounts_dir = os.path.join(user_root(uid), "accounts")
        if not os.path.exists(accounts_dir):
            os.makedirs(accounts_dir, exist_ok=True)

        accounts = os.listdir(accounts_dir)

        if not accounts:
            await msg.channel.send("No ArchCord account. Run `/bootsys`.")
            return

        accid = accounts[0]
        session = ArchCordSession(msg.author, accid, bot)


        output = await SHELL(msg, session, [])
        if output:
            await msg.channel.send(output)

        session.save()
        return

    if isinstance(msg.channel, discord.DMChannel) and content.startswith(">"):
        uid = msg.author.id
        accounts_dir = os.path.join(user_root(uid), "accounts")

        if not os.path.exists(accounts_dir):
            os.makedirs(accounts_dir, exist_ok=True)

        accounts = os.listdir(accounts_dir)
        if not accounts:
            await msg.channel.send("No ArchCord account. Run `/bootsys`.")
            return

        accid = accounts[0]
        session = ArchCordSession(msg.author, accid, bot)

        output = await SHELL(msg, session, [])
        if output:
            await msg.channel.send(output)

        session.save()
        return


    return


def get_allowed_channel(guild_id):
    path = os.path.join("data", "guilds", f"{guild_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f)
            return data.get("command_channel")
    except:
        return None



@bot.tree.command(name="setcchannel", description="Set the server channel for ArchCord SHELL commands.")
@app_commands.checks.has_permissions(administrator=True)
async def setCchannel(interaction: discord.Interaction, channel: discord.TextChannel):

    guild_id = interaction.guild.id
    path = os.path.join("data", "guilds", f"{guild_id}.json")

    os.makedirs(os.path.dirname(path), exist_ok=True)

    data = {"command_channel": channel.id}

    with open(path, "w") as f:
        json.dump(data, f)

    await interaction.response.send_message(f"Command channel set to {channel.mention}")

@setCchannel.error
async def setCchannel_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "Only server admins can run this command.",
            ephemeral=True
        )

@bot.tree.command(name="reinstall", description="Reinstall your ArchCord VM (deletes all accounts).")
async def reinstall(interaction: discord.Interaction):
    await interaction.response.send_message(
        "Reinstalling ArchCord VM... Check your DMs.",
        ephemeral=True
    )
    print("please add something here")


# ADDITIONAL COMMANDS


@bot.tree.command(name="Reload Additional Commands", description="Reload additional commands from ADDCOMMANDS And load new ones.")
async def reload_additional_commands(interaction: discord.Interaction):
    if interaction.user.id != DEV_ID:
        await interaction.response.send_message("You are not authorized to use this command.",ephemeral=True)
        return

    elif interaction.user.id == DEV_ID:
        filenames = next(os.walk(ADDCOMMANDS), (None, None, []))[2]
        for file in filenames:
            try:
                if file.startswith("ADD_"):
                    await bot.unload_extension(f"data.ADDCOMMANDS.{file[:-3]}")
                    await bot.load_extension(f"data.ADDCOMMANDS.{file[:-3]}")
            except Exception as e:
                await interaction.response.send_message(f"Error reloading {file}: {e}",ephemeral=True)
                return
                    
            await interaction.response.send_message("Reloaded successfully.",ephemeral=True)

# RUN THE DAMN THING


if __name__ == "__main__":
    ensure_dirs()
    bot.run(TOKEN)
