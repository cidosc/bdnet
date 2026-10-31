# 百度网盘新版每日签到

针对手机 App 扫码入口对应的[成长值任务页](https://pan.baidu.com/operation/activitys/taskSystem/growth?isFullScreen=1)，使用 Python 请求新版任务中心接口。`BAIDU_COOKIE` 与 [tunecc/DuPan](https://github.com/tunecc/DuPan) 相同。

默认完成：查询今日状态 → 未签时签到 → 回查日历 → 领取每日签到任务奖励 → 领取已达标的累计签到奖励。重复运行会根据服务端状态跳过已完成操作。任务 ID 从列表实时获取，不写死。

## 运行

需要 Python 3.10 或更新版本。

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `.env`：

```dotenv
BAIDU_COOKIE=BDUSS=...; STOKEN=...; BAIDUID=...;
```

已有 `.env` 时直接编辑，保留现有配置。填写 `pan.baidu.com` 的完整 Cookie，包含 `BAIDUID` 或 `MAWEBCUID`，脚本据此构造网页通道的 `cuid/devuid`。

```powershell
python du.py                 # 新版签到和领奖
python du.py --status        # 只查询状态
python du.py --json          # 机器可读结果
python du.py --with-legacy   # 额外运行旧版会员签到和每日答题
```

`.env`、日志、HAR 抓包文件及 `*.local.json` 均已加入 `.gitignore`。Cookie 只发给百度网盘。

## NUC 每日自动执行

选择一个实际运行位置，避免多台机器重复执行。

部署配置在 `deploy/bdnet-daily-signin.service` 和 `deploy/bdnet-daily-signin.timer`，使用当前用户的用户级 systemd 和独立 Python venv。部署目录为 `$HOME/bdnet-daily-signin`，unit 使用 `%h` 指向当前用户 home。每天 **Asia/Shanghai 09:15** 执行，错过时间会补跑；运行用户可按需启用 lingering。`.env` 由 Python 读取，文件权限设为 `600`。

维护命令：

```bash
systemctl --user status bdnet-daily-signin.timer
systemctl --user start bdnet-daily-signin.service
journalctl --user -u bdnet-daily-signin.service -n 30 --no-pager
# 暂停定时执行：
systemctl --user disable --now bdnet-daily-signin.timer
```

访问方式与凭据由实际部署环境单独配置。

### 可选 Windows 安装

仅在明确需要 Windows 作为运行位置时，在项目目录执行：

```powershell
.\install-task.ps1
# 自定义时间，例如：
.\install-task.ps1 -At '09:15'
```

安装当前用户的 `BDnet-DailySignIn` 计划任务，默认每天北京时间 09:15（使用 Windows 本地时区）。后台运行，日志在 `logs/YYYY-MM-DD.log`，错过运行时间会在电脑可用时补跑。任务需要这台电脑开机并登录当前 Windows 用户，无需保存 Windows 密码。

青龙：安装 Python 依赖 `requests`、`python-dotenv`，配置环境变量 `BAIDU_COOKIE`，任务命令 `task du.py`，cron `15 9 * * *`。Linux cron 同样可以每天调用 `python /绝对路径/du.py`。保留了 `handler(event, context)` 入口。

退出码 `0` 表示本次查询或执行成功，`1` 表示签到或领奖未完成；日志会区分“已签到”和“奖励领取失败”。

## 接口与奖励

| 步骤 | 接口 | 判断依据 |
| --- | --- | --- |
| 日历 | `/coins/taskcenter/signinlist` | `signed_today`，或 `day` 对应的 `signin_list[].signed` |
| 任务列表 | `/coins/taskcenter/tasklist` | `task_type=166` 为每日签到任务 |
| 签到 | `/coins/taskcenter/signin` | 提交后重新读取日历确认 |
| 每日任务领奖 | `/api/taskscore/antisave` | 待领 `task_status=6`；领取后重新查询确认 `task_status=1` |
| 累计签到领奖 | `/coins/taskcenter/signinaward` | `reward_list[].received=1` 待领，领取后确认变为 `2` |

签到和每日奖励领取是两个请求。累计奖励也单独领取。脚本依据 JSON 业务结果和回查状态判断，不把 HTTP 200 直接当成功。

默认采用已实测可查询的网页通道：`clienttype=5`，`cuid/devuid` 取 Cookie 中的 `MAWEBCUID`，其次取 `BAIDUID` 冒号前部分。`is_growth=1` 对应用户提供的成长值页面。

部分账号的每日奖励接口可能要求 App 上下文或风控参数。可在 `.env` 用 `BAIDU_TASK_PARAMS` JSON 补充**本人账号**的请求参数（如 `clienttype/cuid/devuid/z/rand/time/aid/ev/jt/jsToken`）。脚本合并这些参数并按官方公式计算每日领奖 `token`。有时效的 App 参数过期后仍需更新；未完成领取会返回失败，不能视为奖励到账。

## 已查到的新版实现

- [GGBondHere/QingLongScripts](https://github.com/GGBondHere/QingLongScripts/blob/79238495c2489b52a6cc001ba9d6703ae6d57955/scripts/baidupan.py)：动态获取签到任务，使用新版签到接口；源码明确提示 App 奖励仍需手动领取。
- [xvkong233/qlscript](https://github.com/xvkong233/qlscript/blob/91150efc89baec0a857203555b964502fafa58e7/baidu_netdisk.py)：有新版任务中心、网页与 App 参数研究；其网页通道在文档中仍属尝试，并未证明通用签到成功。
- [原作者的新版接口讨论](https://gist.github.com/BlueSkyXN/f451b01af21bbda885d191444356401f?permalink_comment_id=5832742)：也区分了签到打卡与每日奖励领取。

实现同时核对了百度官方当前页面构建 [index.ad414dee.js](https://staticplat.cdn.bcebos.com/taskSystem/js/index.ad414dee.js)。没有复制上述仓库的整份脚本或使用他人的设备参数。

## 验证

```powershell
python -m unittest discover -s tests -v
```

离线测试覆盖状态判断、重复运行、签到回查、每日与累计领奖等流程。实际签到和奖励到账需要在自有配置环境中验证。
