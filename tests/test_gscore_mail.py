"""gscore_mail：邮箱池策略与公开 send()。随插件仓库走，不进 gsuid-core。"""

# ruff: noqa: E402
from __future__ import annotations

import sys
import asyncio
from pathlib import Path

import pytest

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from gscore_mail.api import send as mail_send, infer_qq_mail
from gscore_mail.api.hosts import SMTP_HOST_PRESETS
from gscore_mail.api.agently import (
    send_args,
    spawn_argv,
    resolve_cli,
    is_auth_error,
    extract_login_url,
    parse_cli_payload,
    extract_message_id,
    agently_error_message,
    extract_confirmation_token,
)
from gscore_mail.api.settings import (
    MailAccount,
    MailSettings,
    smtp_from_row,
    merge_accounts,
    select_accounts,
    agently_from_row,
)
from gscore_mail.gscore_mail_config.config_default import CONFIG_DEFAULT


def _account(**overrides: object) -> MailAccount:
    base = MailAccount(
        name="main",
        enabled=True,
        kind="smtp",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="from@example.com",
        smtp_password="secret",
        smtp_from="from@example.com",
        smtp_security="starttls",
        smtp_timeout=10,
        agently_cli="agently-cli",
        agently_home="",
        agently_timeout=15,
    )
    data = base.__dict__.copy()
    data.update(overrides)
    return MailAccount(**data)


def _settings(**overrides: object) -> MailSettings:
    accounts = overrides["accounts"] if "accounts" in overrides else (_account(),)
    if not isinstance(accounts, tuple):
        raise TypeError("accounts must be tuple[MailAccount, ...]")
    strategy = overrides["send_strategy"] if "send_strategy" in overrides else "failover"
    if not isinstance(strategy, str):
        raise TypeError("send_strategy must be str")
    enable_send = overrides["enable_send"] if "enable_send" in overrides else True
    if not isinstance(enable_send, bool):
        raise TypeError("enable_send must be bool")
    auto_confirm = overrides["agently_auto_confirm"] if "agently_auto_confirm" in overrides else True
    if not isinstance(auto_confirm, bool):
        raise TypeError("agently_auto_confirm must be bool")
    return MailSettings(
        enable_send=enable_send,
        send_strategy=strategy,
        agently_auto_confirm=auto_confirm,
        accounts=accounts,
    )


def test_smtp_host_presets_cover_common_providers() -> None:
    assert "smtp.gmail.com" in SMTP_HOST_PRESETS
    assert "smtp.qq.com" in SMTP_HOST_PRESETS
    assert "smtp.163.com" in SMTP_HOST_PRESETS
    pool = CONFIG_DEFAULT["smtp_accounts"]
    from gsuid_core.utils.plugins_config.models import GsStrConfig, GsRepeatGroupConfig

    assert isinstance(pool, GsRepeatGroupConfig)
    host = pool.template["smtp_host"]
    assert isinstance(host, GsStrConfig)
    assert host.options == SMTP_HOST_PRESETS


def test_config_splits_smtp_and_agently_groups() -> None:
    from gsuid_core.utils.plugins_config.models import GsRepeatGroupConfig

    assert "mail_accounts" not in CONFIG_DEFAULT
    smtp = CONFIG_DEFAULT["smtp_accounts"]
    agently = CONFIG_DEFAULT["agently_accounts"]
    assert isinstance(smtp, GsRepeatGroupConfig)
    assert isinstance(agently, GsRepeatGroupConfig)
    assert "smtp_host" in smtp.template
    assert "agently_cli" not in smtp.template
    assert "kind" not in smtp.template
    assert "agently_cli" in agently.template
    assert "smtp_host" not in agently.template
    assert "kind" not in agently.template


def test_row_parsers_and_merge_order() -> None:
    from gsuid_core.utils.plugins_config.models import GsIntConfig, GsStrConfig, GsBoolConfig

    smtp = smtp_from_row(
        {
            "name": GsStrConfig("", "", "qq"),
            "enabled": GsBoolConfig("", "", True),
            "smtp_host": GsStrConfig("", "", "smtp.qq.com"),
            "smtp_user": GsStrConfig("", "", "a@qq.com"),
            "smtp_password": GsStrConfig("", "", "auth"),
        },
        "smtp-1",
    )
    agently = agently_from_row(
        {
            "name": GsStrConfig("", "", "agent"),
            "enabled": GsBoolConfig("", "", True),
            "agently_cli": GsStrConfig("", "", "agently-cli"),
            "agently_timeout": GsIntConfig("", "", 45),
        },
        "agently-1",
    )
    assert smtp.kind == "smtp"
    assert smtp.smtp_host == "smtp.qq.com"
    assert agently.kind == "agently"
    assert agently.agently_timeout == 45
    pool = merge_accounts([smtp], [agently])
    assert [item.kind for item in pool] == ["smtp", "agently"]


