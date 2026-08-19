"""gscore_mail 配置项。"""

from typing import Dict

from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsDivider,
    GsIntConfig,
    GsStrConfig,
    GsBoolConfig,
    GsRepeatGroupConfig,
)

from ..api.hosts import SMTP_HOST_PRESETS

_SMTP_TEMPLATE: Dict[str, GSC] = {
    "name": GsStrConfig(
        title="备注名",
        desc="如 QQ主号 / 备用Gmail。永不切换时按 SMTP 列表再 Agently 列表的第一条启用账号发",
        data="",
    ),
    "enabled": GsBoolConfig(
        title="启用",
        desc="关闭后不参与发送与状态检查",
        data=True,
    ),
    "smtp_host": GsStrConfig(
        title="SMTP 主机",
        desc="常见服务商可直接选；其它请填完整主机名",
        data="",
        options=list(SMTP_HOST_PRESETS),
    ),
    "smtp_port": GsIntConfig(
        title="SMTP 端口",
        desc="STARTTLS 常用 587，SSL 常用 465",
        data=587,
    ),
    "smtp_user": GsStrConfig(
        title="SMTP 用户名",
        desc="通常是完整邮箱地址",
        data="",
    ),
    "smtp_password": GsStrConfig(
        title="SMTP 密码 / 授权码",
        desc="QQ 邮箱须用授权码，不是登录密码",
        data="",
        secret=True,
    ),
    "smtp_from": GsStrConfig(
        title="发件人 From",
        desc="留空则使用 SMTP 用户名",
        data="",
    ),
    "smtp_security": GsStrConfig(
        title="SMTP 加密",
        desc="starttls / ssl / none",
        data="starttls",
        options=["starttls", "ssl", "none"],
    ),
    "smtp_timeout": GsIntConfig(
        title="SMTP 超时（秒）",
        desc="连接与发送超时",
        data=30,
    ),
}

_AGENTLY_TEMPLATE: Dict[str, GSC] = {
    "name": GsStrConfig(
        title="备注名",
        desc="如 Agently-1。与 SMTP 备注不要重名",
        data="",
    ),
    "enabled": GsBoolConfig(
        title="启用",
        desc="关闭后不参与发送与状态检查",
        data=True,
    ),
    "agently_cli": GsStrConfig(
        title="agently-cli 路径",
        desc="默认从 PATH 找；可填绝对路径或 agently-cli.cmd",
        data="agently-cli",
    ),
    "agently_home": GsStrConfig(
        title="Agently 隔离目录",
        desc="可选。给该账号单独 HOME，便于同一机器多套 OAuth。留空用系统默认",
        data="",
    ),
    "agently_timeout": GsIntConfig(
        title="CLI 超时（秒）",
        desc="单次 agently-cli 最长等待",
        data=60,
    ),
}

CONFIG_DEFAULT: Dict[str, GSC] = {
    "enable_send": GsBoolConfig(
        title="允许发送",
        desc="关闭后库 API 与 AI 工具均拒绝发送（命令仍可查状态）",
        data=True,
    ),
    "send_strategy": GsStrConfig(
        title="发送策略",
        desc="合并顺序 SMTP 再 Agently。random=抽一条；failover=失败才切；never=只用合并后第一条",
        data="failover",
        options=["random", "failover", "never"],
    ),
    "agently_auto_confirm": GsBoolConfig(
        title="库 API 自动 --confirmed",
        desc="其它插件调用 send() 时 Agently 是否带 --confirmed。AI 工具默认仍需 confirmed=True",
        data=True,
    ),
    "SmtpSection": GsDivider("SMTP 账号", "QQ / Gmail / 163 等标准发信", "SMTP 账号"),
    "smtp_accounts": GsRepeatGroupConfig(
        title="SMTP 账号",
        desc="可添加多条。失败切换时先按本列表顺序，再试 Agently 列表",
        data=[],
        template=_SMTP_TEMPLATE,
    ),
    "AgentlySection": GsDivider("Agently 账号", "腾讯 Agently Mail", "Agently 账号"),
    "agently_accounts": GsRepeatGroupConfig(
        title="Agently 账号",
        desc="可添加多条。装好 CLI 后主人必须发「邮件授权」微信扫码，未授权不能发信",
        data=[],
        template=_AGENTLY_TEMPLATE,
    ),
}
