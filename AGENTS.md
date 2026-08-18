# AGENTS.md

> 本文件遵循 [AGENTS.md](https://agents.md/)：给编码 Agent 的仓库说明（README for agents）。
> 人类用户说明见 [README.md](./README.md)。源码是唯一事实源。

本仓库是 **GsCore 基础设施插件（meta plugin）**，独立于 `gsuid-core`。clone 到 `gsuid_core/plugins/gscore_mail/`，走插件安装 / 更新，不要跟框架一起提交。

## Skills

改本插件前先读框架技能入口，再按任务打开**一篇** `references/`，不要把整个技能塞进上下文：

- 入口：[gscore-plugin-development/SKILL.md](../../../.agents/skills/gscore-plugin-development/SKILL.md)
- 目录 / 嵌套加载 / **meta plugin** / Ruff·VS Code：[references/01-plugin-basics.md](../../../.agents/skills/gscore-plugin-development/references/01-plugin-basics.md)
- SV 与触发器（`on_fullmatch` / `on_prefix`、`pm=0`）：[references/02-sv-and-triggers.md](../../../.agents/skills/gscore-plugin-development/references/02-sv-and-triggers.md)
- 配置（`CONFIG_DEFAULT` / `StringConfig` / `GsRepeatGroupConfig` / `secret`）：[references/04-config-management.md](../../../.agents/skills/gscore-plugin-development/references/04-config-management.md)
- 纯 AI 工具（`@ai_tools`、`covers` / `aliases`、`visible_when`）：[references/11-ai-tools-decorator.md](../../../.agents/skills/gscore-plugin-development/references/11-ai-tools-decorator.md)
- 代码红线：[references/17-code-redlines.md](../../../.agents/skills/gscore-plugin-development/references/17-code-redlines.md)

命令同时也给用户点 → 用 `to_ai`，不要再叠 `@ai_tools`。本仓库的发信 / 读信是 **AI 专用**，命令是主人核验，两边分开是对的。见 [references/10-ai-to-ai-and-ai-return.md](../../../.agents/skills/gscore-plugin-development/references/10-ai-to-ai-and-ai-return.md)。

## Project overview

一个邮箱池，SMTP 与腾讯 Agently Mail 都是池成员。`send()` 按 `send_strategy` 挑选账号。

| 策略 | 行为 |
|------|------|
| `random` | `random.choice` 一条启用账号，失败不换 |
| `failover` | 按配置列表顺序，只有失败才试下一条 |
| `never` | 只用第一条启用账号 |

`[tool.gsuid] kind = "meta"`，`provides = "mail"`。框架先于常规插件加载本目录，并把 `gscore_mail` / `gscore_mail.api` 挂进 `sys.modules`。短 import 用的是**目录名**（`from gscore_mail.api import send`），不是 `provides`。

Agently 是 npm 包 `@tencent-qqmail/agently-cli`，**不是** PyPI。不要往 `pyproject.toml` 里写它。框架已有的 python / fastapi / pydantic / gsuid-core / sqlmodel / apscheduler / pydantic-ai 也不要重复声明。

## Repository map

```
.
├── AGENTS.md / README.md / pyproject.toml
├── ruff.toml / pyrightconfig.json
├── __init__.py / __nest__.py / __meta_plugin__.py
└── gscore_mail/
    ├── __init__.py           # Plugins(..., allow_empty_prefix=True)
    ├── __full__.py
    ├── api/
    │   ├── __init__.py       # send / status / agently_*
    │   ├── settings.py       # MailAccount / MailSettings / select_accounts
    │   ├── hosts.py          # SMTP_HOST_PRESETS
    │   ├── smtp.py           # 入参是 MailAccount
    │   └── agently.py        # CLI；可选 HOME 隔离
    ├── gscore_mail_config/   # enable_send / send_strategy / mail_accounts
    ├── gscore_mail_cmd/
    └── gscore_mail_tools/    # visible_when = 池里有启用的 Agently
```

运行时配置落在 `data/gscore_mail/gscore_mail_config.json`，不要写进仓库。

## Setup commands

在**本插件目录**执行。解释器指向 Core 仓库根 `.venv`。

```sh
uv run ruff check gscore_mail tests
uv run ruff format --check gscore_mail tests
uv run pytest tests -q
```

没有本目录 `.venv` 时，到 Core 仓库根用同一个解释器跑 `pytest gsuid_core/plugins/gscore_mail/tests`。

用 VS Code **打开本插件目录**。`pyrightconfig.json` 的 `extraPaths` 以本目录为 `gsuid_core/plugins/gscore_mail` 计算，指到 Core 仓库根。其他插件要看到本包类型，在**对方**的 `extraPaths` 加 `../gscore_mail`。详见技能 [§1.7](../../../.agents/skills/gscore-plugin-development/references/01-plugin-basics.md#17-插件仓库的-ruff--vs-code-配置)。

`ruff.toml` 必须排除 `pyproject.toml`。

## Code style

遵守技能 [十七、代码红线](../../../.agents/skills/gscore-plugin-development/references/17-code-redlines.md) 与 Core 根 `AGENTS.md` §1：

- 禁止用 `try/except` 掩盖类型或逻辑问题；禁止 `cast`、自身代码的 `type: ignore`、`getattr` / `dict.get` 兜底、`Any`、同步阻塞 I/O。
- 对外结果用 `TypedDict`（`MailSendResult` 含 `account`、`MailStatus`、`AgentlyRunResult`）。
- 函数全标注。`#` 注释最多两行、每行不超过 88 字。
- 行宽 120。isort：`known-first-party = ["gsuid_core", "gscore_mail"]`，`length-sort`。

本仓库**允许**的例外：

- `send()` 捕获 SMTP 网络/协议异常，转成 `ok=False`，并 `logger.warning`。
- `run_agently` 捕获 `FileNotFoundError` / `NotImplementedError` / 超时。
- `parse_cli_payload` 解析 CLI 文本；JSON 失败则原样返回字符串。
- `aiosmtplib` 缺失时 `smtp.py` 抛 `OSError`。

不要在消费者插件里 `try/except ImportError` 探测本包。软依赖只走 `import_api("gscore_mail")`。详见技能 [§1.6](../../../.agents/skills/gscore-plugin-development/references/01-plugin-basics.md#16-基础设施插件meta-plugin)。

## Testing

- 测试在 `tests/test_gscore_mail.py`。`monkeypatch` `load_settings`、`send_smtp`、`run_agently`。
- 不要打真实 SMTP / 真实 CLI。
- 改策略：覆盖 `select_accounts`（never 只留第一条启用；failover 去掉 disabled；random 长度为 1）以及 `send()` 的 failover / never。
- 改 CLI 参数：`--confirmed` vs `--confirmation-token`。
- 改 `send()` 契约：`enable_send=false`、空收件人、空主题必须 `ok=False`。
- 常见主机列表改了：断言 `CONFIG_DEFAULT["mail_accounts"].template["smtp_host"].options` 与 `SMTP_HOST_PRESETS` 一致。

## 本仓库结构约定

- **对外只从 `gscore_mail.api` 再导出。** 新发信能力加在 `send()` / `status()`，不要让别人 import `smtp` / `agently`。
- **配置每次调用再读。** `load_settings()` 解析 `mail_accounts`（`GsRepeatGroupConfig`）。组内字段用 `isinstance` 收窄后读 `.data`。
- **池为空时**才读旧版孤儿键 `backend` / `smtp_*` / `agently_*`，合成一条 `legacy` 账号。不要在新 UI 里把这些键加回去。
- **常见 SMTP 主机**只维护 `api/hosts.py` 的 `SMTP_HOST_PRESETS`，配置 `options` 必须引用它。
- **嵌套加载**：外层 `__nest__.py` + 内层 `__full__.py`。不要在内层 `__init__.py` 手工 import 子包。
- **命令** `pm=0`。状态 `on_fullmatch`，测试发信 `on_prefix`。
- **AI 工具** `category="common"`，带 `covers` / `aliases`。`send_email` 保持 `approval="user"`。Agently 三个工具 `visible_when` 看池里是否有启用的 `kind=agently`。
- `select_accounts` 是纯函数，单测直接喂 `MailAccount` 列表，不要为它 mock 配置文件。

## 坑点

1. **`provides` ≠ import 名。** `require("mail")` 用 `provides`；`import_api` / `from gscore_mail.api import send` 用目录名。
2. **策略语义不要混。** `random` 抽中谁就只试谁；`failover` 才依次换；`never` 失败也不碰后面的 Agently。
3. **Agently 是池成员，不是第二套全局后端。** 不要再加顶层 `backend=smtp|agently` 开关。
4. **多套 Agently 靠 `agently_home`。** CLI 默认把 token 放系统钥匙串 / 用户目录，同一 HOME 会抢同一登录。隔离目录要在 `run_agently(..., home=)` 里写成 `HOME` / `USERPROFILE` / `XDG_CONFIG_HOME`。
5. **`confirmed` 仍是全局库开关**（`agently_auto_confirm`），不是按账号配。AI `send_email(confirmed=False)` 默认不带 `--confirmed`。
6. **`html=True` 只对 SMTP 有效。** failover 到 Agently 时正文仍当纯文本 `--body`。
7. **`GsRepeatGroupConfig` 读取**是 `item["name"].data`，且必须先 `isinstance`。`set_config` 传入的是裸值列表，不是 GSC。见技能 [§4.6](../../../.agents/skills/gscore-plugin-development/references/04-config-management.md#46-可重复配置组-gsrepeatgroupconfig)。
8. **QQ SMTP 密码是授权码。** 池内 `smtp_password` 已 `secret=True`。
9. **邮件正文不可信。** `list_emails` / `read_email` 必须保留前缀；`message_id` 必须以 `msg_` 开头。
10. **`send()` 业务失败返回字典，不抛。** failover 全部失败时 `message` 拼各账号原因。
11. **不要**做成 PyPI 包，不要往 Core 里写 `MailAPI`，不要把 meta plugin 和 `on_meta` 搞混。
12. **加池字段**只改 `config_default.py` 的 `_ACCOUNT_TEMPLATE`。字段名是 `title` / `desc` / `data`。读取必须 `.data`。
13. **版本**改两处：`pyproject.toml` 与 `gscore_mail/version.py`。

## Security notes

- SMTP 授权码、Agently OAuth 都在运行机本地；不要写入 git，不要打进日志全文。
- `enable_send=false` 必须挡住整池（库 API 和 AI 工具）。
- AI 发信保持 `approval="user"`。
- 公网 Core 仍走框架的 `WS_TOKEN` / WebConsole 鉴权；本插件不另开端口。
