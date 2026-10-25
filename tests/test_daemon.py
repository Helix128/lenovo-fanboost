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


def cfg(**kw):
    c = dict(fb.DEFAULTS, hold=10.0)
    c.update(kw)
    return fb.validate(c)


class FakeHwmon:
    def __init__(self, case):
        self.tmp = tempfile.TemporaryDirectory()
        case.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        for i, (n, files) in enumerate([
                ("k10temp", {"temp1_input": "40000\n"}),
                ("lenovo_fanboost", {"fan1_target": "0\n", "fan1_raw": "7\n"})]):
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


class ControllerTests(unittest.TestCase):
    def test_boost_at_threshold(self):
        c = fb.Controller(cfg())
        self.assertIsNone(c.step(69.9, 0))
        self.assertEqual(c.step(70.0, 1), "boost")
        self.assertIsNone(c.step(75, 2))

    def test_hold_and_release(self):
        c = fb.Controller(cfg())
        c.step(80, 0)
        self.assertIsNone(c.step(59, 1))      # below off, hold starts
        self.assertIsNone(c.step(59, 10.9))
        self.assertEqual(c.step(59, 11), "auto")

    def test_hysteresis_band_keeps_boost_and_resets_hold(self):
        c = fb.Controller(cfg())
        c.step(80, 0)
        c.step(55, 1)
        self.assertIsNone(c.step(65, 5))      # in band: hold timer reset
        self.assertIsNone(c.step(55, 6))
        self.assertIsNone(c.step(55, 15))     # only 9 s since restart
        self.assertEqual(c.step(55, 16), "auto")

    def test_levels(self):
        self.assertEqual(fb.level_rpm("low"), 2400)
        self.assertEqual(fb.level_rpm("medium"), 3200)
        self.assertEqual(fb.level_rpm("high"), 4000)

    def test_never_exceeds_max_or_below_auto(self):
        for lv in fb.LEVELS:
            self.assertTrue(0 < fb.level_rpm(lv) <= 4000)

    def test_validation(self):
        with self.assertRaises(ValueError):
            cfg(on=60, off=60)
        with self.assertRaises(ValueError):
            cfg(level="turbo")


class RunTests(unittest.TestCase):
    def run_loop(self, temps, hw, fail_at=None):
        it = iter(temps)
        now = [0.0]
        count = [0]

        def read():
            count[0] += 1
            if fail_at is not None and count[0] == fail_at:
                raise OSError("gone")
            return next(it)

        def stop():
            return count[0] >= len(temps)

        seen = []

        def sleep(_):
            now[0] += 1
            seen.append(hw.target())

        fb.run(cfg(interval=0.5), fb.Fan(os.path.join(hw.root, "hwmon1")),
               read, clock=lambda: now[0], sleep=sleep, stop=stop)
        return seen

    def test_boost_then_exit_writes_zero(self):
        hw = FakeHwmon(self)
        seen = self.run_loop([50, 72, 72, 65], hw)
        self.assertEqual(seen, [0, 3200, 3200, 3200])
        self.assertEqual(hw.target(), 0)

    def test_release_after_hold(self):
        hw = FakeHwmon(self)
        seen = self.run_loop([72] + [50] * 12, hw)
        self.assertEqual(seen[0], 3200)
        self.assertEqual(seen[-1], 0)
        self.assertEqual(hw.target(), 0)

    def test_sensor_fault_releases(self):
        hw = FakeHwmon(self)
        seen = self.run_loop([72, 72, 72], hw, fail_at=2)
        self.assertEqual(seen[:2], [3200, 0])

    def test_exception_still_writes_zero(self):
        hw = FakeHwmon(self)
        fan = fb.Fan(os.path.join(hw.root, "hwmon1"))

        def read():
            fan.set(3200)
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            fb.run(cfg(), fan, read, sleep=lambda _: None)
        self.assertEqual(hw.target(), 0)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.orig = cli.systemctl
        cli.systemctl = lambda *a: (self.calls.append(a), (0, "active"))[1]
        self.addCleanup(setattr, cli, "systemctl", self.orig)

    def config(self, text='[fanboost]\non = 65.0\nlevel = "high"   # comment\n'):
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
        fb.Fan(os.path.join(hw.root, "hwmon1")).set(3200)
        self.assertIn("boost", cli.status_line(a))

    def test_level_rewrites_config_and_restarts(self):
        p = self.config()
        orig = os.geteuid
        os.geteuid = lambda: 0
        self.addCleanup(setattr, os, "geteuid", orig)
        cli.main(["--config", p, "level", "low"])
        with open(p) as f:
            text = f.read()
        self.assertIn('level = "low"   # comment', text)
        self.assertIn(("restart", cli.SERVICE), self.calls)

    def test_level_requires_root(self):
        orig = os.geteuid
        os.geteuid = lambda: 1000
        self.addCleanup(setattr, os, "geteuid", orig)
        with self.assertRaises(SystemExit):
            cli.main(["--config", self.config(), "level", "low"])

    def test_find_hwmon(self):
        hw = FakeHwmon(self)
        self.assertTrue(fb.find_hwmon("k10temp", hw.root).endswith("hwmon0"))
        self.assertIsNone(fb.find_hwmon("nope", hw.root))


if __name__ == "__main__":
    unittest.main()
