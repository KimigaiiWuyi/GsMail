"""gscore_mail：SMTP / Agently 后端与公开 send()。随插件仓库走，不进 gsuid-core。"""

# ruff: noqa: E402
from __future__ import annotations

import sys
import asyncio
from pathlib import Path

import pytest

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from gscore_mail.api import send as mail_send
from gscore_mail.api.agently import send_args, parse_cli_payload
from gscore_mail.api.settings import MailSettings


def _settings(**overrides: object) -> MailSettings:
    base = MailSettings(
        enable_send=True,
        backend="smtp",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="from@example.com",
        smtp_password="secret",
        smtp_from="from@example.com",
        smtp_security="starttls",
        smtp_timeout=10,
        agently_cli="agently-cli",
        agently_auto_confirm=True,
        agently_timeout=15,
    )
    data = base.__dict__.copy()
    data.update(overrides)
    return MailSettings(**data)


def test_agently_send_args_confirmed_and_token() -> None:
    args = send_args(["a@b.c"], "Hi", "Body", [], [], True, "")
    assert args[:2] == ["message", "+send"]
    assert "--to" in args and "a@b.c" in args
    assert "--confirmed" in args
    assert "--confirmation-token" not in args

    args2 = send_args(["a@b.c"], "Hi", "Body", ["c@d.e"], [], False, "ctk_1")
    assert "--confirmed" not in args2
    assert args2[args2.index("--confirmation-token") + 1] == "ctk_1"
    assert "c@d.e" in args2


def test_parse_cli_payload_json_and_text() -> None:
    assert parse_cli_payload('{"ok": true}') == {"ok": True}
    assert parse_cli_payload("not-json") == "not-json"
    assert parse_cli_payload("  ") == ""


def test_send_disabled_and_empty_to(monkeypatch: pytest.MonkeyPatch) -> None:
    import gscore_mail.api as api_mod

    async def _run() -> None:
        monkeypatch.setattr(api_mod, "load_settings", lambda: _settings(enable_send=False))
        off = await mail_send(to="a@b.c", subject="s", body="b")
        assert off["ok"] is False
        assert "enable_send" in off["message"]

        monkeypatch.setattr(api_mod, "load_settings", lambda: _settings(enable_send=True))
        empty = await mail_send(to="", subject="s", body="b")
        assert empty["ok"] is False
        assert "收件人" in empty["message"]

    asyncio.run(_run())


def test_send_smtp_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import gscore_mail.api as api_mod

    called: list[object] = []

    async def fake_smtp(*args: object) -> None:
        called.append(args)

    async def _run() -> None:
        monkeypatch.setattr(api_mod, "load_settings", lambda: _settings())
        monkeypatch.setattr(api_mod, "send_smtp", fake_smtp)
        result = await mail_send(to="to@ex.com", subject="S", body="B", cc="c@ex.com")
        assert result["ok"] is True
        assert result["backend"] == "smtp"
        assert called

    asyncio.run(_run())


def test_send_agently_uses_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    import gscore_mail.api as api_mod

    captured: list[list[str]] = []

    async def fake_run(cli: str, args: list[str], timeout: int) -> dict[str, object]:
        captured.append(args)
        return {"exit_code": 0, "stdout": '{"id":"msg_1"}', "stderr": ""}

    async def _run() -> None:
        monkeypatch.setattr(api_mod, "load_settings", lambda: _settings(backend="agently"))
        monkeypatch.setattr(api_mod.agently_backend, "run_agently", fake_run)
        result = await mail_send(to="to@ex.com", subject="S", body="B")
        assert result["ok"] is True
        assert result["backend"] == "agently"
        assert captured
        assert "--confirmed" in captured[0]

    asyncio.run(_run())


def test_smtp_send_uses_starttls(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from gscore_mail.api.smtp import send_smtp

    captured: list[dict[str, object]] = []

    async def fake_send(msg: object, **kwargs: object) -> None:
        captured.append(kwargs)

    monkeypatch.setitem(sys.modules, "aiosmtplib", SimpleNamespace(send=fake_send))

    async def _run() -> None:
        await send_smtp(_settings(), ["to@ex.com"], "S", "B", [], [], False)

    asyncio.run(_run())
    assert captured
    assert captured[0]["hostname"] == "smtp.example.com"
    assert captured[0]["port"] == 587
    assert captured[0]["start_tls"] is True
    assert captured[0]["use_tls"] is False
    assert captured[0]["username"] == "from@example.com"
