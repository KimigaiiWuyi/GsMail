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

_ACCOUNT_TEMPLATE: Dict[str, GSC] = {
    "name": GsStrConfig(
        title="备注名",
        desc="如 QQ主号 / 备用Gmail / Agently-1。永不切换时按列表第一条启用账号发",
        data="",
    ),
    "enabled": GsBoolConfig(
        title="启用",
        desc="关闭后不参与发送与状态检查",
        data=True,
    ),
    "kind": GsStrConfig(
        title="类型",
        desc="smtp=标准 SMTP；agently=腾讯 Agently Mail（也是池里的一种）",
        data="smtp",
        options=["smtp", "agently"],
    ),
    "smtp_host": GsStrConfig(
        title="SMTP 主机",
        desc="常见服务商可直接选；其它请填完整主机名。仅 kind=smtp 时使用",
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
    "agently_cli": GsStrConfig(
        title="agently-cli 路径",
        desc="仅 kind=agently。默认从 PATH 找；可填绝对路径",
        data="agently-cli",
    ),
    "agently_home": GsStrConfig(
        title="Agently 隔离目录",
        desc="可选。给该账号单独 HOME，便于同一机器多套 OAuth。留空用系统默认",
        data="",
    ),
    "agently_timeout": GsIntConfig(
        title="CLI 超时（秒）",
        desc="仅 kind=agently。单次 agently-cli 最长等待",
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
        desc="random=每次随机抽一个账号；failover=按列表顺序，失败才切下一个；never=永远只用第一条启用账号",
        data="failover",
        options=["random", "failover", "never"],
    ),
    "agently_auto_confirm": GsBoolConfig(
        title="库 API 自动 --confirmed",
        desc="其它插件调用 send() 时 Agently 是否带 --confirmed。AI 工具默认仍需 confirmed=True",
        data=True,
    ),
    "PoolSection": GsDivider("邮箱池", "SMTP 与 Agently 都是池成员", "邮箱池"),
    "mail_accounts": GsRepeatGroupConfig(
        title="邮箱账号",
        desc="可添加多条 SMTP / 多条 Agently。策略作用于整个池，SMTP 失败可以兜底到 Agently",
        data=[],
        template=_ACCOUNT_TEMPLATE,
    ),
}
