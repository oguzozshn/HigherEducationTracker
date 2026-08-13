"""Tests for the Study in NL adapter.

The sample record is a trimmed copy of a real API response, so the field names
and shapes are the ones the source actually sends.
"""

import json
import unittest
from urllib.parse import parse_qs, urlparse

from het.adapters import studyinnl_nl
from het.adapters.studyinnl_nl import StudyInNlAdapter

MAASTRICHT = {
    "id": 1004,
    "slug": "european-studies-1004-maastricht-university",
    "name": "European Studies on Society, Science and Technology",
    "type": "Master",
    "qualification": "Master of Arts",
    "description": "<p>The emergence of new technologies.</p>",
    "website": "https://www.maastrichtuniversity.nl/education/master/esst",
    "duration": "1 year",
    "ects_credits": None,
    "full_time": 1, "part_time": 0, "dual": 0,
    "field_of_study": "Humanities, social sciences, communication and arts",
    "institution": {"name": "Maastricht University", "city": "Maastricht",
                    "sector": "Research university"},
    "locations": [{"name": "Maastricht"}],
    "languages": [{"name": "English"}],
    "language_requirements": [
        {"minimum_score": "575", "description": "TOEFL paper based"},
        {"minimum_score": "233", "description": "TOEFL computer based"},
        {"minimum_score": "90", "description": "TOEFL internet based"},
        {"minimum_score": "6.5", "description": "IELTS overall band"},
    ],
    "scholarships": [{"name": "NL Scholarship"}],
    "start_months": [
        {"start_date": "2027-09-01", "application_deadline": "2027-06-01",
         "application_deadline_non_eu": "2027-05-01", "month": 9},
    ],
    "tuitions": [
        {"year": 2026, "amount": 2694, "tuition_fee_type": "statutory", "period": "year"},
        {"year": 2026, "amount": 20200, "tuition_fee_type": "international", "period": "year"},
    ],
    "accreditations": [{"name": "NVAO"}],
    "admission_url": ["https://www.maastrichtuniversity.nl/esst/admission"],
}

BACHELOR = dict(MAASTRICHT, id=2002, type="Bachelor", name="Some Bachelor")
HBO_MASTER = dict(MAASTRICHT, id=3003, name="Applied Master",
                  institution={"name": "Fontys", "city": "Eindhoven",
                               "sector": "University of applied sciences"})


def make_fetch(records, *, honour_offset=True, calls=None):
    def fetch(url, max_age=None):
        query = parse_qs(urlparse(url).query)
        if calls is not None:
            calls.append(query)
        offset = int(query.get("offset", ["0"])[0]) if honour_offset else 0
        limit = int(query.get("limit", ["500"])[0])
        page = records[offset:offset + limit]
        return json.dumps({"data": {"totalAmount": len(records), "programs": page}})
    return fetch


class AdapterTestCase(unittest.TestCase):
    def setUp(self):
        self._real = studyinnl_nl.fetch

    def tearDown(self):
        studyinnl_nl.fetch = self._real

    def listings(self, records, **kwargs):
        studyinnl_nl.fetch = make_fetch(records)
        return list(StudyInNlAdapter().list_programs(**kwargs))


