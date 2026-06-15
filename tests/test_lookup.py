from __future__ import annotations

import tempfile
import shutil
import unittest
from pathlib import Path
from unittest import mock

from paper_vocab.lookup import lookup_expression, split_sentences, venue_year_from_path
from paper_vocab.vocab_db import build_vocab_db, lookup_db_expression


class LookupTests(unittest.TestCase):
    def test_lookup_counts_files_occurrences_and_examples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "text"
            make_text(corpus / "ccs" / "2013" / "a.txt", "We evaluate this system in the wild. In the wild, failures happen.")
            make_text(corpus / "ccs" / "2013" / "b.txt", "This paper studies cryptographic protocols.")
            make_text(corpus / "sp" / "2014" / "c.txt", "In the wild deployments are noisy.")

            with mock.patch("paper_vocab.lookup.rg_candidate_files", return_value=None):
                result = lookup_expression(
                    "in the wild",
                    corpus_dir=corpus,
                    year=2013,
                    limit_files=50,
                    max_examples=10,
                )

        self.assertEqual(result.files_scanned, 2)
        self.assertEqual(result.files_matched, 1)
        self.assertEqual(result.sentence_count, 2)
        self.assertEqual(result.occurrence_count, 2)
        self.assertEqual(len(result.examples), 2)

    def test_venue_year_from_path(self) -> None:
        corpus = Path("/tmp/corpus")
        venue, year = venue_year_from_path(corpus / "ccs" / "2013" / "paper.txt", corpus)

        self.assertEqual(venue, "ccs")
        self.assertEqual(year, 2013)

    def test_split_sentences_keeps_sentence_text(self) -> None:
        self.assertEqual(split_sentences("One sentence. Another sentence? Final."), ["One sentence.", "Another sentence?", "Final."])

    @unittest.skipIf(shutil.which("rg") is None, "rg required")
    def test_lookup_follows_symlink_corpus_root_with_rg(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = root / "real-text"
            make_text(corpus / "ccs" / "2013" / "a.txt", "Side channel attacks appear here.")
            link = root / "linked-text"
            link.symlink_to(corpus, target_is_directory=True)

            result = lookup_expression("side channel", corpus_dir=link, year=2013, max_examples=10)

        self.assertEqual(result.files_scanned, 1)
        self.assertEqual(result.files_matched, 1)
        self.assertEqual(result.occurrence_count, 1)

    def test_phrase_lookup_matches_flexible_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "text"
            make_text(corpus / "ccs" / "2013" / "a.txt", "Side\nchannel attacks appear here.")

            result = lookup_expression("side channel", corpus_dir=corpus, year=2013, max_examples=10)

        self.assertEqual(result.files_scanned, 1)
        self.assertEqual(result.files_matched, 1)
        self.assertEqual(result.occurrence_count, 1)

    def test_build_and_lookup_vocab_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = root / "text"
            make_text(corpus / "ccs" / "2013" / "a.txt", "We evaluate this system in the wild. In the wild, failures happen.")
            make_text(corpus / "ccs" / "2014" / "b.txt", "This paper studies cryptographic protocols.")
            db_path = root / "paper_vocab.sqlite"

            build_result = build_vocab_db(db_path=db_path, corpus_dir=corpus, year_from=2013, year_to=2014)
            lookup_result = lookup_db_expression("in the wild", db_path=db_path, year=2013, max_examples=10)

        self.assertEqual(build_result.files_indexed, 2)
        self.assertEqual(lookup_result.files_scanned, 1)
        self.assertEqual(lookup_result.files_matched, 1)
        self.assertEqual(lookup_result.sentence_count, 2)
        self.assertEqual(lookup_result.occurrence_count, 2)


def make_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
