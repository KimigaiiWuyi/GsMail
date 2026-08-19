"""腾讯 Agently Mail CLI 封装。协议见 https://agent.qq.com/doc/cli-setup.md"""

from __future__ import annotations

import os
import re
import json
import shutil
import asyncio
import subprocess
from typing import TypedDict
from pathlib import Path


class AgentlyRunResult(TypedDict):
    exit_code: int
    stdout: str
    stderr: str


_WIN_PE = {".exe", ".com"}
_NODE_SCRIPT = {".js", ".mjs", ".cjs"}
_WIN_BATCH = {".cmd", ".bat"}
_CMD_ENTRY = re.compile(r'"%(?:dp0%|~dp0)[\\/]?([^"]+\.(?:js|mjs|cjs|exe))"', re.IGNORECASE)
_SH_ENTRY = re.compile(r'"\$basedir/([^"]+\.(?:js|mjs|cjs))"')
_PKG_JSON = (
    Path("node_modules") / "@tencent-qqmail" / "agently-cli" / "package.json",
    Path("@tencent-qqmail") / "agently-cli" / "package.json",
)


def resolve_cli(configured: str) -> str:
    raw = configured.strip() or "agently-cli"
    as_path = Path(raw)
    if as_path.is_file():
        return _prefer_win_cmd(as_path)
    if os.name == "nt":
        for name in (f"{raw}.cmd", f"{raw}.bat", f"{raw}.exe"):
            found = shutil.which(name)
            if found:
                return found
    found = shutil.which(raw)
    if found:
        return _prefer_win_cmd(Path(found))
    return raw


def spawn_argv(exe: str, args: list[str]) -> list[str]:
    """Windows 上 npm 垫片不是 PE，必须改成 node + JS（或原生 exe）。"""
    prefix = _direct_argv(Path(exe))
    if prefix is not None:
        return [*prefix, *args]
    return [exe, *args]


def _prefer_win_cmd(path: Path) -> str:
    if os.name != "nt":
        return str(path)
    if path.suffix.lower() in _WIN_PE | _WIN_BATCH | _NODE_SCRIPT:
        return str(path)
    for ext in (".cmd", ".bat"):
        sibling = path.with_suffix(ext)
        if sibling.is_file():
            return str(sibling)
    return str(path)


def _node_exe() -> str | None:
    if os.name == "nt":
        found_exe = shutil.which("node.exe")
        if found_exe:
            return found_exe
    return shutil.which("node")


