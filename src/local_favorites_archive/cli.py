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
    parser.add_argument("--lan", action="store_true", help="允许局域网设备完整管理归档（无身份验证）")
    args = parser.parse_args()
    settings = Settings(archive_root=args.archive, port=args.port, host="0.0.0.0" if args.lan else "127.0.0.1", lan_enabled=args.lan)
    settings.ensure_dirs()
    if args.command == "init":
        ArchiveStore(settings.archive_root)
        print(f"归档目录已初始化：{settings.archive_root.resolve()}")
    elif args.command == "retry-media":
        import asyncio
        store = ArchiveStore(settings.archive_root)
        print(asyncio.run(MediaDownloader(store, settings.max_media_concurrency).run()))
    else:
        if args.lan:
            print("警告：局域网访问未启用身份验证，局域网内设备拥有完整管理权限。")
        uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
