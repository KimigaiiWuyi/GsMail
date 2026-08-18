"""异步 SMTP 发送（aiosmtplib，调用时再 import）。"""

from __future__ import annotations

from email.message import EmailMessage

from .settings import MailSettings


def _build_message(
    settings: MailSettings,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str],
    html: bool,
) -> EmailMessage:
    from_addr = settings.smtp_from or settings.smtp_user
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
    settings: MailSettings,
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

    msg = _build_message(settings, to, subject, body, cc, html)
    recipients = to + cc + bcc
    use_tls = settings.smtp_security == "ssl"
    start_tls = settings.smtp_security == "starttls"
    username = settings.smtp_user or None
    password = settings.smtp_password if username else None
    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=username,
        password=password,
        recipients=recipients,
        timeout=settings.smtp_timeout,
        use_tls=use_tls,
        start_tls=start_tls,
    )
