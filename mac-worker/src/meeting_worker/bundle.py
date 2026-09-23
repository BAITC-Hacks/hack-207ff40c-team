"""One export contract for initial inference and reviewed revisions."""
from pathlib import Path
import os

from .exports import export_csv, export_docx, export_ics, export_json, export_pdf


def write_exports(directory: Path, protocol, transcript, font_path=None) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    paths = {kind: directory / ("meeting." + kind) for kind in ("json", "csv", "pdf", "docx", "ics")}
    export_json(paths["json"], protocol, transcript)
    export_csv(paths["csv"], protocol)
    export_pdf(paths["pdf"], protocol, font_path=font_path, transcript=transcript)
    export_docx(paths["docx"], protocol, transcript=transcript)
    export_ics(paths["ics"], protocol)
    for path in paths.values():
        path.chmod(0o600)
        with path.open("rb") as stream:
            os.fsync(stream.fileno())
    sync_directory(directory)
    sync_directory(directory.parent)
    return {kind: str(path) for kind, path in paths.items()}


def sync_directory(path: Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
