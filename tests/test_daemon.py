import importlib.machinery
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    path = os.path.join(HERE, "..", "daemon", name)
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


fb = load("lenovo-fanboostd")
cli = load("lenovo-fanboost")


class FakeHwmon:
    def __init__(self, case, max_rpm=4000):
        self.tmp = tempfile.TemporaryDirectory()
        case.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        for i, (n, files) in enumerate([
                ("k10temp", {"temp1_input": "40000\n"}),
                ("lenovo_fanboost", {"fan1_target": "0\n", "fan1_raw": "7\n", "fan1_max": f"{max_rpm}\n"})]):
            d = os.path.join(self.root, f"hwmon{i}")
            os.mkdir(d)
            with open(os.path.join(d, "name"), "w") as f:
                f.write(n + "\n")
            for k, v in files.items():
                with open(os.path.join(d, k), "w") as f:
                    f.write(v)
        self.fan = os.path.join(self.root, "hwmon1", "fan1_target")

    def target(self):
        with open(self.fan) as f:
            return int(f.read())


class CurveTests(unittest.TestCase):
    def test_interpolate_percent_bounds(self):
        pts = [[50, 0], [60, 40], [80, 80], [90, 100]]
        self.assertEqual(fb.interpolate_percent(pts, 40), 0.0)
        self.assertEqual(fb.interpolate_percent(pts, 50), 0.0)
        self.assertEqual(fb.interpolate_percent(pts, 95), 100.0)

    def test_interpolate_percent_linear(self):
        pts = [[50, 0], [70, 50], [90, 100]]
        self.assertAlmostEqual(fb.interpolate_percent(pts, 60), 25.0)
        self.assertAlmostEqual(fb.interpolate_percent(pts, 70), 50.0)
        self.assertAlmostEqual(fb.interpolate_percent(pts, 80), 75.0)

    def test_percent_to_rpm(self):
        self.assertEqual(fb.percent_to_rpm(0, 4000), 0)
        self.assertEqual(fb.percent_to_rpm(100, 4000), 4000)
        self.assertEqual(fb.percent_to_rpm(50, 4000), 2000)
        # Test custom hardware max rpm (e.g. 5000)
        self.assertEqual(fb.percent_to_rpm(50, 5000), 2500)
        # Test rounding to 50 RPM steps
        # 33% of 4000 = 1320 -> round to 1300
        self.assertEqual(fb.percent_to_rpm(33, 4000), 1300)

    def test_curve_controller_steps(self):
        pts = [[50, 0], [60, 50], [80, 100]]
        c = fb.CurveController(pts, max_rpm=4000)
        self.assertIsNone(c.step(45))  # target 0, already 0
        self.assertEqual(c.step(60), 2000)  # changes to 2000
        self.assertIsNone(c.step(60))  # unchanged
        self.assertEqual(c.step(80), 4000)  # changes to 4000
        self.assertEqual(c.step(40), 0)  # return to EC auto

    def test_curve_controller_fault(self):
        pts = [[50, 0], [60, 50]]
        c = fb.CurveController(pts, max_rpm=4000)
        c.step(60)
        self.assertEqual(c.current_target, 2000)
        self.assertEqual(c.fault(), 0)
        self.assertIsNone(c.fault())


class ConfigTests(unittest.TestCase):
    def test_load_default_profiles(self):
        cfg = fb.load_config("/nonexistent.toml")
        self.assertEqual(cfg["profile"], "Balanced")
        self.assertIn("Balanced", cfg["profiles"])
        self.assertIn("Quiet", cfg["profiles"])
        self.assertIn("Aggressive", cfg["profiles"])

    def test_legacy_level_mapping(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".toml") as f:
            f.write('[fanboost]\nlevel = "high"\n')
            f.flush()
            cfg = fb.load_config(f.name)
            self.assertEqual(cfg["profile"], "Aggressive")

    def test_custom_profile_loading(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".toml") as f:
            f.write('[fanboost]\nprofile = "Custom"\n\n[profiles.Custom]\npoints = [[30, 0], [80, 100]]\n')
            f.flush()
            cfg = fb.load_config(f.name)
            self.assertEqual(cfg["profile"], "Custom")
            self.assertEqual(cfg["points"], [[30.0, 0.0], [80.0, 100.0]])