def test_load_pool_prefers_split_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    import gscore_mail.api.settings as settings_mod
    import gscore_mail.gscore_mail_config as cfg_mod
    from gsuid_core.utils.plugins_config.models import GsStrConfig, GsBoolConfig, GsRepeatGroupConfig

    smtp_group = GsRepeatGroupConfig(
        title="",
        desc="",
        data=[
            {
                "name": GsStrConfig("", "", "qq"),
                "enabled": GsBoolConfig("", "", True),
                "smtp_host": GsStrConfig("", "", "smtp.qq.com"),
                "smtp_user": GsStrConfig("", "", "a@qq.com"),
            }
        ],
        template={},
    )
    agently_group = GsRepeatGroupConfig(
        title="",
        desc="",
        data=[
            {
                "name": GsStrConfig("", "", "agent"),
                "enabled": GsBoolConfig("", "", True),
                "agently_cli": GsStrConfig("", "", "agently-cli"),
            }
        ],
        template={},
    )
    old_group = GsRepeatGroupConfig(
        title="",
        desc="",
        data=[{"name": GsStrConfig("", "", "legacy-mixed"), "kind": GsStrConfig("", "", "smtp")}],
        template={},
    )
    written: list[tuple[str, object]] = []

    class _Fake:
        def get_config(self, key: str, default_value: object = None) -> object:
            if key == "smtp_accounts":
                return smtp_group
            if key == "agently_accounts":
                return agently_group
            if key == "mail_accounts":
                return old_group
            return GsBoolConfig("", "", False)

        def set_config(self, key: str, value: object) -> bool:
            written.append((key, value))
            return True

    monkeypatch.setattr(cfg_mod, "mail_config", _Fake())
    pool = settings_mod._load_pool()
    assert [item.name for item in pool] == ["qq", "agent"]
    assert written == []


def test_load_pool_migrates_unified_orphan(monkeypatch: pytest.MonkeyPatch) -> None:
    import gscore_mail.api.settings as settings_mod
    import gscore_mail.gscore_mail_config as cfg_mod
    from gsuid_core.utils.plugins_config.models import GsStrConfig, GsBoolConfig, GsRepeatGroupConfig

    empty = GsRepeatGroupConfig(title="", desc="", data=[], template={})
    old_group = GsRepeatGroupConfig(
        title="",
        desc="",
        data=[
            {
                "name": GsStrConfig("", "", "old-smtp"),
                "enabled": GsBoolConfig("", "", True),
                "kind": GsStrConfig("", "", "smtp"),
                "smtp_host": GsStrConfig("", "", "smtp.163.com"),
            },
            {
                "name": GsStrConfig("", "", "old-agent"),
                "enabled": GsBoolConfig("", "", True),
                "kind": GsStrConfig("", "", "agently"),
                "agently_cli": GsStrConfig("", "", "agently-cli"),
            },
        ],
        template={},
    )
    written: list[str] = []

    class _Fake:
        def get_config(self, key: str, default_value: object = None) -> object:
            if key in {"smtp_accounts", "agently_accounts"}:
                return empty
            if key == "mail_accounts":
                return old_group
            return GsBoolConfig("", "", False)

        def set_config(self, key: str, value: object) -> bool:
            written.append(key)
            return True

    monkeypatch.setattr(cfg_mod, "mail_config", _Fake())
    pool = settings_mod._load_pool()
    assert [item.name for item in pool] == ["old-smtp", "old-agent"]
    assert [item.kind for item in pool] == ["smtp", "agently"]
    assert written == ["smtp_accounts", "agently_accounts"]


def test_select_accounts_never_failover_random() -> None:
    first = _account(name="a")
    second = _account(name="b", kind="agently")
    off = _account(name="off", enabled=False)
    pool = [first, off, second]
    never = select_accounts(pool, "never")
    assert never == [first]
    fail = select_accounts(pool, "failover")
    assert fail == [first, second]
    picked = select_accounts(pool, "random")
    assert len(picked) == 1
    assert picked[0] in (first, second)


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


