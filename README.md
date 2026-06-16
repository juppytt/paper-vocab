# Paper Vocab

Vocabulary lookup over paper text corpora. The immediate goal is to check
whether a word or phrase is common in prior security papers, and to inspect the
sentences where it appears.

Raw text files are the canonical corpus. The CLI can scan those files directly
or build a SQLite/FTS vocabulary DB for repeated lookups.

## Corpus Layout

```text
data/corpus/text/
  ccs/
    2013/
      paper-a.txt
  sp/
    2013/
      paper-b.txt
```

The text files can be produced by `paper-collect`:

```bash
python3 -m pip install -e ../paper-collect
python3 -m pip install -e .
```

`paper-collect` exports a console command through its `pyproject.toml`:

```toml
[project.scripts]
paper-collect = "paper_collect.cli:main"
```

Use that command to download PDFs and extract text:

```bash
paper-collect download \
  --db data/sample_2013/paper_collect.sqlite \
  --target pdf \
  --venues security sp \
  --year 2013 \
  --limit 50 \
  --output-dir data/sample_2013/raw
```

```bash
paper-collect extract-text \
  --db data/sample_2013/paper_collect.sqlite \
  --venues security sp \
  --year 2013 \
  --limit 50 \
  --output-dir data/sample_2013/raw \
  --delete-pdfs
```

Then expose the extracted text as the lookup corpus:

```bash
mkdir -p data/corpus
ln -sfn ../sample_2013/raw/text data/corpus/text
```

PDFs are not needed for lookup after text extraction. Use `--delete-pdfs` for a
text-only local corpus; omit it when the raw PDFs should stay available for
debugging or re-extraction.

## Vocab DB

Build a SQLite/FTS DB from extracted text:

```bash
paper-vocab build-db \
  --corpus-dir data/corpus/text \
  --manifest-db ../paper-collect/data/paper_collect.sqlite \
  --db data/paper_vocab.sqlite \
  --year-from 2013 \
  --year-to 2022 \
  --force
```

Query the DB:

```bash
paper-vocab lookup-db "in the wild" \
  --db data/paper_vocab.sqlite \
  --year-from 2013 \
  --year-to 2022
```

`lookup-db` uses the SQLite FTS index to find candidate documents before
rescanning those documents for sentence examples and exact occurrence counts.
FTS is token-based, so use `--legacy` to compare against the old full-document
substring scan or to preserve arbitrary substring matches inside larger words:

```bash
paper-vocab lookup-db "in the wild" \
  --db data/paper_vocab.sqlite \
  --year-from 2013 \
  --year-to 2022 \
  --legacy
```

## Lookup

```bash
paper-vocab lookup "in the wild" \
  --corpus-dir data/corpus/text \
  --year 2013 \
  --limit-files 50 \
  --examples 20
```

Pass the `paper-collect` SQLite DB to show paper metadata next to sentence
examples:

```bash
paper-vocab lookup "in the wild" \
  --corpus-dir data/corpus/text \
  --manifest-db data/sample_2013/paper_collect.sqlite \
  --year 2013 \
  --limit-files 50
```

The command reports:

```text
files_scanned
files_matched
sentences
occurrences
tokens
per_million_tokens
examples
```

`--limit-files 50` means: after applying path filters such as `--year 2013` and
`--venues security sp`, scan the first 50 sorted text files. It does not download
anything and it is not random sampling.

The example list is the matching sentence list. Increase `--examples` to print
more matching sentences:

```bash
paper-vocab lookup "in the wild" \
  --corpus-dir data/corpus/text \
  --manifest-db data/sample_2013/paper_collect.sqlite \
  --year 2013 \
  --limit-files 50 \
  --examples 50
```

Use JSON output when another script or LLM tool should consume the result:

```bash
paper-vocab lookup "side channel" \
  --corpus-dir data/corpus/text \
  --year 2013 \
  --limit-files 50 \
  --json
```

## Current Sample

The local sample used for initial testing is:

```text
year: 2013
papers: 50
venues: security 45, sp 5
pdf size: 111 MB
text size: 3.8 MB
```

Example lookup results over that sample:

```text
expression: in the wild
files_scanned: 50
files_matched: 7
sentences: 16
occurrences: 16
tokens: 619426
per_million_tokens: 25.830
```

```text
expression: side channel
files_scanned: 50
files_matched: 3
sentences: 28
occurrences: 30
tokens: 619426
per_million_tokens: 48.432
```

```text
expression: we propose
files_scanned: 50
files_matched: 30
sentences: 95
occurrences: 95
tokens: 619426
per_million_tokens: 153.368
```

## Next Step

The next improvement is richer DB metadata and cached sentence spans, so phrase
lookups do not need to rescan matching document text for example sentences.
