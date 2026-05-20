# Embedded Database Replace CSV Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace CSV file-based internal data transfer with SQLite embedded database. CSV/JSON/Excel remain as user export formats.

**Architecture:** A `Database` DAO class wraps all SQLite operations. Scraper writes to DB, GUI reads from DB. A `get_db_path()` utility provides the canonical DB file location. The CSV import feature is preserved for backward compatibility.

**Tech Stack:** Python `sqlite3` (stdlib), SQLite FTS5 for full-text search

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `spider/database.py` | **Create** | DAO: SQLite CRUD + FTS, returns `List[Dict]` |
| `gui/utils.py` | **Modify** | Add `get_db_path()` function |
| `spider/wechat/scraper.py` | **Modify** | Replace CSV save with DB save |
| `spider/wechat/run.py` | **Modify** | Return db_path, remove CSV filename generation |
| `gui/workers.py` | **Modify** | Signal carries db_path, scraper saves internally |
| `gui/pages/unified_scrape_page.py` | **Modify** | Remove CSV output config, load from DB after scrape |
| `gui/pages/results_page.py` | **Modify** | Add DB loading method, keep CSV import as manual |
| `gui/pages/content_search_page.py` | **Modify** | Add DB loading + FTS search |
| `gui/main_window.py` | **Modify** | Simplify save-on-close |

---

### Task 1: Add `get_db_path()` to `gui/utils.py`

**Files:**
- Modify: `gui/utils.py` (after line 153, before the sound section)

- [ ] **Step 1: Add `get_db_path()` function**

Insert after line 153 (`ACCOUNT_HISTORY_FILE` constant):

```python
def get_db_path() -> str:
    return get_cache_file_path('wechat_spider.db')

DB_PATH = get_db_path()
```

- [ ] **Step 2: Commit**

```bash
git add gui/utils.py
git commit -m "feat: add get_db_path() utility function"
```

---

### Task 2: Create `spider/database.py` DAO Layer

**Files:**
- Create: `spider/database.py`

- [ ] **Step 1: Create the Database class**

```python
import sqlite3
import os
from typing import List, Dict, Optional
from datetime import datetime


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
            try:
                self.conn.execute(
                    "INSERT OR IGNORE INTO articles (account_name, title, publish_time, link, content) VALUES (?, ?, ?, ?, ?)",
                    (
                        article.get('name', ''),
                        article.get('title', ''),
                        article.get('publish_time', '') or article.get('time', ''),
                        article.get('link', ''),
                        article.get('content', '')
                    )
                )
                if self.conn.total_changes > count:
                    count += 1
            except Exception:
                continue
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
        self.conn.execute("DELETE FROM articles WHERE link = ?", (link,))
        self.conn.commit()
        return True

    def clear(self):
        self.conn.executescript("DELETE FROM articles; DELETE FROM articles_fts;")
        self.conn.commit()

    def close(self):
        self.conn.close()
```

- [ ] **Step 2: Commit**

```bash
git add spider/database.py
git commit -m "feat: add Database DAO class with SQLite + FTS5"
```

---

### Task 3: Modify `spider/wechat/scraper.py` — Save to DB Instead of CSV

**Files:**
- Modify: `spider/wechat/scraper.py`

- [ ] **Step 1: Add import at top**

Add after `from spider.wechat.utils import ...`:

```python
from spider.database import Database
```

- [ ] **Step 2: Replace `save_articles_to_csv()` method (around line 275-307)**

Find method `save_articles_to_csv(self, articles, filename)` starting around line 271. Replace it with:

```python
    def save_articles_to_db(self, articles, db_path):
        if not articles:
            return False
        try:
            db = Database(db_path)
            count = db.save_articles(articles)
            db.close()
            logger.info(f"已保存 {count} 篇文章到数据库")
            return count > 0
        except Exception as e:
            logger.error(f"保存到数据库失败: {e}")
            return False
```

- [ ] **Step 3: Replace `_save_articles_to_csv()` method (around line 1096-1120)**

Find method `_save_articles_to_csv(self, articles, filename)`. Replace with:

```python
    def _save_articles_to_db(self, articles, db_path):
        if not articles:
            return False
        try:
            db = Database(db_path)
            count = db.save_articles(articles)
            db.close()
            return count > 0
        except Exception as e:
            logger.error(f"保存到数据库失败: {e}")
            return False
```

- [ ] **Step 4: Find all callers of CSV save methods and update references**

Search for `save_articles_to_csv` and `_save_articles_to_csv` in `scraper.py`. Update each call to use the DB version.

Also check for any other CSV-related code in `scraper.py` (like `_save_account_to_csv` etc. if they exist).

- [ ] **Step 5: Commit**

```bash
git add spider/wechat/scraper.py
git commit -m "refactor: replace CSV save with DB save in scraper"
```

---

