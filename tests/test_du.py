"""Offline behavior checks; no account cookies, environment files, or live HTTP."""

import hashlib
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import du


CALENDAR = "/coins/taskcenter/signinlist"
TASKS = "/coins/taskcenter/tasklist"
SIGN = "/coins/taskcenter/signin"
AWARD = "/coins/taskcenter/signinaward"
DAILY_AWARD = "/api/taskscore/antisave"
LOGIN = "/api/loginstatus"
COOKIE = "BDUSS=offline-test; BAIDUID=OFFLINE-BROWSER:FG=1"


def calendar(signed=1, rewards=None):
    return {
        "errno": 0,
        "data": {
            "signed_today": signed,
            "day": 2,
            "signin_days": 2 if signed else 1,
            "signin_list": [{"day": 1, "signed": 1}, {"day": 2, "signed": signed}],
            "reward_list": [] if rewards is None else rewards,
        },
    }


def tasks(status=1):
    return {
        "errno": 0,
        "result": {
            "list": [
                {"task_type": 47, "task_status": 6, "task_id_str": "unrelated"},
                {
                    "task_type": 166,
                    "task_status": status,
                    "task_id": 123456789012345678,
                    "task_id_str": "123456789012345678",
                    "task_from": "task_sys_daily",
                },
            ]
        },
    }


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


class ScriptedSession:
    """Require each request to match the next expected route, in order."""

    def __init__(self, test, script):
        self.test = test
        self.script = list(script)
        self.headers = {}
        self.calls = []

    def get(self, url, *, params, timeout):
        path = urlsplit(url).path
        self.calls.append((path, dict(params)))
        self.test.assertTrue(self.script, f"Unexpected request: {path}")
        expected_path, payload = self.script.pop(0)
        self.test.assertEqual(path, expected_path)
        return FakeResponse(payload)

    def close(self):
        pass


