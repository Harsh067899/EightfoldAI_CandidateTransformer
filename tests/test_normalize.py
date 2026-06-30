from canonical.normalize import (
    normalize_phone, normalize_country, canonicalize_skill, normalize_month,
)
from canonical.normalize.dates import normalize_date_range


def test_phone_formats_collapse_to_one_e164():
    forms = ["(415) 555-0182", "+1 415-555-0182", "415.555.0182", "+14155550182"]
    out = {normalize_phone(f) for f in forms}
    assert out == {"+14155550182"}


def test_phone_garbage_returns_none_not_a_guess():
    assert normalize_phone("call me maybe") is None
    assert normalize_phone("123") is None
    assert normalize_phone("") is None


def test_country_aliases_and_codes():
    assert normalize_country("USA") == "US"
    assert normalize_country("United States") == "US"
    assert normalize_country("uk") == "GB"
    assert normalize_country("US") == "US"
    assert normalize_country("Narnia") is None


def test_skill_canonicalization():
    assert canonicalize_skill("JS") == "JavaScript"
    assert canonicalize_skill("k8s") == "Kubernetes"
    assert canonicalize_skill("react.js") == "React"
    # An unknown skill is preserved, never force-mapped.
    assert canonicalize_skill("Rust") == "Rust"


def test_skill_does_not_confuse_java_and_javascript():
    # "Java" must stay Java — mis-mapping to JavaScript is the wrong-but-confident trap.
    assert canonicalize_skill("Java") == "Java"


def test_date_normalization_and_present():
    assert normalize_month("Jan 2021") == "2021-01"
    assert normalize_month("March 2021") == "2021-03"
    assert normalize_month("Present") == "present"
    assert normalize_month("garbage") is None


def test_date_range_split():
    assert normalize_date_range("Jan 2021 - Present") == ("2021-01", "present")
    assert normalize_date_range("Jun 2018 – Dec 2020") == ("2018-06", "2020-12")
