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


if __name__ == "__main__":
    unittest.main()
