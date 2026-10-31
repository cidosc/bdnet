#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
new Env('百度网盘新版每日签到')
cron: 15 9 * * *

BAIDU_COOKIE 与 tunecc/DuPan 兼容。默认执行新版签到和领奖；
--status 只查询，--with-legacy 同时执行旧版签到和答题。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_URL = "https://pan.baidu.com"
REFERER = BASE_URL + "/operation/activitys/taskSystem/growth?isFullScreen=1"
TASK_FROM = "task_sys_beginner task_sys_daily task_sys_space task_sys_ai task_sys_function task_sys_growth"
SIGN_TOKEN_KEY = "ae82c240578eb391de93c2f4c3dfc3ba"
CHINA_TZ = timezone(timedelta(hours=8))


class ApiError(RuntimeError):
    def __init__(self, path: str, code: object, message: str):
        self.path, self.code = path, code
        super().__init__(f"{path}: {message} (errno={code})")


def today_signed(calendar: dict) -> bool:
    """优先使用服务端当天标记，不把日历中的历史签到当作今天。"""
    if "signed_today" in calendar:
        return str(calendar["signed_today"]) == "1"
    return any(
        str(item.get("day")) == str(calendar.get("day"))
        and str(item.get("signed")) == "1"
        for item in calendar.get("signin_list", [])
    )


def prize_text(prizes: list) -> str:
    names = {"10": "积分", "3": "成长值"}
    return "、".join(
        f"{names.get(str(p.get('type')), p.get('name') or '奖励')} +{p.get('unit', '?')}"
        for p in prizes
    ) or "服务端未返回奖励明细"


