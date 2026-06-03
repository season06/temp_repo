import asyncio
import json
import os
import tempfile
import unittest
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import monitor


class DependencyTaskTests(unittest.TestCase):
    @unittest.skip("replaced in Task 6/9")
    def test_render_monitoring_displays_nested_dependencies(self):
        releases = [
            monitor.Release(
                id=1,
                name="test_release",
                root_task_id=101,
                root_task_name="task-A",
            )
        ]
        tasks = {
            101: monitor.Task(
                id=101,
                name="task-A",
                status="InProgress",
                dependency_id=102,
                dependency_name="task-B",
            ),
            102: monitor.Task(
                id=102,
                name="task-B",
                status="InProgress",
                dependency_id=103,
                dependency_name="task-C",
            ),
            103: monitor.Task(
                id=103,
                name="task-C",
                status="NotStarted",
            ),
        }

        output = monitor.render_monitoring(releases, tasks)

        self.assertIn("test_release - task-A : InProgress", output)
        self.assertIn("|_task-B : InProgress", output)
        self.assertIn("|_task-C : NotStarted", output)


class DataModelTests(unittest.TestCase):
    def test_release_holds_available_tasks(self):
        release = monitor.Release(
            id=1,
            name="release-1",
            available_tasks=[
                monitor.ReleaseTaskDef(id=101, name="task-a"),
                monitor.ReleaseTaskDef(id=102, name="task-b"),
            ],
        )
        self.assertEqual(release.available_tasks[0].name, "task-a")
        self.assertEqual(release.available_tasks[1].id, 102)

    def test_release_task_def_is_frozen(self):
        td = monitor.ReleaseTaskDef(id=101, name="task-a")
        with self.assertRaises(Exception):
            td.id = 999


class ReleaseRunnerConstructionTests(unittest.TestCase):
    def _release(self):
        return monitor.Release(
            id=1,
            name="release-1",
            available_tasks=[
                monitor.ReleaseTaskDef(id=101, name="task-a"),
                monitor.ReleaseTaskDef(id=201, name="task-c"),
            ],
        )

    def test_from_input_resolves_release_and_tasks(self):
        runner = monitor.ReleaseRunner.from_input(
            "release-1", ["task-a", "task-c"], [self._release()]
        )
        self.assertEqual(runner.release.name, "release-1")
        self.assertEqual(runner.trigger_queue, ["task-a", "task-c"])
        self.assertEqual(runner.triggered, [])
        self.assertIsNone(runner.active_root_id)
        self.assertFalse(runner.is_done())

    def test_from_input_raises_on_unknown_release(self):
        with self.assertRaises(ValueError):
            monitor.ReleaseRunner.from_input("nope", ["task-a"], [self._release()])

    def test_from_input_raises_on_unknown_task_name(self):
        with self.assertRaises(ValueError):
            monitor.ReleaseRunner.from_input("release-1", ["task-x"], [self._release()])

    def test_resolve_name_returns_task_id(self):
        runner = monitor.ReleaseRunner.from_input("release-1", ["task-a"], [self._release()])
        self.assertEqual(runner._resolve_name("task-a"), 101)
        self.assertEqual(runner._resolve_name("task-c"), 201)


class ChainTerminalTests(unittest.TestCase):
    def test_all_terminal_returns_true(self):
        tasks = {
            101: monitor.Task(id=101, name="task-a", status="Successed", dependency_id=102, dependency_name="task-b"),
            102: monitor.Task(id=102, name="task-b", status="Failed"),
        }
        self.assertTrue(monitor.chain_terminal(101, tasks))

    def test_partial_terminal_returns_false(self):
        tasks = {
            101: monitor.Task(id=101, name="task-a", status="Successed", dependency_id=102, dependency_name="task-b"),
            102: monitor.Task(id=102, name="task-b", status="InProgress"),
        }
        self.assertFalse(monitor.chain_terminal(101, tasks))

    def test_root_not_terminal_returns_false(self):
        tasks = {101: monitor.Task(id=101, name="task-a", status="InProgress")}
        self.assertFalse(monitor.chain_terminal(101, tasks))

    def test_handles_cycle(self):
        tasks = {
            101: monitor.Task(id=101, name="task-a", status="Successed", dependency_id=102, dependency_name="task-b"),
            102: monitor.Task(id=102, name="task-b", status="Successed", dependency_id=101, dependency_name="task-a"),
        }
        self.assertTrue(monitor.chain_terminal(101, tasks))

    def test_handles_broken_chain_when_dep_missing(self):
        tasks = {
            101: monitor.Task(id=101, name="task-a", status="Successed", dependency_id=999, dependency_name="ghost"),
        }
        self.assertFalse(monitor.chain_terminal(101, tasks))

    def test_error_status_is_not_terminal(self):
        tasks = {101: monitor.Task(id=101, name="task-a", status="Error")}
        self.assertFalse(monitor.chain_terminal(101, tasks))


class AsyncApiTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._original_mock_file = monitor.MOCK_API_FILE
        monitor.MOCK_API_FILE = os.path.join(self._tmpdir, "mock.json")
        with open(monitor.MOCK_API_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "releases": [{
                    "release_id": 1,
                    "release_name": "release-1",
                    "available_tasks": [
                        {"task_id": 101, "task_name": "task-a"},
                        {"task_id": 102, "task_name": "task-b"},
                    ],
                }],
                "tasks": {
                    "101": {"status": "NotStarted", "dependency_task_id": 102, "dependency_task_name": "task-b"},
                    "102": {"status": "NotStarted", "dependency_task_id": None, "dependency_task_name": None},
                },
            }, f)

    async def asyncTearDown(self):
        monitor.MOCK_API_FILE = self._original_mock_file
        import shutil
        shutil.rmtree(self._tmpdir)

    async def test_get_release_metadata_returns_releases(self):
        releases = await monitor.get_release_metadata()
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0].name, "release-1")
        self.assertEqual(releases[0].available_tasks[0].name, "task-a")
        self.assertEqual(releases[0].available_tasks[0].id, 101)

    async def test_get_release_task_info_returns_dict(self):
        info = await monitor.get_release_task_info(101)
        self.assertEqual(info["status"], "NotStarted")
        self.assertEqual(info["dependency_task_id"], 102)

    async def test_get_release_task_info_raises_on_unknown(self):
        with self.assertRaises(KeyError):
            await monitor.get_release_task_info(999)

    async def test_trigger_task_sets_status_to_inprogress(self):
        await monitor.trigger_task(101)
        info = await monitor.get_release_task_info(101)
        self.assertEqual(info["status"], "InProgress")

    async def test_trigger_task_is_idempotent(self):
        await monitor.trigger_task(101)
        await monitor.trigger_task(101)
        info = await monitor.get_release_task_info(101)
        self.assertEqual(info["status"], "InProgress")

    async def test_fetch_task_update_returns_error_on_failure(self):
        update = await monitor.fetch_task_update(999)
        self.assertEqual(update.status, "Error")
        self.assertIsNone(update.dependency_id)


class PollTaskAsyncTests(IsolatedAsyncioTestCase):
    async def test_poll_task_updates_in_place(self):
        task = monitor.Task(id=101, name="task-a")

        async def fake_fetch(task_id):
            return monitor.TaskUpdate(status="InProgress", dependency_id=102, dependency_name="task-b")

        with patch.object(monitor, "fetch_task_update", side_effect=fake_fetch):
            new_dep = await monitor.poll_task(task)

        self.assertEqual(task.status, "InProgress")
        self.assertEqual(task.dependency_id, 102)
        self.assertIsNotNone(new_dep)
        self.assertEqual(new_dep.id, 102)
        self.assertEqual(new_dep.name, "task-b")

    async def test_poll_task_skips_when_terminal(self):
        task = monitor.Task(id=101, name="task-a", status="Successed")

        async def fake_fetch(task_id):
            raise AssertionError("should not be called")

        with patch.object(monitor, "fetch_task_update", side_effect=fake_fetch):
            result = await monitor.poll_task(task)

        self.assertIsNone(result)

    async def test_poll_task_returns_none_when_no_dep(self):
        task = monitor.Task(id=102, name="task-b")

        async def fake_fetch(task_id):
            return monitor.TaskUpdate(status="InProgress")

        with patch.object(monitor, "fetch_task_update", side_effect=fake_fetch):
            result = await monitor.poll_task(task)

        self.assertIsNone(result)


class PollChainTests(IsolatedAsyncioTestCase):
    def _runner(self):
        release = monitor.Release(
            id=1, name="release-1",
            available_tasks=[
                monitor.ReleaseTaskDef(id=101, name="task-a"),
                monitor.ReleaseTaskDef(id=102, name="task-b"),
                monitor.ReleaseTaskDef(id=201, name="task-c"),
            ],
        )
        return monitor.ReleaseRunner.from_input("release-1", ["task-a", "task-c"], [release])

    async def test_poll_chain_discovers_dependency(self):
        runner = self._runner()
        tasks = {101: monitor.Task(id=101, name="task-a")}

        responses = {
            101: monitor.TaskUpdate(status="InProgress", dependency_id=102, dependency_name="task-b"),
            102: monitor.TaskUpdate(status="NotStarted"),
        }

        async def fake_fetch(task_id):
            return responses[task_id]

        with patch.object(monitor, "fetch_task_update", side_effect=fake_fetch):
            await runner._poll_chain(101, tasks)

        self.assertIn(102, tasks)
        self.assertEqual(tasks[102].name, "task-b")
        self.assertEqual(tasks[101].status, "InProgress")
        self.assertEqual(tasks[102].status, "NotStarted")


