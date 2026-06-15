from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from paper_vocab.lookup import lookup_expression, split_sentences, venue_year_from_path


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


def make_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
