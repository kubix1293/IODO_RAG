from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from iodo_rag.config import get_settings
from iodo_rag.ingest import ingest_path
from iodo_rag.search import search as run_search

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def ingest(path: Path) -> None:
    """Import a PDF or DOCX file, generate embeddings, and store chunks in Postgres."""
    settings = get_settings()
    paths = sorted(path.rglob("*")) if path.is_dir() else [path]
    supported = [item for item in paths if item.suffix.lower() in {".pdf", ".docx"}]
    if not supported:
        raise typer.BadParameter("No supported .pdf or .docx files found")

    for item in supported:
        document_id, chunk_count = ingest_path(item, settings)
        console.print(f"[green]Imported[/green] {item} as document {document_id} ({chunk_count} chunks)")


@app.command()
def search(query: str, limit: int = 5) -> None:
    """Run hybrid vector and full-text search."""
    settings = get_settings()
    rows = run_search(query, settings, limit=limit)

    table = Table(title=f"Results for: {query}")
    table.add_column("Score")
    table.add_column("Source")
    table.add_column("Ref")
    table.add_column("Excerpt")

    for row in rows:
        ref = " ".join(
            str(value)
            for value in [row.get("section"), row.get("article"), row.get("paragraph")]
            if value
        )
        excerpt = str(row["chunk_text"]).replace("\n", " ")[:280]
        table.add_row(
            f"{float(row['hybrid_score']):.4f}",
            str(row["source_file"]),
            ref,
            excerpt,
        )

    console.print(table)


if __name__ == "__main__":
    app()
