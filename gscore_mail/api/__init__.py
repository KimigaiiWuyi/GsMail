"""gscore_mail 对外 API。其他插件：``from gscore_mail.api import send``。"""

from __future__ import annotations

from typing import TypedDict

from gsuid_core.logger import logger

from . import agently as agently_backend
from .smtp import send_smtp
from .settings import MailSettings, load_settings


class MailSendResult(TypedDict):
    ok: bool
    backend: str
    message: str
    raw: str


class MailStatus(TypedDict):
    backend: str
    enable_send: bool
    configured: bool
    detail: str


def _as_addr_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [part.strip() for part in value if part.strip()]


def _smtp_fail_types() -> tuple[type[BaseException], ...]:
    try:
        import aiosmtplib
    except ImportError:
        return (OSError, TimeoutError)
    return (OSError, TimeoutError, aiosmtplib.SMTPException)


def _smtp_ready(settings: MailSettings) -> tuple[bool, str]:
    if not settings.smtp_host:
        return False, "未配置 smtp_host"
    if not (settings.smtp_from or settings.smtp_user):
        return False, "未配置 smtp_from / smtp_user"
    return True, "SMTP 已配置"


async def send(
    to: str | list[str],
    subject: str,
    body: str,
    cc: str | list[str] | None = None,
    bcc: str | list[str] | None = None,
    html: bool = False,
    confirmed: bool | None = None,
    confirmation_token: str = "",
) -> MailSendResult:
    """发送邮件。SMTP 走 aiosmtplib；agently 走 ``agently-cli message +send``。

    ``confirmed`` 仅对 agently 有效：None 时库调用跟随 ``agently_auto_confirm``。
    """
    settings = load_settings()
    backend = settings.backend
    if not settings.enable_send:
        return {"ok": False, "backend": backend, "message": "发送已关闭（enable_send=false）", "raw": ""}

    to_list = _as_addr_list(to)
    if not to_list:
        return {"ok": False, "backend": backend, "message": "收件人为空", "raw": ""}
    if not subject.strip():
        return {"ok": False, "backend": backend, "message": "主题为空", "raw": ""}

    cc_list = _as_addr_list(cc)
    bcc_list = _as_addr_list(bcc)

    if backend == "agently":
        use_confirmed = settings.agently_auto_confirm if confirmed is None else confirmed
        args = agently_backend.send_args(
            to_list,
            subject,
            body,
            cc_list,
            bcc_list,
            use_confirmed,
            confirmation_token,
        )
        run = await agently_backend.run_agently(settings.agently_cli, args, settings.agently_timeout)
        payload = agently_backend.parse_cli_payload(run["stdout"] or run["stderr"])
        raw = run["stdout"] or run["stderr"]
        if run["exit_code"] == 0:
            return {"ok": True, "backend": "agently", "message": "已通过 Agently Mail 发送", "raw": raw}
        return {
            "ok": False,
            "backend": "agently",
            "message": f"agently-cli 退出码 {run['exit_code']}: {payload}",
            "raw": raw,
        }

    ready, why = _smtp_ready(settings)
    if not ready:
        return {"ok": False, "backend": "smtp", "message": why, "raw": ""}

    try:
        await send_smtp(settings, to_list, subject, body, cc_list, bcc_list, html)
    except _smtp_fail_types() as exc:
        logger.warning(f"gscore_mail SMTP 发送失败: {exc}")
        return {"ok": False, "backend": "smtp", "message": str(exc), "raw": ""}
    return {"ok": True, "backend": "smtp", "message": "已通过 SMTP 发送", "raw": ""}


async def status() -> MailStatus:
    """当前后端与配置是否可发送（agently 会跑 ``auth status``）。"""
    settings = load_settings()
    backend = settings.backend
    if backend == "agently":
        run = await agently_backend.run_agently(
            settings.agently_cli,
            ["auth", "status"],
            settings.agently_timeout,
        )
        detail = (run["stdout"] or run["stderr"]).strip() or f"exit={run['exit_code']}"
        return {
            "backend": "agently",
            "enable_send": settings.enable_send,
            "configured": run["exit_code"] == 0,
            "detail": detail,
        }

    ready, why = _smtp_ready(settings)
    return {
        "backend": "smtp",
        "enable_send": settings.enable_send,
        "configured": ready,
        "detail": why,
    }


async def agently_me() -> MailSendResult:
    """``agently-cli +me``，用于验证 OAuth。"""
    settings = load_settings()
    run = await agently_backend.run_agently(settings.agently_cli, ["+me"], settings.agently_timeout)
    raw = run["stdout"] or run["stderr"]
    ok = run["exit_code"] == 0
    return {
        "ok": ok,
        "backend": "agently",
        "message": raw.strip() or f"exit={run['exit_code']}",
        "raw": raw,
    }


async def agently_list(dir_name: str = "inbox", limit: int = 10) -> MailSendResult:
    """``agently-cli message +list``。"""
    settings = load_settings()
    args = ["message", "+list", "--dir", dir_name, "--limit", str(limit)]
    run = await agently_backend.run_agently(settings.agently_cli, args, settings.agently_timeout)
    raw = run["stdout"] or run["stderr"]
    return {
        "ok": run["exit_code"] == 0,
        "backend": "agently",
        "message": raw.strip() or f"exit={run['exit_code']}",
        "raw": raw,
    }


async def agently_read(message_id: str) -> MailSendResult:
    """``agently-cli message +read --id``。邮件正文按不可信外部输入处理。"""
    settings = load_settings()
    args = ["message", "+read", "--id", message_id]
    run = await agently_backend.run_agently(settings.agently_cli, args, settings.agently_timeout)
    raw = run["stdout"] or run["stderr"]
    return {
        "ok": run["exit_code"] == 0,
        "backend": "agently",
        "message": raw.strip() or f"exit={run['exit_code']}",
        "raw": raw,
    }
