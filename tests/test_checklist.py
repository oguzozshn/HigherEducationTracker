"""Tests for checklist generation.

Field texts here are verbatim from real DAAD programme pages.
"""

import unittest

from het.checklist import suggest

GOETTINGEN = {
    "Academic admission requirements": (
        "A Bachelor's degree with at least 180 ECTS is needed. At least 60 ECTS have to be "
        "successfully completed in the area of data science, computer science, statistics, "
        "mathematics or a related field. All applicants who are on the shortlist for the "
        "programme will be invited to a personal interview, conducted as a video call."
    ),
    "English language skills": (
        "C1 required, please provide an official language certificate, e.g.:\n"
        "IELTS Academic: 6.5\nTOEFL iBT Home Edition (before 2026): 95\n"
        "UNIcert English: UNIcert III"
    ),
    "German language skills": "No minimum language level required",
    # Curriculum text — must not be treated as an admission requirement.
    "Course organisation": (
        "Students carry out a research lab rotation or an industry internship and "
        "acquire additional key competencies."
    ),
}


def labels(fields):
    return [label for label, _ in suggest(fields)]


class TestSuggest(unittest.TestCase):
    def test_baseline_items_always_present(self):
        got = labels({})
        for expected in ["Lisans diploması", "CV", "Pasaport kopyası"]:
            self.assertIn(expected, got)

    def test_english_certificate_with_targets(self):
        items = dict(suggest(GOETTINGEN))
        self.assertIn("İngilizce yeterlilik belgesi", items)
        detail = items["İngilizce yeterlilik belgesi"]
        self.assertIn("C1", detail)
        self.assertIn("IELTS 6.5", detail)
        self.assertIn("TOEFL 95", detail)

    def test_no_german_certificate_when_not_required(self):
        self.assertNotIn("Almanca yeterlilik belgesi", labels(GOETTINGEN))

    def test_interview_detected(self):
        self.assertIn("Mülakat", labels(GOETTINGEN))

    def test_curriculum_internship_is_not_a_document(self):
        # "industry internship" appears only in the curriculum description.
        self.assertNotIn("Staj belgesi", labels(GOETTINGEN))

    def test_internship_in_admission_requirements_is_a_document(self):
        got = labels({"Academic admission requirements":
                      "Applicants must provide proof of a completed internship."})
        self.assertIn("Staj belgesi", got)

    def test_uni_assist_detected(self):
        got = labels({"Submit application via": "Please apply via uni-assist."})
        self.assertIn("uni-assist üzerinden ön değerlendirme (VPD)", got)

    def test_recommendation_and_motivation(self):
        got = labels({"Academic admission requirements":
                      "Submit a letter of motivation and two letters of recommendation."})
        self.assertIn("Motivasyon mektubu", got)
        self.assertIn("Referans mektubu", got)

    def test_german_certificate_when_required(self):
        items = dict(suggest({"German language skills": "B2 required, e.g. TestDaF: 4"}))
        self.assertIn("Almanca yeterlilik belgesi", items)
        self.assertIn("TestDaF 4", items["Almanca yeterlilik belgesi"])

    def test_no_duplicate_labels(self):
        got = labels(GOETTINGEN)
        self.assertEqual(len(got), len(set(got)))


if __name__ == "__main__":
    unittest.main()
