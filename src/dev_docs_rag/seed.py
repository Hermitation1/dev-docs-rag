"""Seed the demo documentation sources: FastAPI and Pydantic."""

from .services.fetch import fetch_git_source
from .worker.tasks import index_file

SOURCES = (
    {
        "library": "fastapi",
        "version": "master",
        "git_url": "https://github.com/tiangolo/fastapi",
        "ref": "master",
        "docs_dir": "docs/en/docs",
        "license": "MIT",
    },
    {
        "library": "pydantic",
        "version": "main",
        "git_url": "https://github.com/pydantic/pydantic",
        "ref": "main",
        "docs_dir": "docs",
        "license": "MIT",
    },
)


def main() -> None:
    """Clone the demo repositories, copy their docs and queue every file."""
    total = 0
    for item in SOURCES:
        copied = fetch_git_source(
            library=item["library"],
            version=item["version"],
            git_url=item["git_url"],
            ref=item["ref"],
            docs_dir=item["docs_dir"],
            license_id=item["license"],
        )
        for relative in copied:
            index_file.delay(relative)
        print(f"{item['library']} {item['version']}: queued {len(copied)} file(s)")
        total += len(copied)
    print(f"queued {total} file(s); the worker will index them")


if __name__ == "__main__":
    main()
