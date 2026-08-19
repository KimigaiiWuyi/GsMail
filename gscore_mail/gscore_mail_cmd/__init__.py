"""主人侧核验命令。"""

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..api import send, status, agently_login, resolve_send_to

sv_mail = SV("gscore_mail", pm=0)


@sv_mail.on_fullmatch(("邮件状态", "mailstatus"), block=True)
async def cmd_mail_status(bot: Bot, ev: Event) -> None:
    st = await status()
    flag = "开" if st["enable_send"] else "关"
    ready = "就绪" if st["configured"] else "未就绪"
    await bot.send(f"[gscore_mail] 后端={st['backend']} {ready} 发送={flag}\n{st['detail']}")


@sv_mail.on_command(("测试发信", "mailtest"), block=True)
async def cmd_mail_test(bot: Bot, ev: Event) -> None:
    target = resolve_send_to(ev.text, ev.bot_id, ev.user_id)
    if not target or "@" not in target:
        await bot.send("用法：测试发信 user@example.com（QQ / OneBot 可不填，默认 你的QQ号@qq.com）")
        return

    async def on_auth_url(url: str) -> None:
        await bot.send(f"Agently 需要微信授权。请打开此链接（不要改）：\n{url}\n扫码成功后会继续发测试信。")

    result = await send(
        to=target,
        subject="gscore_mail 测试",
        body="这是一封来自 GsCore gscore_mail 的测试邮件。",
        on_auth_url=on_auth_url,
    )
    prefix = "成功" if result["ok"] else "失败"
    label = result["account"] or result["backend"]
    await bot.send(f"[gscore_mail] {prefix}（{label}）→ {target}：{result['message']}")


@sv_mail.on_command(("邮件授权", "maillogin"), block=True)
async def cmd_mail_login(bot: Bot, ev: Event) -> None:
    result = await agently_login(ev.text.strip())
    await bot.send(f"[gscore_mail] {result['message']}")
