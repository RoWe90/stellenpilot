"""Relevance-based, factual selection for the German CV.

Content is always chosen from immutable source bullet indices. No model is
allowed to rewrite employment history. Users can opt out with focus='full'.
"""
from __future__ import annotations

from copy import deepcopy

FOCUS_LIMITS = {
    "full": None,
    "balanced": (6, 3, 2, 2, 1),
    "concise": (4, 2, 2, 1, 1),
}
EDUCATION_MODES = {"full", "compact", "essential"}


def curate(profile: dict, plan: dict, focus: str = "balanced",
           education_mode: str = "compact") -> tuple[dict, list[str]]:
    """Return independent plan plus human-readable disclosure of omitted data.

    Always keep the profile's original chronological order, retain at least one
    available bullet per employment position, and preserve selected indices in
    LLM/keyword relevance order. The source profile is never mutated.
    """
    if focus not in FOCUS_LIMITS:
        raise ValueError(f"unknown cv_focus: {focus}")
    if education_mode not in EDUCATION_MODES:
        raise ValueError(f"unknown cv_education: {education_mode}")
    result = deepcopy(plan)
    notes: list[str] = []
    experiences = profile.get("experience") or []
    available = plan.get("experience") or []
    chosen = []
    for n, entry in enumerate(experiences):
        original = entry.get("bullets") or []
        indexes = available[n] if n < len(available) and isinstance(available[n], list) else list(range(len(original)))
        indexes = list(dict.fromkeys(x for x in indexes if type(x) is int and 0 <= x < len(original)))
        if not indexes and original:
            indexes = list(range(len(original)))
        limits = FOCUS_LIMITS[focus]
        limit = None if limits is None else limits[min(n, len(limits) - 1)]
        selected = indexes if limit is None else indexes[:limit]
        chosen.append(selected)
        if len(selected) < len(original):
            title = entry.get("title") or f"Station {n + 1}"
            notes.append(f"CV-Auswahl ({focus}): {len(original) - len(selected)} Stichpunkte bei '{title}' "
                         "nicht im Bewerbungs-CV, aber vollständig im Profil erhalten.")
    result["experience"] = chosen
    education = profile.get("education") or []
    if education_mode == "essential":
        selected = [i for i, e in enumerate(education)
                    if not any(term in str(e.get("degree", "")).casefold()
                               for term in ("ohne abschluss", "kein abschluss", "abgebrochen"))]
        if not selected and education:
            selected = [0]  # never silently produce an empty education section
    else:
        selected = list(range(len(education)))
    result["education_indices"] = selected
    result["education_mode"] = education_mode
    if len(selected) < len(education):
        notes.append(f"CV-Auswahl: {len(education) - len(selected)} nicht abgeschlossene "
                     "Ausbildungsstationen ausgelassen; weiterhin im Profil verfügbar.")
    return result, notes
