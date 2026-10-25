"""Clone a git repository and copy its markdown docs into the knowledge directory."""

import subprocess
import tempfile
from pathlib import Path

from ..config import get_settings
from .knowledge import add_local_source


def fetch_git_source(
    *,
    library: str,
    version: str,
    git_url: str,
    ref: str = "main",
    docs_dir: str | None = None,
    license_id: str = "unknown",
    project: str | None = None,
) -> list[str]:
    """Clone ``git_url`` at ``ref`` and copy its docs, returning knowledge-relative paths."""
    settings = get_settings()
    with tempfile.TemporaryDirectory(prefix="devdocs-fetch-") as tmp:
        checkout = Path(tmp) / "repo"
        command = ["git", "clone", "--depth", "1", "--branch", ref, git_url, str(checkout)]
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=settings.git_clone_timeout_seconds,
            )
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or "").strip()[:500]
            raise ValueError(f"git clone failed: {message}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ValueError(
                f"git clone timed out after {settings.git_clone_timeout_seconds}s"
            ) from exc

        return add_local_source(
            library=library,
            version=version,
            project=project,
            source=checkout,
            docs_dir=docs_dir,
            license_id=license_id,
            source_url=f"{git_url}/blob/{ref}",
        )
