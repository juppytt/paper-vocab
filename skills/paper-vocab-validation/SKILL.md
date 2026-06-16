---
name: paper-vocab-validation
description: "Validate assistant-introduced systems/security paper phrases against a paper-vocab SQLite corpus. Use when drafting, revising, or auditing technical prose and a phrase feels plausible but may be non-standard or overly artificial."
---

# Paper Vocab Validation

Use `paper-vocab` as a usage check for questionable systems/security wording
that the assistant introduced while drafting, rewriting, summarizing, or editing.

## Corpus

Install the tool from <https://github.com/juppytt/paper-vocab>:

```bash
python3 -m pip install git+https://github.com/juppytt/paper-vocab.git
```

Default DB:

```text
<path-to-db>
```

Lookup command:

```bash
paper-vocab lookup-db "PHRASE" \
  --db <path-to-db> \
  --year-from 2013 \
  --year-to 2022 \
  --examples 5
```

Restrict by venue when helpful:

```bash
paper-vocab lookup-db "PHRASE" \
  --db <path-to-db> \
  --venues sp ccs security ndss \
  --year-from 2013 \
  --year-to 2022 \
  --examples 5
```

If the console script is not installed, use the module form with an absolute
`PYTHONPATH`:

```bash
PYTHONPATH=<path-to-paper-vocab-repo>/src python3 -m paper_vocab.cli lookup-db "PHRASE" \
  --db <path-to-db> \
  --year-from 2013 \
  --year-to 2022 \
  --examples 5
```

## Query Boundary

Query only phrases introduced by the assistant.

Do not query or replace terms that came from:

- The user.
- The source note or draft.
- A cited paper, benchmark, system, attack, technique, or local terminology file.
- An established acronym or term, such as `HITL`.
- A deliberately named project term, mode, or component, such as `auto-mode`.

Do not use absence from the corpus as evidence against a new project-specific
term or a term that emerged after the corpus period.

## Good Query Targets

Query assistant-coined phrases that sound plausible but may be non-standard:

- Component-like nouns: `permission engine`, `blocking pass`.
- Unusual compound phrases: `target process claims`, `HITL burden`.
- Generic field wording that could have a more standard alternative:
  `policy engine`, `reference monitor`, `blocking path`, `cache effectiveness`.

Batch related assistant-introduced phrases in one pass when auditing a note or
paper section.

## Interpreting Results

- Zero hits: treat the assistant phrase as suspicious unless it is a deliberate
  new term from the user or source.
- A few hits concentrated in one paper: acceptable for a named component, weak
  as a general field term.
- Many hits across papers: likely field-standard, but still inspect examples
  for meaning.
- Compare alternatives before recommending a rewrite.

## Reporting

Report only phrases worth acting on.

For each flagged phrase, include:

- The queried phrase.
- The hit count or relevant lookup signal.
- The concrete replacement or a short reason no replacement is needed.

State when no change is recommended because the phrase came from the user,
source text, or project terminology.
