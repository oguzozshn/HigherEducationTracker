"""Turn extracted requirement text into a concrete document checklist.

The requirement fields are prose. What an applicant actually needs is a list of
things to obtain, so this module scans that prose for the signals that imply a
document ("IELTS 6.5" implies a language certificate, "uni-assist" implies a
VPD, "interview" implies a scheduled call) and proposes items accordingly.

Every suggestion carries the snippet it came from, so a wrong guess is visible
rather than silent. Suggestions are a starting point, never a complete list —
the UI says so, and the user can add their own items.
"""

from __future__ import annotations

import re

# Fields whose text is worth scanning for document signals.
#
# Deliberately excludes curriculum descriptions such as "Course organisation":
# those mention internships and projects as part of the *programme*, which
# would otherwise be misread as things the applicant must supply up front.
_SCANNED = [
    "Academic admission requirements",
    "English language skills",
    "German language skills",
    "Application periods",
    "Submit application via",
    "Language requirements exemptions",
    "Costs of living",          # where proof-of-finances is usually stated
]

# Items every application in scope needs, regardless of what the page says.
_ALWAYS: list[tuple[str, str]] = [
    ("Lisans diploması", "Mezun değilsen güncel öğrenci belgesi + beklenen mezuniyet tarihi"),
    ("Transkript (ECTS ve not ortalaması ile)", "Çoğu program ECTS bazlı eşik arıyor"),
    ("CV", "Avrupa formatı (Europass) yaygın kabul görüyor"),
    ("Pasaport kopyası", "Geçerlilik süresi başvuru döneminin ötesinde olmalı"),
]

# (regex over the requirement text, checklist label, why-note)
_RULES: list[tuple[str, str, str]] = [
    (r"\bmotivat(?:ion|ional)\b|letter of motivation|statement of purpose|\bSOP\b",
     "Motivasyon mektubu", None),
    (r"letters? of recommendation|\breferences?\b|referees?",
     "Referans mektubu", None),
    (r"\binterview\b",
     "Mülakat", "Kısa listeye kalanlar görüşmeye çağrılıyor"),
    (r"\bGRE\b", "GRE skoru", None),
    (r"\bGMAT\b", "GMAT skoru", None),
    (r"\bportfolio\b", "Portfolyo", None),
    (r"uni-?assist",
     "uni-assist üzerinden ön değerlendirme (VPD)",
     "Başvuru uni-assist üzerinden gidiyor; VPD çıkması haftalar alabilir"),
    (r"\bAPS\b",
     "APS sertifikası", "Sadece bazı ülkelerin mezunları için gerekli"),
    (r"work experience|professional experience|years? of experience",
     "İş deneyimi belgesi", None),
    (r"\binternship\b", "Staj belgesi", None),
    (r"research proposal|exposé", "Araştırma önerisi", None),
    (r"proof of financ|blocked account|Sperrkonto",
     "Blokeli hesap / finansal yeterlilik kanıtı",
     "Vize aşaması için; başvurudan sonra ama erken hazırlanmalı"),
    (r"aptitude test|Eignungs|entrance exam|admission test",
     "Yetenek/giriş sınavı", None),
]

# Language certificate score patterns, so the checklist can name the target.
_SCORE_PATTERNS = [
    (r"IELTS[^\n:]*:?\s*([0-9](?:\.[05])?)", "IELTS {}"),
    (r"TOEFL[^\n:]*:?\s*(\d{2,3})", "TOEFL {}"),
    (r"Duolingo[^\n:]*:?\s*(\d{2,3})", "Duolingo {}"),
    (r"TestDaF[^\n:]*:?\s*(\d)", "TestDaF {}"),
    (r"\bDSH[- ]?([123])\b", "DSH-{}"),
]

_NO_REQUIREMENT = re.compile(r"no minimum language level|not required|none", re.I)


def _language_targets(text: str) -> str | None:
    """Summarise the accepted certificates/scores mentioned in a language field."""
    targets = []
    for pattern, template in _SCORE_PATTERNS:
        m = re.search(pattern, text, re.I)
        if m:
            targets.append(template.format(m.group(1)))
    level = re.search(r"\b([ABC][12])\s*(?:required|level)", text, re.I)
    if level:
        targets.insert(0, level.group(1).upper())
    return " / ".join(targets) if targets else None


def suggest(fields: dict[str, str]) -> list[tuple[str, str | None]]:
    """Return (label, detail) suggestions for one programme."""
    items: list[tuple[str, str | None]] = list(_ALWAYS)
    seen = {label for label, _ in items}

    def add(label: str, detail: str | None) -> None:
        if label not in seen:
            seen.add(label)
            items.append((label, detail))

    # Language certificates get their own handling so the target score shows up.
    for field_name, language in (("English language skills", "İngilizce"),
                                 ("German language skills", "Almanca")):
        value = fields.get(field_name)
        if not value or _NO_REQUIREMENT.search(value.strip()[:60]):
            continue
        targets = _language_targets(value)
        add(f"{language} yeterlilik belgesi",
            f"Hedef: {targets}" if targets else "Detay için program sayfasına bak")

    haystack = "\n".join(fields.get(name, "") for name in _SCANNED)
    for pattern, label, note in _RULES:
        m = re.search(pattern, haystack, re.I)
        if not m:
            continue
        snippet = haystack[max(0, m.start() - 60):m.end() + 60]
        snippet = re.sub(r"\s+", " ", snippet).strip()
        add(label, note or f"…{snippet}…")

    return items
