"""Generate the one-page Stage 1 design document as a PDF.

Structure follows the brief: pipeline breakdown, canonical schema + normalized
formats, merge/conflict-resolution + confidence, runtime config handling, and
3-5 edge cases + deliberate descoping.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

ACCENT = HexColor("#1a4d7a")
GREY = HexColor("#444444")
LIGHT = HexColor("#eef2f6")

doc = SimpleDocTemplate(
    "../outputs/Design_YourName_youremail_Eightfold.pdf",
    pagesize=letter,
    leftMargin=0.6 * inch, rightMargin=0.6 * inch,
    topMargin=0.5 * inch, bottomMargin=0.45 * inch,
)

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Title"], fontSize=14, leading=16,
                    textColor=ACCENT, spaceAfter=1, alignment=0)
SUB = ParagraphStyle("SUB", parent=ss["Normal"], fontSize=7.6, leading=9.5,
                     textColor=GREY, spaceAfter=4)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=8.8, leading=10,
                    textColor=ACCENT, spaceBefore=4, spaceAfter=1.5)
BODY = ParagraphStyle("BODY", parent=ss["Normal"], fontSize=7.4, leading=9.2,
                      spaceAfter=2)
SMALL = ParagraphStyle("SMALL", parent=ss["Normal"], fontSize=6.9, leading=8.4)
MONO = ParagraphStyle("MONO", parent=ss["Code"], fontSize=6.6, leading=8,
                      textColor=HexColor("#222222"))

s = []
s.append(Paragraph("Multi-Source Candidate Data Transformer &mdash; Design", H1))
s.append(Paragraph(
    "Your Name &nbsp;&middot;&nbsp; you@example.com &nbsp;&middot;&nbsp; "
    "Stage 1 technical design. Guiding principle: <b>wrong-but-confident is worse "
    "than honestly-empty</b> &mdash; when in doubt, emit null, never a guess.", SUB))

# --- Pipeline ---
s.append(Paragraph("1 &nbsp; Pipeline", H2))
s.append(Paragraph(
    "<b>detect &rarr; extract &rarr; normalize &rarr; match &rarr; merge &rarr; "
    "project &rarr; validate.</b> Each <i>source adapter</i> turns raw input into a "
    "flat stream of typed <b>Observations</b> <font face='Courier' size=6.5>"
    "(field, value, raw_value, source, method)</font>. Nothing downstream sees a raw "
    "source again, so adding a source = one new adapter, zero changes elsewhere. The "
    "engine always builds one rich, fixed <b>internal canonical record</b>; a separate "
    "<b>projection layer</b> reshapes it to the requested output. The engine never "
    "knows the output config exists &mdash; that boundary is the core of the design.", BODY))

# --- Schema + normalized formats ---
s.append(Paragraph("2 &nbsp; Canonical schema &amp; normalized formats", H2))
schema_rows = [
    ["Field", "Shape", "Normalized form"],
    ["candidate_id, full_name, headline", "string", "trimmed"],
    ["emails / phones / links / skills", "list", "deduped; phones → E.164"],
    ["location", "{city, region, country}", "country → ISO-3166 alpha-2"],
    ["years_experience", "number", "float"],
    ["skills[]", "{name, confidence, sources}", "canonical names (JS→JavaScript)"],
    ["experience[]", "{title, company, start, end}", "dates → YYYY-MM (+ present)"],
    ["education[]", "{institution, degree, field, year}", "dates → YYYY-MM"],
]
t = Table(schema_rows, colWidths=[2.0 * inch, 1.7 * inch, 3.6 * inch])
t.setStyle(TableStyle([
    ("FONT", (0, 0), (-1, -1), "Helvetica", 6.6),
    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 6.8),
    ("TEXTCOLOR", (0, 0), (-1, 0), ACCENT),
    ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#ffffff"), HexColor("#f7f9fb")]),
    ("LINEBELOW", (0, 0), (-1, 0), 0.4, ACCENT),
    ("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
    ("LEFTPADDING", (0, 0), (-1, -1), 4),
]))
s.append(t)
s.append(Spacer(1, 3))

# --- Merge + confidence ---
s.append(Paragraph("3 &nbsp; Match, merge &amp; confidence", H2))
s.append(Paragraph(
    "<b>Match keys</b>, in priority order: normalized email &rarr; normalized phone &rarr; "
    "name+company. Records sharing a strong key are clustered (blocking + union-find) so "
    "the same engine scales from one candidate to thousands. <b>Winner selection</b> per "
    "field: each observation has <font face='Courier' size=6.5>strength = source_trust "
    "&times; method_reliability</font> (CSV column 1.0 &middot; ATS field 0.85 &middot; "
    "labeled prose 0.7 &middot; regex prose 0.5; source trust: CSV 1.0 &rarr; notes 0.55). "
    "The highest-strength camp wins; multi-valued fields union+dedupe instead. "
    "<b>Confidence</b> is a noisy-OR over agreeing evidence, "
    "<font face='Courier' size=6.5>1 &minus; &Pi;(1 &minus; strength<sub>i</sub>)</font>: one "
    "strong source scores high, corroboration raises it (never past 1.0), conflict "
    "discounts the winner. Below a floor, a single-valued field is emitted null rather "
    "than a low-trust guess. Every winning value records provenance: source, method, "
    "raw value, who corroborated, who it outranked, and why.", BODY))

# --- Config ---
s.append(Paragraph("4 &nbsp; Runtime custom-output config", H2))
s.append(Paragraph(
    "The projection layer (the only config-aware code) selects a field subset, renames/"
    "remaps via a <b>from</b>-path language (<font face='Courier' size=6.5>emails[0]</font>, "
    "<font face='Courier' size=6.5>location.city</font>, <font face='Courier' size=6.5>"
    "skills[].name</font>), toggles provenance/confidence, and applies a per-field missing "
    "policy <font face='Courier' size=6.5>null | omit | error</font>. The projected result "
    "is then validated against the <i>requested</i> schema (declared types + required), "
    "keeping internal-record validation (pydantic) separate from output validation.", BODY))

# --- Edge cases ---
s.append(Paragraph("5 &nbsp; Edge cases &amp; deliberate descoping", H2))
edge = [
    ["Edge case", "Handling"],
    ["Same phone in 3 formats", "all normalize to one E.164; corroboration → high confidence"],
    ["Typo'd email (exmaple.con)", "near-duplicate of verified email → suppressed, not shipped"],
    ["Conflicting job title", "higher trust source wins; conflict + reason recorded"],
    ["Garbage / corrupt source", "adapter wrapped: yields 0 observations, logs, run continues"],
    ["Field no source provides", "stays null / [] — never invented"],
]
t2 = Table(edge, colWidths=[2.0 * inch, 5.3 * inch])
t2.setStyle(TableStyle([
    ("FONT", (0, 0), (-1, -1), "Helvetica", 6.6),
    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 6.8),
    ("TEXTCOLOR", (0, 0), (-1, 0), ACCENT),
    ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#ffffff"), HexColor("#f7f9fb")]),
    ("LINEBELOW", (0, 0), (-1, 0), 0.4, ACCENT),
    ("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
    ("LEFTPADDING", (0, 0), (-1, -1), 4),
]))
s.append(t2)
s.append(Spacer(1, 3))
s.append(Paragraph(
    "<b>Deliberately left out under time pressure:</b> a UI (CLI is sufficient per the "
    "brief); ML-based entity resolution (blocking + strong keys is the right complexity); "
    "a persistent datastore. Optimization is focused where it matters &mdash; matching is "
    "the only super-linear cost, so it gets blocking + union-find and C-backed fuzzy "
    "matching; per-value work is left simple and readable.", SMALL))

doc.build(s)
print("wrote design PDF")
