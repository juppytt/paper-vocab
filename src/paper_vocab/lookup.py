from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
WHITESPACE_RE = re.compile(r"\s+")
WORD_RE = re.compile(r"\b[\w-]+\b", re.UNICODE)


@dataclass(frozen=True)
class PaperMeta:
    venue: str | None = None
    year: int | None = None
    title: str | None = None
    doi: str | None = None


@dataclass(frozen=True)
class MatchExample:
    path: str
    sentence: str
    count: int
    metadata: PaperMeta

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "sentence": self.sentence,
            "count": self.count,
            "venue": self.metadata.venue,
            "year": self.metadata.year,
            "title": self.metadata.title,
            "doi": self.metadata.doi,
        }


@dataclass(frozen=True)
class LookupResult:
    expression: str
    files_scanned: int
    files_matched: int
    sentence_count: int
    occurrence_count: int
    token_count: int
    per_million_tokens: float
    examples: list[MatchExample]

    def to_dict(self) -> dict[str, object]:
        return {
            "expression": self.expression,
            "files_scanned": self.files_scanned,
            "files_matched": self.files_matched,
            "sentence_count": self.sentence_count,
            "occurrence_count": self.occurrence_count,
            "token_count": self.token_count,
            "per_million_tokens": self.per_million_tokens,
            "examples": [example.to_dict() for example in self.examples],
        }


def lookup_expression(
    expression: str,
    *,
    corpus_dir: Path,
    manifest_db: Path | None = None,
    venues: set[str] | None = None,
    year: int | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    limit_files: int | None = None,
    max_examples: int = 20,
    ignore_case: bool = True,
) -> LookupResult:
    files = select_text_files(
        corpus_dir,
        venues=venues,
        year=year,
        year_from=year_from,
        year_to=year_to,
        limit_files=limit_files,
    )
    candidate_files = None if expression_uses_flexible_whitespace(expression) else rg_candidate_files(
        corpus_dir,
        expression,
        ignore_case=ignore_case,
    )
    metadata = load_manifest_metadata(manifest_db) if manifest_db else {}
    pattern = expression_pattern(expression, ignore_case=ignore_case)

    files_matched = 0
    sentence_count = 0
    occurrence_count = 0
    token_count = 0
    examples: list[MatchExample] = []

    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        token_count += count_tokens(text)
        if candidate_files is not None and path not in candidate_files:
            continue
        file_occurrences = 0
        for sentence in split_sentences(text):
            matches = pattern.findall(sentence)
            if not matches:
                continue
            count = len(matches)
            file_occurrences += count
            sentence_count += 1
            occurrence_count += count
            if len(examples) < max_examples:
                examples.append(
                    MatchExample(
                        path=str(path),
                        sentence=clean_sentence(sentence),
                        count=count,
                        metadata=metadata_for_path(path, metadata),
                    )
                )
        if file_occurrences:
            files_matched += 1

    per_million_tokens = (occurrence_count / token_count * 1_000_000) if token_count else 0.0
    return LookupResult(
        expression=expression,
        files_scanned=len(files),
        files_matched=files_matched,
        sentence_count=sentence_count,
        occurrence_count=occurrence_count,
        token_count=token_count,
        per_million_tokens=per_million_tokens,
        examples=examples,
    )


def select_text_files(
    corpus_dir: Path,
    *,
    venues: set[str] | None,
    year: int | None,
    year_from: int | None,
    year_to: int | None,
    limit_files: int | None,
) -> list[Path]:
    corpus_root = corpus_dir.resolve() if corpus_dir.is_symlink() else corpus_dir
    files = [
        path
        for path in sorted(corpus_root.rglob("*.txt"))
        if path_matches_filters(path, corpus_root, venues=venues, year=year, year_from=year_from, year_to=year_to)
    ]
    if limit_files is not None:
        files = files[:limit_files]
    return files


def rg_candidate_files(corpus_dir: Path, expression: str, *, ignore_case: bool) -> set[Path] | None:
    rg = shutil.which("rg")
    if rg is None:
        return None
    corpus_root = corpus_dir.resolve() if corpus_dir.is_symlink() else corpus_dir
    command = [rg, "--files-with-matches", "--fixed-strings", "--glob", "*.txt"]
    if ignore_case:
        command.append("--ignore-case")
    command.extend([expression, str(corpus_root)])
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode not in (0, 1):
        raise RuntimeError(completed.stderr.strip() or "rg failed")
    if completed.returncode == 1:
        return set()
    return {Path(line.strip()) for line in completed.stdout.splitlines() if line.strip()}