class TestMapping(AdapterTestCase):
    def test_core_fields(self):
        p = self.listings([MAASTRICHT])[0].program
        self.assertEqual(p.source, "studyinnl")
        self.assertEqual(p.source_id, "1004")
        self.assertEqual(p.country, "NL")
        self.assertEqual(p.university, "Maastricht University")
        self.assertEqual(p.city, "Maastricht")
        self.assertEqual(p.degree, "Master of Arts")
        self.assertEqual(p.languages, ["English"])
        self.assertEqual(p.start_terms, "September 2027")
        self.assertIn("studyinnl.org/dutch-education/studies/", p.detail_url)

    def test_detail_is_complete_at_listing_time(self):
        # No per-programme fetch should ever be needed for this source.
        listing = self.listings([MAASTRICHT])[0]
        self.assertIsNotNone(listing.program.detail_fetched_at)
        self.assertTrue(listing.fields)

    def test_tuition_summary_spans_the_fee_types(self):
        p = self.listings([MAASTRICHT])[0].program
        self.assertEqual(p.tuition, "2,694–20,200 EUR/year")

    def test_tuition_period_is_read_not_assumed(self):
        # Real data contains period="course" as well as "year".
        record = dict(MAASTRICHT, tuitions=[
            {"amount": 1500, "tuition_fee_type": "institutional", "period": "course"}])
        self.assertEqual(self.listings([record])[0].program.tuition,
                         "1,500 EUR/course")

    def test_tuition_period_omitted_when_mixed(self):
        record = dict(MAASTRICHT, tuitions=[
            {"amount": 1500, "tuition_fee_type": "institutional", "period": "course"},
            {"amount": 2694, "tuition_fee_type": "statutory", "period": "year"}])
        self.assertEqual(self.listings([record])[0].program.tuition,
                         "1,500–2,694 EUR")

    def test_lone_statutory_rate_is_qualified(self):
        # 448 of 1300 real Dutch masters publish only the EU/EEA rate. Left
        # bare it reads as the price to a non-EU applicant, for whom the real
        # figure is several times higher.
        record = dict(MAASTRICHT, tuitions=[
            {"amount": 2694, "tuition_fee_type": "statutory", "period": "year"}])
        listing = self.listings([record])[0]
        self.assertEqual(listing.program.tuition, "2,694 EUR/year (EU/EEA only)")
        fields = {f.label: f.value for f in listing.fields}
        self.assertIn("Non-EU rate not published", fields["Tuition fees"])

    def test_no_qualifier_when_non_eu_rate_is_known(self):
        listing = self.listings([MAASTRICHT])[0]      # statutory + international
        self.assertNotIn("EU/EEA only", listing.program.tuition)
        fields = {f.label: f.value for f in listing.fields}
        self.assertNotIn("not published", fields["Tuition fees"])

    def test_missing_qualification_falls_back_to_type(self):
        # 34 of 439 real masters carry no `qualification`.
        record = dict(MAASTRICHT, qualification=None)
        self.assertEqual(self.listings([record])[0].program.degree, "Master")

    def test_missing_city_everywhere_is_tolerated(self):
        record = dict(MAASTRICHT, institution={"name": "X", "sector": "Research university"},
                      locations=[])
        self.assertIsNone(self.listings([record])[0].program.city)

    def test_partial_deadline_entry(self):
        # 49 real entries publish no general date, 72 no non-EU date.
        record = dict(MAASTRICHT, start_months=[
            {"start_date": "2027-09-01", "application_deadline": None,
             "application_deadline_non_eu": "2027-05-01", "month": 9}])
        deadlines = self.listings([record])[0].deadlines
        self.assertEqual(len(deadlines), 1)
        self.assertIn("non-EU", deadlines[0].label)

    def test_tuition_field_names_who_pays_what(self):
        fields = {f.label: f.value for f in self.listings([MAASTRICHT])[0].fields}
        self.assertIn("EU/EEA (statutory): 2,694 EUR/year", fields["Tuition fees"])
        self.assertIn("Non-EU (international): 20,200 EUR/year", fields["Tuition fees"])


class TestDeadlines(AdapterTestCase):
    def test_eu_and_non_eu_are_separate_and_exact(self):
        deadlines = self.listings([MAASTRICHT])[0].deadlines
        by_date = {d.date: d for d in deadlines}
        self.assertEqual(set(by_date), {"2027-06-01", "2027-05-01"})
        self.assertTrue(all(d.confidence == "exact" for d in deadlines))
        self.assertIn("EU/EEA applicants", by_date["2027-06-01"].label)
        self.assertIn("non-EU applicants", by_date["2027-05-01"].label)

    def test_non_eu_deadline_is_the_earlier_one(self):
        # The distinction that actually matters to a Turkish applicant.
        deadlines = self.listings([MAASTRICHT])[0].deadlines
        non_eu = next(d for d in deadlines if "non-EU" in d.label)
        eu = next(d for d in deadlines if "EU/EEA" in d.label)
        self.assertLess(non_eu.date, eu.date)

    def test_identical_dates_collapse_to_one_entry(self):
        record = dict(MAASTRICHT, start_months=[
            {"start_date": "2027-09-01", "application_deadline": "2027-05-01",
             "application_deadline_non_eu": "2027-05-01", "month": 9}])
        deadlines = self.listings([record])[0].deadlines
        self.assertEqual(len(deadlines), 1)
        self.assertIn("all applicants", deadlines[0].label)

    def test_malformed_dates_are_dropped(self):
        record = dict(MAASTRICHT, start_months=[
            {"start_date": "2027-09-01", "application_deadline": "onbekend",
             "application_deadline_non_eu": None, "month": 9}])
        self.assertEqual(self.listings([record])[0].deadlines, [])

    def test_missing_start_months(self):
        record = dict(MAASTRICHT, start_months=None)
        listing = self.listings([record])[0]
        self.assertEqual(listing.deadlines, [])
        self.assertIsNone(listing.program.deadline_raw)


