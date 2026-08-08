"""Tests for the free-text deadline parser.

The inputs here are verbatim strings taken from real DAAD pages — that is the
only thing that keeps this parser honest.
"""

import unittest
from datetime import date

from het.deadlines import parse_deadlines
from het.text import strip_html

TODAY = date(2026, 8, 4)


def parse(text):
    return {(d.date, d.label) for d in parse_deadlines(text, today=TODAY)}


class TestParseDeadlines(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(parse_deadlines(None), [])
        self.assertEqual(parse_deadlines(""), [])

    def test_explicit_year(self):
        self.assertIn(("2026-11-01", "Application deadline"),
                      parse("Register by 1 November 2026"))

    def test_missing_year_rolls_forward(self):
        # 1 May has already passed in 2026, so it must resolve to 2027.
        self.assertIn(("2027-05-01", "Application deadline"), parse("apply until 1 May"))
        # 1 November is still ahead, so it stays in 2026.
        self.assertIn(("2026-11-01", "Application deadline"), parse("apply until 1 November"))

    def test_numeric_format(self):
        self.assertIn(("2027-01-15", "Application deadline"), parse("Deadline: 15.01.2027"))

    def test_month_first_format(self):
        self.assertIn(("2027-01-15", "Application deadline"), parse("Deadline: January 15, 2027"))

    def test_semester_labels_follow_nearest_keyword(self):
        # Verbatim from the University of Göttingen "Applied Data Science" page.
        text = (
            "The following is valid for applicants from:\nall countries\n"
            "For the summer semester:\nuntil 1 November\n"
            "The following is valid for applicants from:\nall countries\n"
            "For the winter semester:\nuntil 1 May"
        )
        got = parse(text)
        self.assertIn(("2026-11-01", "summer semester / all countries"), got)
        self.assertIn(("2027-05-01", "winter semester / all countries"), got)

    def test_non_eu_beats_eu(self):
        text = "The following is valid for applicants from: non-EU countries until 31 October"
        labels = {label for _, label in parse(text)}
        self.assertTrue(any("non-EU" in lb for lb in labels), labels)

    def test_generic_label_when_no_context(self):
        self.assertIn(("2026-10-15", "Application deadline"), parse("Register by 15 October 2026"))

    def test_range_keeps_only_the_closing_date(self):
        # Verbatim from Ansbach "Applied Biotechnology": this is a window.
        text = ("The following is valid for applicants from: all countries "
                "For the winter semester: 1 May - 31 May")
        got = parse(text)
        self.assertEqual({d for d, _ in got}, {"2027-05-31"})

    def test_range_with_to_keyword(self):
        got = parse("Applications run from 1 June to 15 July 2027")
        self.assertEqual({d for d, _ in got}, {"2027-07-15"})

    def test_and_joins_two_separate_deadlines(self):
        got = parse("Deadlines are 1 November 2026 and 1 May 2027")
        self.assertEqual({d for d, _ in got}, {"2026-11-01", "2027-05-01"})

    def test_invalid_date_ignored(self):
        self.assertEqual(parse_deadlines("31 February 2027", today=TODAY), [])

    def test_deduplicates_repeated_dates(self):
        text = "until 1 November 2026 ... until 1 November 2026"
        self.assertEqual(len(parse_deadlines(text, today=TODAY)), 1)

    def test_source_text_is_retained(self):
        found = parse_deadlines("Register by 1 November 2026", today=TODAY)
        self.assertIn("1 November 2026", found[0].source_text)


class TestStripHtml(unittest.TestCase):
    def test_tags_and_entities(self):
        self.assertEqual(
            strip_html("<p>Start in October (WiSe):&nbsp;opens on 1 December</p>"),
            "Start in October (WiSe): opens on 1 December",
        )

    def test_block_tags_become_newlines(self):
        self.assertEqual(strip_html("<li>a</li><li>b</li>"), "a\nb")

    def test_passthrough(self):
        self.assertIsNone(strip_html(None))
        self.assertEqual(strip_html("plain"), "plain")


if __name__ == "__main__":
    unittest.main()
