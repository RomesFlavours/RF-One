#!/usr/bin/env python
"""REGISTRY_CLOVER_CREATE_001 — the HTTP requests the Clover employee writer sends (fake HTTP session, no network)."""
import os
import sys
import unittest

DATA_STORE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "RF-One Data Store"))
sys.path.insert(0, DATA_STORE_DIR)

import requests  # noqa: E402
from rfone_data_store.technical.connectors.clover import employee_writer as ew  # noqa: E402


class Response:
    def __init__(self, status, data):
        self.status_code, self._data, self.ok = status, data, 200 <= status < 300

    def json(self):
        return self._data


class Session:
    def __init__(self, post=None, get=None):
        self.calls, self._post, self._get = [], post, get or {}

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append(("POST", url, json, headers["Authorization"]))
        if isinstance(self._post, Exception):
            raise self._post
        return self._post

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append(("GET", url, params, headers["Authorization"]))
        for suffix, response in self._get.items():
            if url.endswith(suffix):
                return response
        return Response(404, {})


def writer(session, mode="sandbox"):
    return ew.HttpCloverEmployeeWriter(merchant_id="MD123", token="tok", mode=mode, session=session)


class WriterTest(unittest.TestCase):
    def test_create_posts_once_to_the_merchant_with_base_level_and_existing_role(self):
        s = Session(post=Response(200, {"id": "EMPNEW"}))
        result = writer(s).create_employee(name="Giulia Both", custom_id="RF1-7", role_id="ROLE1")
        self.assertEqual((result.outcome, result.employee_id), ("CREATED", "EMPNEW"))
        self.assertEqual(s.calls, [("POST", "https://apisandbox.dev.clover.com/v3/merchants/MD123/employees",
                                    {"name": "Giulia Both", "customId": "RF1-7", "role": "EMPLOYEE",
                                     "roles": [{"id": "ROLE1"}]}, "Bearer tok")])

    def test_answers_are_classified_and_never_retried(self):
        for response, outcome in ((Response(400, {"message": "bad"}), "REFUSED"), (Response(401, {}), "REFUSED"),
                                  (Response(500, {}), "UNCERTAIN"), (Response(429, {}), "UNCERTAIN"),
                                  (Response(200, {}), "UNCERTAIN"), (requests.Timeout(), "UNCERTAIN"),
                                  (requests.ConnectionError(), "UNCERTAIN")):
            s = Session(post=response)
            self.assertEqual(writer(s).create_employee(name="n", custom_id="c", role_id="r").outcome, outcome)
            self.assertEqual(len(s.calls), 1)

    def test_role_check_and_custom_id_search(self):
        s = Session(get={"/roles/R1": Response(200, {"name": "Server", "systemRole": "EMPLOYEE"}),
                         "/employees": Response(200, {"elements": [{"id": "A", "customId": "RF1-7"},
                                                                   {"id": "B", "customId": "RF1-70"}]})})
        w = writer(s, mode="production")
        self.assertEqual((w.check_role("R1").found, w.check_role("R1").system_role), (True, "EMPLOYEE"))
        self.assertFalse(w.check_role("R2").found)
        self.assertEqual(w.find_by_custom_id("RF1-7").employee_ids, ["A"])        # exact custom ID only
        self.assertTrue(all(c[1].startswith("https://api.clover.com/v3/merchants/MD123/") for c in s.calls))
        self.assertFalse(any(c[0] == "POST" for c in s.calls))

    def test_disabled_unless_enabled_and_credentials_per_merchant(self):
        os.environ.pop(ew.ENABLE_ENV, None)
        self.assertIn("not enabled", ew.availability("MD123"))
        os.environ[ew.ENABLE_ENV] = "sandbox"
        try:
            self.assertIn("CLOVER_SANDBOX_API_TOKEN__MD123", ew.availability("MD123"))
            os.environ["CLOVER_SANDBOX_API_TOKEN__MD123"] = "x"
            self.assertIsNone(ew.availability("MD123"))
            self.assertIsNotNone(ew.availability("WP999"))                       # never another merchant's token
        finally:
            os.environ.pop(ew.ENABLE_ENV, None); os.environ.pop("CLOVER_SANDBOX_API_TOKEN__MD123", None)


if __name__ == "__main__":
    unittest.main()
