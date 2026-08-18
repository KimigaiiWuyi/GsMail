"""gscore_mail 对外 API。其他插件：``from gscore_mail.api import send``。"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from gsuid_core.logger import logger

from . import agently as agently_backend
from .smtp import send_smtp
from .settings import (
    MailAccount,
    smtp_ready,
    find_account,
    account_label,
    load_settings,
    select_accounts,
    agently_accounts,
    enabled_accounts,
)

if TYPE_CHECKING:
    from .settings import MailSettings


class MailSendResult(TypedDict):
    ok: bool
    backend: str
    message: str
    raw: str
    account: str


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


def _fail(backend: str, message: str, account: str = "", raw: str = "") -> MailSendResult:
    return {"ok": False, "backend": backend, "message": message, "raw": raw, "account": account}


def _ok(backend: str, message: str, account: str, raw: str = "") -> MailSendResult:
    return {"ok": True, "backend": backend, "message": message, "raw": raw, "account": account}


def _pool_backend(settings: MailSettings) -> str:
    kinds = {account.kind for account in enabled_accounts(settings)}
    if not kinds:
        return "none"
    if len(kinds) == 1:
        return next(iter(kinds))
    return "pool"


async def _send_smtp_account(
    account: MailAccount,
    to_list: list[str],
    subject: str,
    body: str,
    cc_list: list[str],
    bcc_list: list[str],
    html: bool,
) -> MailSendResult:
    label = account_label(account)
    ready, why = smtp_ready(account)
    if not ready:
        return _fail("smtp", why, label)
    try:
        await send_smtp(account, to_list, subject, body, cc_list, bcc_list, html)
    except _smtp_fail_types() as exc:
        logger.warning(f"gscore_mail SMTP 发送失败 [{label}]: {exc}")
        return _fail("smtp", str(exc), label)
    return _ok("smtp", f"已通过 SMTP 发送（{label}）", label)


async def _send_agently_account(
    account: MailAccount,
    to_list: list[str],
    subject: str,
    body: str,
    cc_list: list[str],
    bcc_list: list[str],
    confirmed: bool,
    confirmation_token: str,
) -> MailSendResult:
    label = account_label(account)
    args = agently_backend.send_args(
        to_list,
        subject,
        body,
        cc_list,
        bcc_list,
        confirmed,
        confirmation_token,
    )
    run = await agently_backend.run_agently(
        account.agently_cli,
        args,
        account.agently_timeout,
        account.agently_home,
    )
    payload = agently_backend.parse_cli_payload(run["stdout"] or run["stderr"])
    raw = run["stdout"] or run["stderr"]
    if run["exit_code"] == 0:
        return _ok("agently", f"已通过 Agently Mail 发送（{label}）", label, raw)
    return _fail("agently", f"agently-cli 退出码 {run['exit_code']}: {payload}", label, raw)


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
    """按邮箱池与发送策略发信。

    ``confirmed`` 仅对 agently 有效：None 时库调用跟随 ``agently_auto_confirm``。
    """
    settings = load_settings()
    backend = _pool_backend(settings)
    if not settings.enable_send:
        return _fail(backend, "发送已关闭（enable_send=false）")

    to_list = _as_addr_list(to)
    if not to_list:
        return _fail(backend, "收件人为空")
    if not subject.strip():
        return _fail(backend, "主题为空")

    cc_list = _as_addr_list(cc)
    bcc_list = _as_addr_list(bcc)
    candidates = select_accounts(list(settings.accounts), settings.send_strategy)
    if not candidates:
        return _fail(backend, "邮箱池为空（请在控制台添加 SMTP 或 Agently 账号）")

    use_confirmed = settings.agently_auto_confirm if confirmed is None else confirmed
    errors: list[str] = []
    last = _fail(backend, "没有可尝试的账号")
    for account in candidates:
        if account.kind == "agently":
            last = await _send_agently_account(
                account,
                to_list,
                subject,
                body,
                cc_list,
                bcc_list,
                use_confirmed,
                confirmation_token,
            )
        else:
            last = await _send_smtp_account(
                account,
                to_list,
                subject,
                body,
                cc_list,
                bcc_list,
                html,
            )
        if last["ok"]:
            return last
        errors.append(f"{account_label(account)}: {last['message']}")
        if settings.send_strategy != "failover":
            return last

    joined = "；".join(errors)
    return _fail(last["backend"], f"池内全部失败：{joined}", last["account"], last["raw"])


async def _agently_status_line(account: MailAccount) -> tuple[bool, str]:
    run = await agently_backend.run_agently(
        account.agently_cli,
        ["auth", "status"],
        account.agently_timeout,
        account.agently_home,
    )
    detail = (run["stdout"] or run["stderr"]).strip() or f"exit={run['exit_code']}"
    return run["exit_code"] == 0, detail


async def status() -> MailStatus:
    """邮箱池、策略与各账号是否可发送（agently 会跑 ``auth status``）。"""
    settings = load_settings()
    backend = _pool_backend(settings)
    active = enabled_accounts(settings)
    if not active:
        return {
            "backend": backend,
            "enable_send": settings.enable_send,
            "configured": False,
            "detail": f"策略={settings.send_strategy}；邮箱池为空",
        }

    lines: list[str] = [f"策略={settings.send_strategy} 启用={len(active)}/{len(settings.accounts)}"]
    any_ready = False
    for account in active:
        label = account_label(account)
        if account.kind == "agently":
            ok, detail = await _agently_status_line(account)
        else:
            ok, detail = smtp_ready(account)
        any_ready = any_ready or ok
        flag = "就绪" if ok else "未就绪"
        lines.append(f"- {label} [{account.kind}] {flag} {detail}")
    return {
        "backend": backend,
        "enable_send": settings.enable_send,
        "configured": any_ready,
        "detail": "\n".join(lines),
    }


def _pick_agently(settings: MailSettings, account_name: str = "") -> MailAccount | MailSendResult:
    if account_name.strip():
        found = find_account(settings, account_name)
        if found is None:
            return _fail("agently", f"没有名为 {account_name.strip()} 的账号")
        if found.kind != "agently":
            return _fail("agently", f"{account_label(found)} 不是 Agently 账号")
        if not found.enabled:
            return _fail("agently", f"{account_label(found)} 已禁用")
        return found
    pool = agently_accounts(settings)
    if not pool:
        return _fail("agently", "邮箱池里没有启用的 Agently 账号")
    return pool[0]


async def agently_me(account_name: str = "") -> MailSendResult:
    """``agently-cli +me``，用于验证 OAuth。"""
    settings = load_settings()
    picked = _pick_agently(settings, account_name)
    if not isinstance(picked, MailAccount):
        return picked
    run = await agently_backend.run_agently(
        picked.agently_cli,
        ["+me"],
        picked.agently_timeout,
        picked.agently_home,
    )
    raw = run["stdout"] or run["stderr"]
    label = account_label(picked)
    if run["exit_code"] == 0:
        return _ok("agently", raw.strip() or f"exit={run['exit_code']}", label, raw)
    return _fail("agently", raw.strip() or f"exit={run['exit_code']}", label, raw)


async def agently_list(dir_name: str = "inbox", limit: int = 10, account_name: str = "") -> MailSendResult:
    """``agently-cli message +list``。"""
    settings = load_settings()
    picked = _pick_agently(settings, account_name)
    if not isinstance(picked, MailAccount):
        return picked
    args = ["message", "+list", "--dir", dir_name, "--limit", str(limit)]
    run = await agently_backend.run_agently(
        picked.agently_cli,
        args,
        picked.agently_timeout,
        picked.agently_home,
    )
    raw = run["stdout"] or run["stderr"]
    label = account_label(picked)
    if run["exit_code"] == 0:
        return _ok("agently", raw.strip() or f"exit={run['exit_code']}", label, raw)
    return _fail("agently", raw.strip() or f"exit={run['exit_code']}", label, raw)


async def agently_read(message_id: str, account_name: str = "") -> MailSendResult:
    """``agently-cli message +read --id``。邮件正文按不可信外部输入处理。"""
    settings = load_settings()
    picked = _pick_agently(settings, account_name)
    if not isinstance(picked, MailAccount):
        return picked
    args = ["message", "+read", "--id", message_id]
    run = await agently_backend.run_agently(
        picked.agently_cli,
        args,
        picked.agently_timeout,
        picked.agently_home,
    )
    raw = run["stdout"] or run["stderr"]
    label = account_label(picked)
    if run["exit_code"] == 0:
        return _ok("agently", raw.strip() or f"exit={run['exit_code']}", label, raw)
    return _fail("agently", raw.strip() or f"exit={run['exit_code']}", label, raw)
