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


if __name__ == "__main__":
    unittest.main()
