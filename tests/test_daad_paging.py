"""Pagination regression tests for the DAAD adapter.

The search endpoint pages by `offset` and silently ignores `page`. Sending
`page` looked healthy — HTTP 200, a full page of results every time — while
returning the first page forever, so a full ingest produced 1600 records that
collapsed to 100 unique rows. These tests pin the behaviour without touching
the network.
"""

import json
import unittest
from urllib.parse import parse_qs, urlparse

from het.adapters import daad_de

TOTAL = 250
PAGE = daad_de.PAGE_SIZE


def _course(i):
    return {"id": i, "courseName": f"Programme {i}", "academy": "Uni",
            "city": "Berlin", "languages": ["English"], "link": f"/detail/{i}/"}


def make_fetch(honour_offset=True, calls=None):
    """Fake `fetch` returning a slice of a synthetic catalogue."""
    def fetch(url, max_age=None):
        query = parse_qs(urlparse(url).query)
        if calls is not None:
            calls.append(query)
        offset = int(query.get("offset", ["0"])[0]) if honour_offset else 0
        courses = [_course(i) for i in range(offset, min(offset + PAGE, TOTAL))]
        return json.dumps({"courses": courses, "numResults": TOTAL})
    return fetch


class TestPaging(unittest.TestCase):
    def setUp(self):
        self._real_fetch = daad_de.fetch

    def tearDown(self):
        daad_de.fetch = self._real_fetch

    def test_walks_the_whole_catalogue(self):
        daad_de.fetch = make_fetch()
        got = list(daad_de.DaadAdapter().list_programs())
        self.assertEqual(len(got), TOTAL)
        self.assertEqual(len({l.program.source_id for l in got}), TOTAL)

    def test_listings_carry_no_detail(self):
        # DAAD search results are summary-only; requirements and dates come
        # later, from the detail page and the prose parser respectively.
        daad_de.fetch = make_fetch()
        listing = next(iter(daad_de.DaadAdapter().list_programs()))
        self.assertEqual(listing.fields, [])
        self.assertIsNone(listing.deadlines)
        self.assertIsNone(listing.program.detail_fetched_at)

    def test_sends_offset_not_page(self):
        calls = []
        daad_de.fetch = make_fetch(calls=calls)
        list(daad_de.DaadAdapter().list_programs())
        self.assertTrue(all("page" not in q for q in calls), calls)
        self.assertEqual([int(q["offset"][0]) for q in calls],
                         list(range(0, TOTAL + PAGE, PAGE))[:len(calls)])

    def test_stops_when_source_ignores_offset(self):
        # Exactly the failure we hit: the server keeps returning page one.
        # The walk must end rather than spin, and must not emit duplicates.
        daad_de.fetch = make_fetch(honour_offset=False)
        got = list(daad_de.DaadAdapter().list_programs())
        self.assertEqual(len(got), PAGE)
        self.assertEqual(len({l.program.source_id for l in got}), PAGE)

    def test_limit_stops_early(self):
        daad_de.fetch = make_fetch()
        got = list(daad_de.DaadAdapter().list_programs(limit=15))
        self.assertEqual(len(got), 15)

    def test_empty_catalogue(self):
        daad_de.fetch = lambda url, max_age=None: json.dumps(
            {"courses": [], "numResults": 0})
        self.assertEqual(list(daad_de.DaadAdapter().list_programs()), [])


if __name__ == "__main__":
    unittest.main()
