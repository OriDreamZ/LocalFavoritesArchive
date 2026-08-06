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

    async def run(self) -> dict[str, int]:
        with self.store._connect() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM media WHERE status != 'downloaded' AND source_url != ''").fetchall()]
        sem = asyncio.Semaphore(self.concurrency)
        stats = {"downloaded": 0, "failed": 0}
        async with httpx.AsyncClient(follow_redirects=True, timeout=60, headers={"User-Agent": "Mozilla/5.0"}) as client:
            async def one(row):
                async with sem:
                    target = self.store.root / row["local_path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temp = Path(str(target) + ".part")
                    try:
                        async with client.stream("GET", row["source_url"]) as response:
                            response.raise_for_status()
                            digest = hashlib.sha256()
                            size = 0
                            with temp.open("wb") as handle:
                                async for chunk in response.aiter_bytes():
                                    handle.write(chunk); digest.update(chunk); size += len(chunk)
                        os.replace(temp, target)
                        with self.store._connect() as db:
                            db.execute("UPDATE media SET status='downloaded', byte_size=?, checksum=?, mime_type=COALESCE(mime_type,?), error=NULL WHERE post_id=? AND media_index=?", (size, digest.hexdigest(), response.headers.get("content-type", "").split(";")[0], row["post_id"], row["media_index"]))
                        stats["downloaded"] += 1
                    except Exception as exc:
                        temp.unlink(missing_ok=True)
                        with self.store._connect() as db:
                            db.execute("UPDATE media SET status='failed', error=? WHERE post_id=? AND media_index=?", (str(exc)[:500], row["post_id"], row["media_index"]))
                        stats["failed"] += 1
            await asyncio.gather(*(one(row) for row in rows))
        return stats