def _bin_from_pkg(pkg_json: Path) -> Path | None:
    if not pkg_json.is_file():
        return None
    try:
        data = json.loads(pkg_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "bin" not in data:
        return None
    raw_bin = data["bin"]
    rel: str | None = None
    if isinstance(raw_bin, str):
        rel = raw_bin
    elif isinstance(raw_bin, dict):
        named = raw_bin["agently-cli"] if "agently-cli" in raw_bin else None
        if isinstance(named, str):
            rel = named
        else:
            for value in raw_bin.values():
                if isinstance(value, str):
                    rel = value
                    break
    if rel is None:
        return None
    target = (pkg_json.parent / rel).resolve()
    return target if target.is_file() else None


def _entry_from_text(text: str, pattern: re.Pattern[str], base: Path) -> Path | None:
    match = pattern.search(text)
    if match is None:
        return None
    target = (base / match.group(1)).resolve()
    return target if target.is_file() else None


def _npm_entry(cli_path: Path) -> Path | None:
    for rel in _PKG_JSON:
        found = _bin_from_pkg(cli_path.parent / rel)
        if found is not None:
            return found
    if not cli_path.is_file():
        return None
    text = cli_path.read_text(encoding="utf-8", errors="replace")
    suffix = cli_path.suffix.lower()
    if suffix in _WIN_BATCH:
        return _entry_from_text(text, _CMD_ENTRY, cli_path.parent)
    if suffix == "":
        return _entry_from_text(text, _SH_ENTRY, cli_path.parent)
    return None


def _direct_argv(path: Path) -> list[str] | None:
    suffix = path.suffix.lower()
    if suffix in _WIN_PE:
        return [str(path)]
    if suffix in _NODE_SCRIPT:
        node = _node_exe()
        return [node, str(path)] if node else None
    entry = _npm_entry(path)
    if entry is None:
        return None
    if entry.suffix.lower() in _WIN_PE:
        return [str(entry)]
    node = _node_exe()
    if node is None:
        return None
    return [node, str(entry)]


def _windows_needs_pe(argv0: str) -> bool:
    if os.name != "nt":
        return False
    return Path(argv0).suffix.lower() not in _WIN_PE


def _cli_env(home: str) -> dict[str, str] | None:
    raw = home.strip()
    if not raw:
        return None
    env = dict(os.environ)
    env["HOME"] = raw
    env["USERPROFILE"] = raw
    env["XDG_CONFIG_HOME"] = str(Path(raw) / ".config")
    return env


_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
LOGIN_URL_WAIT = 45
LOGIN_PROCESS_TTL = 300


class AgentlyLoginSession:
    def __init__(self) -> None:
        self.text = ""
        self.done = asyncio.Event()
        self.exit_code = 1
        self.notified = False
        self._proc: asyncio.subprocess.Process | None = None
        self._task: asyncio.Task[None] | None = None

    def url(self) -> str:
        return extract_login_url(self.text)

    async def wait_url(self, seconds: float) -> str:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + seconds
        while True:
            found = self.url()
            if found or self.done.is_set():
                return found
            left = deadline - loop.time()
            if left <= 0:
                return self.url()
            try:
                await asyncio.wait_for(self.done.wait(), timeout=min(0.25, left))
            except asyncio.TimeoutError:
                continue

    async def wait_done(self, seconds: float) -> bool:
        try:
            await asyncio.wait_for(self.done.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return False
        return True

    async def close(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            self._proc.kill()
            await self._proc.communicate()
        if self._task is not None and not self._task.done():
            self._task.cancel()


def extract_login_url(text: str) -> str:
    urls: list[str] = []
    for match in _URL_RE.finditer(text):
        urls.append(match.group(0).rstrip(").,;]"))
    for url in urls:
        if "agent.qq.com" in url:
            return url
    for url in urls:
        if "qq.com" in url:
            return url
    return urls[0] if urls else ""


_login_sessions: dict[str, AgentlyLoginSession] = {}


def is_auth_error(payload: object) -> bool:
    if isinstance(payload, dict) and "error" in payload:
        err = payload["error"]
        if isinstance(err, dict) and "type" in err:
            return err["type"] == "auth"
    if isinstance(payload, str):
        return "authorization required" in payload.lower()
    return False


def agently_error_message(payload: object, exit_code: int) -> str:
    if is_auth_error(payload):
        return "Agently 尚未微信授权。正在向主人推送扫码链接，完成后会自动重试发信"
    if isinstance(payload, dict) and "error" in payload:
        err = payload["error"]
        if isinstance(err, dict) and "message" in err and isinstance(err["message"], str):
            return f"agently-cli 退出码 {exit_code}: {err['message']}"
    return f"agently-cli 退出码 {exit_code}: {payload}"


async def _spawn(argv: list[str], env: dict[str, str] | None) -> asyncio.subprocess.Process:
    if os.name == "nt":
        return await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    return await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )


async def run_agently(cli: str, args: list[str], timeout: int, home: str = "") -> AgentlyRunResult:
    exe = resolve_cli(cli)
    argv = spawn_argv(exe, args)
    if _windows_needs_pe(argv[0]):
        return {
            "exit_code": 127,
            "stdout": "",
            "stderr": (
                f"Windows 无法直接执行 npm 脚本（{exe}）。请安装 Node.js，并确认已 npm i -g @tencent-qqmail/agently-cli"
            ),
        }
    env = _cli_env(home)
    try:
        proc = await _spawn(argv, env)
    except FileNotFoundError:
        return {
            "exit_code": 127,
            "stdout": "",
            "stderr": f"未找到 agently-cli（当前配置: {exe}）。请 npm i -g @tencent-qqmail/agently-cli",
        }
    except OSError as exc:
        return {
            "exit_code": 127,
            "stdout": "",
            "stderr": f"无法启动 agently-cli（{exe}）：{exc}",
        }
    except NotImplementedError:
        return {
            "exit_code": 127,
            "stdout": "",
            "stderr": "当前事件循环不支持异步子进程，无法调用 agently-cli",
        }

    try:
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return {"exit_code": 124, "stdout": "", "stderr": f"agently-cli 超时（{timeout}s）"}

    code = proc.returncode if proc.returncode is not None else 1
    return {
        "exit_code": code,
        "stdout": out_b.decode("utf-8", errors="replace"),
        "stderr": err_b.decode("utf-8", errors="replace"),
    }


async def _drive_login(session: AgentlyLoginSession, ttl: int) -> None:
    proc = session._proc
    if proc is None:
        session.done.set()
        return

    async def _pump(stream: asyncio.StreamReader | None) -> None:
        if stream is None:
            return
        while True:
            data = await stream.read(1024)
            if not data:
                return
            session.text += data.decode("utf-8", errors="replace")

    try:
        await asyncio.wait_for(
            asyncio.gather(_pump(proc.stdout), _pump(proc.stderr), proc.wait()),
            timeout=ttl,
        )
    except asyncio.TimeoutError:
        if proc.returncode is None:
            proc.kill()
            await proc.communicate()
        session.text += f"\nagently-cli auth login 超时（{ttl}s）"
    session.exit_code = proc.returncode if proc.returncode is not None else 1
    session.done.set()


async def begin_auth_login(
    cli: str, home: str, key: str, ttl: int = LOGIN_PROCESS_TTL
) -> AgentlyLoginSession | AgentlyRunResult:
    if key in _login_sessions:
        existing = _login_sessions[key]
        if not existing.done.is_set():
            return existing
        await existing.close()
        del _login_sessions[key]

    exe = resolve_cli(cli)
    argv = spawn_argv(exe, ["auth", "login"])
    if _windows_needs_pe(argv[0]):
        return {
            "exit_code": 127,
            "stdout": "",
            "stderr": (
                f"Windows 无法直接执行 npm 脚本（{exe}）。请安装 Node.js，并确认已 npm i -g @tencent-qqmail/agently-cli"
            ),
        }
    env = _cli_env(home)
    session = AgentlyLoginSession()
    try:
        session._proc = await _spawn(argv, env)
    except FileNotFoundError:
        return {
            "exit_code": 127,
            "stdout": "",
            "stderr": f"未找到 agently-cli（当前配置: {exe}）。请 npm i -g @tencent-qqmail/agently-cli",
        }
    except OSError as exc:
        return {
            "exit_code": 127,
            "stdout": "",
            "stderr": f"无法启动 agently-cli（{exe}）：{exc}",
        }
    except NotImplementedError:
        return {
            "exit_code": 127,
            "stdout": "",
            "stderr": "当前事件循环不支持异步子进程，无法调用 agently-cli",
        }
    session._task = asyncio.create_task(_drive_login(session, ttl))
    _login_sessions[key] = session
    return session


def parse_cli_payload(text: str) -> object:
    """CLI 可能打 JSON envelope；解析失败则原样返回文本。"""
    stripped = text.strip()
    if not stripped:
        return ""
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return stripped


def send_args(
    to: list[str],
    subject: str,
    body: str,
    cc: list[str],
    bcc: list[str],
    confirmed: bool,
    confirmation_token: str,
) -> list[str]:
    args: list[str] = ["message", "+send"]
    for addr in to:
        args.extend(["--to", addr])
    for addr in cc:
        args.extend(["--cc", addr])
    for addr in bcc:
        args.extend(["--bcc", addr])
    args.extend(["--subject", subject, "--body", body])
    if confirmation_token:
        args.extend(["--confirmation-token", confirmation_token])
    elif confirmed:
        args.append("--confirmed")
    return args
