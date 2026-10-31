# BDnet 安全源码备份

- 快照日期：2026-10-31（Asia/Shanghai）。
- 来源目录：`D:/Softerware/AHack/BDnet`。
- 目标：`cidosc/bdnet` 私有仓库的独立首次提交，仅供源码备份。
- 原工作目录、原 Git 仓库和现有 NUC 部署均未更改。本次没有查询签到、执行部署或扩展开发。

## 文件清单

本备份包含以下 10 个白名单文件，另加本说明，共 11 个文件：

1. `.env.example`
2. `.gitignore`
3. `README.md`
4. `du.py`
5. `install-task.ps1`
6. `requirements.txt`
7. `run.ps1`
8. `tests/test_du.py`
9. `deploy/bdnet-daily-signin.service`
10. `deploy/bdnet-daily-signin.timer`

## 脱敏差异

- `.env.example` 经检查仅含空值和省略占位；测试中的离线 Cookie、用户 ID 和任务 ID 为虚构样本。
- `README.md` 移除实际 OS 用户名、用户目录、机器配置、部署与账号签到验收快照，并删除指向被排除运维记录的链接；保留通用操作说明。
- 用户级 service 模板将实际 home 绝对路径改为 `%h/bdnet-daily-signin`。该模板变化仅存在于备份副本，未用于现有部署。
- `du.py` 中 `SIGN_TOKEN_KEY` 是百度官方公开页面构建中的协议常量，已核对公开来源并保留；它不是用户凭据。
- 其余白名单文件保持来源字节内容。

## 排除范围

不包含 `.env`、`logs/`、Python/测试缓存、虚拟环境、HAR、`*.local.json`、`NUC_ACCESS_HANDOFF.md`、`deploy/NUC.md`，以及 Cookie、STOKEN、访问令牌、真实账号/设备数据、数据库、会话、SSH 或其他密钥。没有复制来源 `.git` 历史或配置。

推送前检查了工作副本、明确暂存清单和首次提交的完整可达对象历史。GitHub Actions 保持关闭，不建立部署流程、公开入口或协作者。