class ReleaseRunnerRunTests(IsolatedAsyncioTestCase):
    def _release(self):
        return monitor.Release(
            id=1, name="release-1",
            available_tasks=[
                monitor.ReleaseTaskDef(id=101, name="task-a"),
                monitor.ReleaseTaskDef(id=102, name="task-b"),
                monitor.ReleaseTaskDef(id=201, name="task-c"),
            ],
        )

    async def test_run_triggers_queue_sequentially(self):
        """trigger order must be [101, 201]; 201 not triggered until 101+cascade terminal."""
        runner = monitor.ReleaseRunner.from_input(
            "release-1", ["task-a", "task-c"], [self._release()],
        )
        tasks = {}

        trigger_order = []

        async def fake_trigger(tid):
            trigger_order.append(tid)

        status_table = {
            101: monitor.TaskUpdate(status="Successed", dependency_id=102, dependency_name="task-b"),
            102: monitor.TaskUpdate(status="Successed"),
            201: monitor.TaskUpdate(status="Successed"),
        }

        async def fake_fetch(task_id):
            return status_table[task_id]

        with patch.object(monitor, "trigger_task", side_effect=fake_trigger), \
             patch.object(monitor, "fetch_task_update", side_effect=fake_fetch):
            await runner.run(tasks)

        self.assertEqual(trigger_order, [101, 201])
        self.assertTrue(runner.is_done())
        self.assertEqual(runner.triggered, [101, 201])
        self.assertIsNone(runner.active_root_id)

    async def test_run_waits_for_cascade_before_advancing(self):
        """task-c is not triggered until task-a AND task-b reach terminal."""
        runner = monitor.ReleaseRunner.from_input(
            "release-1", ["task-a", "task-c"], [self._release()],
        )
        tasks = {}

        trigger_order = []
        poll_count = {101: 0, 102: 0, 201: 0}

        async def fake_trigger(tid):
            trigger_order.append(tid)

        async def fake_fetch(task_id):
            poll_count[task_id] += 1
            if task_id == 101:
                return monitor.TaskUpdate(status="Successed", dependency_id=102, dependency_name="task-b")
            if task_id == 102:
                if poll_count[102] < 3:
                    return monitor.TaskUpdate(status="InProgress")
                return monitor.TaskUpdate(status="Successed")
            if task_id == 201:
                return monitor.TaskUpdate(status="Successed")

        async def no_sleep(_):
            return

        with patch.object(monitor, "trigger_task", side_effect=fake_trigger), \
             patch.object(monitor, "fetch_task_update", side_effect=fake_fetch), \
             patch.object(monitor.asyncio, "sleep", side_effect=no_sleep):
            await runner.run(tasks)

        self.assertEqual(trigger_order, [101, 201])
        self.assertGreaterEqual(poll_count[102], 3)

    async def test_run_continues_after_trigger_failure(self):
        """trigger_task raises for 101 → task is marked Error, run() advances to 201."""
        runner = monitor.ReleaseRunner.from_input(
            "release-1", ["task-a", "task-c"], [self._release()],
        )
        tasks = {}
        trigger_order = []

        async def fake_trigger(tid):
            trigger_order.append(tid)
            if tid == 101:
                raise ConnectionError("simulated")

        async def fake_fetch(task_id):
            return monitor.TaskUpdate(status="Successed")

        with patch.object(monitor, "trigger_task", side_effect=fake_trigger), \
             patch.object(monitor, "fetch_task_update", side_effect=fake_fetch):
            await runner.run(tasks)

        self.assertEqual(trigger_order, [101, 201])
        self.assertEqual(tasks[101].status, "Error")
        self.assertTrue(runner.is_done())

    async def test_run_continues_after_task_failure(self):
        """task-a returns Failed (terminal) → 201 still triggered."""
        runner = monitor.ReleaseRunner.from_input(
            "release-1", ["task-a", "task-c"], [self._release()],
        )
        tasks = {}
        trigger_order = []

        async def fake_trigger(tid):
            trigger_order.append(tid)

        async def fake_fetch(task_id):
            if task_id == 101:
                return monitor.TaskUpdate(status="Failed")
            return monitor.TaskUpdate(status="Successed")

        with patch.object(monitor, "trigger_task", side_effect=fake_trigger), \
             patch.object(monitor, "fetch_task_update", side_effect=fake_fetch):
            await runner.run(tasks)

        self.assertEqual(trigger_order, [101, 201])
        self.assertEqual(tasks[101].status, "Failed")


if __name__ == "__main__":
    unittest.main()
