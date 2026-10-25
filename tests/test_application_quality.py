"""Quality guard and DIN A4 export regression tests."""
import tempfile
import unittest
from pathlib import Path

from docx import Document

from stellenpilot.tailor import (
    LETTER_SYSTEM, LETTER_SYSTEM_DE, ProfileQualityError,
    build_cv, build_letter, keyword_plan, profile_quality_issues,
    tailor_job, template_letter_de,
)


PROFILE = {
    "person": {
        "name": "Example Developer", "location": "Berlin", "email": "example@sample.de",
        "languages": ["Deutsch (C2)", "English (B2)"],
        "headlines": ["Software Developer | Python"],
        "summary": "Softwareentwickler mit Erfahrung in Python-Projekten und Entwicklungsautomatisierung.",
    },
    "skills": {"Programming": ["Python"], "DevOps": ["Azure", "CI/CD"]},
    "experience": [
        {"title": "Software Developer", "company": "Example GmbH",
         "dates": "2021 - heute",
         "bullets": ["Entwicklung von Python-Werkzeugen zur Datenaufbereitung.",
                     "Automatisierung von Entwicklungsabläufen über Azure Pipelines."]},
    ],
    "projects": [],
    "education": [{"degree": "B.Sc. Informatik", "school": "Example Hochschule", "dates": "2021"}],
}
JOB = {"title": "Software Developer", "company": "Beispiel AG",
       "description": "Entwicklung mit Python und CI/CD."}


class ProfileQualityTests(unittest.TestCase):
    def test_clean_profile_has_no_warning(self):
        self.assertEqual(profile_quality_issues(PROFILE), [])

    def test_imported_long_title_with_bullets_is_rejected(self):
        bad = {**PROFILE, "experience": [
            {**PROFILE["experience"][0], "title": "Softwareentwickler • Datenverarbeitung • Python-Skripte"}
        ]}
        self.assertIn("Titel", profile_quality_issues(bad)[0])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ProfileQualityError, "Berufsstation 1"):
                tailor_job(JOB, bad, Path(directory), make_pdf=False)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_imported_duplicate_bullets_flagged_without_dropping_facts(self):
        role = dict(PROFILE["experience"][0])
        role["bullets"] = ["Python Tool entwickelt.", "  Python   Tool entwickelt. "]
        bad = {**PROFILE, "experience": [role]}
        issues = profile_quality_issues(bad)
        self.assertTrue(any("doppelte" in issue for issue in issues))
        self.assertEqual(len(role["bullets"]), 2)


class DocumentLayoutTests(unittest.TestCase):
    def test_german_cv_is_din_a4_with_preserved_bullets(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "cv.docx"
            build_cv(PROFILE, keyword_plan(JOB, PROFILE), target, style="lebenslauf")
            doc = Document(target)
            section = doc.sections[0]
            self.assertAlmostEqual(section.page_width.mm, 210, delta=0.6)
            self.assertAlmostEqual(section.page_height.mm, 297, delta=0.6)
            self.assertTrue(any("BERUFSERFAHRUNG" in p.text for p in doc.paragraphs))
            self.assertTrue(any("Automatisierung von Entwicklungsabläufen" in p.text
                                for p in doc.paragraphs))
            header = next(p for p in doc.paragraphs if "Software Developer, Example GmbH" in p.text)
            self.assertTrue(header.paragraph_format.keep_with_next)

    def test_letter_is_din_a4_and_has_distinct_subject(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "letter.docx"
            build_letter(JOB, PROFILE, "Mein Python-Projekt passt zur Stelle.", target, "de")
            doc = Document(target)
            self.assertAlmostEqual(doc.sections[0].page_width.mm, 210, delta=0.6)
            self.assertTrue(any(p.text.startswith("Bewerbung als") for p in doc.paragraphs))
            self.assertTrue(any("Mein Python-Projekt" in p.text for p in doc.paragraphs))


class LetterPromptTests(unittest.TestCase):
    def test_prompts_discourage_unsolicited_deficits_and_inventions(self):
        self.assertIn("keine vermeintlichen Defizite", LETTER_SYSTEM_DE)
        self.assertIn("do not volunteer missing skills", LETTER_SYSTEM.lower())
        self.assertIn("Keine erfundenen", LETTER_SYSTEM_DE)

    def test_fallback_does_not_invent_missing_experience(self):
        plan = keyword_plan(JOB, PROFILE)
        plan.update({"covered": ["Python"], "learning": [], "missing": ["Kubernetes", "Terraform"]})
        text = template_letter_de(JOB, plan)
        self.assertNotIn("Kubernetes", text)
        self.assertNotIn("Terraform", text)
        self.assertNotIn("noch nicht", text)


if __name__ == "__main__":
    unittest.main()
