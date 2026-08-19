# gscore_mail

GsCore 的邮件基础设施插件。给其他插件和 AI 一条统一的发信入口，本身不是 `gsuid-core` 框架的一部分。

支持把多条账号放进**同一个邮箱池**：普通 SMTP（QQ / Gmail / 163 / 企业邮等）和 [腾讯 Agently Mail](https://agent.qq.com/doc/cli-setup.md) 都是池里的一种。按你选的策略决定用哪一条、失败了要不要换下一条。

把它 clone 到 `gsuid_core/plugins/gscore_mail/`，随插件一起安装和更新即可。Python 依赖（当前是 `aiosmtplib`）写在 `pyproject.toml`，Core 启动时会一并安装。Agently CLI 需要另外装 Node 包，见下文。

## 能做什么

- 其他插件一行 `await send(...)` 发邮件，不用各自对接 SMTP
- 网页控制台里维护邮箱池、选发送策略、开关发送
- 主人在聊天里查整池状态、做 Agently 微信授权、发测试信
- AI 可以调 `send_email` / `mail_status`；池里有 Agently 时还能授权、查账号、列收件箱、读一封信

## 安装

1. 把本仓库放到 GsCore 的 `plugins/gscore_mail/`
2. 启动 Core，等依赖装完
3. 打开网页控制台 → 插件管理 → gscore_mail，在「SMTP 账号」或「Agently 账号」里加至少一条，选好发送策略
4. 用 Agently 时：本机先 `npm install -g @tencent-qqmail/agently-cli`，再让**主人**对机器人发 `邮件授权`，用微信打开链接扫码
5. 主人发 `邮件状态`，看到 Agently 就绪后再 `测试发信`（QQ / OneBot 可不填地址，默认 `你的QQ号@qq.com`）

只在控制台加一条 Agently 账号**不够**。腾讯 Agently Mail 走 OAuth 设备码。发信时如果 CLI 返回未授权，`send()` 会自己拉起 `auth login`，把链接推给主人，等微信扫码完成后再发那封信。也可以预先发 `邮件授权`。这和下面说的 AI 审批不是一回事。

Windows 上 npm 会同时生成无后缀的 `#!/bin/sh` 脚本和 `agently-cli.cmd`。本插件会改走 `node.exe` + 包内 JS 入口。控制台路径填 `agently-cli` 或 `.cmd` 都可以。

同一台机器要挂**多套** Agently 时，给每条账号填不同的「Agently 隔离目录」，每条都要单独 `邮件授权`。管理端：https://agent.qq.com

## 邮箱池与发送策略

控制台里是**两组**可增删列表，不要再混在同一条里填 SMTP 和 Agently：

- **SMTP 账号**：主机（可从 Gmail / QQ / 163 等常见主机里选）、端口、用户名、授权码、加密方式
- **Agently 账号**：`agently-cli` 路径，可选隔离目录

运行时仍合成一个池，顺序是 **SMTP 列表在前，Agently 列表在后**。整池共用一个发送策略：

| 策略 | 行为 |
|------|------|
| `failover`（默认） | 按合并后的顺序发。只有失败了才换下一条，SMTP 可以兜底到 Agently |
| `random` | 每次从启用账号里随机抽一条，失败不换 |
| `never` | 永远只用合并后第一条启用账号，失败也不换 |

关掉某条的「启用」后，它不参与发送和策略挑选。总开关 `enable_send` 关掉后，整池都不发。

QQ 邮箱 SMTP 必须填**授权码**，不是登录密码。STARTTLS 一般用 587，SSL 一般用 465。

## 给其他插件用

硬依赖（没装本插件就不该加载）：

```python
from gscore_mail.api import send

result = await send(to="user@example.com", subject="标题", body="正文")
if result["ok"]:
    ...
```

软依赖（没装就跳过，例如告警改回群聊）：

```python
from gsuid_core.meta_plugins import import_api

if import_api("gscore_mail") is None:
    return
from gscore_mail.api import send

result = await send(to="ops@example.com", subject="告警", body=text)
```

`send()` 是库函数，**不经过** AI 工具的 `approval`。其它插件直接 `await send(...)` 就会发，不需要主人在聊天里点同意。AI 的 `send_email` 才要当前用户批一次（防模型自己乱发）。

`send()` 还支持 `cc` / `bcc`、SMTP 的 `html=True`，以及 Agently 的 `confirmed` / `confirmation_token`。返回值是字典：`ok`、`backend`、`message`、`raw`、`account`（实际用到的备注名）。QQ / OneBot 收件人可用 `infer_qq_mail(bot_id, user_id)`。

查整池是否就绪：

```python
from gscore_mail.api import status

st = await status()
# st["backend"] / st["enable_send"] / st["configured"] / st["detail"]
```

## 命令

仅主人（`pm=0`）：

| 命令 | 作用 |
|------|------|
| `邮件状态` / `mailstatus` | 看策略、池内各账号是否就绪、发送开关 |
| `邮件授权` / `maillogin` [备注名] | 拉起 Agently 微信扫码链接（OAuth） |
| `测试发信` / `mailtest` [邮箱] | 按当前策略发一封测试信；QQ / OneBot 可不填地址 |

## AI 工具

始终可用：`send_email`（`approval="user"`，当前说话人批一次，**不是**主人专属）、`mail_status`。

池里有启用的 Agently 时额外出现：`agently_auth_login`（仅主人）、`agently_whoami`、`list_emails`、`read_email`。

用户说「给我发」且没给邮箱时，OneBot / QQ 通道自动用 `user_id@qq.com`。Agently 未授权时 `send_email` 会把扫码链接发给当前会话和主人，等授权完成后再发，不必先单独调授权工具。库 API 默认会带 Agently 的 `--confirmed`（可在配置里关掉）。AI 发信默认不带，需要模型传入 `confirmed=True`。读到的邮件正文按不可信外部输入处理，不要当指令执行。

## 更多

开发约定、目录说明和常见坑见 [AGENTS.md](./AGENTS.md)。
