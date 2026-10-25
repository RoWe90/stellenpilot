# Application quality and profile validation

Stellenpilot does not invent or rewrite your employment history. In CVs,
experience bullet points are copied verbatim from `profile.toml`. Poorly
parsed imports cannot be fixed by selecting a more expensive LLM.

## Before generating applications

From Unraid / Docker Compose:

```bash
cd /mnt/user/appdata/stellenpilot-source/unraid || exit 1
docker compose exec -T stellenpilot stellenpilot --home /data doctor
```

The doctor reports obvious imported-CV corruption, including:

- Descriptions or bullet marks inside an experience title or company field
- Unusually long titles or company fields
- Duplicate bullet points in a single position

For a bad profile, document generation stops with a specific error instead
of silently producing another malformed application. No profile file is
modified automatically. Edit the private `profile.toml` and review the
facts, dates and project claims:

```bash
TERM=xterm nano /mnt/user/appdata/stellenpilot/profile.toml
```

Example of a well-structured position:

```toml
[[experience]]
title = "Software Developer"
company = "Example GmbH"
dates = "05/2022 – heute"
bullets = [
  "Entwicklung und Automatisierung von Python-Werkzeugen für Datenanalysen.",
  "Pflege von Datenpipelines und Abstimmung mit Entwicklungsteams.",
]
```

Do not place job descriptions in `title` or `company`. Keep each bullet as
one complete, truthful statement without leading bullet glyphs.

## Generation and layout

The DOCX renderer now explicitly uses DIN A4 (210 × 297 mm), a metrically
compatible `Carlito` font installed in the Docker image, consistent spacing,
and keep-with-next for section and experience headings. The existing
`classic`, `compact` and `lebenslauf` modes remain available; the last
uses German section names and puts dates first.

The prompts emphasize specific experiences and job requirements rather than
volunteering missing skills. Unsupported claims continue to be rejected.
If an AI fails or produces unsupported claims, the report documents the
fallback; **review `report.md` and both documents before sending**.

You can change the layout and language in `/data/config.toml`:

```toml
[tailor]
cv_style = "lebenslauf"
letter_language = "de"
```

Edit the existing `[tailor]` block, do not add a duplicate block.
After editing the profile or settings, restart Stellenpilot and explicitly
regenerate a selected application. Existing documents and job records are
not overwritten unless you regenerate the same job/date.

## Verification

Run from a Python environment with the project's dependencies:

```bash
python -m unittest discover -s tests -p 'test_application_quality.py' -v
python -m unittest discover -s tests
```

Check resulting DOCX files in an office editor and PDFs in a PDF viewer.
The document builder does not guarantee a two-page CV irrespective of input
length. Remove irrelevant entries or shorten *verified facts* in the profile
rather than shrinking the font until the contents are unreadable.