def path_matches_filters(
    path: Path,
    corpus_dir: Path,
    *,
    venues: set[str] | None,
    year: int | None,
    year_from: int | None,
    year_to: int | None,
) -> bool:
    parsed_venue, parsed_year = venue_year_from_path(path, corpus_dir)
    if venues and parsed_venue not in venues:
        return False
    if year is not None and parsed_year != year:
        return False
    if year_from is not None and (parsed_year is None or parsed_year < year_from):
        return False
    if year_to is not None and (parsed_year is None or parsed_year > year_to):
        return False
    return True


def venue_year_from_path(path: Path, corpus_dir: Path) -> tuple[str | None, int | None]:
    try:
        parts = path.relative_to(corpus_dir).parts
    except ValueError:
        parts = path.parts
    for index, part in enumerate(parts[:-1]):
        if part.isdigit() and len(part) == 4:
            venue = parts[index - 1] if index > 0 else None
            return venue, int(part)
    return None, None


def expression_pattern(expression: str, *, ignore_case: bool) -> re.Pattern[str]:
    flags = re.IGNORECASE if ignore_case else 0
    escaped = re.escape(expression.strip())
    escaped = escaped.replace(r"\ ", r"\s+")
    return re.compile(escaped, flags)


def expression_uses_flexible_whitespace(expression: str) -> bool:
    return bool(re.search(r"\s", expression.strip()))


def split_sentences(text: str) -> list[str]:
    normalized = WHITESPACE_RE.sub(" ", text.replace("\n", " ")).strip()
    if not normalized:
        return []
    return [part.strip() for part in SENTENCE_BOUNDARY_RE.split(normalized) if part.strip()]


def clean_sentence(sentence: str) -> str:
    return WHITESPACE_RE.sub(" ", sentence).strip()


def count_tokens(text: str) -> int:
    return len(WORD_RE.findall(text))


def load_manifest_metadata(db_path: Path) -> dict[str, PaperMeta]:
    conn = sqlite3.connect(db_path)
    rows = conn.execute("select venue, year, title, doi, text_path from papers where text_path is not null").fetchall()
    conn.close()
    metadata: dict[str, PaperMeta] = {}
    for venue, year, title, doi, text_path in rows:
        meta = PaperMeta(venue=venue, year=int(year), title=title, doi=doi)
        path = Path(text_path)
        metadata[str(text_path)] = meta
        metadata[str(path)] = meta
        metadata[path.name] = meta
        if len(path.parts) >= 3:
            metadata["/".join(path.parts[-3:])] = meta
    return metadata


def metadata_for_path(path: Path, metadata: dict[str, PaperMeta]) -> PaperMeta:
    suffix = "/".join(path.parts[-3:]) if len(path.parts) >= 3 else None
    return metadata.get(str(path)) or (metadata.get(suffix) if suffix else None) or metadata.get(path.name) or PaperMeta()


