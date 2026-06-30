# Architecture

This is the deep-dive companion to the one-page Stage 1 design PDF. Every
diagram below is generated from the actual code in `src/canonical/` — the
sources live in [`docs/diagrams/`](docs/diagrams) as editable `.mmd` files and
render natively on GitHub.

**North star:** the system optimises for one property — *never be confidently
wrong*. "Wrong-but-confident is worse than honestly-empty." Everything here is
derived from that plus the brief's four constraints: deterministic, explainable,
robust, scalable.

---

## The core idea: build truth once, then project it

The single most important boundary in the system: the **engine** builds one
rich, fixed internal record (`CanonicalProfile`) with full provenance and
confidence, and the **projection layer** is the *only* code that knows the
requested output shape. The engine never imports or sees the config. Changing
the output is pure config; it can never touch resolution logic.

```mermaid
flowchart TB
    subgraph Sources["Inputs (any subset)"]
        CSV["Recruiter CSV<br/>structured"]
        ATS["ATS JSON<br/>semi-structured"]
        RES["Resume PDF<br/>unstructured"]
        NOTE["Recruiter notes<br/>unstructured"]
    end

    subgraph Engine["ENGINE — builds the truth (config-blind)"]
        direction TB
        AD["Adapters via safe_extract<br/>emit Observation(field, value, raw, source, method)"]
        NORM["normalize_all<br/>phones · dates · country · skills · degree"]
        MATCH["group_records<br/>blocking + union-find"]
        MERGE["merge<br/>trust×reliability · noisy-OR · typo-suppress"]
        CANON[("CanonicalProfile<br/>+ provenance + confidence")]
        AD --> NORM --> MATCH --> MERGE --> CANON
    end

    subgraph Projection["PROJECTION — formats the answer"]
        direction TB
        PROJ["project<br/>select · remap (from-paths) · on_missing"]
        VAL["validate<br/>types + required"]
        OUT["Output JSON<br/>(requested shape)"]
        PROJ --> VAL --> OUT
    end

    CFG["Runtime config"]

    CSV --> AD
    ATS --> AD
    RES --> AD
    NOTE --> AD
    CANON --> PROJ
    CFG -. only touches projection .-> PROJ
```

---

## Class model

The data model is deliberately small. Adapters emit `Observation`s; the merge
stage resolves them into one `Field_` per canonical field (value + confidence +
provenance); eleven `Field_`s make a `CanonicalProfile`.

```mermaid
classDiagram
    class Method {
        <<enumeration>>
        STRUCTURED_FIELD
        SEMI_STRUCTURED
        LABELED_PROSE
        REGEX_PROSE
        INFERRED
    }
    class Observation {
        +str field
        +Any value
        +Any raw_value
        +str source
        +Method method
        +bool dropped
        +reliability() float
    }
    class Provenance {
        +str source
        +Method method
        +Any raw_value
        +list~str~ corroborated_by
        +list~str~ conflicted_with
        +str decision
    }
    class Field_ {
        +Any value
        +float confidence
        +list~Provenance~ provenance
        +list~float~ item_confidences
    }
    class CanonicalProfile {
        +Field_ candidate_id
        +Field_ full_name
        +Field_ emails
        +Field_ phones
        +Field_ location
        +Field_ links
        +Field_ headline
        +Field_ years_experience
        +Field_ skills
        +Field_ experience
        +Field_ education
        +float overall_confidence
        +field_names() list~str~
    }
    class SourceAdapter {
        <<interface>>
        +str name
        +extract(path) list~Observation~
    }
    class RecruiterCsvAdapter
    class AtsJsonAdapter
    class ResumeAdapter
    class RecruiterNotesAdapter

    Observation --> Method
    Provenance --> Method
    Field_ "1" o-- "*" Provenance
    CanonicalProfile "1" *-- "11" Field_
    SourceAdapter <|.. RecruiterCsvAdapter
    SourceAdapter <|.. AtsJsonAdapter
    SourceAdapter <|.. ResumeAdapter
    SourceAdapter <|.. RecruiterNotesAdapter
    SourceAdapter ..> Observation : emits
```

---

## Request lifecycle

A single `run()` call (`pipeline.run`) flows through the stages in order.
`extract_sources` runs each adapter under `safe_extract` and then `normalize_all`.

```mermaid
sequenceDiagram
    actor User
    participant CLI as cli.main
    participant P as pipeline.run
    participant A as Adapters
    participant N as normalize_all
    participant M as merge
    participant PR as project
    participant V as validate

    User->>CLI: --recruiter_csv ... --config
    CLI->>P: run(sources, config)
    loop each named source
        P->>A: safe_extract(adapter, path)
        A-->>P: list[Observation]  (or [] on bad source)
    end
    P->>N: normalize_all(observations)
    N-->>P: normalized (unparseable values dropped)
    P->>M: merge(observations)
    M-->>P: CanonicalProfile (+ provenance + confidence)
    P->>PR: project(profile, config)
    PR-->>P: output dict (requested shape)
    P->>V: validate(output, config)
    V-->>P: problems[]
    P-->>CLI: {profile, valid, problems, internal}
    CLI-->>User: JSON
```

