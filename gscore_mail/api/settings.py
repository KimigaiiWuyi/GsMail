"""调用时读取配置，避免 import 期绑死。"""

from dataclasses import dataclass

from gsuid_core.utils.plugins_config.models import GsIntConfig, GsStrConfig, GsBoolConfig


@dataclass(frozen=True)
class MailSettings:
    enable_send: bool
    backend: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_security: str
    smtp_timeout: int
    agently_cli: str
    agently_auto_confirm: bool
    agently_timeout: int


def _str(key: str) -> str:
    from ..gscore_mail_config import mail_config

    item = mail_config.get_config(key)
    if isinstance(item, GsStrConfig):
        return item.data.strip()
    return ""


def _bool(key: str) -> bool:
    from ..gscore_mail_config import mail_config

    item = mail_config.get_config(key)
    if isinstance(item, GsBoolConfig):
        return bool(item.data)
    return False


def _int(key: str) -> int:
    from ..gscore_mail_config import mail_config

    item = mail_config.get_config(key)
    if isinstance(item, GsIntConfig):
        return int(item.data)
    return 0


def load_settings() -> MailSettings:
    return MailSettings(
        enable_send=_bool("enable_send"),
        backend=_str("backend") or "smtp",
        smtp_host=_str("smtp_host"),
        smtp_port=_int("smtp_port") or 587,
        smtp_user=_str("smtp_user"),
        smtp_password=_str("smtp_password"),
        smtp_from=_str("smtp_from"),
        smtp_security=_str("smtp_security") or "starttls",
        smtp_timeout=_int("smtp_timeout") or 30,
        agently_cli=_str("agently_cli") or "agently-cli",
        agently_auto_confirm=_bool("agently_auto_confirm"),
        agently_timeout=_int("agently_timeout") or 60,
    )