class CheckInTests(unittest.TestCase):
    def client(self, script, params=None):
        session = ScriptedSession(self, script)
        with patch("du.requests.Session", return_value=session):
            client = du.BaiduPan(COOKIE, params)
        self.addCleanup(lambda: self.assertEqual(session.script, [], "Unconsumed requests"))
        return client, session

    def test_already_signed_and_claimed_does_not_write(self):
        client, session = self.client([(CALENDAR, calendar()), (TASKS, tasks())])
        result = client.run()
        self.assertTrue(result["ok"])
        self.assertTrue(result["already_signed"])
        self.assertEqual([path for path, _ in session.calls], [CALENDAR, TASKS])
        self.assertEqual(session.calls[0][1]["clienttype"], "5")
        self.assertEqual(session.calls[0][1]["cuid"], "OFFLINE-BROWSER")
        self.assertEqual(session.calls[0][1]["devuid"], "OFFLINE-BROWSER")

    def test_status_mode_reports_pending_rewards_without_writing(self):
        client, session = self.client([
            (CALENDAR, calendar(0, [{"day": 7, "received": 1}])),
            (TASKS, tasks(6)),
        ])
        result = client.run(status_only=True)
        self.assertTrue(result["ok"])
        self.assertFalse(result["signed_today"])
        self.assertEqual(result["task_status"], 6)
        self.assertEqual(result["claimable_milestones"], [7])
        self.assertEqual(len(session.calls), 2)

    def test_new_sign_in_is_verified_by_calendar(self):
        client, session = self.client([
            (CALENDAR, calendar(0)), (TASKS, tasks(0)),
            (SIGN, {"errno": 0}), (CALENDAR, calendar()), (TASKS, tasks()),
        ])
        result = client.run()
        self.assertTrue(result["ok"])
        self.assertFalse(result["already_signed"])
        self.assertTrue(result["signed_today"])
        sign_query = next(query for path, query in session.calls if path == SIGN)
        self.assertEqual(sign_query["task_id_str"], "123456789012345678")
        self.assertEqual(sign_query["is_growth"], "1")

    def test_http_200_business_error_does_not_report_sign_in_success(self):
        client, _ = self.client([
            (CALENDAR, calendar(0)), (TASKS, tasks(0)),
            (SIGN, {"errno": 2, "error": "param error"}), (CALENDAR, calendar(0)),
        ])
        with self.assertRaises(du.ApiError) as raised:
            client.run()
        self.assertEqual(raised.exception.code, 2)

    def test_success_response_without_calendar_change_is_unconfirmed(self):
        client, _ = self.client([
            (CALENDAR, calendar(0)), (TASKS, tasks(0)),
            (SIGN, {"errno": 0}), (CALENDAR, calendar(0)),
        ])
        with self.assertRaises(du.ApiError) as raised:
            client.run()
        self.assertEqual(raised.exception.code, "unconfirmed")

    def test_error_response_after_committed_sign_in_is_reconciled(self):
        client, session = self.client([
            (CALENDAR, calendar(0)), (TASKS, tasks(0)),
            (SIGN, {"errno": 9001, "error": "response interrupted"}),
            (CALENDAR, calendar()), (TASKS, tasks()),
        ])
        result = client.run()
        self.assertTrue(result["ok"])
        self.assertEqual(sum(path == SIGN for path, _ in session.calls), 1)

    def test_daily_reward_is_claimed_and_task_is_checked_again(self):
        client, session = self.client([
            (CALENDAR, calendar()), (TASKS, tasks(6)),
            (LOGIN, {"errno": 0, "login_info": {"uk": 42}}),
            (DAILY_AWARD, {"errno": 0, "result": {"addScore": 6, "addGrowScore": 2}}),
            (TASKS, tasks(1)),
        ])
        result = client.run()
        self.assertTrue(result["ok"])
        self.assertEqual(result["task_status"], "1")
        query = next(query for path, query in session.calls if path == DAILY_AWARD)
        self.assertEqual(query["task_id"], "123456789012345678")
        self.assertEqual(query["action"], "receive_award")
        self.assertEqual(query["uk"], 42)
        expected = hashlib.md5(
            b"123456789012345678_42_undefined_undefined_ae82c240578eb391de93c2f4c3dfc3ba"
        ).hexdigest()
        self.assertEqual(query["token"], expected)
        self.assertNotIn("rand", query)
        self.assertNotIn("time", query)

    def test_daily_reward_http_success_with_pending_task_is_not_success(self):
        client, _ = self.client([
            (CALENDAR, calendar()), (TASKS, tasks(6)),
            (LOGIN, {"errno": 0, "login_info": {"uk": 42}}),
            (DAILY_AWARD, {"errno": 0}), (TASKS, tasks(6)),
        ])
        result = client.run()
        self.assertFalse(result["ok"])
        self.assertTrue(result["signed_today"])
        self.assertEqual(result["task_status"], "6")
        self.assertIn("unconfirmed", result["errors"][0])

    def test_daily_reward_business_error_preserves_signed_state(self):
        client, _ = self.client([
            (CALENDAR, calendar()), (TASKS, tasks(6)),
            (LOGIN, {"errno": 0, "login_info": {"uk": 42}}),
            (DAILY_AWARD, {"errno": 8001, "error": "anti request rejected"}),
        ])
        result = client.run()
        self.assertFalse(result["ok"])
        self.assertTrue(result["signed_today"])
        self.assertEqual(result["task_status"], "6")
        self.assertIn("8001", result["errors"][0])

    def test_milestone_claim_requires_received_transition(self):
        pending = [{"day": 7, "received": 1}, {"day": 14, "received": 0}]
        claimed = [{"day": 7, "received": 2}, {"day": 14, "received": 0}]
        client, session = self.client([
            (CALENDAR, calendar(1, pending)), (TASKS, tasks()),
            (AWARD, {"errno": 0, "data": {"prize": [{"type": 10, "unit": 20}]}}),
            (CALENDAR, calendar(1, claimed)),
        ])
        result = client.run()
        self.assertTrue(result["ok"])
        self.assertEqual(result["claimed_milestones"], [7])
        query = next(query for path, query in session.calls if path == AWARD)
        self.assertEqual(query["day"], 7)
        self.assertNotIn("task_id", query)

    def test_milestone_claim_without_received_transition_is_not_success(self):
        pending = [{"day": 7, "received": 1}]
        client, _ = self.client([
            (CALENDAR, calendar(1, pending)), (TASKS, tasks()),
            (AWARD, {"errno": 0}), (CALENDAR, calendar(1, pending)),
        ])
        result = client.run()
        self.assertFalse(result["ok"])
        self.assertEqual(result["claimed_milestones"], [])


    def test_legacy_repeated_sign_and_answer_are_idempotent(self):
        client, _ = self.client([
            ("/rest/2.0/membership/level", {"errno": 421001, "error_msg": "repeat signin"}),
            ("/act/v2/membergrowv2/getdailyquestion", {
                "errno": 0, "data": {"answer_status": -1, "answer": 1, "ask_id": 1240},
            }),
            ("/act/v2/membergrowv2/answerquestion", {"errno": 9502, "show_msg": "today answered"}),
        ])
        self.assertEqual(client.run_legacy(), ["旧版今日已签到", "旧版今日已答题"])


class CalendarTests(unittest.TestCase):
    def test_signed_today_overrides_historical_and_current_calendar_entries(self):
        self.assertFalse(du.today_signed({
            "signed_today": 0, "day": 2,
            "signin_list": [{"day": 1, "signed": 1}, {"day": 2, "signed": 1}],
        }))
        self.assertTrue(du.today_signed({"signed_today": "1", "signin_list": []}))

    def test_history_does_not_count_as_today(self):
        self.assertFalse(du.today_signed({
            "day": 2, "signin_list": [{"day": 1, "signed": 1}, {"day": 2, "signed": 0}],
        }))
        self.assertTrue(du.today_signed({
            "day": "2", "signin_list": [{"day": 2, "signed": "1"}],
        }))

    def test_reward_units_match_official_prize_types(self):
        self.assertEqual(du.prize_text([
            {"type": 10, "unit": 20}, {"type": 3, "unit": 5},
        ]), "积分 +20、成长值 +5")


if __name__ == "__main__":
    unittest.main()
