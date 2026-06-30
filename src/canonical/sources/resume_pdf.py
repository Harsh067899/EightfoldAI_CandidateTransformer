"""Resume adapter (unstructured source: PDF prose).

Two-step: extract text from the PDF, then pull fields out of prose. Everything
here is lower-trust by construction — values come out as LABELED_PROSE (when
they sit under a clear "Skills:" style label) or REGEX_PROSE (free-floating
emails/phones matched by pattern). The engine will weight these accordingly so
a clean CSV beats a resume guess on conflict.

Accepts a ``.pdf`` (parsed with pdfplumber) or a ``.txt`` fallback, so the
pipeline is demoable even without a PDF toolchain.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..models import Method, Observation
from ..normalize.dates import normalize_date_range

SOURCE = "resume"

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(\+?\d[\d\s().\-]{7,}\d)")
_URL = re.compile(r"((?:https?://)?(?:www\.)?(?:linkedin\.com|github\.com)/[^\s,;|]+)", re.IGNORECASE)
_SECTION = re.compile(r"^\s*(skills|education|experience|summary)\s*:?\s*$", re.IGNORECASE)
_DEGREE = re.compile(r"\b(B\.?S\.?|B\.?A\.?|M\.?S\.?|M\.?A\.?|Ph\.?D\.?|MBA|B\.?Tech|M\.?Tech)\b", re.IGNORECASE)
_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def _read_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages)
    return path.read_text(encoding="utf-8")


class ResumeAdapter:
    name = SOURCE

    def extract(self, path: Path) -> list[Observation]:
        text = _read_text(Path(path))
        out: list[Observation] = []

        # Free-floating contact info: regex, lowest trust.
        for m in _EMAIL.findall(text):
            out.append(Observation(field="emails", value=m, raw_value=m,
                                   source=SOURCE, method=Method.REGEX_PROSE))
        for m in _PHONE.findall(text):
            if len(re.sub(r"\D", "", m)) >= 10:
                out.append(Observation(field="phones", value=m, raw_value=m,
                                       source=SOURCE, method=Method.REGEX_PROSE))

        # Link URLs (LinkedIn / GitHub), regex-extracted from prose.
        for m in _URL.findall(text):
            out.append(Observation(field="links", value=m.rstrip(".,;"), raw_value=m,
                                   source=SOURCE, method=Method.REGEX_PROSE))

        # Section-based parsing for skills / education / experience.
        sections = self._split_sections(text)

        for raw_skill in re.split(r"[,\u2022\n]", sections.get("skills", "")):
            s = raw_skill.strip()
            # Strip category labels like "Languages: Java" → "Java"
            if ":" in s:
                s = s.split(":", 1)[1].strip()
            # Drop orphaned brackets and empty tokens
            s = s.strip("() ")
            if s and len(s) < 40 and not s.startswith(("(", ")")):
                out.append(Observation(field="skills", value=s, raw_value=raw_skill.strip(),
                                       source=SOURCE, method=Method.LABELED_PROSE))

        edu_lines = [l.strip() for l in sections.get("education", "").splitlines() if l.strip()]
        for i, line in enumerate(edu_lines):
            prev_line = edu_lines[i-1] if i > 0 else ""
            entry = self._parse_education_line(line, prev_line)
            if entry and (entry["institution"] or entry["degree"]):
                out.append(Observation(field="education", value=entry,
                                       raw_value=line, source=SOURCE, method=Method.LABELED_PROSE))

        exp_lines = [l.strip() for l in sections.get("experience", "").splitlines() if l.strip()]
        for i, line in enumerate(exp_lines):
            # Skip bullet points
            if line.startswith(("(cid:", "•", "-", "*")) or len(line) > 100:
                continue
            prev_line = exp_lines[i-1] if i > 0 else ""
            entry = self._parse_experience_line(line, prev_line)
            if entry and (entry["title"] or entry["company"]):
                out.append(Observation(field="experience", value=entry, raw_value=line,
                                       source=SOURCE, method=Method.LABELED_PROSE))

        # First non-empty line is often the candidate's name.
        first_lines = [l.strip() for l in text.splitlines() if l.strip()]
        if first_lines and "@" not in first_lines[0] and len(first_lines[0].split()) <= 4:
            out.append(Observation(field="full_name", value=first_lines[0],
                                   raw_value=first_lines[0], source=SOURCE,
                                   method=Method.REGEX_PROSE))
        return out

    def _split_sections(self, text: str) -> dict[str, str]:
        sections: dict[str, str] = {}
        current = None
        buf: list[str] = []
        for line in text.splitlines():
            m = _SECTION.match(line)
            if m:
                if current:
                    sections[current] = "\n".join(buf)
                current = m.group(1).lower()
                buf = []
            elif current:
                buf.append(line)
        if current:
            sections[current] = "\n".join(buf)
        return sections

    # Common location words to strip from company names.
    _LOCATIONS = re.compile(
        r"\s+(?:Remote|Pune|Bengaluru|Bangalore|Hyderabad|Mumbai|Delhi|Chennai|"
        r"New Delhi|Gurgaon|Noida|India|San Francisco|New York|London|Berlin|"
        r"Singapore|Remote/Hybrid|Hybrid|USA|US|UK)\s*$",
        re.IGNORECASE,
    )

    def _parse_experience_line(self, line: str, prev_line: str = "") -> dict | None:
        # Pattern 1: "Title, Company (Jan 2021 - Present)"
        m = re.match(r"(?P<title>[^,]+),\s*(?P<company>[^(]+)\((?P<dates>[^)]+)\)", line)
        if m:
            start, end = normalize_date_range(m.group("dates"))
            return {
                "title": m.group("title").strip(),
                "company": m.group("company").strip(),
                "start": start, "end": end, "summary": None,
            }
        
        # Pattern 2: "Title   Dec 2025 – Present" with Company on previous line
        # Common in real resumes where title and dates share a line.
        date_pattern = r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4} ?(?:-|–|—|to| ) ?(?:Present|Current|\d{4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}))\b"
        date_match = re.search(date_pattern, line, re.IGNORECASE)
        if date_match and not line.startswith(("(cid:", "•", "-", "*")):
            title = line[:date_match.start()].strip(" -|,")
            start, end = normalize_date_range(date_match.group(1))
            
            # The company is often the previous non-bullet line
            company = None
            if prev_line and not prev_line.startswith(("(cid:", "•", "-", "*")):
                # Strip location from company line ("ZS Associates Pune, India" → "ZS Associates")
                company = re.split(r",", prev_line)[0].strip()
                company = self._LOCATIONS.sub("", company).strip()
            
            # Only return if we found a reasonable title
            if len(title) > 2 and len(title) < 50:
                return {
                    "title": title,
                    "company": company,
                    "start": start, "end": end, "summary": None,
                }
            
        return None

    def _parse_education_line(self, line: str, prev_line: str = "") -> dict | None:
        """Parse education into {institution, degree, field, end_year}.

        Handles two common layouts:
          Pattern 1 — "B.S. Computer Science, UC Berkeley, 2016"
                      (single line, no prev_line available)
          Pattern 2 — Institution on prev_line, degree + field on current line
                      e.g. prev="SRM Institute, Chennai, India"
                           line="B.Tech, Computer Science and Engineering — CGPA: 9.55"
        Fields it cannot confidently extract stay null rather than guessed.
        """
        degree = None
        dm = _DEGREE.search(line)
        if dm:
            degree = dm.group(0)
        if not degree:
            return None  # Lines without a degree token are institution headers — skip

        year = None
        ym = _YEAR.search(line)
        if ym:
            year = ym.group(0)

        parts = [p.strip() for p in line.split(",") if p.strip()]
        institution = None
        field = None

        # Decide which layout we have based on whether prev_line is a real institution line.
        has_prev = (prev_line
                    and not re.match(r"^\s*education\s*:?\s*$", prev_line, re.IGNORECASE)
                    and not _DEGREE.search(prev_line))

        if has_prev:
            # Pattern 2: Institution is on the previous line.
            institution = prev_line.split(",")[0].strip()

            # Field comes from the part after the degree on the current line.
            if len(parts) >= 2:
                raw_field = parts[1]
            else:
                raw_field = re.sub(_DEGREE, "", parts[0], count=1).strip(" .") if parts else ""

            # Strip noise: CGPA, dates, pipes, em-dashes
            raw_field = re.split(r"[—–|]", raw_field)[0].strip(" .,:-")
            raw_field = re.sub(r"\s*(?:CGPA|GPA|CPI).*$", "", raw_field, flags=re.IGNORECASE).strip()
            field = raw_field or None
        else:
            # Pattern 1: everything on one line — "B.S. Computer Science, UC Berkeley, 2016"
            # field is in the first part (after stripping the degree token), institution is in the second.
            if parts:
                field = re.sub(_DEGREE, "", parts[0], count=1).strip(" .") or None
            if len(parts) >= 2:
                # parts[1] is institution (might have a year we strip)
                inst_candidate = re.sub(r"\b(19|20)\d{2}\b", "", parts[1]).strip(" ,")
                institution = inst_candidate or None
            if len(parts) >= 3 and not institution:
                institution = parts[2].strip()

        return {"institution": institution, "degree": degree, "field": field, "end_year": year}