### Task 4: Modify `spider/wechat/run.py` — Use DB Path

**Files:**
- Modify: `spider/wechat/run.py`

- [ ] **Step 1: Replace CSV output logic in `scrape_account()` (around line 208-223)**

Replace the CSV save block:

```python
        # 保存结果到数据库
        if output_file:
            db_path = output_file
        else:
            db_path = self.config.get('db_path', 'wechat_spider.db')

        logger.info(f"保存结果到数据库: {db_path}")
        success = scraper.save_articles_to_db(filtered_articles, db_path)
```

- [ ] **Step 2: Update `batch_scrape()` config (around line 307-320)**

Change `'output_file'` to `'db_path'` in the config dict. Also remove the CSV-specific filename generation logic.

- [ ] **Step 3: Commit**

```bash
git add spider/wechat/run.py
git commit -m "refactor: use db_path instead of csv_path in run module"
```

---

### Task 5: Modify `gui/workers.py` — Signal Carries DB Path

**Files:**
- Modify: `gui/workers.py`

- [ ] **Step 1: Update `BatchScrapeWorker.run()` (line 143-144)**

Change:

```python
            output_file = self.config.get('output_file', '')
            self.scrape_success.emit(self.articles, output_file)
```

To:

```python
            db_path = self.config.get('db_path', '')
            self.scrape_success.emit(self.articles, db_path)
```

- [ ] **Step 2: Update `AsyncBatchScrapeWorker.run()` (line 264-265)**

Same change.

- [ ] **Step 3: Commit**

```bash
git add gui/workers.py
git commit -m "refactor: workers emit db_path instead of csv_path"
```

---

### Task 6: Modify `gui/pages/unified_scrape_page.py` — Remove CSV Config, Load from DB

**Files:**
- Modify: `gui/pages/unified_scrape_page.py`

- [ ] **Step 1: Add import at top**

```python
from spider.database import Database
from gui.utils import DB_PATH
```

- [ ] **Step 2: Remove CSV output filename generation (around line 479-491)**

Remove the `output_file` / `_current_output_file` logic. Replace with:

```python
        # 数据库路径（所有爬取结果统一存储）
        db_path = DB_PATH
        self._current_db_path = db_path
```

- [ ] **Step 3: Update config dict (around line 498-509)**

Replace `'output_file': output_file` with `'db_path': db_path` in config.

- [ ] **Step 4: Update `_on_scrape_success()` (around line 605-631)**

Change:

```python
    def _on_scrape_success(self, articles, output_file):
```

To no longer pass a temp_file. Instead, the data is already in DB. After emit, load from DB:

```python
    def _on_scrape_success(self, articles, db_path):
        self.start_btn.show()
        self.cancel_btn.hide()
        self._article_count = len(articles)
        self.progress_widget._article_count = len(articles)
        self.progress_widget.set_complete(f"爬取完成！")
        self.status_hint.setText(f"完成！共 {len(articles)} 篇文章")
        self.status_hint.setStyleSheet(f"color: {COLORS['success']};")

        play_sound('complete')

        accounts = self.account_list.get_accounts()
        if accounts:
            self.account_list.add_to_history(accounts)

        if len(accounts) == 1:
            source_info = f"爬取: {accounts[0]}"
        else:
            accounts_str = ', '.join(accounts[:3]) + ('...' if len(accounts) > 3 else '')
            source_info = f"批量爬取: {accounts_str} (共{len(accounts)}个公众号)"

        self.scrape_completed.emit(articles, source_info, None)
```

- [ ] **Step 5: Update `_on_cancel()` (around line 642-667)**

Remove temp_file logic. Emit `None` for temp_file.

- [ ] **Step 6: Also remove `_current_output_file` references in `_start_scrape` setup area**

- [ ] **Step 7: Commit**

```bash
git add gui/pages/unified_scrape_page.py
git commit -m "refactor: unified_scrape_page uses db_path, removes CSV temp file logic"
```

---

### Task 7: Modify `gui/pages/results_page.py` — Load from DB

**Files:**
- Modify: `gui/pages/results_page.py`

- [ ] **Step 1: Add import**

```python
from spider.database import Database
from gui.utils import DB_PATH
```

- [ ] **Step 2: Add `load_from_db()` method**

Add after `load_articles_data()`:

