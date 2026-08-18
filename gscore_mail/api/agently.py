"""腾讯 Agently Mail CLI 封装。协议见 https://agent.qq.com/doc/cli-setup.md"""

from __future__ import annotations

import os
import json
import shutil
import asyncio
from typing import TypedDict
from pathlib import Path


class AgentlyRunResult(TypedDict):
    exit_code: int
    stdout: str
    stderr: str


def resolve_cli(configured: str) -> str:
    raw = configured.strip() or "agently-cli"
    as_path = Path(raw)
    if as_path.is_file():
        return str(as_path)
    found = shutil.which(raw)
    if found:
        return found
    return raw


def _cli_env(home: str) -> dict[str, str] | None:
    raw = home.strip()
    if not raw:
        return None
    env = dict(os.environ)
    env["HOME"] = raw
    env["USERPROFILE"] = raw
    env["XDG_CONFIG_HOME"] = str(Path(raw) / ".config")
    return env


async def run_agently(cli: str, args: list[str], timeout: int, home: str = "") -> AgentlyRunResult:
    exe = resolve_cli(cli)
    env = _cli_env(home)
    try:
        proc = await asyncio.create_subprocess_exec(
            exe,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
    except FileNotFoundError:
        return {
            "exit_code": 127,
            "stdout": "",
            "stderr": f"未找到 agently-cli（当前配置: {exe}）。请 npm i -g @tencent-qqmail/agently-cli",
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
