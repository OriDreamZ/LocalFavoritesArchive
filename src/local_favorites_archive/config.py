from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    archive_root: Path = Path("archive")
    host: str = "127.0.0.1"
    port: int = 8765
    max_media_concurrency: int = 2
    lan_enabled: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "archive_root", Path(self.archive_root).expanduser())

    @property
    def db_path(self) -> Path:
        return self.archive_root / "archive.sqlite3"

    @property
    def raw_dir(self) -> Path:
        return self.archive_root / "raw"

    @property
    def media_dir(self) -> Path:
        return self.archive_root / "media"

    def ensure_dirs(self) -> None:
        for path in (self.archive_root, self.raw_dir, self.media_dir):
            path.mkdir(parents=True, exist_ok=True)
