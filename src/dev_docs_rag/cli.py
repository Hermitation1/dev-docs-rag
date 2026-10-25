"""Owner CLI: ingest into the knowledge directory and reindex it."""

import argparse
from pathlib import Path

from .services.fetch import fetch_git_source
from .services.knowledge import add_local_source, iter_documents
from .worker.tasks import index_file


def main() -> None:
    """Entry point for the ``devdocs`` command."""
    parser = argparse.ArgumentParser(prog="devdocs", description="Dev-Docs RAG owner CLI")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="add documentation to the knowledge directory")
    actions = ingest.add_subparsers(dest="action", required=True)

    add = actions.add_parser("add", help="copy markdown files from a local directory")
    add.add_argument("--library")
    add.add_argument("--version")
    add.add_argument("--project")
    add.add_argument("--source", required=True, type=Path)
    add.add_argument("--docs-dir")
    add.add_argument("--license", default="unknown")
    add.add_argument("--source-url")

    fetch = actions.add_parser("fetch", help="clone a git repository and add its markdown docs")
    fetch.add_argument("--library")
    fetch.add_argument("--version")
    fetch.add_argument("--project")
    fetch.add_argument("--git-url", required=True)
    fetch.add_argument("--ref", default="main")
    fetch.add_argument("--docs-dir")
    fetch.add_argument("--license", default="unknown")

    commands.add_parser("reindex", help="enqueue every knowledge document")

    args = parser.parse_args()
    if args.command == "ingest" and args.action == "add":
        _ingest_add(args)
    elif args.command == "ingest" and args.action == "fetch":
        _ingest_fetch(args)
    elif args.command == "reindex":
        _reindex()


def _ingest_add(args: argparse.Namespace) -> None:
    library, version = _identity(args)
    _copy_and_queue(
        library=library,
        version=version,
        project=args.project,
        source=args.source,
        docs_dir=args.docs_dir,
        license_id=args.license,
        source_url=args.source_url,
    )


def _identity(args: argparse.Namespace) -> tuple[str, str]:
    library = args.library or args.project
    version = args.version or ("current" if args.project else None)
    if not library or not version:
        raise SystemExit("error: --library and --version are required without --project")
    return library, version


def _ingest_fetch(args: argparse.Namespace) -> None:
    library, version = _identity(args)
    try:
        copied = fetch_git_source(
            library=library,
            version=version,
            project=args.project,
            git_url=args.git_url,
            ref=args.ref,
            docs_dir=args.docs_dir,
            license_id=args.license,
        )
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from exc
    _queue_files(copied, library=library, version=version)


def _copy_and_queue(
    *,
    library: str,
    version: str,
    project: str | None,
    source: Path,
    docs_dir: str | None,
    license_id: str,
    source_url: str | None,
) -> None:
    try:
        copied = add_local_source(
            library=library,
            version=version,
            project=project,
            source=source,
            docs_dir=docs_dir,
            license_id=license_id,
            source_url=source_url,
        )
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from exc

    _queue_files(copied, library=library, version=version)


def _queue_files(copied: list[str], *, library: str, version: str) -> None:
    for relative in copied:
        index_file.delay(relative)
        print(f"queued {relative}")
    print(f"queued {len(copied)} file(s) for {library} {version}")


def _reindex() -> None:
    documents = iter_documents()
    for relative in documents:
        index_file.delay(relative)
        print(f"queued {relative}")
    print(f"queued {len(documents)} file(s)")
