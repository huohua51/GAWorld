import unittest

from gaworld.sim import _curiosity


def _agent():
    return {
        "id": 7,
        "name": "测试居民",
        "age": 31,
        "job": "外卖骑手",
        "personality": "务实，关注收入",
        "daily_life": "每天跑单，晚上看手机资讯",
        "values": "重视收入稳定",
        "state": {
            "stress": 0.7,
            "econ_security": 0.4,
            "platform_dependence": 0.6,
            "risk_preference": 0.5,
        },
        "growth_profile": {"items": [{"name": "理财", "kind": "skill", "priority": 1, "level": 0.2}]},
        "memory": [],
    }


class TestAssembleContext(unittest.TestCase):
    def test_assembles_four_signal_groups(self):
        ctx = _curiosity.assemble_curiosity_context(
            _agent(),
            scheduled_activity="跑单途中",
            recent_events=["平台调整了配送费规则"],
            day=2,
            time_str="12:30",
        )
        self.assertEqual(ctx["activity"], "跑单途中")
        self.assertIn("平台调整了配送费规则", ctx["recent_events"])
        self.assertAlmostEqual(ctx["state"]["stress"], 0.7)
        self.assertIn("理财", ctx["growth_focus"])
        self.assertEqual(ctx["day"], 2)
        self.assertEqual(ctx["time_str"], "12:30")


if __name__ == "__main__":
    unittest.main()
