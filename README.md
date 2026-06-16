# Paper Vocab

Paper Vocab searches extracted paper text for words and phrases, reports how
often they appear, and prints matching sentences.

Extracted `.txt` files are the source data. The CLI can search those files
directly, or build a SQLite/FTS DB for faster repeated lookups.

## Installation

Install `paper-vocab` from <https://github.com/juppytt/paper-vocab>:

```bash
git clone https://github.com/juppytt/paper-vocab.git
cd paper-vocab
python3 -m pip install -e .
```

Or install directly from GitHub:

```bash
python3 -m pip install git+https://github.com/juppytt/paper-vocab.git
```

After installation, use the console command directly:

```bash
paper-vocab --help
```

## Use an Existing DB File

If you already have `paper_vocab.sqlite`, `paper-collect`, PDFs, and extracted
`.txt` files are not required for lookup. Point `lookup-db` at the DB file:

```bash
paper-vocab lookup-db "in the wild" \
  --db <path-to-paper_vocab.sqlite> \
  --year-from 2013 \
  --year-to 2022
```

Useful filters:

```bash
paper-vocab lookup-db "side channel" \
  --db <path-to-paper_vocab.sqlite> \
  --venues sp ccs

paper-vocab lookup-db "permission engine" \
  --db <path-to-paper_vocab.sqlite> \
  --year-from 2018 \
  --year-to 2022
```

## Build a DB From Text Files

Use this section only when creating a new `paper_vocab.sqlite`.

To collect papers and extract text, install
[`paper-collect`](https://github.com/juppytt/paper-collect) alongside this repo:

```bash
# From the parent directory that contains paper-vocab/
git clone https://github.com/juppytt/paper-collect.git
python3 -m pip install -e paper-collect
```

Arrange extracted text files by venue and year:

```text
data/corpus/text/
  ccs/
    2013/
      paper-a.txt
  sp/
    2013/
      paper-b.txt
```

`paper-vocab` reads `.txt` files. Use `paper-collect` to download PDFs and
extract text:

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

For these commands, create `data/corpus/text` as a symlink to the text directory
produced by `paper-collect`:

```bash
mkdir -p data/corpus
ln -sfn ../sample_2013/raw/text data/corpus/text
```

PDFs are not needed for lookup after text extraction. Use `--delete-pdfs` to
keep only extracted text; omit it when the raw PDFs should stay available for
debugging or re-extraction.

## Vocab DB

Build a SQLite/FTS DB for repeated searches:

```bash
paper-vocab build-db \
  --corpus-dir data/corpus/text \
  --manifest-db ../paper-collect/data/paper_collect.sqlite \
  --db data/paper_vocab.sqlite \
  --year-from 2013 \
  --year-to 2022 \
  --force
```

Search the DB:

```bash
paper-vocab lookup-db "in the wild" \
  --db data/paper_vocab.sqlite \
  --year-from 2013 \
  --year-to 2022
```

`lookup-db` uses SQLite FTS to narrow the search first, then counts exact
matches and prints matching sentences. FTS is token-based. Use
`--substring-search` only when you want to scan every filtered DB document and
allow matches inside larger words:

```bash
paper-vocab lookup-db "in the wild" \
  --db data/paper_vocab.sqlite \
  --year-from 2013 \
  --year-to 2022 \
  --substring-search
```

## Direct Text Search

```bash
paper-vocab lookup "in the wild" \
  --corpus-dir data/corpus/text \
  --year 2013 \
  --limit-files 50 \
  --examples 20
```

Pass the `paper-collect` SQLite DB to show paper metadata next to matching
sentences:

```bash
paper-vocab lookup "in the wild" \
  --corpus-dir data/corpus/text \
  --manifest-db data/sample_2013/paper_collect.sqlite \
  --year 2013 \
  --limit-files 50
```

### CLI Arguments

Common lookup options:

| Option | Meaning |
| --- | --- |
| `--corpus-dir data/corpus/text` | Text-file root for `lookup`. |
| `--db data/paper_vocab.sqlite` | SQLite vocab DB for `lookup-db`. |
| `--manifest-db path/to/paper_collect.sqlite` | Optional `paper-collect` DB used to show venue/year/title metadata in examples. |
| `--venues security sp` | Include only those venues. |
| `--year 2013` | Include only one publication year. |
| `--year-from 2013 --year-to 2022` | Include a publication-year range. |
| `--limit-files 50` | After applying venue/year filters, scan or index the first 50 sorted text files/documents. This is not random sampling. |
| `--examples 20` | Print at most 20 matching sentence examples. |
| `--case-sensitive` | Match exact letter case. |
| `--json` | Print machine-readable JSON. |
| `--substring-search` | For `lookup-db`, scan every filtered DB document instead of narrowing the search with FTS. |

### Output Fields

| Field | Meaning |
| --- | --- |
| `files_scanned` | Number of text files or DB documents included after filters and `--limit-files`. |
| `files_matched` | Number of scanned files/documents that contain at least one match. |
| `sentences` | Number of matching sentences. |
| `occurrences` | Total number of expression matches. A sentence can contain more than one occurrence. |
| `tokens` | Total token count across scanned files/documents. |
| `per_million_tokens` | `occurrences / tokens * 1,000,000`. |
| `examples` | Matching sentence examples, up to the `--examples` limit. |

Increase `--examples` to print more matching sentences:

```bash
paper-vocab lookup "in the wild" \
  --corpus-dir data/corpus/text \
  --manifest-db data/sample_2013/paper_collect.sqlite \
  --year 2013 \
  --limit-files 50 \
  --examples 50
```

Use JSON output when another script should read the result:

```bash
paper-vocab lookup "side channel" \
  --corpus-dir data/corpus/text \
  --year 2013 \
  --limit-files 50 \
  --json
```

## Example Data

The 2013 text data built with the commands above has this size:

```text
year: 2013
papers: 50
venues: security 45, sp 5
pdf size: 111 MB
text size: 3.8 MB
```

Example lookup results over that text data:

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

## TODO

- [ ] Add richer DB metadata, e.g., authors, DOI, venue, year, title, and source PDF URL.
- [ ] Add normalized lookup text for PDF line-break hyphenation.
