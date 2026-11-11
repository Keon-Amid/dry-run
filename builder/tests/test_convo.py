import json
import os
import tempfile
import unittest
from unittest import mock

from builder import convo
from builder.types import CONVERSATION


class ConvoTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.disk = self._td.name
        self.path = os.path.join(self.disk, CONVERSATION)

    def tearDown(self):
        self._td.cleanup()

    def test_empty_when_missing(self):
        self.assertEqual(convo.load(self.disk), [])
        self.assertEqual(convo.messages(self.disk), [])
        self.assertEqual(convo.max_step(self.disk), 0)
        self.assertEqual(convo.truncate_after(self.disk, 0), 0)

    def test_append_roundtrip(self):
        convo.append_step(self.disk, 1, [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}])
        convo.append_step(self.disk, 2, [{"role": "user", "content": "c"}])
        recs = convo.load(self.disk)
        self.assertEqual([r["step"] for r in recs], [1, 1, 2])
        self.assertEqual([m["content"] for m in convo.messages(self.disk)], ["a", "b", "c"])
        self.assertEqual(convo.max_step(self.disk), 2)
        with open(self.path) as f:
            lines = f.read().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(json.loads(lines[0]), {"step": 1, "msg": {"role": "user", "content": "a"}})

    def test_append_is_one_write_one_flush_one_fsync(self):
        convo.append_step(self.disk, 1, [{"role": "user", "content": "x"}])  # file exists now
        writes, flushes = [], []
        real_open = open

        class Spy:
            def __init__(self, f):
                self._f = f

            def write(self, s):
                writes.append(s)
                return self._f.write(s)

            def flush(self):
                flushes.append(1)
                return self._f.flush()

            def fileno(self):
                return self._f.fileno()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self._f.close()

        def spy_open(*a, **kw):
            return Spy(real_open(*a, **kw))

        msgs = [{"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "bash",
                                                   "input": {"cmd": "ls"}}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]},
                {"role": "assistant", "content": "done"}]
        with mock.patch("builder.convo.open", spy_open, create=True), \
                mock.patch("builder.convo.os.fsync", wraps=os.fsync) as fs:
            convo.append_step(self.disk, 2, msgs)
        self.assertEqual(len(writes), 1, "all msgs of a step must go in one write")
        self.assertEqual(writes[0].count("\n"), 3)
        self.assertEqual(len(flushes), 1)
        self.assertEqual(fs.call_count, 1)
        self.assertEqual([r["step"] for r in convo.load(self.disk)], [1, 2, 2, 2])

    def test_fsync_happens_after_write(self):
        order = []
        real_fsync = os.fsync

        def fsync(fd):
            with open(self.path) as f:
                order.append(f.read().count("\n"))
            return real_fsync(fd)

        with mock.patch("builder.convo.os.fsync", side_effect=fsync):
            convo.append_step(self.disk, 1, [{"a": 1}, {"b": 2}])
        self.assertEqual(order[0], 2)  # data flushed before fsync

    def test_truncate_after(self):
        for k in (1, 2, 3):
            convo.append_step(self.disk, k, [{"n": k, "i": 0}, {"n": k, "i": 1}])
        self.assertEqual(convo.truncate_after(self.disk, 1), 4)
        self.assertEqual([r["step"] for r in convo.load(self.disk)], [1, 1])
        self.assertEqual(convo.max_step(self.disk), 1)
        self.assertEqual(convo.truncate_after(self.disk, 1), 0)
        self.assertFalse(os.path.exists(self.path + ".tmp"))
        self.assertEqual(convo.truncate_after(self.disk, 0), 2)
        self.assertEqual(convo.load(self.disk), [])

    def test_truncate_is_atomic_replace(self):
        convo.append_step(self.disk, 1, [{"a": 1}])
        convo.append_step(self.disk, 2, [{"a": 2}])
        with mock.patch("builder.convo.os.replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                convo.truncate_after(self.disk, 1)
        self.assertEqual(convo.max_step(self.disk), 2)  # original untouched

    def test_torn_tail_ignored_and_repaired(self):
        convo.append_step(self.disk, 1, [{"a": 1}])
        with open(self.path, "a") as f:
            f.write('{"step": 2, "msg": {"a"')
        self.assertEqual(convo.max_step(self.disk), 1)
        self.assertEqual(convo.truncate_after(self.disk, 1), 0)
        with open(self.path) as f:
            self.assertEqual(f.read(), '{"step": 1, "msg": {"a": 1}}\n')


if __name__ == "__main__":
    unittest.main()