def test_extract_confirmation_token_and_message_id() -> None:
    pending = {"ok": True, "data": {"confirmation_token": "ctk_abc", "summary": "send?"}}
    assert extract_confirmation_token(pending) == "ctk_abc"
    assert extract_confirmation_token("please confirm ctk_xyz") == "ctk_xyz"
    assert extract_message_id({"ok": True, "data": {"id": "msg_1"}}) == "msg_1"
    assert extract_confirmation_token({"ok": True, "id": "msg_1"}) == ""


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
        assert result["account"] == "main"
        assert called

    asyncio.run(_run())


def test_send_agently_uses_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    import gscore_mail.api as api_mod

    captured: list[list[str]] = []

    async def fake_run(cli: str, args: list[str], timeout: int, home: str = "") -> dict[str, object]:
        captured.append(args)
        return {"exit_code": 0, "stdout": '{"id":"msg_1"}', "stderr": ""}

    async def _run() -> None:
        settings = _settings(accounts=(_account(name="ag1", kind="agently"),))
        monkeypatch.setattr(api_mod, "load_settings", lambda: settings)
        monkeypatch.setattr(api_mod.agently_backend, "run_agently", fake_run)
        result = await mail_send(to="to@ex.com", subject="S", body="B")
        assert result["ok"] is True
        assert result["backend"] == "agently"
        assert captured
        assert "--confirmed" in captured[0]

    asyncio.run(_run())


def test_send_agently_pending_token_is_not_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import gscore_mail.api as api_mod

    async def fake_run(cli: str, args: list[str], timeout: int, home: str = "") -> dict[str, object]:
        return {
            "exit_code": 0,
            "stdout": '{"ok":true,"data":{"confirmation_token":"ctk_hold","summary":"send?"}}',
            "stderr": "",
        }

    async def _run() -> None:
        settings = _settings(accounts=(_account(name="AG", kind="agently"),), agently_auto_confirm=False)
        monkeypatch.setattr(api_mod, "load_settings", lambda: settings)
        monkeypatch.setattr(api_mod.agently_backend, "run_agently", fake_run)
        result = await mail_send(to="to@ex.com", subject="S", body="B", confirmed=False)
        assert result["ok"] is False
        assert "尚未发出" in result["message"]
        assert "ctk_hold" in result["message"]

    asyncio.run(_run())


def test_send_agently_retries_confirmation_token(monkeypatch: pytest.MonkeyPatch) -> None:
    import gscore_mail.api as api_mod

    calls: list[list[str]] = []

    async def fake_run(cli: str, args: list[str], timeout: int, home: str = "") -> dict[str, object]:
        calls.append(args)
        if "--confirmation-token" in args:
            return {"exit_code": 0, "stdout": '{"ok":true,"id":"msg_9"}', "stderr": ""}
        return {
            "exit_code": 0,
            "stdout": '{"ok":true,"data":{"confirmation_token":"ctk_go"}}',
            "stderr": "",
        }

    async def _run() -> None:
        settings = _settings(accounts=(_account(name="AG", kind="agently"),))
        monkeypatch.setattr(api_mod, "load_settings", lambda: settings)
        monkeypatch.setattr(api_mod.agently_backend, "run_agently", fake_run)
        result = await mail_send(to="to@ex.com", subject="S", body="B", confirmed=True)
        assert result["ok"] is True
        assert "msg_9" in result["message"]
        assert any("--confirmation-token" in item and "ctk_go" in item for item in calls)

    asyncio.run(_run())


def test_failover_smtp_then_agently(monkeypatch: pytest.MonkeyPatch) -> None:
    import gscore_mail.api as api_mod

    async def boom(*_args: object) -> None:
        raise OSError("smtp down")

    captured: list[str] = []

    async def fake_run(cli: str, args: list[str], timeout: int, home: str = "") -> dict[str, object]:
        captured.append(cli)
        return {"exit_code": 0, "stdout": "ok", "stderr": ""}

    async def _run() -> None:
        settings = _settings(
            send_strategy="failover",
            accounts=(
                _account(name="qq", kind="smtp"),
                _account(name="agent", kind="agently", agently_cli="agently-cli"),
            ),
        )
        monkeypatch.setattr(api_mod, "load_settings", lambda: settings)
        monkeypatch.setattr(api_mod, "send_smtp", boom)
        monkeypatch.setattr(api_mod.agently_backend, "run_agently", fake_run)
        result = await mail_send(to="to@ex.com", subject="S", body="B")
        assert result["ok"] is True
        assert result["backend"] == "agently"
        assert result["account"] == "agent"
        assert captured

    asyncio.run(_run())


