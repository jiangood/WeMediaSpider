import sqlite3
import os
from typing import List, Dict, Optional


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_name TEXT NOT NULL,
                title TEXT NOT NULL,
                publish_time TEXT DEFAULT '',
                link TEXT UNIQUE NOT NULL,
                content TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
                title, content, content=articles, content_rowid=id
            );

            CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
                INSERT INTO articles_fts(rowid, title, content)
                VALUES (new.id, new.title, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
                INSERT INTO articles_fts(articles_fts, rowid, title, content)
                VALUES ('delete', old.id, old.title, old.content);
            END;

            CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
                INSERT INTO articles_fts(articles_fts, rowid, title, content)
                VALUES ('delete', old.id, old.title, old.content);
                INSERT INTO articles_fts(rowid, title, content)
                VALUES (new.id, new.title, new.content);
            END;
        """)
        self.conn.commit()

    def save_articles(self, articles: List[Dict]) -> int:
        count = 0
        for article in articles:
            cursor = self.conn.execute(
                "INSERT OR IGNORE INTO articles (account_name, title, publish_time, link, content) VALUES (?, ?, ?, ?, ?)",
                (
                    article.get('name', ''),
                    article.get('title', ''),
                    article.get('publish_time', '') or article.get('time', ''),
                    article.get('link', ''),
                    article.get('content', '')
                )
            )
            if cursor.rowcount > 0:
                count += 1
        self.conn.commit()
        return count

    def get_articles(self, account: Optional[str] = None) -> List[Dict]:
        if account:
            rows = self.conn.execute(
                "SELECT account_name, title, publish_time, link, content FROM articles WHERE account_name = ? ORDER BY publish_time DESC",
                (account,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT account_name, title, publish_time, link, content FROM articles ORDER BY publish_time DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_accounts(self) -> List[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT account_name FROM articles ORDER BY account_name"
        ).fetchall()
        return [r['account_name'] for r in rows]

    def get_articles_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS cnt FROM articles").fetchone()
        return row['cnt']

    def search_articles(self, keyword: str) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT a.account_name, a.title, a.publish_time, a.link, a.content "
            "FROM articles_fts f JOIN articles a ON f.rowid = a.id "
            "WHERE articles_fts MATCH ? ORDER BY rank",
            (keyword,)
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_article(self, link: str) -> bool:
        cursor = self.conn.execute("DELETE FROM articles WHERE link = ?", (link,))
        self.conn.commit()
        return cursor.rowcount > 0

    def clear(self):
        self.conn.executescript("DELETE FROM articles; DELETE FROM articles_fts;")
        self.conn.commit()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