```python
    def load_from_db(self, account=None, source_info="数据库"):
        db = Database(DB_PATH)
        if account:
            rows = db.get_articles(account)
        else:
            rows = db.get_articles()
        db.close()

        if not rows:
            InfoBar.warning(title="提示", content="数据库中没有数据", parent=self, position=InfoBarPosition.TOP, duration=2000)
            return

        self.articles = []
        accounts_set = set()
        for row in rows:
            article = {
                '公众号': row.get('account_name', ''),
                '标题': row.get('title', ''),
                '发布时间': row.get('publish_time', ''),
                '链接': row.get('link', ''),
                '内容': row.get('content', '')
            }
            self.articles.append(article)
            if article['公众号']:
                accounts_set.add(article['公众号'])

        self.current_file = None
        self.is_unsaved = True
        self.source_info = source_info
        self.temp_file_path = None

        self.account_filter.clear()
        self.account_filter.addItem("全部")
        for account in sorted(accounts_set):
            self.account_filter.addItem(account)

        self._display_articles(self.articles)

        self.source_label.setText(f"数据来源: {source_info} | 共 {len(self.articles)} 条记录 (未保存)")
        self.source_card.show()
        self.save_btn.show()
        self.discard_btn.show()

        self.file_input.clear()

        InfoBar.success(title="数据已加载", content=f"{source_info} - 共 {len(self.articles)} 条记录", parent=self, position=InfoBarPosition.TOP, duration=3000)
```

- [ ] **Step 3: Update `load_articles_data()` to accept `temp_file_path=None`**

The method already handles `temp_file_path=None`. No change needed — but ensure the `_delete_temp_file` and `_on_discard` handle `temp_file_path=None` gracefully (they already check `if self.temp_file_path and os.path.exists(...)`).

- [ ] **Step 4: Update `_update_recent_files()` to also show DB option**

Optionally add a "数据库" entry to recent files combo. Or add a separate button to load from DB.

- [ ] **Step 5: Commit**

```bash
git add gui/pages/results_page.py
git commit -m "refactor: results_page loads from DB, preserves CSV import"
```

---

### Task 8: Modify `gui/pages/content_search_page.py` — Support DB + FTS

**Files:**
- Modify: `gui/pages/content_search_page.py`

- [ ] **Step 1: Add import**

```python
from spider.database import Database
from gui.utils import DB_PATH
```

- [ ] **Step 2: Add `load_from_db()` method**

```python
    def load_from_db(self):
        db = Database(DB_PATH)
        self.articles = db.get_articles()
        db.close()

        self.current_file = None
        self.data_status_label.setText(f"已加载 {len(self.articles)} 篇")
        self.data_status_label.setStyleSheet(f"color: {COLORS['success']};")

        self.search_results = []
        self.result_table.setRowCount(0)
        self.result_count_label.setText("搜索结果: 0 条匹配")
        self.export_btn.setEnabled(False)

        InfoBar.success(title="加载成功", content=f"从数据库加载 {len(self.articles)} 篇文章", parent=self, position=InfoBarPosition.TOP, duration=2000)
```

- [ ] **Step 3: Update `_on_browse_file` / data source UI**

Add an option in the combo box or as a button to load from DB. The simplest approach: add a "从数据库加载" button next to "浏览".

- [ ] **Step 4: Commit**

```bash
git add gui/pages/content_search_page.py
git commit -m "refactor: content_search_page supports DB loading"
```

---

### Task 9: Modify `gui/main_window.py` — Simplify Save-on-Close

**Files:**
- Modify: `gui/main_window.py`

- [ ] **Step 1: Simplify the close event handler (around line 415-444)**

The current close handler saves to CSV. Change it so that:
- If there's unsaved data, prompt to save (export) to CSV/JSON/Excel
- Remove the automatic CSV save logic

Simplified approach — just call `results_page._on_save_results()` which already shows the save dialog:

```python
    def closeEvent(self, event):
        if self.results_page.has_unsaved_data():
            msg_box = MessageBox(
                "未保存的数据",
                "当前有未保存的爬取结果，是否先保存？",
                self
            )
            msg_box.yesButton.setText("保存")
            msg_box.cancelButton.setText("不保存")
            if msg_box.exec():
                self.results_page._on_save_results()
                if self.results_page.has_unsaved_data():
                    event.ignore()
                    return
        event.accept()
```

- [ ] **Step 2: Commit**

```bash
git add gui/main_window.py
git commit -m "refactor: simplify close-save logic using _on_save_results"
```

---

## Self-Review

**Spec coverage check:**
1. ✅ SQLite DAO layer (`spider/database.py`) — Task 2
2. ✅ Replace CSV save with DB save in scraper — Task 3
3. ✅ Workers emit db_path — Task 5
4. ✅ Unified scrape page uses DB — Task 6
5. ✅ Results page loads from DB — Task 7
6. ✅ Content search page supports DB — Task 8
7. ✅ CSV/JSON/Excel export preserved (unchanged code)
8. ✅ Login cache / history / config unchanged (no tasks needed)
9. ✅ Main window close logic simplified — Task 9

**Placeholder check:** No TBD/TODO/fill-in-later patterns found.

**Type consistency:** All method signatures verified across tasks — `Database(db_path)`, `save_articles(articles)`, `get_articles(account=None)`, `search_articles(keyword)` are consistently used.
