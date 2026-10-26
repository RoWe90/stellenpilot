"""Render one stored job through the complete application pipeline without mutating its DB row.

Usage (from the Docker image):
    python /src/scripts/smoke_application_flow.py --home /data --job-id YOUR_ID

The profile and advertisement remain private on the local machine. Generated
documents go under /data/quality-smoke-tests, not the live output folder.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from docx import Document
from pypdf import PdfReader

from stellenpilot.config import Settings
from stellenpilot.llm import LLM
from stellenpilot.tailor import profile_quality_issues, tailor_job


def run(home: Path, job_id: str, no_llm: bool = False, *,
        cv_style: str | None = None, cv_focus: str | None = None,
        cv_education: str | None = None) -> int:
    settings = Settings(home)
    problems = profile_quality_issues(settings.profile)
    if problems:
        print("PROFILE FAILED: fix /data/profile.toml before generating:", file=sys.stderr)
        for problem in problems:
            print(" -", problem, file=sys.stderr)
        return 2

    with sqlite3.connect(f"file:{settings.db_path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            print("FAIL: job ID not found in the local database", file=sys.stderr)
            return 2
        job = dict(row)

    tailor = settings["tailor"]
    print("Profile OK:", len(settings.profile.get("experience") or []), "experience entries")
    print("Model:", settings["llm"].get("provider"), settings["llm"].get("model"))
    llm = None if no_llm else LLM(settings)
    if llm is not None and not llm.enabled:
        print("FAIL: no LLM configured; enable it to test real AI generation", file=sys.stderr)
        return 2

    # Unique location on the private appdata volume; never overwrite production documents.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    output = home / "quality-smoke-tests" / stamp
    output.mkdir(parents=True, exist_ok=False)

    from stellenpilot.pipeline import my_german_level
    result = tailor_job(
        job, settings.profile, output, llm,
        make_pdf=True,
        letter_setting=tailor.get("letter_language", "auto"),
        my_german=my_german_level(settings),
        cv_style=cv_style or tailor.get("cv_style", "classic"),
        cv_focus=cv_focus or tailor.get("cv_focus", "balanced"),
        cv_education=cv_education or tailor.get("cv_education", "compact"),
    )
    folder = Path(result["folder"])
    report = (folder / "report.md").read_text(encoding="utf-8")
    errors = ("LLM plan failed", "LLM letter failed", "LLM drafts mentioned",
              "Generated summary mentioned")
    for flag in errors:
        if flag in report:
            print("FAIL:", flag, "reported in", folder / "report.md", file=sys.stderr)
            print(report[report.find(flag):report.find(flag) + 350], file=sys.stderr)
            return 1

    docx_files = [Path(p) for p in result["files"] if p.endswith(".docx")]
    pdf_files = [Path(p) for p in result["files"] if p.endswith(".pdf")]
    if len(docx_files) != 2 or len(pdf_files) != 2:
        print("FAIL: expected 2 DOCX and 2 PDF files", file=sys.stderr)
        return 1

    for doc_path in docx_files:
        doc = Document(doc_path)
        section = doc.sections[0]
        if not 209 <= section.page_width.mm <= 211 or not 296 <= section.page_height.mm <= 298:
            print("FAIL: DOCX is not DIN A4:", doc_path.name, file=sys.stderr)
            return 1
        print("DOCX DIN A4:", doc_path.name)

    for pdf_path in pdf_files:
        pdf = PdfReader(str(pdf_path))
        if not pdf.pages:
            print("FAIL: empty PDF", pdf_path.name, file=sys.stderr)
            return 1
        for page in pdf.pages:
            width, height = float(page.mediabox.width), float(page.mediabox.height)
            if not 591 <= width <= 597 or not 839 <= height <= 845:
                print("FAIL: PDF not A4:", pdf_path.name, width, height, file=sys.stderr)
                return 1
        print("PDF DIN A4:", pdf_path.name, "| pages:", len(pdf.pages))
        if "_CV_" in pdf_path.name and len(pdf.pages) > 2:
            print("WARN: CV exceeds two pages; review content and pagination")

    # Generator also writes detailed selection and QA findings into report.md.
    if "## Dokumentenprüfung" not in report or "## CV-Auswahl" not in report:
        print("FAIL: missing document quality or selection report", file=sys.stderr)
        return 1
    print("PASS: complete application generation, local files and A4 check")
    print("Documents:", folder)
    print("No production document or application-status changes made")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, default=Path("/data"))
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--no-llm", action="store_true",
                        help="Only test document layout, not the AI")
    parser.add_argument("--cv-style", choices=["classic", "compact", "lebenslauf"],
                        help="Test this style without changing live settings")
    parser.add_argument("--cv-focus", choices=["full", "balanced", "concise"])
    parser.add_argument("--cv-education", choices=["full", "compact", "essential"])
    args = parser.parse_args()
    try:
        sys.exit(run(args.home.resolve(), args.job_id, args.no_llm,
                     cv_style=args.cv_style, cv_focus=args.cv_focus,
                     cv_education=args.cv_education))
    except Exception as exc:
        print(f"FAIL: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
