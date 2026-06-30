from canonical.merge import merge
from canonical.models import Method, Observation


def _obs(field, value, source, method=Method.STRUCTURED_FIELD):
    return Observation(field=field, value=value, raw_value=value, source=source, method=method)


def test_higher_trust_source_wins_conflict():
    obs = [
        _obs("headline", "Senior Engineer", "recruiter_csv", Method.STRUCTURED_FIELD),
        _obs("headline", "Staff Engineer", "ats_json", Method.SEMI_STRUCTURED),
    ]
    profile = merge(obs)
    assert profile.headline.value == "Senior Engineer"
    assert "ats_json" in profile.headline.provenance[0].conflicted_with


def test_corroboration_raises_confidence():
    one = merge([_obs("full_name", "Maya Chen", "resume", Method.REGEX_PROSE)])
    two = merge([
        _obs("full_name", "Maya Chen", "resume", Method.REGEX_PROSE),
        _obs("full_name", "Maya Chen", "recruiter_csv", Method.STRUCTURED_FIELD),
    ])
    assert two.full_name.confidence > one.full_name.confidence


def test_low_confidence_single_value_drops_to_null():
    # A lone, weakest-possible source should not be emitted confidently.
    profile = merge([_obs("headline", "Maybe a Manager", "recruiter_notes", Method.INFERRED)])
    assert profile.headline.value is None


def test_email_typo_is_suppressed():
    obs = [
        _obs("emails", "maya.chen@example.com", "recruiter_csv", Method.STRUCTURED_FIELD),
        _obs("emails", "maya.chen@exmaple.con", "recruiter_notes", Method.LABELED_PROSE),
    ]
    profile = merge(obs)
    assert profile.emails.value == ["maya.chen@example.com"]


def test_distinct_emails_both_kept():
    obs = [
        _obs("emails", "maya@work.com", "recruiter_csv", Method.STRUCTURED_FIELD),
        _obs("emails", "maya@personal.com", "ats_json", Method.SEMI_STRUCTURED),
    ]
    profile = merge(obs)
    assert set(profile.emails.value) == {"maya@work.com", "maya@personal.com"}