def test_never_does_not_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    import gscore_mail.api as api_mod

    async def boom(*_args: object) -> None:
        raise OSError("smtp down")

    called = {"agently": 0}

    async def fake_run(cli: str, args: list[str], timeout: int, home: str = "") -> dict[str, object]:
        called["agently"] += 1
        return {"exit_code": 0, "stdout": "ok", "stderr": ""}

    async def _run() -> None:
        settings = _settings(
            send_strategy="never",
            accounts=(
                _account(name="qq", kind="smtp"),
                _account(name="agent", kind="agently"),
            ),
        )
        monkeypatch.setattr(api_mod, "load_settings", lambda: settings)
        monkeypatch.setattr(api_mod, "send_smtp", boom)
        monkeypatch.setattr(api_mod.agently_backend, "run_agently", fake_run)
        result = await mail_send(to="to@ex.com", subject="S", body="B")
        assert result["ok"] is False
        assert result["account"] == "qq"
        assert called["agently"] == 0

    asyncio.run(_run())


def test_infer_qq_mail_onebot_only() -> None:
    assert infer_qq_mail("onebot", "444835641") == "444835641@qq.com"
    assert infer_qq_mail("qqgroup", "12345") == "12345@qq.com"
    assert infer_qq_mail("discord", "444835641") == ""
    assert infer_qq_mail("onebot", "abc") == ""


def test_extract_login_url_prefers_agent_qq() -> None:
    text = "open https://example.com/x and https://agent.qq.com/auth?code=1 please"
    assert extract_login_url(text) == "https://agent.qq.com/auth?code=1"


def test_agently_auth_error_is_human() -> None:
    payload = {"ok": False, "error": {"type": "auth", "message": "authorization required"}}
    assert is_auth_error(payload) is True
    msg = agently_error_message(payload, 3)
    assert "授权" in msg
    assert "authorization required" not in msg


class _FakeLogin:
    def __init__(self, url: str, exit_code: int) -> None:
        self.text = f"open {url}" if url else "no url"
        self.done = asyncio.Event()
        self.done.set()
        self.exit_code = exit_code
        self.notified = False
        self._url = url

    def url(self) -> str:
        return self._url

    async def wait_url(self, seconds: float) -> str:
        return self._url

    async def wait_done(self, seconds: float) -> bool:
        return True


def test_send_agently_auth_retries_after_oauth(monkeypatch: pytest.MonkeyPatch) -> None:
    import gscore_mail.api as api_mod

    sent: list[str] = []
    calls: list[list[str]] = []

    async def fake_run(cli: str, args: list[str], timeout: int, home: str = "") -> dict[str, object]:
        calls.append(args)
        if args[:2] == ["message", "+send"] and sum(1 for item in calls if item[:2] == ["message", "+send"]) == 1:
            return {
                "exit_code": 3,
                "stdout": '{"ok":false,"error":{"type":"auth","message":"authorization required"}}',
                "stderr": "",
            }
        return {"exit_code": 0, "stdout": "ok", "stderr": ""}

    async def fake_login(cli: str, home: str, key: str, ttl: int = 300) -> _FakeLogin:
        return _FakeLogin("https://agent.qq.com/auth?x=1", 0)

    async def fake_master(message: object) -> None:
        sent.append(str(message))

    async def _run() -> None:
        settings = _settings(accounts=(_account(name="AG", kind="agently"),))
        monkeypatch.setattr(api_mod, "load_settings", lambda: settings)
        monkeypatch.setattr(api_mod.agently_backend, "run_agently", fake_run)
        monkeypatch.setattr(api_mod.agently_backend, "begin_auth_login", fake_login)
        monkeypatch.setattr(api_mod, "send_msg_to_master", fake_master)
        result = await mail_send(to="a@b.c", subject="S", body="B")
        assert result["ok"] is True
        assert any("agent.qq.com" in item for item in sent)
        assert sum(1 for item in calls if item[:2] == ["message", "+send"]) == 2

    asyncio.run(_run())


