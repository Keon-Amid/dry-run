import json
import os
import tempfile
import unittest
from unittest import mock

from builder import state
from builder.types import STATE, State, StepResult


class StateTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.disk = self._td.name
        self.path = os.path.join(self.disk, STATE)

    def tearDown(self):
        self._td.cleanup()

    def test_missing_is_zero(self):
        st = state.load(self.disk)
        self.assertEqual(st.last_done, 0)
        self.assertEqual(st.steps, [])

    def test_roundtrip(self):
        st = State(last_done=2, patch_id="r1", patch_applied=True, model="m",
                   params={"max_calls": 5},
                   steps=[StepResult(step=1, commit="abc", tool_calls=3, capped=False, wall_s=1.5,
                                     model_calls=4)])
        state.save(self.disk, st)
        got = state.load(self.disk)
        self.assertEqual(got, st)
        self.assertIsInstance(got.steps[0], StepResult)
        with open(self.path) as f:
            self.assertEqual(json.load(f)["last_done"], 2)

    def test_atomic_sequence(self):
        calls = []
        real_fsync, real_replace = os.fsync, os.replace

        def fsync(fd):
            import stat
            calls.append(("fsync", stat.S_ISDIR(os.fstat(fd).st_mode)))
            return real_fsync(fd)

        def replace(a, b):
            calls.append(("replace", os.path.dirname(a) == os.path.dirname(b)))
            return real_replace(a, b)

        with mock.patch("builder.state.os.fsync", side_effect=fsync), \
                mock.patch("builder.state.os.replace", side_effect=replace):
            state.save(self.disk, State(last_done=1))
        kinds = [c[0] for c in calls]
        self.assertEqual(kinds, ["fsync", "replace", "fsync"])
        self.assertFalse(calls[0][1], "first fsync is the tmp file")
        self.assertTrue(calls[1][1], "tmp file must be in the same dir as state.json")
        self.assertTrue(calls[2][1], "last fsync is the directory")
        self.assertEqual(state.load(self.disk).last_done, 1)
        self.assertEqual(os.listdir(self.disk), [STATE])

    def test_failure_before_replace_keeps_old(self):
        state.save(self.disk, State(last_done=1))
        with open(self.path, "rb") as f:
            before = f.read()
        with mock.patch("builder.state.os.replace", side_effect=OSError("crash")):
            with self.assertRaises(OSError):
                state.save(self.disk, State(last_done=2))
        with open(self.path, "rb") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(state.load(self.disk).last_done, 1)
        self.assertEqual(os.listdir(self.disk), [STATE])  # tmp cleaned up

    def test_failure_during_fsync_keeps_old(self):
        state.save(self.disk, State(last_done=1))
        with mock.patch("builder.state.os.fsync", side_effect=OSError("io")):
            with self.assertRaises(OSError):
                state.save(self.disk, State(last_done=5))
        self.assertEqual(state.load(self.disk).last_done, 1)


if __name__ == "__main__":
    unittest.main()
