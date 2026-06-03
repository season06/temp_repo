import unittest
from unittest.mock import patch

import monitor


class DependencyTaskTests(unittest.TestCase):
    def test_poll_active_tasks_discovers_nested_dependencies(self):
        releases = [
            monitor.Release(
                id=1,
                name="test_release",
                root_task_id=101,
                root_task_name="task-A",
            )
        ]
        tasks = {}
        task_info_by_id = {
            101: {
                "status": "InProgress",
                "dependency_task_id": 102,
                "dependency_task_name": "task-B",
            },
            102: {
                "status": "InProgress",
                "dependency_task_id": 103,
                "dependency_task_name": "task-C",
            },
            103: {
                "status": "NotStarted",
                "dependency_task_id": None,
                "dependency_task_name": None,
            },
        }

        with patch("monitor.get_release_task_info", side_effect=task_info_by_id.__getitem__):
            monitor.poll_active_tasks(releases, tasks)

        self.assertEqual(set(tasks), {101, 102, 103})
        self.assertEqual(tasks[101].name, "task-A")
        self.assertEqual(tasks[102].name, "task-B")
        self.assertEqual(tasks[103].name, "task-C")
        self.assertEqual(tasks[103].status, "NotStarted")

    def test_poll_active_tasks_skips_terminated_tasks(self):
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
                status="Successed",
            )
        }

        with patch("monitor.get_release_task_info") as get_release_task_info:
            monitor.poll_active_tasks(releases, tasks)

        get_release_task_info.assert_not_called()
        self.assertEqual(tasks[101].status, "Successed")

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

    def test_all_tasks_terminated_requires_tasks_and_terminal_statuses(self):
        self.assertFalse(monitor.all_tasks_terminated({}))
        self.assertFalse(
            monitor.all_tasks_terminated(
                {
                    101: monitor.Task(id=101, name="task-A", status="Successed"),
                    102: monitor.Task(id=102, name="task-B", status="InProgress"),
                }
            )
        )
        self.assertTrue(
            monitor.all_tasks_terminated(
                {
                    101: monitor.Task(id=101, name="task-A", status="Successed"),
                    102: monitor.Task(id=102, name="task-B", status="Failed"),
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
