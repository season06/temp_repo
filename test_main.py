import base64
import sys
import unittest
from unittest.mock import patch

import main


class AuthAndTransportTests(unittest.TestCase):
    def test_basic_auth_encodes_pat_with_leading_colon(self):
        expected = "Basic " + base64.b64encode(b":abc").decode()
        self.assertEqual(main._basic_auth("abc"), expected)

    def test_send_request_is_unimplemented_stub(self):
        with self.assertRaises(NotImplementedError):
            main._send_request("GET", "https://example/x", "PAT")


class AzureRequestShapingTests(unittest.TestCase):
    def test_find_release_definition_shapes_request_and_fuzzy_filters(self):
        captured = {}

        def fake_send(method, url, pat, body=None):
            captured.update(method=method, url=url, pat=pat, body=body)
            return {"value": [
                {"id": 10, "name": "Deploy-App"},
                {"id": 11, "name": "Build-Lib"},
            ]}

        with patch.object(main, "_send_request", side_effect=fake_send):
            result = main.find_release_definition("PAT", "app")

        self.assertEqual(captured["method"], "GET")
        self.assertIn("/definitions", captured["url"])
        self.assertIn("searchText=app", captured["url"])
        self.assertEqual(captured["pat"], "PAT")
        self.assertEqual(result, [("Deploy-App", 10)])

    def test_create_release_posts_definition_id_and_returns_id(self):
        captured = {}

        def fake_send(method, url, pat, body=None):
            captured.update(method=method, url=url, body=body)
            return {"id": 500}

        with patch.object(main, "_send_request", side_effect=fake_send):
            release_id = main.create_release("PAT", 10)

        self.assertEqual(captured["method"], "POST")
        self.assertIn("/releases", captured["url"])
        self.assertEqual(captured["body"], {"definitionId": 10})
        self.assertEqual(release_id, 500)

    def test_get_release_shapes_request_and_returns_payload(self):
        captured = {}
        payload = {"name": "Deploy-App", "environments": [{"id": 7, "name": "stage-1", "status": "notStarted"}]}

        def fake_send(method, url, pat, body=None):
            captured.update(method=method, url=url)
            return payload

        with patch.object(main, "_send_request", side_effect=fake_send):
            result = main.get_release("PAT", 500)

        self.assertEqual(captured["method"], "GET")
        self.assertIn("/releases/500", captured["url"])
        self.assertEqual(result, payload)

    def test_trigger_release_task_patches_environment_to_inprogress(self):
        captured = {}

        def fake_send(method, url, pat, body=None):
            captured.update(method=method, url=url, body=body)
            return {"id": 7, "status": "inProgress"}

        with patch.object(main, "_send_request", side_effect=fake_send):
            result = main.trigger_release_task("PAT", 500, 7)

        self.assertEqual(captured["method"], "PATCH")
        self.assertIn("/releases/500/environments/7", captured["url"])
        self.assertEqual(captured["body"], {"status": "inProgress"})
        self.assertEqual(result["status"], "inProgress")


class ParseSelectionTests(unittest.TestCase):
    def test_parses_comma_separated_one_based_to_zero_based(self):
        self.assertEqual(main.parse_selection("1,3", 3), [0, 2])

    def test_strips_whitespace_and_ignores_empty_parts(self):
        self.assertEqual(main.parse_selection(" 2 , ", 3), [1])

    def test_rejects_empty(self):
        with self.assertRaises(ValueError):
            main.parse_selection("", 3)

    def test_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            main.parse_selection("9", 3)

    def test_rejects_non_numeric(self):
        with self.assertRaises(ValueError):
            main.parse_selection("x", 3)


class AzureApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_task_info_maps_environment_status(self):
        def fake_get_release(pat, release_id):
            return {"name": "rel", "environments": [
                {"id": 5, "name": "stage-1", "status": "inProgress"},
            ]}

        with patch.object(main, "get_release", side_effect=fake_get_release):
            api = main.AzureApi("PAT")
            info = await api.get_task_info(1, 5, "stage-1")

        self.assertEqual(info["status"], "inProgress")
        self.assertIsNone(info["dependency_task_id"])
        self.assertIsNone(info["dependency_task_name"])

    async def test_get_task_info_unknown_environment_is_unknown(self):
        with patch.object(main, "get_release", side_effect=lambda p, r: {"environments": []}):
            api = main.AzureApi("PAT")
            info = await api.get_task_info(1, 999, "missing")
        self.assertEqual(info["status"], "Unknown")

    async def test_trigger_task_calls_trigger_release_task(self):
        calls = []

        def fake_trigger(pat, release_id, env_id):
            calls.append((pat, release_id, env_id))
            return {}

        with patch.object(main, "trigger_release_task", side_effect=fake_trigger):
            api = main.AzureApi("PAT")
            await api.trigger_task(1, 5)

        self.assertEqual(calls, [("PAT", 1, 5)])


class MainFlowTests(unittest.TestCase):
    def test_main_happy_path_builds_runners_and_runs(self):
        inputs = iter(["app", "1", "1"])  # search text, definition pick, task pick
        captured = {}

        def fake_find(pat, text):
            return [("Deploy-App", 10)]

        def fake_create(pat, def_id):
            return 500

        def fake_get(pat, release_id):
            return {"name": "Deploy-App",
                    "environments": [{"id": 7, "name": "stage-1", "status": "notStarted"}]}

        async def fake_orch(runners, tasks, api, writer):
            captured["runners"] = runners
            captured["api"] = api

        argv = ["prog", "--pat", "SECRET"]
        with patch.object(sys, "argv", argv), \
             patch("builtins.input", side_effect=lambda *a: next(inputs)), \
             patch.object(main, "find_release_definition", side_effect=fake_find), \
             patch.object(main, "create_release", side_effect=fake_create), \
             patch.object(main, "get_release", side_effect=fake_get), \
             patch.object(main, "run_orchestration", side_effect=fake_orch):
            main.main()

        runners = captured["runners"]
        self.assertEqual(len(runners), 1)
        self.assertEqual(runners[0].release.name, "Deploy-App")
        self.assertEqual(runners[0].trigger_queue, ["stage-1"])
        self.assertIsInstance(captured["api"], main.AzureApi)


class PromptSelectionTests(unittest.TestCase):
    def test_reprompts_until_valid(self):
        answers = iter(["bad", "0", "2"])  # non-numeric, out-of-range, then valid
        with patch("builtins.input", side_effect=lambda *a: next(answers)):
            result = main._prompt_selection("pick: ", 3)
        self.assertEqual(result, [1])


if __name__ == "__main__":
    unittest.main()
