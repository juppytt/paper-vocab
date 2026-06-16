from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .lookup import (
    LookupResult,
    MatchExample,
    PaperMeta,
    clean_sentence,
    count_tokens,
    expression_pattern,
    load_manifest_metadata,
    metadata_for_path,
    select_text_files,
    split_sentences,
    venue_year_from_path,
)


SCHEMA = """
create table if not exists documents (
    id integer primary key,
    path text not null unique,
    venue text,
    year integer,
    title text,
    doi text,
    token_count integer not null,
    text text not null,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create virtual table if not exists documents_fts using fts5(
    title,
    text,
    content='documents',
    content_rowid='id',
    tokenize='unicode61'
);

create table if not exists metadata (
    key text primary key,
    value text not null
);
"""


@dataclass(frozen=True)
class BuildDbResult:
    db_path: Path
    files_indexed: int
    token_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "db_path": str(self.db_path),
            "files_indexed": self.files_indexed,
            "token_count": self.token_count,
        }


@dataclass(frozen=True)
class DocumentRow:
    id: int
    path: str
    venue: str | None
    year: int | None
    title: str | None
    doi: str | None
    token_count: int
    text: str

    @property
    def metadata(self) -> PaperMeta:
        return PaperMeta(venue=self.venue, year=self.year, title=self.title, doi=self.doi)


def build_vocab_db(
    *,
    db_path: Path,
    corpus_dir: Path,
    manifest_db: Path | None = None,
    venues: set[str] | None = None,
    year: int | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    limit_files: int | None = None,
    force: bool = False,
) -> BuildDbResult:
    if force:
        remove_sqlite_files(db_path)

    files = select_text_files(
        corpus_dir,
        venues=venues,
        year=year,
        year_from=year_from,
        year_to=year_to,
        limit_files=limit_files,
    )
    metadata = load_manifest_metadata(manifest_db) if manifest_db else {}

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as conn:
        init_db(conn)
        conn.execute("delete from documents_fts")
        conn.execute("delete from documents")

        total_tokens = 0
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            token_count = count_tokens(text)
            total_tokens += token_count
            parsed_venue, parsed_year = venue_year_from_path(path, corpus_dir)
            meta = metadata_for_path(path, metadata)
            venue = meta.venue or parsed_venue
            doc_year = meta.year or parsed_year
            cursor = conn.execute(
                """
                insert into documents (path, venue, year, title, doi, token_count, text)
                values (:path, :venue, :year, :title, :doi, :token_count, :text)
                """,
                {
                    "path": str(path),
                    "venue": venue,
                    "year": doc_year,
                    "title": meta.title,
                    "doi": meta.doi,
                    "token_count": token_count,
                    "text": text,
                },
            )
            conn.execute(
                "insert into documents_fts (rowid, title, text) values (?, ?, ?)",
                (cursor.lastrowid, meta.title or "", text),
            )

        conn.execute(
            """
            insert into metadata (key, value)
            values ('source_corpus_dir', :source_corpus_dir)
            on conflict(key) do update set value = excluded.value
            """,
            {"source_corpus_dir": str(corpus_dir)},
        )
        conn.execute(
            """
            insert into metadata (key, value)
            values ('files_indexed', :files_indexed)
            on conflict(key) do update set value = excluded.value
            """,
            {"files_indexed": str(len(files))},
        )
        conn.commit()

    return BuildDbResult(db_path=db_path, files_indexed=len(files), token_count=total_tokens)


