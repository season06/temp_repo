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


if __name__ == "__main__":
    unittest.main()
