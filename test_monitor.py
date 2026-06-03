import unittest
from unittest.mock import patch

import monitor


class DependencyTaskTests(unittest.TestCase):
    def test_poll_active_tasks_discovers_nested_dependencies(self):
        releases = [(1, "test_release", 101, "task-A")]
        task_cache = {}
        monitored_tasks = {}
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
            monitor.poll_active_tasks(releases, task_cache, monitored_tasks)

        self.assertEqual(
            monitored_tasks,
            {
                101: "task-A",
                102: "task-B",
                103: "task-C",
            },
        )
        self.assertEqual(task_cache[103]["status"], "NotStarted")

    def test_render_monitoring_displays_nested_dependencies(self):
        releases = [(1, "test_release", 101, "task-A")]
        task_cache = {
            101: {
                "task_name": "task-A",
                "status": "InProgress",
                "dependency_task_id": 102,
                "dependency_task_name": "task-B",
            },
            102: {
                "task_name": "task-B",
                "status": "InProgress",
                "dependency_task_id": 103,
                "dependency_task_name": "task-C",
            },
            103: {
                "task_name": "task-C",
                "status": "NotStarted",
                "dependency_task_id": None,
                "dependency_task_name": None,
            },
        }

        output = monitor.render_monitoring(releases, task_cache)

        self.assertIn("test_release - task-A : InProgress", output)
        self.assertIn("|_task-B : InProgress", output)
        self.assertIn("|_task-C : NotStarted", output)


if __name__ == "__main__":
    unittest.main()
