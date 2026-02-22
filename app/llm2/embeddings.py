from typing import Annotated

import openai

from iafisher_foundation import tabular, timehelper
from iafisher_foundation.prelude import *
from lib import command, obsidian, pdb, secrets


def main_create_obsidian_journal(
    *,
    recreate: Annotated[
        bool,
        command.Extra(help="Recreate existing embeddings. (default is to skip them)"),
    ] = False,
) -> None:
    set_openai_api_key()

    vault = obsidian.Vault.main()
    with pdb.connect() as db:
        existing_documents = fetch_documents(db)
        for journal_path in sorted(list_journal_paths(vault), reverse=True):
            document_name = journal_path.relative_to(vault.path()).as_posix()
            if document_name in existing_documents:
                if recreate:
                    delete_embeddings_for_document(db, document_name)
                else:
                    continue

            document = obsidian.Document.from_path(journal_path)
            entries = list(obsidian.journal.entries(document))
            print(f"==> {journal_path} ({pluralize(len(entries), 'entry', 'entries')})")
            chunks_to_insert: List[Dict[str, Any]] = []
            document_name = journal_path.relative_to(vault.path()).as_posix()
            document_id = insert_document(
                db, name=document_name, category="obsidian_journal"
            )
            with timehelper.print_time("calculate_embedding"):
                for entry in entries:
                    contents = entry.section.content()
                    embedding = calculate_embedding(contents)
                    chunks_to_insert.append(
                        dict(
                            document_id=document_id,
                            chunk_title=entry.title,
                            chunk_content=contents,
                            embedding=embedding,
                        )
                    )

            with timehelper.print_time("insert_rows"):
                insert_chunks(db, chunks_to_insert)


def fetch_documents(db: pdb.Connection) -> Set[str]:
    rows = db.fetch_all(
        "SELECT DISTINCT(document_name) FROM llm_embedding_documents", t=pdb.tuple_row
    )
    return set(row[0] for row in rows)


def delete_embeddings_for_document(db: pdb.Connection, document_name: str) -> None:
    db.execute(
        "DELETE FROM llm_embedding_documents WHERE document_name = %s", (document_name,)
    )


def list_journal_paths(vault: obsidian.Vault) -> Generator[pathlib.Path, None, None]:
    yield from vault.glob("**/*[0-9]-journal.md")
    for p in vault.glob("**/[0-9][0-9][0-9][0-9]-[0-9][0-9].md"):
        if p.stem >= "2024-06":
            yield p


def calculate_embedding(content: str) -> List[float]:
    response = openai.embeddings.create(input=[content], model="text-embedding-3-small")
    return response.data[0].embedding


def insert_document(db: pdb.Connection, *, name: str, category: str) -> int:
    return db.fetch_one(
        """
        INSERT INTO llm_embedding_documents (document_name, document_category, time_created)
        VALUES (%(name)s, %(category)s, %(time_created)s)
        RETURNING document_id
        """,
        dict(name=name, category=category, time_created=timehelper.now()),
        t=pdb.tuple_row,
    )[0]


def insert_chunks(db: pdb.Connection, chunks_to_insert: List[Dict[str, Any]]) -> None:
    db.execute_many(
        """
        INSERT INTO llm_embedding_chunks (document, chunk_title, chunk_content, embedding)
        VALUES (%(document_id)s, %(chunk_title)s, %(chunk_content)s, %(embedding)s)
        """,
        chunks_to_insert,
    )


def main_search(words: List[str], *, limit: int = 5) -> None:
    set_openai_api_key()

    query = " ".join(words)
    query_embedding = calculate_embedding(query)
    with pdb.connect() as db:
        results = search_embeddings(db, query_embedding, limit=limit)
        table = tabular.Table()
        table.header(["name", "category", "title", "similarity"])
        for name, category, title, similarity in results:
            table.row([name, category, title, f"{similarity:.3f}"])
        table.flush()


def search_embeddings(
    db: pdb.Connection, query_embedding: List[float], *, limit: int
) -> List[Tuple[str, str, str, float]]:
    return db.fetch_all(
        """
        SELECT document_name, document_category, chunk_title, 1 - (embedding <=> %(embedding)s::vector) AS similarity
        FROM llm_embedding_chunks chunks
        JOIN llm_embedding_documents documents ON chunks.document = documents.document_id
        ORDER BY similarity DESC
        LIMIT %(limit)s
        """,
        dict(embedding=query_embedding, limit=limit),
        t=pdb.tuple_row,
    )


def set_openai_api_key() -> None:
    os.environ["OPENAI_API_KEY"] = secrets.get_or_raise("OPENAI_API_KEY")


cmd = command.Group(help="Work with text embeddings.")
create_cmd = command.Group(help="Create new embeddings.")
create_cmd.add2(
    "obsidian-journal",
    main_create_obsidian_journal,
    help="Create embeddings from my Obsidian journal files",
)
cmd.add("create", create_cmd)
cmd.add2("search", main_search, help="Search the embeddings database.")
