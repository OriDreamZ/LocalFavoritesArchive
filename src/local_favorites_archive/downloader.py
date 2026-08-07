import asyncio
import hashlib
import os
from pathlib import Path

import httpx

from .storage import ArchiveStore


class MediaDownloader:
    def __init__(self, store: ArchiveStore, concurrency: int = 2):
        self.store = store
        self.concurrency = concurrency

    async def run(
        self,
        targets: list[tuple[str, int]] | None = None,
    ) -> dict[str, int]:
        stats = {"downloaded": 0, "failed": 0}
        if targets == []:
            return stats
        where = ["status NOT IN ('downloaded', 'deferred')", "source_url != ''"]
        args: list[object] = []
        if targets is not None:
            unique_targets = list(dict.fromkeys(targets))
            where.append(
                "(" + " OR ".join(
                    "(post_id=? AND media_index=?)" for _ in unique_targets
                ) + ")"
            )
            args.extend(value for target in unique_targets for value in target)
        with self.store._connect() as db:
            rows = [
                dict(row)
                for row in db.execute(
                    f"SELECT * FROM media WHERE {' AND '.join(where)}",
                    args,
                ).fetchall()
            ]
        sem = asyncio.Semaphore(self.concurrency)
        async with httpx.AsyncClient(follow_redirects=True, timeout=60, headers={"User-Agent": "Mozilla/5.0"}) as client:
            async def one(row):
                async with sem:
                    target = self.store.root / row["local_path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temp = Path(str(target) + ".part")
                    try:
                        async with client.stream("GET", row["source_url"]) as response:
                            response.raise_for_status()
                            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                            expected = "video/" if row["kind"] == "video" else "image/"
                            if not content_type.startswith(expected):
                                raise ValueError(f"媒体类型校验失败：推文 {row['post_id']} 第 {row['media_index'] + 1} 项应为{expected}，实际为 {content_type or '未知'}")
                            digest = hashlib.sha256()
                            size = 0
                            with temp.open("wb") as handle:
                                async for chunk in response.aiter_bytes():
                                    handle.write(chunk); digest.update(chunk); size += len(chunk)
                        os.replace(temp, target)
                        with self.store._connect() as db:
                            db.execute("UPDATE media SET status='downloaded', byte_size=?, checksum=?, mime_type=COALESCE(mime_type,?), error=NULL WHERE post_id=? AND media_index=?", (size, digest.hexdigest(), content_type, row["post_id"], row["media_index"]))
                        stats["downloaded"] += 1
                    except Exception as exc:
                        temp.unlink(missing_ok=True)
                        with self.store._connect() as db:
                            db.execute("UPDATE media SET status='failed', error=? WHERE post_id=? AND media_index=?", (str(exc)[:500], row["post_id"], row["media_index"]))
                        stats["failed"] += 1
            await asyncio.gather(*(one(row) for row in rows))
        return stats
