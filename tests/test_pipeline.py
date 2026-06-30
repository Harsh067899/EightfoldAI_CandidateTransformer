import json
from pathlib import Path

import pytest

from canonical import run
from canonical.pipeline import extract_sources

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample"

SOURCES = {
    "recruiter_csv": SAMPLE / "recruiter_export.csv",
    "ats_json": SAMPLE / "ats_profile.json",
    "resume": SAMPLE / "resume.pdf",
    "recruiter_notes": SAMPLE / "recruiter_notes.txt",
}


def test_gold_profile_end_to_end():
    """The full pipeline on the sample inputs must produce the known-good profile.

    This pins every reconciliation decision: phone unification, email typo
    suppression, title conflict resolution, skill canonicalization, date
    normalization.
    """
    result = run(SOURCES, json.loads((Path(__file__).resolve().parents[1]
                                      / "configs" / "default.json").read_text()))
    p = result["profile"]

    assert p["full_name"] == "Maya R. Chen"
    assert p["emails"] == ["maya.chen@example.com"]          # typo suppressed
    assert p["phones"] == ["+14155550182"]                   # 3 formats unified
    assert p["location"]["country"] == "US"
    assert p["headline"] == "Senior Software Engineer at Acme Robotics"  # CSV beat ATS
    assert p["years_experience"] == 8.0

    skill_names = {s["name"] for s in p["skills"]}
    assert {"JavaScript", "Kubernetes", "Python", "React"} <= skill_names

    # Corroborated skills outrank single-source ones.
    by_name = {s["name"]: s["confidence"] for s in p["skills"]}
    assert by_name["Python"] > by_name["React"]

    # links is the schema OBJECT shape, populated from resume + ATS.
    assert p["links"]["github"] == "github.com/mayachen"
    assert p["links"]["linkedin"] == "linkedin.com/in/mayachen"
    assert set(p["links"].keys()) == {"linkedin", "github", "portfolio", "other"}

    # experience carries the schema's summary field; education is structured.
    assert all("summary" in e for e in p["experience"])
    assert p["education"] == [{"institution": "UC Berkeley", "degree": "B.S.",
                               "field": "Computer Science", "end_year": "2016"}]

    # default output includes the provenance array [{field, source, method}].
    assert isinstance(p["provenance"], list) and p["provenance"]
    assert {"field", "source", "method"} <= set(p["provenance"][0].keys())


def test_robust_to_corrupt_source(tmp_path):
    """A garbage source must not crash the run, and must contribute nothing."""
    bad = tmp_path / "corrupt.json"
    bad.write_text("{ not valid json ,,,")
    result = run({"recruiter_csv": SOURCES["recruiter_csv"], "ats_json": bad}, {})
    assert result["profile"]["full_name"] == "Maya R. Chen"


def test_missing_value_is_null_never_invented():
    """A field no source provides stays null / empty-shape."""
    result = run({"recruiter_csv": SOURCES["recruiter_csv"]}, {})
    assert result["profile"]["links"] == {"linkedin": None, "github": None,
                                          "portfolio": None, "other": []}
    assert result["profile"]["education"] == []


def test_candidate_id_fallback_is_deterministic():
    """With no source id, a stable id is derived from the strongest key."""
    from canonical.merge import merge
    from canonical.models import Method, Observation
    obs = [Observation(field="emails", value="a@b.com", raw_value="a@b.com",
                       source="ats_json", method=Method.SEMI_STRUCTURED)]
    p1 = merge(obs)
    p2 = merge(obs)
    assert p1.candidate_id.value is not None
    assert p1.candidate_id.value.startswith("gen-")
    assert p1.candidate_id.value == p2.candidate_id.value  # deterministic


def test_deterministic_output():
    """Same inputs -> identical output, every time."""
    cfg = {}
    a = json.dumps(run(SOURCES, cfg)["profile"], sort_keys=True, default=str)
    b = json.dumps(run(SOURCES, cfg)["profile"], sort_keys=True, default=str)
    assert a == b
