import pytest

from canonical.merge import merge
from canonical.models import Method, Observation
from canonical.project import project, MissingFieldError


def _obs(field, value, source, method=Method.STRUCTURED_FIELD):
    return Observation(field=field, value=value, raw_value=value, source=source, method=method)


def _profile():
    return merge([
        _obs("full_name", "Maya Chen", "recruiter_csv"),
        _obs("emails", "maya@work.com", "recruiter_csv"),
        _obs("phones", "+14155550182", "recruiter_csv"),
        _obs("skills", "Python", "recruiter_csv"),
    ])


def test_default_projection_emits_full_schema():
    out = project(_profile(), {})
    assert out["full_name"] == "Maya Chen"
    assert "skills" in out and isinstance(out["skills"], list)


def test_remap_and_indexed_path():
    cfg = {"fields": [
        {"path": "primary_email", "from": "emails[0]", "type": "string"},
    ]}
    out = project(_profile(), cfg)
    assert out["primary_email"] == "maya@work.com"


def test_map_path_extracts_skill_names():
    cfg = {"fields": [{"path": "skills", "from": "skills[].name", "type": "string[]"}]}
    out = project(_profile(), cfg)
    assert out["skills"] == ["Python"]


def test_missing_omit_drops_key():
    cfg = {"fields": [{"path": "gh", "from": "links[0]", "on_missing": "omit"}]}
    out = project(_profile(), cfg)
    assert "gh" not in out


def test_missing_error_on_required_raises():
    cfg = {"fields": [{"path": "gh", "from": "links[0]", "required": True, "on_missing": "error"}]}
    with pytest.raises(MissingFieldError):
        project(_profile(), cfg)


def test_missing_null_sets_none():
    cfg = {"fields": [{"path": "gh", "from": "links[0]", "on_missing": "null"}]}
    out = project(_profile(), cfg)
    assert out["gh"] is None


def test_include_provenance_toggle():
    prof = _profile()
    with_prov = project(prof, {"include_provenance": True})
    without = project(prof, {"include_provenance": False})
    assert "provenance" in with_prov
    assert "provenance" not in without


def test_links_path_resolves_from_object():
    from canonical.models import Method, Observation
    prof = merge([
        _obs("full_name", "Maya Chen", "recruiter_csv"),
        Observation(field="links", value="github.com/maya", raw_value="github.com/maya",
                    source="resume", method=Method.REGEX_PROSE),
    ])
    out = project(prof, {"fields": [{"path": "gh", "from": "links.github"}]})
    assert out["gh"] == "github.com/maya"
