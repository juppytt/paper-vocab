from __future__ import annotations

import io
import json
import tempfile
import shutil
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from paper_vocab.lookup import (
    LookupResult,
    MatchExample,
    PaperMeta,
    lookup_expression,
    print_text_result,
    run,
    split_sentences,
    venue_year_from_path,
)
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

    def test_db_lookup_fts_matches_substring_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = root / "text"
            make_text(corpus / "ccs" / "2013" / "a.txt", "Side channel attacks appear here.")
            make_text(corpus / "ccs" / "2013" / "b.txt", "This paper studies cryptographic protocols.")
            db_path = root / "paper_vocab.sqlite"

            build_vocab_db(db_path=db_path, corpus_dir=corpus)
            fts_result = lookup_db_expression("side channel", db_path=db_path, year=2013, max_examples=10)
            substring_result = lookup_db_expression(
                "side channel",
                db_path=db_path,
                year=2013,
                max_examples=10,
                substring_search=True,
            )

        self.assertEqual(fts_result.to_dict(), substring_result.to_dict())
        self.assertEqual(fts_result.files_scanned, 2)
        self.assertEqual(fts_result.files_matched, 1)

    def test_db_lookup_limit_applies_before_fts_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = root / "text"
            make_text(corpus / "ccs" / "2013" / "a.txt", "This paper studies cryptographic protocols.")
            make_text(corpus / "ccs" / "2013" / "z.txt", "Side channel attacks appear here.")
            db_path = root / "paper_vocab.sqlite"

            build_vocab_db(db_path=db_path, corpus_dir=corpus)
            result = lookup_db_expression("side channel", db_path=db_path, year=2013, limit_files=1)

        self.assertEqual(result.files_scanned, 1)
        self.assertEqual(result.files_matched, 0)
        self.assertEqual(result.occurrence_count, 0)

    def test_db_lookup_fts_keeps_final_token_prefix_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = root / "text"
            make_text(corpus / "ccs" / "2013" / "a.txt", "The value appears in the wildcard table.")
            make_text(corpus / "ccs" / "2013" / "b.txt", "This paper studies cryptographic protocols.")
            db_path = root / "paper_vocab.sqlite"

            build_vocab_db(db_path=db_path, corpus_dir=corpus)
            fts_result = lookup_db_expression("in the wild", db_path=db_path, year=2013, max_examples=10)
            substring_result = lookup_db_expression(
                "in the wild",
                db_path=db_path,
                year=2013,
                max_examples=10,
                substring_search=True,
            )

        self.assertEqual(fts_result.to_dict(), substring_result.to_dict())
        self.assertEqual(fts_result.files_matched, 1)

    def test_lookup_db_cli_substring_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = root / "text"
            make_text(corpus / "ccs" / "2013" / "a.txt", "The value appears in the wildcard table.")
            db_path = root / "paper_vocab.sqlite"
            build_vocab_db(db_path=db_path, corpus_dir=corpus)

            output = io.StringIO()
            with redirect_stdout(output):
                status = run(
                    [
                        "lookup-db",
                        "in the wild",
                        "--db",
                        str(db_path),
                        "--year",
                        "2013",
                        "--examples",
                        "0",
                        "--substring-search",
                        "--json",
                    ]
                )

        result = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(result["files_matched"], 1)

    def test_text_output_pretty_prints_examples(self) -> None:
        result = LookupResult(
            expression="in the wild",
            files_scanned=1,
            files_matched=1,
            sentence_count=2,
            occurrence_count=3,
            token_count=20,
            per_million_tokens=100000.0,
            examples=[
                MatchExample(
                    path="/tmp/text/ccs/2013/example.txt",
                    sentence=(
                        "We evaluate this system in the wild because deployments in the wild "
                        "exercise failure modes that short tests miss."
                    ),
                    count=2,
                    metadata=PaperMeta(venue="ccs", year=2013, title="A Study of Deployed Systems"),
                ),
                MatchExample(
                    path="/tmp/text/ccs/2013/example.txt",
                    sentence="In the wild, the same assumptions often fail differently.",
                    count=1,
                    metadata=PaperMeta(venue="ccs", year=2013, title="A Study of Deployed Systems"),
                ),
            ],
        )

        output = io.StringIO()
        with mock.patch("paper_vocab.lookup.output_width", return_value=72), redirect_stdout(output):
            print_text_result(result)

        text = output.getvalue()
        self.assertIn("Lookup\n------\n", text)
        self.assertIn("files scanned  1\n", text)
        self.assertIn("per million    100,000.000\n", text)
        self.assertIn("Examples\n--------\n", text)
        self.assertIn("showing 2 (total: 2, sources: 1)\n", text)
        self.assertEqual(text.count("1. [ccs 2013] A Study of Deployed Systems\n"), 1)
        self.assertIn("   - We evaluate this system in the wild because deployments in the wild\n", text)
        self.assertIn("     exercise failure modes that short tests miss.\n", text)
        self.assertIn("     matches: 2\n", text)
        self.assertIn("   - In the wild, the same assumptions often fail differently.\n", text)


def make_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
