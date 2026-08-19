"""调用时读取配置，避免 import 期绑死。"""

from __future__ import annotations

import random
from dataclasses import dataclass

from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsIntConfig,
    GsStrConfig,
    GsBoolConfig,
    GsRepeatGroupConfig,
)

STRATEGIES = ("random", "failover", "never")


@dataclass(frozen=True)
class MailAccount:
    name: str
    enabled: bool
    kind: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_security: str
    smtp_timeout: int
    agently_cli: str
    agently_home: str
    agently_timeout: int


@dataclass(frozen=True)
class MailSettings:
    enable_send: bool
    send_strategy: str
    agently_auto_confirm: bool
    accounts: tuple[MailAccount, ...]


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


def _field_str(row: dict[str, GSC], key: str) -> str:
    if key not in row:
        return ""
    item = row[key]
    if isinstance(item, GsStrConfig):
        return item.data.strip()
    return ""


def _field_bool(row: dict[str, GSC], key: str, default: bool) -> bool:
    if key not in row:
        return default
    item = row[key]
    if isinstance(item, GsBoolConfig):
        return bool(item.data)
    return default


def _field_int(row: dict[str, GSC], key: str, default: int) -> int:
    if key not in row:
        return default
    item = row[key]
    if isinstance(item, GsIntConfig):
        value = int(item.data)
        return value if value > 0 else default
    return default


def account_label(account: MailAccount) -> str:
    if account.name:
        return account.name
    if account.kind == "agently":
        return "agently"
    return account.smtp_user or account.smtp_host or "smtp"


def smtp_ready(account: MailAccount) -> tuple[bool, str]:
    if not account.smtp_host:
        return False, "未配置 smtp_host"
    if not (account.smtp_from or account.smtp_user):
        return False, "未配置 smtp_from / smtp_user"
    return True, "SMTP 已配置"


def account_ready(account: MailAccount) -> tuple[bool, str]:
    if account.kind == "agently":
        if not account.agently_cli:
            return False, "未配置 agently_cli"
        return True, "Agently 已配置 CLI"
    return smtp_ready(account)


def smtp_from_row(row: dict[str, GSC], fallback_name: str) -> MailAccount:
    return MailAccount(
        name=_field_str(row, "name") or fallback_name,
        enabled=_field_bool(row, "enabled", True),
        kind="smtp",
        smtp_host=_field_str(row, "smtp_host"),
        smtp_port=_field_int(row, "smtp_port", 587),
        smtp_user=_field_str(row, "smtp_user"),
        smtp_password=_field_str(row, "smtp_password"),
        smtp_from=_field_str(row, "smtp_from"),
        smtp_security=_field_str(row, "smtp_security") or "starttls",
        smtp_timeout=_field_int(row, "smtp_timeout", 30),
        agently_cli="agently-cli",
        agently_home="",
        agently_timeout=60,
    )


def agently_from_row(row: dict[str, GSC], fallback_name: str) -> MailAccount:
    return MailAccount(
        name=_field_str(row, "name") or fallback_name,
        enabled=_field_bool(row, "enabled", True),
        kind="agently",
        smtp_host="",
        smtp_port=587,
        smtp_user="",
        smtp_password="",
        smtp_from="",
        smtp_security="starttls",
        smtp_timeout=30,
        agently_cli=_field_str(row, "agently_cli") or "agently-cli",
        agently_home=_field_str(row, "agently_home"),
        agently_timeout=_field_int(row, "agently_timeout", 60),
    )


def merge_accounts(smtp: list[MailAccount], agently: list[MailAccount]) -> tuple[MailAccount, ...]:
    """运行时池：SMTP 列表在前，Agently 列表在后。"""
    return tuple([*smtp, *agently])


def _unified_from_row(row: dict[str, GSC], fallback_name: str) -> MailAccount:
    kind = _field_str(row, "kind") or "smtp"
    if kind == "agently":
        return agently_from_row(row, fallback_name)
    return smtp_from_row(row, fallback_name)


def _smtp_raw(account: MailAccount) -> dict[str, object]:
    return {
        "name": account.name,
        "enabled": account.enabled,
        "smtp_host": account.smtp_host,
        "smtp_port": account.smtp_port,
        "smtp_user": account.smtp_user,
        "smtp_password": account.smtp_password,
        "smtp_from": account.smtp_from,
        "smtp_security": account.smtp_security,
        "smtp_timeout": account.smtp_timeout,
    }


