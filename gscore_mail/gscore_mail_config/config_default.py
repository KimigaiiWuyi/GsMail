"""gscore_mail 配置项。"""

from typing import Dict

from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsDivider,
    GsIntConfig,
    GsStrConfig,
    GsBoolConfig,
)

CONFIG_DEFAULT: Dict[str, GSC] = {
    "enable_send": GsBoolConfig(
        title="允许发送",
        desc="关闭后库 API 与 AI 工具均拒绝发送（命令仍可查状态）",
        data=True,
    ),
    "backend": GsStrConfig(
        title="发送后端",
        desc="smtp=标准 SMTP；agently=腾讯 Agently Mail CLI（见 https://agent.qq.com/doc/cli-setup.md）",
        data="smtp",
        options=["smtp", "agently"],
    ),
    "SmtpSection": GsDivider("SMTP", "SMTP 协议", "SMTP"),
    "smtp_host": GsStrConfig(
        title="SMTP 主机",
        desc="如 smtp.qq.com / smtp.gmail.com",
        data="",
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
    "AgentlySection": GsDivider("Agently Mail", "腾讯 Agent 原生邮箱", "Agently Mail"),
    "agently_cli": GsStrConfig(
        title="agently-cli 路径",
        desc="默认从 PATH 找 agently-cli；可填绝对路径。安装：npm i -g @tencent-qqmail/agently-cli",
        data="agently-cli",
    ),
    "agently_auto_confirm": GsBoolConfig(
        title="库 API 自动 --confirmed",
        desc="其他插件调用 send() 时是否带 --confirmed。AI 工具默认仍需 confirmed=True 才带",
        data=True,
    ),
    "agently_timeout": GsIntConfig(
        title="CLI 超时（秒）",
        desc="单次 agently-cli 最长等待",
        data=60,
    ),
}