---

## Observation lifecycle

How one observation becomes part of a resolved field. The `dropped` branch is
the load-bearing one: an unparseable value contributes nothing rather than
becoming a confident guess.

```mermaid
flowchart LR
    RAW["raw source value"] -->|adapter.extract| OBS["Observation<br/>method = extraction kind"]
    OBS -->|normalize_observation| DEC{"parse ok?"}
    DEC -->|yes| NORMED["normalized value"]
    DEC -->|no| DROP["dropped = true<br/>contributes nothing<br/>(never invented)"]
    NORMED -->|group by field, value| GRP["evidence groups"]
    GRP -->|single-valued| WIN["winner = max(trust×reliability)<br/>dissent discounts confidence"]
    GRP -->|multi-valued| UNION["union + dedupe<br/>emails: near-dup typos suppressed"]
    WIN --> FIELD["Field_<br/>value + confidence + provenance"]
    UNION --> FIELD
```

---

## Stage responsibilities (where each lives)

| Stage | File | Responsibility |
|-------|------|----------------|
| extract | `sources/*.py` + `sources/base.py` | one adapter per source → `Observation`s; `safe_extract` guarantees a bad source yields `[]`, never a crash |
| normalize | `normalize_stage.py`, `normalize/` | phones→E.164, dates→`YYYY-MM`, country→ISO-3166, skills→canonical, degree→canonical; failure ⇒ `dropped` |
| match | `match.py` | `group_records`: blocking + union-find clusters records for one person; scales past one candidate |
| confidence | `confidence.py` | `strength = trust × reliability`; `noisy_or`; conflict discount |
| merge | `merge.py` | per-field winner / union; `_resolve_links` (object shape); `_suppress_typos`; `candidate_id` fallback |
| project | `project.py` | config-driven select / remap / `on_missing`; the only config-aware code |
| validate | `validate.py` | projected output vs requested schema (types + required) |
| orchestrate | `pipeline.py`, `cli.py` | `run` / `run_batch`; CLI surface with `--explain` |

---

## Key algorithms

**Trust = source × method.** Each observation's weight is
`SOURCE_TRUST[source] × METHOD_RELIABILITY[method]`. A CSV column (`1.0 × 1.0`)
outranks a regex-from-prose hit (`0.65 × 0.50`) even for the same field. Source
trust and method reliability are data tables (policy), kept out of the merge
logic (mechanism).

**Confidence = noisy-OR.** `c = 1 − Π(1 − sᵢ)` over agreeing evidence. One
strong source already scores high; corroboration raises it (an average
wouldn't); conflicting evidence discounts the winner. Below a floor a
single-valued field is emitted `null`.

**Matching = blocking + union-find.** The only super-linear cost at scale.
Records sharing a strong key (normalized email/phone) are unioned via a
path-compressed disjoint-set, keeping the dominant cost near-linear instead of
O(n²). Everything else is left simple on purpose.

**Email typo suppression.** A low-confidence email within edit-similarity ≥ 88
of a higher-confidence one is treated as a corruption of it and dropped — the
"wrong-but-confident is worse than empty" principle in running code.

---

## Extending the system: add a source

1. Write an adapter class with `name` and `extract(path) -> list[Observation]`,
   tagging each value with the right `Method`.
2. Register it in `sources/__init__.py` (`ADAPTERS`) and give it a `SOURCE_TRUST`.
3. Done — normalize, match, merge, project, validate all work unchanged, because
   they only ever see `Observation`s.

---

## Design decisions & rejected alternatives

- **LLM/ML resolution — rejected.** Non-deterministic and untraceable, and it
  would confidently mis-map `Java → JavaScript` (the exact failure to avoid).
  Rule-based resolution with a similarity floor cannot make that error.
- **Last-write-wins merge — rejected.** Can't explain or score a decision.
- **Deliberately out of scope (time):** a UI (CLI suffices per brief), a
  persistent datastore, and ML entity-resolution — blocking + strong keys is the
  right complexity here.

## Limitations (honest)

- Free-text resume parsing is best-effort: dense "Tool (sub, sub)" lists and
  mid-word line breaks in PDFs can leave minor skill fragments.
- Location is not extracted from resume header lines (comes from structured
  sources); absent ⇒ `null`, never guessed.
- Single default phone region (`US`) when no country code is present.
