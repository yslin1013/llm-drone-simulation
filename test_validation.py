import unittest
from app import validate_plan


class SafetyValidation(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_plan(self.plan())["takeoff_altitude_m"], 3.0)

    @staticmethod
    def plan():
        return dict(takeoff_altitude_m=3, forward_distance_m=5, yaw_clockwise_deg=90, land=True)

    def test_reject_invalid(self):
        for key, value in [("land", "false"), ("land", False),
                           ("takeoff_altitude_m", 100), ("takeoff_altitude_m", True),
                           ("forward_distance_m", -1), ("yaw_clockwise_deg", float("nan")),
                           ("yaw_clockwise_deg", float("inf"))]:
            with self.subTest(key=key, value=value):
                plan = self.plan()
                plan[key] = value
                with self.assertRaises(ValueError):
                    validate_plan(plan)

if __name__ == "__main__":
    unittest.main()
