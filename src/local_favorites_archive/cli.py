import argparse
from pathlib import Path

import uvicorn

from .config import Settings
from .downloader import MediaDownloader
from .storage import ArchiveStore
from .web import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="将 X 喜欢内容归档到本地")
    parser.add_argument("command", choices=["init", "serve", "retry-media"], nargs="?", default="serve")
    parser.add_argument("--archive", type=Path, default=Path("archive"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    settings = Settings(archive_root=args.archive, port=args.port)
    settings.ensure_dirs()
    store = ArchiveStore(settings.archive_root)
    if args.command == "init":
        print(f"归档目录已初始化：{settings.archive_root.resolve()}")
    elif args.command == "retry-media":
        import asyncio
        print(asyncio.run(MediaDownloader(store, settings.max_media_concurrency).run()))
    else:
        uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
