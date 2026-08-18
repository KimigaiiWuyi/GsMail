# gscore_mail

独立的 GsCore **基础设施插件**（meta plugin），**不是** `gsuid-core` 框架的一部分。
请把本仓库 clone 到 `gsuid_core/plugins/gscore_mail/`，走插件安装/更新，不要跟框架一起提交。

Python 依赖写在 `pyproject.toml` 的 `[project].dependencies`（当前为 `aiosmtplib`），
Core 启动时会合并进一次 pip 安装。Agently CLI 需另行 `npm i -g @tencent-qqmail/agently-cli`。

提供 SMTP 与[腾讯 Agently Mail](https://agent.qq.com/doc/cli-setup.md) 两条发信后端，供其他插件和 AI 工具调用。

其他插件按普通 Python 导入（类型就是 `api` 里的注解）：

```python
from gscore_mail.api import send

result = await send(to="user@example.com", subject="标题", body="正文")
```

Core 加载后会把 `gscore_mail.api` 挂进 `sys.modules`，运行时能 import。
编辑器要看到类型，在**自己插件**的 `extraPaths` 加上本目录（`../gscore_mail`）。

软依赖（没装就跳过；不要自己 try/except）：

```python
from gsuid_core.meta_plugins import import_api

if import_api("gscore_mail") is None:
    return
from gscore_mail.api import send

result = await send(to="user@example.com", subject="标题", body="正文")
```

## 配置

网页控制台 → 插件管理 → gscore_mail。

| 项 | 说明 |
|----|------|
| `backend` | `smtp` 或 `agently` |
| `enable_send` | 总开关。关掉后库 API / AI 工具都拒绝发送 |
| SMTP 一组 | host / port / user / 授权码 / From / starttls\|ssl\|none |
| Agently 一组 | `agently-cli` 路径、库 API 是否自动 `--confirmed`、超时 |

QQ 邮箱 SMTP 必须填**授权码**，不是登录密码。

## Agently Mail（agent.qq.com）

按官方 CLI 文档：

```bash
npm install -g @tencent-qqmail/agently-cli
agently-cli auth login
agently-cli +me
```

`auth login` 会打印授权 URL，在浏览器完成 OAuth 后回到终端。管理端：https://agent.qq.com

本插件把 `agently-cli` 当外部进程调用（`message +send` / `auth status` / `+me` / `+list` / `+read`）。库 API 默认带 `--confirmed`（可关）；AI 工具默认不带，需模型传入 `confirmed=True`。

## 命令（主人 pm=0）

- `邮件状态` — 看后端是否就绪
- `测试发信 user@example.com` — 发一封测试信

## AI 工具

`send_email` / `mail_status`；backend=agently 时另有 `agently_whoami` / `list_emails` / `read_email`。邮件正文按不可信外部输入处理。

## 开发

用 VS Code **打开本插件目录**（`plugins/gscore_mail`）以加载 `.vscode`：推荐 Python / BasedPyright / Ruff，保存时 ruff format + organize imports。解释器默认指向仓库根 `.venv`。

```bash
# 在本插件目录
pre-commit install
pre-commit run --all-files
uv run ruff check gscore_mail tests
uv run ruff format --check gscore_mail tests
```