def test_send_agently_auth_login_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    import gscore_mail.api as api_mod

    async def fake_run(cli: str, args: list[str], timeout: int, home: str = "") -> dict[str, object]:
        if args[:2] == ["message", "+send"]:
            return {
                "exit_code": 3,
                "stdout": '{"ok":false,"error":{"type":"auth","message":"authorization required"}}',
                "stderr": "",
            }
        return {"exit_code": 3, "stdout": "still unauthorized", "stderr": ""}

    async def fake_login(cli: str, home: str, key: str, ttl: int = 300) -> _FakeLogin:
        return _FakeLogin("https://agent.qq.com/auth?x=1", 1)

    async def fake_master(message: object) -> None:
        return None

    async def _run() -> None:
        settings = _settings(accounts=(_account(name="AG", kind="agently"),))
        monkeypatch.setattr(api_mod, "load_settings", lambda: settings)
        monkeypatch.setattr(api_mod.agently_backend, "run_agently", fake_run)
        monkeypatch.setattr(api_mod.agently_backend, "begin_auth_login", fake_login)
        monkeypatch.setattr(api_mod, "send_msg_to_master", fake_master)
        result = await mail_send(to="a@b.c", subject="S", body="B")
        assert result["ok"] is False
        assert "agent.qq.com" in result["message"]

    asyncio.run(_run())


def test_smtp_send_uses_starttls(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from gscore_mail.api.smtp import send_smtp

    captured: list[dict[str, object]] = []

    async def fake_send(msg: object, **kwargs: object) -> None:
        captured.append(kwargs)

    monkeypatch.setitem(sys.modules, "aiosmtplib", SimpleNamespace(send=fake_send))

    async def _run() -> None:
        await send_smtp(_account(), ["to@ex.com"], "S", "B", [], [], False)

    asyncio.run(_run())
    assert captured
    assert captured[0]["hostname"] == "smtp.example.com"
    assert captured[0]["port"] == 587
    assert captured[0]["start_tls"] is True
    assert captured[0]["use_tls"] is False
    assert captured[0]["username"] == "from@example.com"


def _write_npm_shim(root: Path) -> tuple[Path, Path, Path]:
    js = root / "node_modules" / "@tencent-qqmail" / "agently-cli" / "bin" / "cli.js"
    js.parent.mkdir(parents=True)
    js.write_text("console.log('ok')\n", encoding="utf-8")
    pkg = root / "node_modules" / "@tencent-qqmail" / "agently-cli" / "package.json"
    pkg.write_text('{"bin":{"agently-cli":"bin/cli.js"}}\n', encoding="utf-8")
    shim = root / "agently-cli"
    shim.write_text(
        '#!/bin/sh\nexec node "$basedir/node_modules/@tencent-qqmail/agently-cli/bin/cli.js" "$@"\n',
        encoding="utf-8",
    )
    cmd = root / "agently-cli.cmd"
    cmd.write_text(
        '@ECHO off\n"%_prog%"  "%dp0%\\node_modules\\@tencent-qqmail\\agently-cli\\bin\\cli.js" %*\n',
        encoding="utf-8",
    )
    return shim, cmd, js


def test_resolve_cli_prefers_windows_cmd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import gscore_mail.api.agently as agently_mod

    shim, cmd, _js = _write_npm_shim(tmp_path)
    monkeypatch.setattr(agently_mod.os, "name", "nt")
    assert Path(resolve_cli(str(shim))) == cmd


def test_spawn_argv_uses_node_entry_on_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import gscore_mail.api.agently as agently_mod

    _shim, cmd, js = _write_npm_shim(tmp_path)
    monkeypatch.setattr(agently_mod.os, "name", "nt")
    monkeypatch.setattr(agently_mod.shutil, "which", lambda name: r"C:\Node\node.exe" if name == "node.exe" else None)
    argv = spawn_argv(str(cmd), ["+me"])
    assert argv[0] == r"C:\Node\node.exe"
    assert Path(argv[1]) == js
    assert argv[2:] == ["+me"]


def test_run_agently_oserror_is_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import gscore_mail.api.agently as agently_mod

    async def boom(*_args: object, **_kwargs: object) -> object:
        raise OSError(193, "%1 is not a valid Win32 application")

    monkeypatch.setattr(agently_mod, "resolve_cli", lambda _cli: r"C:\npm\agently-cli.cmd")
    monkeypatch.setattr(agently_mod, "spawn_argv", lambda exe, args: [r"C:\Node\node.exe", *args])
    monkeypatch.setattr(agently_mod, "_windows_needs_pe", lambda _argv0: False)
    monkeypatch.setattr(agently_mod, "_spawn", boom)

    async def _run() -> None:
        result = await agently_mod.run_agently("agently-cli", ["+me"], 5)
        assert result["exit_code"] == 127
        assert "无法启动" in result["stderr"]

    asyncio.run(_run())