def lookup_db_expression(
    expression: str,
    *,
    db_path: Path,
    venues: set[str] | None = None,
    year: int | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    limit_files: int | None = None,
    max_examples: int = 20,
    ignore_case: bool = True,
    substring_search: bool = False,
) -> LookupResult:
    pattern = expression_pattern(expression, ignore_case=ignore_case)

    with closing(sqlite3.connect(db_path)) as conn:
        files_scanned, token_count = select_document_stats(
            conn,
            venues=venues,
            year=year,
            year_from=year_from,
            year_to=year_to,
            limit_files=limit_files,
        )
        candidate_ids = None if substring_search else fts_candidate_ids(conn, expression)
        rows = select_documents(
            conn,
            venues=venues,
            year=year,
            year_from=year_from,
            year_to=year_to,
            limit_files=limit_files,
            candidate_ids=candidate_ids,
        )

    files_matched = 0
    sentence_count = 0
    occurrence_count = 0
    examples: list[MatchExample] = []

    for row in rows:
        file_occurrences = 0
        for sentence in split_sentences(row.text):
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
                        path=row.path,
                        sentence=clean_sentence(sentence),
                        count=count,
                        metadata=row.metadata,
                    )
                )
        if file_occurrences:
            files_matched += 1

    per_million_tokens = (occurrence_count / token_count * 1_000_000) if token_count else 0.0
    return LookupResult(
        expression=expression,
        files_scanned=files_scanned,
        files_matched=files_matched,
        sentence_count=sentence_count,
        occurrence_count=occurrence_count,
        token_count=token_count,
        per_million_tokens=per_million_tokens,
        examples=examples,
    )


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def select_documents(
    conn: sqlite3.Connection,
    *,
    venues: set[str] | None,
    year: int | None,
    year_from: int | None,
    year_to: int | None,
    limit_files: int | None,
    candidate_ids: set[int] | None = None,
) -> list[DocumentRow]:
    if candidate_ids is not None and not candidate_ids:
        return []

    where, params = document_filter_sql(venues=venues, year=year, year_from=year_from, year_to=year_to)
    limit = "limit :limit" if limit_files is not None else ""
    if limit_files is not None:
        params["limit"] = limit_files

    candidate_where = ""
    if candidate_ids is not None:
        placeholders = []
        for index, document_id in enumerate(sorted(candidate_ids)):
            key = f"candidate_{index}"
            placeholders.append(f":{key}")
            params[key] = document_id
        candidate_where = f"where id in ({', '.join(placeholders)})"

    sql = f"""
        with filtered as (
            select id, path, venue, year, title, doi, token_count, text
            from documents
            {where}
            order by path
            {limit}
        )
        select id, path, venue, year, title, doi, token_count, text
        from filtered
        {candidate_where}
        order by path
    """

    return [document_from_row(row) for row in conn.execute(sql, params).fetchall()]


def select_document_stats(
    conn: sqlite3.Connection,
    *,
    venues: set[str] | None,
    year: int | None,
    year_from: int | None,
    year_to: int | None,
    limit_files: int | None,
) -> tuple[int, int]:
    where, params = document_filter_sql(venues=venues, year=year, year_from=year_from, year_to=year_to)
    limit = "limit :limit" if limit_files is not None else ""
    if limit_files is not None:
        params["limit"] = limit_files

    row = conn.execute(
        f"""
        with filtered as (
            select token_count
            from documents
            {where}
            order by path
            {limit}
        )
        select count(*), coalesce(sum(token_count), 0)
        from filtered
        """,
        params,
    ).fetchone()
    return int(row[0]), int(row[1])


def document_filter_sql(
    *,
    venues: set[str] | None,
    year: int | None,
    year_from: int | None,
    year_to: int | None,
) -> tuple[str, dict[str, object]]:
    clauses: list[str] = []
    params: dict[str, object] = {}

    if venues:
        placeholders = []
        for index, venue in enumerate(sorted(venues)):
            key = f"venue_{index}"
            placeholders.append(f":{key}")
            params[key] = venue
        clauses.append(f"venue in ({', '.join(placeholders)})")
    if year is not None:
        clauses.append("year = :year")
        params["year"] = year
    if year_from is not None:
        clauses.append("year >= :year_from")
        params["year_from"] = year_from
    if year_to is not None:
        clauses.append("year <= :year_to")
        params["year_to"] = year_to

    where = "where " + " and ".join(clauses) if clauses else ""
    return where, params


def fts_candidate_ids(conn: sqlite3.Connection, expression: str) -> set[int] | None:
    try:
        rows = conn.execute(
            "select rowid from documents_fts where documents_fts match ?",
            (fts_phrase_query(expression),),
        ).fetchall()
    except sqlite3.DatabaseError:
        return None
    return {int(row[0]) for row in rows}


def fts_phrase_query(expression: str) -> str:
    # Prefix the final token so FTS narrowing keeps matches like "wildcard".
    return f'"{expression.strip().replace(chr(34), chr(34) + chr(34))}"*'


def document_from_row(row: sqlite3.Row | tuple[object, ...]) -> DocumentRow:
    return DocumentRow(
        id=int(row[0]),
        path=str(row[1]),
        venue=str(row[2]) if row[2] else None,
        year=int(row[3]) if row[3] is not None else None,
        title=str(row[4]) if row[4] else None,
        doi=str(row[5]) if row[5] else None,
        token_count=int(row[6]),
        text=str(row[7]),
    )


def remove_sqlite_files(db_path: Path) -> None:
    for path in (db_path, db_path.with_name(f"{db_path.name}-wal"), db_path.with_name(f"{db_path.name}-shm")):
        if path.exists():
            path.unlink()
