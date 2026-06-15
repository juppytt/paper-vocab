# paper-vocab

Vocabulary lookup over paper text corpora.

This repo starts with an `rg`-based workflow. Raw text files are the corpus, and
the lookup command scans those files to report how often an expression appears
and which sentences use it.

Expected corpus layout:

```text
data/corpus/text/
  ccs/
    2013/
      paper-a.txt
  sp/
    2013/
      paper-b.txt
```

Run a 2013 50-paper sample:

```bash
PYTHONPATH=src python3 -m paper_vocab.cli lookup "in the wild" \
  --corpus-dir data/corpus/text \
  --year 2013 \
  --limit-files 50 \
  --examples 20
```

If the text files came from `paper-collect`, pass its SQLite DB to show paper
metadata next to sentence examples:

```bash
PYTHONPATH=src python3 -m paper_vocab.cli lookup "in the wild" \
  --corpus-dir data/corpus/text \
  --manifest-db ../paper-collect/data/paper_collect.sqlite \
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

This is intentionally not a database yet. The text corpus should remain the
canonical source; a SQLite/FTS index can be built later when repeated lookups
need to be faster or richer.
