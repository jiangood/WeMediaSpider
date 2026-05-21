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

            CREATE TABLE IF NOT EXISTS wechat_account (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'pending',
                error_message TEXT DEFAULT '',
                total_articles INTEGER DEFAULT 0,
                date_range TEXT DEFAULT '最近7天',
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
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

            CREATE INDEX IF NOT EXISTS idx_articles_account_name ON articles(account_name);
            CREATE INDEX IF NOT EXISTS idx_articles_publish_time ON articles(publish_time);
            CREATE INDEX IF NOT EXISTS idx_wechat_account_status ON wechat_account(status);
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

    def get_articles(self, account: Optional[str] = None, include_content: bool = True) -> List[Dict]:
        cols = "account_name, title, publish_time, link"
        if include_content:
            cols += ", content"
        if account:
            rows = self.conn.execute(
                f"SELECT {cols} FROM articles WHERE account_name = ? ORDER BY publish_time DESC",
                (account,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                f"SELECT {cols} FROM articles ORDER BY publish_time DESC"
            ).fetchall()
        result = [dict(r) for r in rows]
        if not include_content:
            for r in result:
                r['content'] = ''
        return result

    def get_accounts(self) -> List[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT account_name FROM articles ORDER BY account_name"
        ).fetchall()
        return [r['account_name'] for r in rows]

    def get_articles_count(self, account: Optional[str] = None) -> int:
        if account:
            row = self.conn.execute("SELECT COUNT(*) AS cnt FROM articles WHERE account_name = ?", (account,)).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) AS cnt FROM articles").fetchone()
        return row['cnt']

    def get_articles_page(self, page: int = 1, page_size: int = 50, account: Optional[str] = None, include_content: bool = False) -> List[Dict]:
        cols = "account_name, title, publish_time, link"
        if include_content:
            cols += ", content"
        offset = max(0, (page - 1) * page_size)
        if account:
            rows = self.conn.execute(
                f"SELECT {cols} FROM articles WHERE account_name = ? ORDER BY publish_time DESC LIMIT ? OFFSET ?",
                (account, page_size, offset)
            ).fetchall()
        else:
            rows = self.conn.execute(
                f"SELECT {cols} FROM articles ORDER BY publish_time DESC LIMIT ? OFFSET ?",
                (page_size, offset)
            ).fetchall()
        result = [dict(r) for r in rows]
        if not include_content:
            for r in result:
                r['content'] = ''
        return result

    def get_existing_links(self) -> set:
        rows = self.conn.execute("SELECT link FROM articles").fetchall()
        return {r['link'] for r in rows}

    def add_account(self, name: str, date_range: str = '最近7天') -> bool:
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO wechat_account (name, date_range) VALUES (?, ?)",
                (name, date_range)
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def delete_account(self, name: str) -> bool:
        cursor = self.conn.execute("DELETE FROM wechat_account WHERE name = ?", (name,))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_wechat_accounts(self, status: Optional[str] = None) -> List[Dict]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM wechat_account WHERE status = ? ORDER BY created_at DESC",
                (status,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM wechat_account ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_pending_account(self) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM wechat_account WHERE status = 'pending' LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def update_account_status(self, name: str, status: str, error_message: str = '', total_articles: int = 0):
        self.conn.execute(
            "UPDATE wechat_account SET status = ?, error_message = ?, total_articles = ?, updated_at = datetime('now','localtime') WHERE name = ?",
            (status, error_message, total_articles, name)
        )
        self.conn.commit()

    def get_article_without_content(self) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT id, account_name, title, link FROM articles WHERE content IS NULL OR content = '' LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

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