def print_text_result(result: LookupResult) -> None:
    print(f"expression: {result.expression}")
    print(f"files_scanned: {result.files_scanned}")
    print(f"files_matched: {result.files_matched}")
    print(f"sentences: {result.sentence_count}")
    print(f"occurrences: {result.occurrence_count}")
    print(f"tokens: {result.token_count}")
    print(f"per_million_tokens: {result.per_million_tokens:.3f}")
    if result.examples:
        print()
        print("examples:")
        for example in result.examples:
            label = example.path
            if example.metadata.title:
                bits = [bit for bit in (example.metadata.venue, str(example.metadata.year), example.metadata.title) if bit]
                label = " | ".join(bits)
            print(f"- {label}")
            print(f"  {example.sentence}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="paper-vocab")
    subparsers = parser.add_subparsers(dest="command", required=True)

    lookup = subparsers.add_parser("lookup", help="Look up expression frequency and example sentences.")
    lookup.add_argument("expression", help="Word or phrase to search.")
    lookup.add_argument("--corpus-dir", type=Path, default=Path("data/corpus/text"), help="Root text corpus directory.")
    lookup.add_argument("--manifest-db", type=Path, default=None, help="Optional paper-collect SQLite DB for metadata.")
    lookup.add_argument("--venues", nargs="+", default=None, help="Venue filters inferred from corpus path.")
    lookup.add_argument("--year", type=int, default=None, help="Exact year filter inferred from corpus path.")
    lookup.add_argument("--year-from", type=int, default=None, help="Inclusive lower year filter.")
    lookup.add_argument("--year-to", type=int, default=None, help="Inclusive upper year filter.")
    lookup.add_argument("--limit-files", type=int, default=None, help="Scan at most this many filtered text files.")
    lookup.add_argument("--examples", type=int, default=20, help="Maximum example sentences.")
    lookup.add_argument("--case-sensitive", action="store_true", help="Use case-sensitive matching.")
    lookup.add_argument("--json", action="store_true", help="Print JSON result.")

    build_db = subparsers.add_parser("build-db", help="Build a SQLite/FTS vocabulary DB from extracted text files.")
    build_db.add_argument("--db", type=Path, default=Path("data/paper_vocab.sqlite"), help="SQLite vocab DB path.")
    build_db.add_argument("--corpus-dir", type=Path, default=Path("data/corpus/text"), help="Root text corpus directory.")
    build_db.add_argument("--manifest-db", type=Path, default=None, help="Optional paper-collect SQLite DB for metadata.")
    build_db.add_argument("--venues", nargs="+", default=None, help="Venue filters inferred from corpus path.")
    build_db.add_argument("--year", type=int, default=None, help="Exact year filter inferred from corpus path.")
    build_db.add_argument("--year-from", type=int, default=None, help="Inclusive lower year filter.")
    build_db.add_argument("--year-to", type=int, default=None, help="Inclusive upper year filter.")
    build_db.add_argument("--limit-files", type=int, default=None, help="Index at most this many filtered text files.")
    build_db.add_argument("--force", action="store_true", help="Replace an existing vocab DB.")
    build_db.add_argument("--json", action="store_true", help="Print JSON result.")

    lookup_db = subparsers.add_parser("lookup-db", help="Look up expression frequency from a SQLite vocab DB.")
    lookup_db.add_argument("expression", help="Word or phrase to search.")
    lookup_db.add_argument("--db", type=Path, default=Path("data/paper_vocab.sqlite"), help="SQLite vocab DB path.")
    lookup_db.add_argument("--venues", nargs="+", default=None, help="Venue filters.")
    lookup_db.add_argument("--year", type=int, default=None, help="Exact year filter.")
    lookup_db.add_argument("--year-from", type=int, default=None, help="Inclusive lower year filter.")
    lookup_db.add_argument("--year-to", type=int, default=None, help="Inclusive upper year filter.")
    lookup_db.add_argument("--limit-files", type=int, default=None, help="Scan at most this many filtered DB documents.")
    lookup_db.add_argument("--examples", type=int, default=20, help="Maximum example sentences.")
    lookup_db.add_argument("--case-sensitive", action="store_true", help="Use case-sensitive matching.")
    lookup_db.add_argument("--json", action="store_true", help="Print JSON result.")
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "lookup":
        result = lookup_expression(
            args.expression,
            corpus_dir=args.corpus_dir,
            manifest_db=args.manifest_db,
            venues=set(args.venues) if args.venues else None,
            year=args.year,
            year_from=args.year_from,
            year_to=args.year_to,
            limit_files=args.limit_files,
            max_examples=args.examples,
            ignore_case=not args.case_sensitive,
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        else:
            print_text_result(result)
        return 0
    if args.command == "build-db":
        from .vocab_db import build_vocab_db

        result = build_vocab_db(
            db_path=args.db,
            corpus_dir=args.corpus_dir,
            manifest_db=args.manifest_db,
            venues=set(args.venues) if args.venues else None,
            year=args.year,
            year_from=args.year_from,
            year_to=args.year_to,
            limit_files=args.limit_files,
            force=args.force,
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        else:
            print(f"db_path: {result.db_path}")
            print(f"files_indexed: {result.files_indexed}")
            print(f"tokens: {result.token_count}")
        return 0
    if args.command == "lookup-db":
        from .vocab_db import lookup_db_expression

        result = lookup_db_expression(
            args.expression,
            db_path=args.db,
            venues=set(args.venues) if args.venues else None,
            year=args.year,
            year_from=args.year_from,
            year_to=args.year_to,
            limit_files=args.limit_files,
            max_examples=args.examples,
            ignore_case=not args.case_sensitive,
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        else:
            print_text_result(result)
        return 0
    raise AssertionError(f"unhandled command: {args.command}")
