"""异步 SMTP 发送（aiosmtplib，调用时再 import）。"""

from __future__ import annotations

from email.message import EmailMessage

from .settings import MailAccount


def _build_message(
    account: MailAccount,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str],
    html: bool,
) -> EmailMessage:
    from_addr = account.smtp_from or account.smtp_user
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    if html:
        msg.set_content(body, subtype="html")
    else:
        msg.set_content(body)
    return msg


async def send_smtp(
    account: MailAccount,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str],
    bcc: list[str],
    html: bool,
) -> None:
    try:
        import aiosmtplib
    except ImportError as exc:
        raise OSError("缺少依赖 aiosmtplib，请重启 Core 让插件按 pyproject.toml 自动安装") from exc

    msg = _build_message(account, to, subject, body, cc, html)
    recipients = to + cc + bcc
    use_tls = account.smtp_security == "ssl"
    start_tls = account.smtp_security == "starttls"
    username = account.smtp_user or None
    password = account.smtp_password if username else None
    await aiosmtplib.send(
        msg,
        hostname=account.smtp_host,
        port=account.smtp_port,
        username=username,
        password=password,
        recipients=recipients,
        timeout=account.smtp_timeout,
        use_tls=use_tls,
        start_tls=start_tls,
    )
