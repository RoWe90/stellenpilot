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


def expand_ranked_bullets(profile: dict, selected_plan: dict,
                          complete_plan: dict, extra: int) -> dict:
    """Return a new plan with up to extra omitted, already verified bullets added.

    Prefer the more recent position; within a position keep the original
    relevance order. Never add an index the source plan excluded.
    """
    if extra < 0:
        raise ValueError("extra must be nonnegative")
    result = deepcopy(selected_plan)
    result["experience"] = [list(idx) for idx in (selected_plan.get("experience") or [])]
    remaining = extra
    for n, entry in enumerate(profile.get("experience") or []):
        if n >= len(result["experience"]):
            break
        existing = result["experience"][n]
        source = complete_plan.get("experience") or []
        valid = source[n] if n < len(source) else []
        bullets = entry.get("bullets") or []
        for idx in valid:
            if remaining == 0:
                break
            if type(idx) is int and 0 <= idx < len(bullets) and idx not in existing:
                existing.append(idx)
                remaining -= 1
        if remaining == 0:
            break
    return result


def omitted_bullet_count(profile: dict, plan: dict, complete_plan: dict) -> int:
    """Count omitted permitted facts without including LLM-excluded items."""
    count = 0
    for n, entry in enumerate(profile.get("experience") or []):
        complete = complete_plan.get("experience") or []
        partial = plan.get("experience") or []
        original = complete[n] if n < len(complete) else []
        current = set(partial[n]) if n < len(partial) else set()
        count += sum(type(idx) is int and 0 <= idx < len(entry.get("bullets") or [])
                     and idx not in current for idx in original)
    return count


def selection_notes(profile: dict, plan: dict, label: str = "balanced") -> list[str]:
    """Explain source omissions after page balancing without touching the profile."""
    notes = []
    for n, entry in enumerate(profile.get("experience") or []):
        original = entry.get("bullets") or []
        partial = plan.get("experience") or []
        idx = partial[n] if n < len(partial) else []
        if len(idx) < len(original):
            title = entry.get("title") or f"Station {n + 1}"
            notes.append(f"CV-Auswahl ({label}): {len(original) - len(idx)} Stichpunkte bei '{title}' "
                         "nicht im Bewerbungs-CV, aber vollständig im Profil erhalten.")
    education = profile.get("education") or []
    selected = plan.get("education_indices")
    if selected is not None and len(selected) < len(education):
        notes.append(f"CV-Auswahl: {len(education) - len(selected)} nicht abgeschlossene "
                     "Ausbildungsstationen ausgelassen; weiterhin im Profil verfügbar.")
    return notes
