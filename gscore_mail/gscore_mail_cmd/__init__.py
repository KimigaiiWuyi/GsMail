"""主人侧核验命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..api import send, status

sv_mail = SV("gscore_mail", pm=0)


@sv_mail.on_fullmatch(("邮件状态", "mailstatus"), block=True)
async def cmd_mail_status(bot: Bot, ev: Event) -> None:
    st = await status()
    flag = "开" if st["enable_send"] else "关"
    ready = "就绪" if st["configured"] else "未就绪"
    await bot.send(f"[gscore_mail] 后端={st['backend']} {ready} 发送={flag}\n{st['detail']}")


@sv_mail.on_prefix(("测试发信", "mailtest"), block=True)
async def cmd_mail_test(bot: Bot, ev: Event) -> None:
    target = ev.text.strip()
    if not target or "@" not in target:
        await bot.send("用法：测试发信 user@example.com")
        return
    result = await send(
        to=target,
        subject="gscore_mail 测试",
        body="这是一封来自 GsCore gscore_mail 的测试邮件。",
    )
    prefix = "成功" if result["ok"] else "失败"
    label = result["account"] or result["backend"]
    await bot.send(f"[gscore_mail] {prefix}（{label}）：{result['message']}")
