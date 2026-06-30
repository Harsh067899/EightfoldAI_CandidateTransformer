# Demo video script (~2 minutes)

A tight screen-recording plan. Keep a terminal open in the repo root with the
venv active. Target ~2:00; the timings below add up to ~1:55.

---

### 0:00 – 0:15 · Frame the problem
> "This takes candidate data from four sources — a recruiter CSV, an ATS JSON
> export, a resume PDF, and free-text recruiter notes — and reconciles them into
> one canonical profile where every field is traceable and confidence-scored.
> The principle I built around is the brief's: wrong-but-confident is worse than
> empty."

### 0:15 – 0:45 · Run the default output
Run:
```bash
PYTHONPATH=src python -m canonical.cli \
  --recruiter_csv data/sample/recruiter_export.csv \
  --ats_json data/sample/ats_profile.json \
  --resume data/sample/resume.pdf \
  --recruiter_notes data/sample/recruiter_notes.txt \
  --config configs/default.json
```
> "One clean profile. The phone appeared in three different formats across
> sources — all collapsed to one E.164 number. Skills like 'JS' and 'k8s' are
> canonicalized to JavaScript and Kubernetes. Notice skills that two sources
> agree on score ~0.87 confidence; ones only the resume mentions score ~0.46."

### 0:45 – 1:10 · Custom config (the configurable-output twist)
Run the same sources with `--config configs/custom_minimal.json`.
> "Same engine, different config — no code change. I've selected a subset,
> renamed emails[0] to primary_email, pulled location.country out, and told it to
> omit portfolio since no source has it. The engine builds one internal record; this
> projection layer is the only thing that knows the output shape."

### 1:10 – 1:40 · The design decision I'm proud of + an edge case
Run the same command with `--explain` and scroll to `emails` and `headline`.
> "Here's the decision I'm proudest of. The recruiter notes contain a typo'd
> email — exmaple dot con. Naively you'd ship it as a second address and silently
> break outreach. My merge step detects it's a near-duplicate of the verified
> email and suppresses it — you can see that in the provenance. Same idea on the
> job title: the CSV and ATS disagree, so it picks the higher-trust source and
> records that it outranked the other."

### 1:40 – 1:55 · Robustness + tests
Run: `python -c "open('bad.json', 'w').write('{bad json')"` then the CLI with `--ats_json bad.json -v`.
> "And if a source is corrupt, it's skipped with a warning — the run never
> crashes and never invents a value. Twenty-two tests cover the normalizers,
> conflict resolution, the typo case, robustness, and a gold-profile end-to-end."
Run: `python -m pytest -q`.

> "That's the system — deterministic, explainable, and honest about what it
> doesn't know."