def _agently_raw(account: MailAccount) -> dict[str, object]:
    return {
        "name": account.name,
        "enabled": account.enabled,
        "agently_cli": account.agently_cli,
        "agently_home": account.agently_home,
        "agently_timeout": account.agently_timeout,
    }


def _legacy_account() -> MailAccount | None:
    """两组与旧 mail_accounts 都空时，读更早的孤儿单账号键。"""
    backend = _str("backend") or "smtp"
    if backend not in ("smtp", "agently"):
        backend = "smtp"
    from ..gscore_mail_config import mail_config

    item = mail_config.get_config("smtp_host")
    has_smtp = isinstance(item, GsStrConfig) and bool(item.data.strip())
    cli_item = mail_config.get_config("agently_cli")
    has_agently = backend == "agently" or (isinstance(cli_item, GsStrConfig) and bool(cli_item.data.strip()))
    if not has_smtp and not has_agently:
        return None
    return MailAccount(
        name="legacy",
        enabled=True,
        kind=backend,
        smtp_host=_str("smtp_host"),
        smtp_port=_int_legacy("smtp_port", 587),
        smtp_user=_str("smtp_user"),
        smtp_password=_str("smtp_password"),
        smtp_from=_str("smtp_from"),
        smtp_security=_str("smtp_security") or "starttls",
        smtp_timeout=_int_legacy("smtp_timeout", 30),
        agently_cli=_str("agently_cli") or "agently-cli",
        agently_home="",
        agently_timeout=_int_legacy("agently_timeout", 60),
    )


def _int_legacy(key: str, default: int) -> int:
    from ..gscore_mail_config import mail_config

    item = mail_config.get_config(key)
    if isinstance(item, GsIntConfig):
        value = int(item.data)
        return value if value > 0 else default
    return default


def _group_rows(key: str) -> list[dict[str, GSC]]:
    from ..gscore_mail_config import mail_config

    item = mail_config.get_config(key)
    if not isinstance(item, GsRepeatGroupConfig):
        return []
    return list(item.data)


def _persist_split(accounts: tuple[MailAccount, ...]) -> None:
    from ..gscore_mail_config import mail_config

    smtp_raw = [_smtp_raw(account) for account in accounts if account.kind != "agently"]
    agently_raw = [_agently_raw(account) for account in accounts if account.kind == "agently"]
    mail_config.set_config("smtp_accounts", smtp_raw)
    mail_config.set_config("agently_accounts", agently_raw)


def _load_pool() -> tuple[MailAccount, ...]:
    smtp = [smtp_from_row(row, f"smtp-{index}") for index, row in enumerate(_group_rows("smtp_accounts"), start=1)]
    agently = [
        agently_from_row(row, f"agently-{index}") for index, row in enumerate(_group_rows("agently_accounts"), start=1)
    ]
    if smtp or agently:
        return merge_accounts(smtp, agently)
    unified = [
        _unified_from_row(row, f"account-{index}") for index, row in enumerate(_group_rows("mail_accounts"), start=1)
    ]
    if unified:
        split = tuple(unified)
        _persist_split(split)
        return split
    legacy = _legacy_account()
    return (legacy,) if legacy is not None else ()


def enabled_accounts(settings: MailSettings) -> list[MailAccount]:
    return [account for account in settings.accounts if account.enabled]


def agently_accounts(settings: MailSettings) -> list[MailAccount]:
    return [account for account in enabled_accounts(settings) if account.kind == "agently"]


def find_account(settings: MailSettings, name: str) -> MailAccount | None:
    needle = name.strip()
    if not needle:
        return None
    for account in settings.accounts:
        if account.name == needle:
            return account
    return None


def select_accounts(accounts: list[MailAccount], strategy: str) -> list[MailAccount]:
    """按策略排出本轮要尝试的账号。random / never 只返回一个；failover 返回全部启用项。"""
    enabled = [account for account in accounts if account.enabled]
    if not enabled:
        return []
    if strategy == "never":
        return [enabled[0]]
    if strategy == "random":
        return [random.choice(enabled)]
    return list(enabled)


def load_settings() -> MailSettings:
    strategy = _str("send_strategy") or "failover"
    if strategy not in STRATEGIES:
        strategy = "failover"
    return MailSettings(
        enable_send=_bool("enable_send"),
        send_strategy=strategy,
        agently_auto_confirm=_bool("agently_auto_confirm"),
        accounts=_load_pool(),
    )
