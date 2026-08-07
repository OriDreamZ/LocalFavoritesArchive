import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .models import Post


class ArchiveStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "archive.sqlite3"
        self.raw_dir = self.root / "raw"
        self.media_dir = self.root / "media"
        self.raw_dir.mkdir(exist_ok=True)
        self.media_dir.mkdir(exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS posts (
              post_id TEXT PRIMARY KEY, url TEXT NOT NULL, text TEXT NOT NULL,
              author_id TEXT, author_handle TEXT, author_name TEXT,
              published_at TEXT, collected_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
              reply_to_id TEXT, quote_id TEXT, language TEXT, raw_path TEXT NOT NULL,
              extraction_version TEXT NOT NULL DEFAULT '1'
            );
            CREATE TABLE IF NOT EXISTS media (
              post_id TEXT NOT NULL, media_index INTEGER NOT NULL, kind TEXT NOT NULL,
              source_url TEXT NOT NULL, local_path TEXT, mime_type TEXT,
              width INTEGER, height INTEGER, duration_ms INTEGER, byte_size INTEGER,
              checksum TEXT, status TEXT NOT NULL DEFAULT 'queued', error TEXT,
              PRIMARY KEY(post_id, media_index), FOREIGN KEY(post_id) REFERENCES posts(post_id)
            );
            CREATE TABLE IF NOT EXISTS post_links (
              post_id TEXT NOT NULL,
              link_index INTEGER NOT NULL,
              display_url TEXT NOT NULL,
              expanded_url TEXT NOT NULL,
              short_url TEXT NOT NULL,
              PRIMARY KEY(post_id, link_index),
              FOREIGN KEY(post_id) REFERENCES posts(post_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS sync_runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
              finished_at TEXT, status TEXT NOT NULL, discovered INTEGER DEFAULT 0,
              new_posts INTEGER DEFAULT 0, downloaded INTEGER DEFAULT 0, failed INTEGER DEFAULT 0,
              error TEXT
            );
            CREATE TABLE IF NOT EXISTS archive_settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            INSERT OR IGNORE INTO archive_settings(key,value)
            VALUES('stop_after_existing','50');
            CREATE TABLE IF NOT EXISTS tags (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL COLLATE NOCASE UNIQUE,
              color TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE TABLE IF NOT EXISTS post_tags (
              post_id TEXT NOT NULL,
              tag_id INTEGER NOT NULL,
              PRIMARY KEY(post_id, tag_id),
              FOREIGN KEY(post_id) REFERENCES posts(post_id) ON DELETE CASCADE,
              FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS post_tags_tag_id_idx ON post_tags(tag_id);
            CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts USING fts5(post_id UNINDEXED, text, author_handle, author_name);
            """)

    def get_stop_after_existing(self) -> int:
        with self._connect() as db:
            row = db.execute(
                "SELECT value FROM archive_settings WHERE key='stop_after_existing'"
            ).fetchone()
        return int(row["value"]) if row else 50

    def set_stop_after_existing(self, value: int) -> int:
        with self._connect() as db:
            db.execute(
                "INSERT INTO archive_settings(key,value) VALUES('stop_after_existing',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(value),),
            )
        return value

    def _owned_path(self, relative: str | Path) -> Path:
        target = (self.root / relative).resolve()
        root = self.root.resolve()
        if target == root or root not in target.parents:
            raise ValueError(f"archive path escapes root: {relative}")
        return target

    def delete_posts(self, post_ids: list[str]) -> dict[str, list[Any]]:
        requested = list(dict.fromkeys(post_ids))
        deleted: list[str] = []
        not_found: list[str] = []
        owned_paths: dict[str, tuple[Path, Path]] = {}
        with self._connect() as db:
            for post_id in requested:
                row = db.execute(
                    "SELECT raw_path FROM posts WHERE post_id=?", (post_id,)
                ).fetchone()
                if not row:
                    not_found.append(post_id)
                    continue
                owned_paths[post_id] = (
                    self._owned_path(row["raw_path"]),
                    self._owned_path(self.media_dir.relative_to(self.root) / post_id),
                )
                db.execute("DELETE FROM media WHERE post_id=?", (post_id,))
                db.execute("DELETE FROM post_links WHERE post_id=?", (post_id,))
                db.execute("DELETE FROM post_tags WHERE post_id=?", (post_id,))
                db.execute("DELETE FROM posts_fts WHERE post_id=?", (post_id,))
                db.execute("DELETE FROM posts WHERE post_id=?", (post_id,))
                deleted.append(post_id)

        cleanup_errors: list[dict[str, str]] = []
        for post_id, (raw_path, media_path) in owned_paths.items():
            try:
                raw_path.unlink(missing_ok=True)
            except OSError as exc:
                cleanup_errors.append({
                    "post_id": post_id,
                    "path": str(raw_path),
                    "error": str(exc),
                })
            try:
                if media_path.exists():
                    shutil.rmtree(media_path)
            except OSError as exc:
                cleanup_errors.append({
                    "post_id": post_id,
                    "path": str(media_path),
                    "error": str(exc),
                })
        return {
            "deleted": deleted,
            "not_found": not_found,
            "file_cleanup_errors": cleanup_errors,
        }

    def media_path(self, post_id: str, index: int, source_url: str) -> Path:
        suffix = Path(source_url.split("?")[0]).suffix.lower() or ".bin"
        safe = hashlib.sha256(source_url.encode()).hexdigest()[:10]
        return self.media_dir / post_id / f"{index}-{safe}{suffix}"

    def upsert_post(self, post: Post) -> bool:
        raw_path = self.raw_dir / f"{post.post_id}.json"
        raw_path.write_text(json.dumps(post.raw, ensure_ascii=False, indent=2), encoding="utf-8")
        with self._connect() as db:
            exists = db.execute("SELECT 1 FROM posts WHERE post_id=?", (post.post_id,)).fetchone() is not None
            db.execute("""INSERT INTO posts(post_id,url,text,author_id,author_handle,author_name,published_at,collected_at,last_seen_at,reply_to_id,quote_id,language,raw_path)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(post_id) DO UPDATE SET
                url=excluded.url,text=excluded.text,author_id=excluded.author_id,author_handle=excluded.author_handle,
                author_name=excluded.author_name,published_at=excluded.published_at,last_seen_at=excluded.last_seen_at,
                reply_to_id=excluded.reply_to_id,quote_id=excluded.quote_id,language=excluded.language,raw_path=excluded.raw_path""",
                (post.post_id, post.url, post.text, post.author_id, post.author_handle, post.author_name, post.published_at.isoformat() if post.published_at else None, post.collected_at.isoformat(), post.collected_at.isoformat(), post.reply_to_id, post.quote_id, post.language, str(raw_path.relative_to(self.root))))
            db.execute("DELETE FROM posts_fts WHERE post_id=?", (post.post_id,))
            db.execute("INSERT INTO posts_fts(post_id,text,author_handle,author_name) VALUES(?,?,?,?)", (post.post_id, post.text, post.author_handle, post.author_name))
            db.execute("DELETE FROM post_links WHERE post_id=?", (post.post_id,))
            db.executemany(
                "INSERT INTO post_links(post_id,link_index,display_url,expanded_url,short_url) VALUES(?,?,?,?,?)",
                [
                    (post.post_id, link.index, link.display_url, link.expanded_url, link.short_url)
                    for link in post.links
                ],
            )
            for item in post.media:
                local_path = str(self.media_path(post.post_id, item.index, item.source_url).relative_to(self.root))
                db.execute("""INSERT INTO media(post_id,media_index,kind,source_url,local_path,mime_type,width,height,duration_ms,status,error)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(post_id,media_index) DO UPDATE SET
                    kind=excluded.kind,source_url=excluded.source_url,mime_type=excluded.mime_type,width=excluded.width,height=excluded.height,duration_ms=excluded.duration_ms""",
                    (post.post_id, item.index, item.kind, item.source_url, local_path, item.mime_type, item.width, item.height, item.duration_ms, item.status, item.error))
        return not exists

    def _post_filters(
        self,
        query: str,
        author: str,
        media_type: str,
        date_from: str,
        date_to: str,
        tag_id: int | None = None,
        tag_ids: list[int] | None = None,
        tag_mode: str = "any",
    ) -> tuple[str, list[Any]]:
        where, args = ["1=1"], []
        if query:
            where.append("p.post_id IN (SELECT post_id FROM posts_fts WHERE posts_fts MATCH ?)"); args.append(query + "*")
        if author:
            where.append("(p.author_handle=? OR p.author_name LIKE ?)"); args.extend([author, f"%{author}%"])
        if media_type == "text":
            where.append("NOT EXISTS (SELECT 1 FROM media m WHERE m.post_id=p.post_id)")
        elif media_type:
            where.append("EXISTS (SELECT 1 FROM media m WHERE m.post_id=p.post_id AND m.kind=? AND m.status='downloaded')"); args.append(media_type)
        if date_from: where.append("p.published_at >= ?"); args.append(date_from)
        if date_to: where.append("p.published_at <= ?"); args.append(date_to)
        selected_tags = list(dict.fromkeys(tag_ids or ([tag_id] if tag_id is not None else [])))
        if selected_tags:
            if tag_mode not in {"all", "any"}:
                raise ValueError("tag mode must be 'all' or 'any'")
            if tag_mode == "all":
                for selected_tag in selected_tags:
                    where.append("EXISTS (SELECT 1 FROM post_tags pt WHERE pt.post_id=p.post_id AND pt.tag_id=?)")
                    args.append(selected_tag)
            else:
                placeholders = ",".join("?" for _ in selected_tags)
                where.append(
                    f"EXISTS (SELECT 1 FROM post_tags pt WHERE pt.post_id=p.post_id AND pt.tag_id IN ({placeholders}))"
                )
                args.extend(selected_tags)
        return " AND ".join(where), args

    def count_posts(self, query: str = "", author: str = "", media_type: str = "", date_from: str = "", date_to: str = "", tag_id: int | None = None, tag_ids: list[int] | None = None, tag_mode: str = "any") -> int:
        where, args = self._post_filters(query, author, media_type, date_from, date_to, tag_id, tag_ids, tag_mode)
        with self._connect() as db:
            return db.execute(f"SELECT COUNT(*) FROM posts p WHERE {where}", args).fetchone()[0]

    def list_posts(self, query: str = "", author: str = "", media_type: str = "", date_from: str = "", date_to: str = "", sort: str = "published_at", direction: str = "desc", limit: int = 100, offset: int = 0, tag_id: int | None = None, tag_ids: list[int] | None = None, tag_mode: str = "any") -> list[dict[str, Any]]:
        order_column = {
            "published_at": "p.published_at",
            "collected_at": "p.collected_at",
            "author": "p.author_handle COLLATE NOCASE",
        }.get(sort, "p.published_at")
        order_direction = "ASC" if direction.lower() == "asc" else "DESC"
        order = f"{order_column} {order_direction}, p.post_id {order_direction}"
        where, args = self._post_filters(query, author, media_type, date_from, date_to, tag_id, tag_ids, tag_mode)
        sql = f"SELECT p.*, (SELECT COUNT(*) FROM media m WHERE m.post_id=p.post_id) AS media_count FROM posts p WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?"
        args.extend([limit, offset])
        with self._connect() as db:
            return [dict(row) for row in db.execute(sql, args).fetchall()]

    def get_post(self, post_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM posts WHERE post_id=?", (post_id,)).fetchone()
            if not row: return None
            data = dict(row)
            data["media"] = [dict(m) for m in db.execute("SELECT * FROM media WHERE post_id=? ORDER BY media_index", (post_id,)).fetchall()]
            data["links"] = [dict(link) for link in db.execute(
                "SELECT link_index,display_url,expanded_url,short_url FROM post_links WHERE post_id=? ORDER BY link_index",
                (post_id,),
            ).fetchall()]
            data["tags"] = [dict(tag) for tag in db.execute(
                "SELECT t.id,t.name,t.color FROM tags t JOIN post_tags pt ON pt.tag_id=t.id WHERE pt.post_id=? ORDER BY t.name COLLATE NOCASE",
                (post_id,),
            ).fetchall()]
            return data

    def overview_stats(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        anchor = now.astimezone(timezone.utc)
        anchor_index = anchor.year * 12 + anchor.month - 1
        months = []
        for offset in range(11, -1, -1):
            year, month_index = divmod(anchor_index - offset, 12)
            months.append(f"{year:04d}-{month_index + 1:02d}")

        with self._connect() as db:
            posts_total = db.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
            authors_total = db.execute(
                "SELECT COUNT(DISTINCT author_handle) FROM posts WHERE COALESCE(author_handle, '') <> ''"
            ).fetchone()[0]
            tagged_posts = db.execute("SELECT COUNT(DISTINCT post_id) FROM post_tags").fetchone()[0]
            media_row = db.execute("""
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN status='downloaded' THEN 1 ELSE 0 END) AS downloaded,
                       SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
                       COALESCE(SUM(byte_size), 0) AS storage_bytes
                FROM media
            """).fetchone()
            image_posts = db.execute(
                "SELECT COUNT(DISTINCT post_id) FROM media WHERE kind='image' AND status='downloaded'"
            ).fetchone()[0]
            video_posts = db.execute(
                "SELECT COUNT(DISTINCT post_id) FROM media WHERE kind='video' AND status='downloaded'"
            ).fetchone()[0]
            text_posts = db.execute(
                "SELECT COUNT(*) FROM posts p WHERE NOT EXISTS (SELECT 1 FROM media m WHERE m.post_id=p.post_id)"
            ).fetchone()[0]
            coverage = db.execute(
                "SELECT MIN(published_at) AS first_date, MAX(published_at) AS last_date FROM posts WHERE published_at IS NOT NULL"
            ).fetchone()
            monthly_counts = {
                row["month"]: row["count"]
                for row in db.execute(
                    """SELECT substr(collected_at, 1, 7) AS month, COUNT(*) AS count
                       FROM posts
                       WHERE substr(collected_at, 1, 7) BETWEEN ? AND ?
                       GROUP BY month""",
                    (months[0], months[-1]),
                ).fetchall()
            }

        media_total = media_row["total"]
        media_downloaded = media_row["downloaded"] or 0
        first_date = coverage["first_date"]
        last_date = coverage["last_date"]
        archive_days = 0
        if first_date and last_date:
            archive_days = (
                datetime.fromisoformat(last_date).date() - datetime.fromisoformat(first_date).date()
            ).days + 1

        return {
            "posts_total": posts_total,
            "authors_total": authors_total,
            "tagged_posts": tagged_posts,
            "tag_coverage_percent": round(tagged_posts / posts_total * 100, 1) if posts_total else 0.0,
            "media_total": media_total,
            "media_downloaded": media_downloaded,
            "media_failed": media_row["failed"] or 0,
            "media_completion_percent": round(media_downloaded / media_total * 100, 1) if media_total else 0.0,
            "image_posts": image_posts,
            "video_posts": video_posts,
            "text_posts": text_posts,
            "archive_days": archive_days,
            "storage_bytes": media_row["storage_bytes"],
            "monthly_additions": [{"month": month, "count": monthly_counts.get(month, 0)} for month in months],
        }

    def count_media_failures(
        self,
        post_id: str | None = None,
        media_index: int | None = None,
    ) -> int:
        where = ["status='failed'"]
        args: list[Any] = []
        if post_id is not None:
            where.append("post_id=?")
            args.append(post_id)
        if media_index is not None:
            where.append("media_index=?")
            args.append(media_index)
        with self._connect() as db:
            return db.execute(
                f"SELECT COUNT(*) FROM media WHERE {' AND '.join(where)}",
                args,
            ).fetchone()[0]

    def claim_failed_media(
        self,
        targets: list[tuple[str, int]] | None = None,
    ) -> list[tuple[str, int]]:
        with self._connect() as db:
            if targets is None:
                rows = db.execute(
                    "SELECT post_id,media_index FROM media "
                    "WHERE status='failed' ORDER BY post_id,media_index"
                ).fetchall()
            else:
                rows = []
                for post_id, media_index in dict.fromkeys(targets):
                    row = db.execute(
                        "SELECT post_id,media_index FROM media "
                        "WHERE post_id=? AND media_index=? AND status='failed'",
                        (post_id, media_index),
                    ).fetchone()
                    if row:
                        rows.append(row)
            claimed = [(row["post_id"], row["media_index"]) for row in rows]
            db.executemany(
                "UPDATE media SET status='queued',error=NULL "
                "WHERE post_id=? AND media_index=? AND status='failed'",
                claimed,
            )
        return claimed

    def restore_claimed_media_failures(
        self,
        targets: list[tuple[str, int]],
        error: str,
    ) -> None:
        with self._connect() as db:
            db.executemany(
                "UPDATE media SET status='failed',error=? "
                "WHERE post_id=? AND media_index=? AND status='queued'",
                [(error[:500], post_id, media_index) for post_id, media_index in targets],
            )

    def list_media_failures(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("""
                SELECT m.post_id,p.author_name,p.author_handle,p.url,p.published_at,
                       m.media_index,m.kind,m.source_url,m.error
                FROM media m
                JOIN posts p ON p.post_id=m.post_id
                WHERE m.status='failed'
                ORDER BY p.published_at DESC, m.media_index ASC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(row) for row in rows]

    def list_tags(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("""
                SELECT t.id,t.name,t.color,t.created_at,COUNT(pt.post_id) AS post_count
                FROM tags t LEFT JOIN post_tags pt ON pt.tag_id=t.id
                GROUP BY t.id ORDER BY t.name COLLATE NOCASE
            """).fetchall()
            return [dict(row) for row in rows]

    def get_tag(self, tag_id: int) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT id,name,color,created_at FROM tags WHERE id=?", (tag_id,)).fetchone()
            return dict(row) if row else None

    def create_tag(self, name: str, color: str) -> dict[str, Any]:
        try:
            with self._connect() as db:
                cursor = db.execute("INSERT INTO tags(name,color) VALUES(?,?)", (name.strip(), color))
                tag_id = cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            raise ValueError("tag name already exists") from exc
        return self.get_tag(tag_id)

    def update_tag(self, tag_id: int, name: str, color: str) -> dict[str, Any] | None:
        try:
            with self._connect() as db:
                cursor = db.execute("UPDATE tags SET name=?,color=? WHERE id=?", (name.strip(), color, tag_id))
                if cursor.rowcount == 0:
                    return None
        except sqlite3.IntegrityError as exc:
            raise ValueError("tag name already exists") from exc
        return self.get_tag(tag_id)

    def delete_tag(self, tag_id: int) -> bool:
        with self._connect() as db:
            return db.execute("DELETE FROM tags WHERE id=?", (tag_id,)).rowcount > 0

    def assign_tag(self, post_id: str, tag_id: int) -> bool:
        with self._connect() as db:
            if not db.execute("SELECT 1 FROM posts WHERE post_id=?", (post_id,)).fetchone():
                return False
            if not db.execute("SELECT 1 FROM tags WHERE id=?", (tag_id,)).fetchone():
                return False
            return db.execute("INSERT OR IGNORE INTO post_tags(post_id,tag_id) VALUES(?,?)", (post_id, tag_id)).rowcount > 0

    def remove_tag(self, post_id: str, tag_id: int) -> bool:
        with self._connect() as db:
            return db.execute("DELETE FROM post_tags WHERE post_id=? AND tag_id=?", (post_id, tag_id)).rowcount > 0