class TestLanguageRequirements(AdapterTestCase):
    def test_recognisable_certificates_come_first(self):
        # The source lists TOEFL paper-based first; surfacing 575 as "the"
        # TOEFL score would mislead, so IELTS and iBT must lead.
        fields = {f.label: f.value for f in self.listings([MAASTRICHT])[0].fields}
        lines = fields["English language skills"].splitlines()
        self.assertTrue(lines[0].startswith("IELTS overall band"), lines)
        self.assertTrue(lines[1].startswith("TOEFL internet based"), lines)

    def test_checklist_reads_the_intended_scores(self):
        from het.checklist import suggest
        fields = {f.label: f.value for f in self.listings([MAASTRICHT])[0].fields}
        items = dict(suggest(fields))
        detail = items["İngilizce yeterlilik belgesi"]
        self.assertIn("IELTS 6.5", detail)
        self.assertIn("TOEFL 90", detail)

    def test_unknown_requirements_still_produce_a_field(self):
        # Absent would read as "not required"; these are English-taught degrees.
        record = dict(MAASTRICHT, language_requirements=None)
        fields = {f.label: f.value for f in self.listings([record])[0].fields}
        self.assertIn("Not specified", fields["English language skills"])


class TestFiltering(AdapterTestCase):
    def test_masters_only_by_default(self):
        got = self.listings([MAASTRICHT, BACHELOR])
        self.assertEqual([l.program.source_id for l in got], ["1004"])

    def test_all_degrees(self):
        got = self.listings([MAASTRICHT, BACHELOR], degree=None)
        self.assertEqual(len(got), 2)

    def test_sector_filter_excludes_hogescholen(self):
        got = self.listings([MAASTRICHT, HBO_MASTER], sector="Research university")
        self.assertEqual([l.program.source_id for l in got], ["1004"])

    def test_subject_query_matches_name_or_field(self):
        got = self.listings([MAASTRICHT, HBO_MASTER], subject_query="applied master")
        self.assertEqual([l.program.source_id for l in got], ["3003"])

    def test_no_filter_parameters_are_sent_to_the_api(self):
        # The endpoint accepts filters and ignores them, so sending any would
        # produce results that silently disagree with what was asked for.
        calls = []
        studyinnl_nl.fetch = make_fetch([MAASTRICHT], calls=calls)
        list(StudyInNlAdapter().list_programs(degree="Master",
                                              sector="Research university"))
        for query in calls:
            self.assertEqual(set(query) - {"limit", "offset"}, set(), query)

    def test_limit_counts_kept_records_not_scanned_ones(self):
        got = self.listings([BACHELOR, BACHELOR, MAASTRICHT], limit=1)
        self.assertEqual([l.program.source_id for l in got], ["1004"])


class TestPaging(AdapterTestCase):
    def test_walks_every_page(self):
        records = [dict(MAASTRICHT, id=i) for i in range(1200)]
        studyinnl_nl.fetch = make_fetch(records)
        got = list(StudyInNlAdapter().list_programs())
        self.assertEqual(len(got), 1200)

    def test_stops_when_source_ignores_offset(self):
        records = [dict(MAASTRICHT, id=i) for i in range(1200)]
        studyinnl_nl.fetch = make_fetch(records, honour_offset=False)
        got = list(StudyInNlAdapter().list_programs())
        self.assertEqual(len(got), studyinnl_nl.PAGE_SIZE)


if __name__ == "__main__":
    unittest.main()