class RunTests(unittest.TestCase):
    def run_loop(self, temps, hw, fail_at=None):
        it = iter(temps)
        now = [0.0]
        count = [0]

        def read():
            count[0] += 1
            if fail_at is not None and count[0] == fail_at:
                raise OSError("sensor read error")
            return next(it)

        def stop():
            return count[0] >= len(temps)

        seen = []

        def sleep(_):
            now[0] += 1
            seen.append(hw.target())

        cfg = {
            "profile": "Balanced",
            "interval": 0.5,
            "points": [[50, 0], [70, 50], [90, 100]]
        }
        fb.run(cfg, fb.Fan(os.path.join(hw.root, "hwmon1")),
               read, clock=lambda: now[0], sleep=sleep, stop=stop)
        return seen

    def test_boost_then_exit_writes_zero(self):
        hw = FakeHwmon(self)
        seen = self.run_loop([40, 70, 70, 40], hw)
        self.assertEqual(seen, [0, 2000, 2000, 0])
        self.assertEqual(hw.target(), 0)

    def test_sensor_fault_releases(self):
        hw = FakeHwmon(self)
        seen = self.run_loop([70, 70, 70], hw, fail_at=2)
        self.assertEqual(seen[:2], [2000, 0])

    def test_exception_still_writes_zero(self):
        hw = FakeHwmon(self)
        fan = fb.Fan(os.path.join(hw.root, "hwmon1"))

        def read():
            fan.set(3200)
            raise KeyboardInterrupt

        cfg = {
            "profile": "Balanced",
            "interval": 0.5,
            "points": [[50, 0], [90, 100]]
        }
        with self.assertRaises(KeyboardInterrupt):
            fb.run(cfg, fan, read, sleep=lambda _: None)
        self.assertEqual(hw.target(), 0)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.orig = cli.systemctl
        cli.systemctl = lambda *a: (self.calls.append(a), (0, "active"))[1]
        self.addCleanup(setattr, cli, "systemctl", self.orig)

    def config(self, text='[fanboost]\nprofile = "Balanced"\n'):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        p = os.path.join(d.name, "c.toml")
        with open(p, "w") as f:
            f.write(text)
        return p

    def test_status_line_auto_and_boost(self):
        hw = FakeHwmon(self)
        a = cli.main.__globals__["argparse"].Namespace(hwmon_root=hw.root)
        self.assertIn("auto", cli.status_line(a))
        fb.Fan(os.path.join(hw.root, "hwmon1")).set(2600)
        self.assertIn("boost", cli.status_line(a))
        self.assertIn("65%", cli.status_line(a))

    def test_profile_rewrites_config_and_restarts(self):
        p = self.config()
        orig = os.geteuid
        os.geteuid = lambda: 0
        self.addCleanup(setattr, os, "geteuid", orig)
        cli.main(["--config", p, "profile", "Quiet"])
        with open(p) as f:
            text = f.read()
        self.assertIn('profile = "Quiet"', text)
        self.assertIn(("restart", cli.SERVICE), self.calls)

    def test_profile_requires_root(self):
        orig = os.geteuid
        os.geteuid = lambda: 1000
        self.addCleanup(setattr, os, "geteuid", orig)
        with self.assertRaises(SystemExit):
            cli.main(["--config", self.config(), "profile", "Quiet"])

    def test_find_hwmon(self):
        hw = FakeHwmon(self)
        self.assertTrue(fb.find_hwmon("k10temp", hw.root).endswith("hwmon0"))
        self.assertIsNone(fb.find_hwmon("nope", hw.root))


if __name__ == "__main__":
    unittest.main()