class BaiduPan:
    def __init__(self, cookie: str, task_params: dict | None = None):
        jar = SimpleCookie()
        jar.load(cookie)
        device = jar.get("MAWEBCUID") or jar.get("BAIDUID")
        device_id = device.value.split(":", 1)[0] if device else ""
        self.params = {"clienttype": "5"}
        if device_id:
            self.params.update(cuid=device_id, devuid=device_id)
        self.params.update(task_params or {})
        self.session = requests.Session()
        self.session.headers.update({
            "Cookie": cookie,
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
            "Referer": REFERER,
            "X-Requested-With": "XMLHttpRequest",
        })

    def get(self, path: str, params: dict | None = None, *, client: bool = True) -> dict:
        query = {**(self.params if client else {}), **(params or {})}
        try:
            response = self.session.get(BASE_URL + path, params=query, timeout=(10, 20))
        except requests.RequestException as exc:
            # 不输出异常中的完整 URL，其中可能含 App 登录参数。
            raise ApiError(path, "network", type(exc).__name__) from exc
        if response.status_code != 200:
            raise ApiError(path, response.status_code, "HTTP 请求失败")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiError(path, "json", "服务端未返回 JSON") from exc
        code = payload.get("errno", payload.get("error_code"))
        if code is None or str(code) != "0":
            message = payload.get("error") or payload.get("error_msg") or payload.get("show_msg") or "请求失败"
            raise ApiError(path, code, str(message))
        return payload

    def calendar(self) -> dict:
        return self.get("/coins/taskcenter/signinlist", {"is_growth": "1"})["data"]

    def sign_task(self) -> dict:
        tasks = self.get("/coins/taskcenter/tasklist", {"task_from": TASK_FROM})["result"]["list"]
        for task in tasks:
            extra = task.get("task_extra") or {}
            if isinstance(extra, str):
                extra = json.loads(extra)
            if str(task.get("task_type", extra.get("task_type"))) == "166":
                return task
        return {}

    def claim_daily_reward(self, task: dict) -> str:
        login = self.get("/api/loginstatus", {"clienttype": "0"}, client=False)
        uk = login["login_info"]["uk"]
        task_id = str(task.get("task_id_str") or task["task_id"])
        # 与官方请求拦截器保持一致：没有 native rand/time 时 JS 拼接为 undefined。
        rand = self.params.get("rand", "undefined")
        timestamp = self.params.get("time", "undefined")
        token = hashlib.md5(f"{task_id}_{uk}_{rand}_{timestamp}_{SIGN_TOKEN_KEY}".encode()).hexdigest()
        result = self.get("/api/taskscore/antisave", {
            "task_id": task_id,
            "task_from": task["task_from"],
            "uk": uk,
            "action": "receive_award",
            "token": token,
        })
        updated = self.sign_task()
        if str(updated.get("task_status")) != "1":
            raise ApiError("/api/taskscore/antisave", "unconfirmed", "领取后任务尚未变为已完成")
        detail = result.get("result", {})
        if "addScore" in detail or "addGrowScore" in detail:
            return f"积分 +{detail.get('addScore', 0)}、成长值 +{detail.get('addGrowScore', 0)}"
        return prize_text(result.get("data", {}).get("prize", []))

    def run(self, *, status_only: bool = False) -> dict:
        calendar = self.calendar()
        task = self.sign_task()
        signed_before = today_signed(calendar)
        messages, errors = [], []
        if status_only:
            return {
                "ok": True, "status_only": True, "signed_today": signed_before,
                "signin_days": calendar.get("signin_days"),
                "task_status": task.get("task_status"),
                "claimable_milestones": [r["day"] for r in calendar.get("reward_list", []) if str(r.get("received")) == "1"],
            }

        if not signed_before:
            sign_params = {k: task[k] for k in ("task_id", "task_id_str", "task_from") if k in task}
            sign_error = None
            try:
                self.get("/coins/taskcenter/signin", {**sign_params, "is_growth": "1"})
            except ApiError as exc:
                sign_error = exc
            # 即使提交响应异常，也回查服务端，避免重试已生效的签到。
            calendar = self.calendar()
            if not today_signed(calendar):
                raise sign_error or ApiError("/coins/taskcenter/signin", "unconfirmed", "回查日历仍未签到")
            task = self.sign_task()
        messages.append("今日已签到" if signed_before else "新版签到成功，已回查确认")

        reward_status = str(task.get("task_status", "unknown"))
        if reward_status == "6":
            try:
                detail = self.claim_daily_reward(task)
                reward_status = "1"
                messages.append("每日签到奖励已领取：" + detail)
            except ApiError as exc:
                errors.append("签到已完成，每日奖励领取失败：" + str(exc))
        elif reward_status == "1":
            messages.append("每日签到任务已完成")
        else:
            errors.append(f"每日奖励状态尚未确认 (task_status={reward_status})")

        milestones = []
        for reward in calendar.get("reward_list", []):
            if str(reward.get("received")) != "1":
                continue
            day = reward["day"]
            try:
                result = self.get("/coins/taskcenter/signinaward", {"day": day})
                check = self.calendar()
                if not any(str(r.get("day")) == str(day) and str(r.get("received")) == "2" for r in check.get("reward_list", [])):
                    raise ApiError("/coins/taskcenter/signinaward", "unconfirmed", f"{day} 天奖励尚未确认到账")
                milestones.append(day)
                messages.append(f"累计 {day} 天奖励已领取：" + prize_text(result.get("data", {}).get("prize", [])))
            except ApiError as exc:
                errors.append(str(exc))

        return {
            "ok": not errors, "signed_today": True, "already_signed": signed_before,
            "signin_days": calendar.get("signin_days"), "task_status": reward_status,
            "claimed_milestones": milestones, "messages": messages, "errors": errors,
        }

    def run_legacy(self) -> list[str]:
        """可选兼容旧会员签到/答题，不用它替代新版签到的结果。"""
        query = {"app_id": "250528", "web": "5"}
        messages = []
        try:
            result = self.get("/rest/2.0/membership/level", {**query, "method": "signin"}, client=False)
            detail = result.get("data", result)
            messages.append(f"旧版签到返回积分：{detail.get('points', '未返回')}")
        except ApiError as exc:
            if str(exc.code) != "421001":
                raise
            messages.append("旧版今日已签到")
        question = self.get("/act/v2/membergrowv2/getdailyquestion", query, client=False)["data"]
        if str(question.get("answer_status")) == "1":
            messages.append("旧版今日已答题")
        elif "answer" in question and "ask_id" in question:
            try:
                result = self.get("/act/v2/membergrowv2/answerquestion", {
                    **query, "answer": question["answer"], "ask_id": question["ask_id"],
                }, client=False)
                detail = result.get("data", result)
                messages.append(f"旧版答题返回积分：{detail.get('score', '未返回')}")
            except ApiError as exc:
                if str(exc.code) != "9502":
                    raise
                messages.append("旧版今日已答题")
        return messages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="百度网盘新版签到与奖励领取")
    parser.add_argument("--status", action="store_true", help="只查询签到与领奖状态")
    parser.add_argument("--with-legacy", action="store_true", help="同时执行旧版会员签到和答题")
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    args = parser.parse_args(argv)
    load_dotenv(Path(__file__).with_name(".env"))
    cookie = os.getenv("BAIDU_COOKIE", "").strip()
    try:
        if not cookie:
            raise ValueError("请在环境变量或脚本旁的 .env 配置 BAIDU_COOKIE")
        params = json.loads(os.getenv("BAIDU_TASK_PARAMS", "{}"))
        if not isinstance(params, dict):
            raise ValueError("BAIDU_TASK_PARAMS 应为 JSON 对象")
        client = BaiduPan(cookie, params)
        try:
            result = client.run(status_only=args.status)
            if args.with_legacy and not args.status:
                try:
                    result["messages"].extend(client.run_legacy())
                except ApiError as exc:
                    result["ok"] = False
                    result["errors"].append("旧版接口失败：" + str(exc))
        finally:
            client.session.close()
    except (ApiError, ValueError, KeyError) as exc:
        result = {"ok": False, "errors": [str(exc)]}
    result["checked_at"] = datetime.now(CHINA_TZ).isoformat(timespec="seconds")
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"[{result['checked_at']}] 百度网盘新版签到")
        if args.status and result["ok"]:
            print(f"今日已签到：{result['signed_today']}；累计 {result['signin_days']} 天；任务状态 {result['task_status']}")
        for message in result.get("messages", []) + result.get("errors", []):
            print(message)
    return 0 if result["ok"] else 1


def handler(event=None, context=None):
    return main([])


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
