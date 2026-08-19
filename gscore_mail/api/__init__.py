"""gscore_mail 对外 API。其他插件：``from gscore_mail.api import send``。"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict
from collections.abc import Callable, Awaitable

from gsuid_core.logger import logger
from gsuid_core.utils.message import send_msg_to_master

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


_QQ_BOTS = frozenset({"onebot", "onebot_v11", "onebot_v12", "qqgroup"})


def infer_qq_mail(bot_id: str, user_id: str) -> str:
    """OneBot / QQ 官方通道：数字 user_id 可写成 user_id@qq.com。"""
    if bot_id not in _QQ_BOTS:
        return ""
    uid = user_id.strip()
    if not uid.isdigit():
        return ""
    return f"{uid}@qq.com"


def resolve_send_to(to: str, bot_id: str, user_id: str) -> str:
    raw = to.strip()
    if raw:
        return raw
    return infer_qq_mail(bot_id, user_id)


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


async def _push_auth_url(
    url: str,
    label: str,
    session: agently_backend.AgentlyLoginSession,
    on_auth_url: Callable[[str], Awaitable[None]] | None,
) -> None:
    if session.notified:
        return
    session.notified = True
    text = (
        f"[gscore_mail] Agently（{label}）需要微信授权。请打开此链接（不要改）：\n"
        f"{url}\n扫码成功后会自动继续刚才的发信。"
    )
    await send_msg_to_master(text)
    if on_auth_url is not None:
        await on_auth_url(url)


async def _complete_agently_oauth(
    account: MailAccount,
    on_auth_url: Callable[[str], Awaitable[None]] | None,
) -> MailSendResult:
    label = account_label(account)
    started = await agently_backend.begin_auth_login(
        account.agently_cli,
        account.agently_home,
        label,
    )
    if isinstance(started, dict):
        return _fail("agently", started["stderr"] or started["stdout"], label, started["stderr"])
    url = await started.wait_url(agently_backend.LOGIN_URL_WAIT)
    if url:
        await _push_auth_url(url, label, started, on_auth_url)
    await started.wait_done(agently_backend.LOGIN_PROCESS_TTL)
    me = await agently_backend.run_agently(
        account.agently_cli,
        ["+me"],
        account.agently_timeout,
        account.agently_home,
    )
    if me["exit_code"] == 0:
        return _ok("agently", (me["stdout"] or me["stderr"]).strip() or "授权已完成", label, me["stdout"])
    if url:
        return _fail("agently", f"已向主人推送授权链接，但尚未完成扫码：{url}", label, started.text)
    payload = agently_backend.parse_cli_payload(started.text or me["stdout"] or me["stderr"])
    return _fail("agently", agently_backend.agently_error_message(payload, me["exit_code"]), label, started.text)


async def _send_agently_once(
    account: MailAccount,
    to_list: list[str],
    subject: str,
    body: str,
    cc_list: list[str],
    bcc_list: list[str],
    confirmed: bool,
    confirmation_token: str,
) -> tuple[MailSendResult, object]:
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
    raw = run["stdout"] or run["stderr"]
    payload = agently_backend.parse_cli_payload(raw)
    if run["exit_code"] == 0:
        return _ok("agently", f"已通过 Agently Mail 发送（{label}）", label, raw), payload
    return _fail("agently", agently_backend.agently_error_message(payload, run["exit_code"]), label, raw), payload


async def _send_agently_account(
    account: MailAccount,
    to_list: list[str],
    subject: str,
    body: str,
    cc_list: list[str],
    bcc_list: list[str],
    confirmed: bool,
    confirmation_token: str,
    on_auth_url: Callable[[str], Awaitable[None]] | None,
    resume_auth: bool,
) -> MailSendResult:
    last, payload = await _send_agently_once(
        account,
        to_list,
        subject,
        body,
        cc_list,
        bcc_list,
        confirmed,
        confirmation_token,
    )
    if last["ok"] or not resume_auth or not agently_backend.is_auth_error(payload):
        return last
    logger.warning(f"gscore_mail Agently 未授权 [{account_label(account)}]，启动 OAuth")
    login = await _complete_agently_oauth(account, on_auth_url)
    if not login["ok"]:
        return login
    retried, _payload = await _send_agently_once(
        account,
        to_list,
        subject,
        body,
        cc_list,
        bcc_list,
        confirmed,
        confirmation_token,
    )
    return retried


async def send(
    to: str | list[str],
    subject: str,
    body: str,
    cc: str | list[str] | None = None,
    bcc: str | list[str] | None = None,
    html: bool = False,
    confirmed: bool | None = None,
    confirmation_token: str = "",
    on_auth_url: Callable[[str], Awaitable[None]] | None = None,
) -> MailSendResult:
    """按邮箱池与发送策略发信。

    ``confirmed`` 仅对 agently 有效：None 时库调用跟随 ``agently_auto_confirm``。
    Agently 未授权时会拉起 ``auth login``，把链接推给主人，等扫码后再发一次。
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
                on_auth_url,
                True,
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
    raw = (run["stdout"] or run["stderr"]).strip() or f"exit={run['exit_code']}"
    if run["exit_code"] == 0:
        return True, raw
    payload = agently_backend.parse_cli_payload(raw)
    return False, agently_backend.agently_error_message(payload, run["exit_code"])


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
    payload = agently_backend.parse_cli_payload(raw)
    return _fail("agently", agently_backend.agently_error_message(payload, run["exit_code"]), label, raw)


async def agently_login(account_name: str = "") -> MailSendResult:
    """启动 ``agently-cli auth login``，尽快抽出微信授权 URL。进程在后台等到扫码或超时。"""
    settings = load_settings()
    picked = _pick_agently(settings, account_name)
    if not isinstance(picked, MailAccount):
        return picked
    label = account_label(picked)
    started = await agently_backend.begin_auth_login(
        picked.agently_cli,
        picked.agently_home,
        label,
    )
    if isinstance(started, dict):
        return _fail("agently", started["stderr"] or started["stdout"], label, started["stderr"])
    url = await started.wait_url(agently_backend.LOGIN_URL_WAIT)
    if url:
        return _ok(
            "agently",
            f"请用微信打开此链接完成 Agently 授权（不要改链接）：\n{url}\n"
            "页面显示登录成功后，发「邮件状态」或让 AI 再查一次 agently_whoami。",
            label,
            started.text,
        )
    if started.done.is_set():
        payload = agently_backend.parse_cli_payload(started.text)
        return _fail(
            "agently",
            agently_backend.agently_error_message(payload, started.exit_code),
            label,
            started.text,
        )
    return _fail("agently", "等待授权链接超时。请确认本机已安装 CLI，然后重试「邮件授权」。", label, started.text)


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
