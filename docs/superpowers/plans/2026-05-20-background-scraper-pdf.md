# 后台爬虫 + PDF 自动生成 — 实施计划

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 爬取页面改为公众号 CRUD 管理，后台守护线程自动轮询爬取 + 下载图片 + 生成 PDF，预览加载本地 PDF

**Architecture:** DB 新增 `wechat_account` 表跟踪状态；后台守护线程轮询 pending 账号，复用现有 `BatchWeChatScraper` 逐个处理；PDF 生成（weasyprint）插入内容获取步骤后，利用请求间隔时间；右下角全局 `ProcessingIndicator` 实时显示状态

**Tech Stack:** Python 3, PyQt6, qfluentwidgets, weasyprint (new), SQLite

---

### Task 1: 数据库 — `wechat_account` 表

**Files:**
- Modify: `spider/database.py`

- [ ] **Step 1: 添加 `wechat_account` 表和 CRUD 方法**

在 `Database` 类末尾（`close` 方法之前或之后）新增：

```python
def init_account_table(self):
    self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS wechat_account (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'pending',
            error_message TEXT DEFAULT '',
            total_articles INTEGER DEFAULT 0,
            date_range TEXT DEFAULT '最近7天',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
    """)
    self.conn.commit()

def add_account(self, name: str, date_range: str = '最近7天') -> bool:
    try:
        self.conn.execute(
            "INSERT INTO wechat_account (name, date_range) VALUES (?, ?)",
            (name, date_range)
        )
        self.conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def delete_account(self, name: str) -> bool:
    cursor = self.conn.execute("DELETE FROM wechat_account WHERE name = ?", (name,))
    self.conn.commit()
    return cursor.rowcount > 0

def get_pending_account(self) -> Optional[dict]:
    row = self.conn.execute(
        "SELECT id, name, date_range FROM wechat_account WHERE status = 'pending' ORDER BY id ASC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None

def get_accounts(self, status: Optional[str] = None) -> List[Dict]:
    if status:
        rows = self.conn.execute(
            "SELECT name, status, total_articles, date_range, created_at, error_message FROM wechat_account WHERE status = ? ORDER BY created_at DESC",
            (status,)
        ).fetchall()
    else:
        rows = self.conn.execute(
            "SELECT name, status, total_articles, date_range, created_at, error_message FROM wechat_account ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]

def update_account_status(self, name: str, status: str, error_message: str = '', total_articles: int = 0):
    self.conn.execute(
        "UPDATE wechat_account SET status = ?, error_message = ?, total_articles = ?, updated_at = datetime('now','localtime') WHERE name = ?",
        (status, error_message, total_articles, name)
    )
    self.conn.commit()
```

在 `_init_schema()` 末尾添加 `self.init_account_table()` 调用：

```python
def _init_schema(self):
    # ... existing schema ...
    self.init_account_table()
```

在文件顶部 imports 添加 `from typing import List, Dict, Optional`（已有则跳过）。

---

### Task 2: PDF 生成器模块

**Files:**
- Create: `spider/wechat/pdf_generator.py`

- [ ] **Step 1: 创建 pdf_generator.py**

```python
import os
import re
import time
import random
import requests

def generate_article_pdf(
    article: dict,
    account_name: str,
    output_root: str,
) -> dict:
    title = article.get('title', 'untitled')
    content_html = article.get('content', '')

    safe_account = _sanitize_filename(str(account_name))
    safe_title = _sanitize_filename(str(title))
    stem = f"{safe_account}_{safe_title}"
    pdf_dir = os.path.join(output_root, safe_account)
    images_dir = os.path.join(pdf_dir, stem)

    os.makedirs(images_dir, exist_ok=True)

    pdf_path = os.path.join(pdf_dir, f"{stem}.pdf")

    if not content_html or content_html.startswith('获取'):
        _write_text_pdf(content_html or '无内容', pdf_path)
        return {'pdf_path': pdf_path, 'images_dir': images_dir}

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(content_html, 'lxml')

    url_to_local = {}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    for i, img in enumerate(soup.find_all('img')):
        src = img.get('src') or img.get('data-src') or ''
        if not src or 'mmbiz.qpic.cn' not in src:
            img.decompose()
            continue

        try:
            ext = _get_image_extension(src)
            local_name = f"{i + 1}{ext}"
            local_path = os.path.join(images_dir, local_name)

            resp = requests.get(src, headers=headers, timeout=30)
            if resp.status_code == 200:
                raw = resp.content
                if ext == '.webp':
                    from io import BytesIO
                    from PIL import Image
                    pil_img = Image.open(BytesIO(raw)).convert('RGB')
                    local_name = f"{i + 1}.png"
                    local_path = os.path.join(images_dir, local_name)
                    pil_img.save(local_path, 'PNG')
                else:
                    with open(local_path, 'wb') as f:
                        f.write(raw)

                url_to_local[src] = local_path

            time.sleep(random.uniform(0.3, 0.5))

        except Exception:
            img.decompose()

    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or ''
        local = url_to_local.get(src)
        if local:
            local_url = local.replace('\\', '/')
            img['src'] = f"file:///{local_url}"
        else:
            img.decompose()

    html = str(soup)
    full_html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif; padding: 20px; line-height: 1.8; color: #333; }}
img {{ max-width: 100%; height: auto; }}
p {{ margin: 8px 0; }}
h1 {{ font-size: 22px; }}
</style></head><body>
<h1>{_escape_html(title)}</h1>
{html}
</body></html>'''

    _html_to_pdf(full_html, pdf_path)
    return {'pdf_path': pdf_path, 'images_dir': images_dir}


def _html_to_pdf(html: str, pdf_path: str):
    from weasyprint import HTML
    HTML(string=html).write_pdf(pdf_path)


def _write_text_pdf(text: str, pdf_path: str):
    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>body {{ font-family: 'Microsoft YaHei', sans-serif; padding: 20px; }}</style>
</head><body><p>{_escape_html(text)}</p></body></html>'''
    _html_to_pdf(html, pdf_path)


def _get_image_extension(url: str) -> str:
    if 'wx_fmt=' in url:
        m = re.search(r'wx_fmt=(\w+)', url)
        if m:
            fmt = m.group(1).lower()
            if fmt in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
                return f'.{fmt}'
    if '.png' in url.lower():
        return '.png'
    if '.jpg' in url.lower() or '.jpeg' in url.lower():
        return '.jpg'
    if '.gif' in url.lower():
        return '.gif'
    if '.webp' in url.lower():
        return '.webp'
    return '.jpg'


def _sanitize_filename(name: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|]', '', name).strip()
    return safe[:120] or 'untitled'


def _escape_html(text: str) -> str:
    if not text:
        return ''
    return (str(text).replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))
```

---

### Task 3: 爬虫 — 集成 PDF 生成

**Files:**
- Modify: `spider/wechat/scraper.py`

- [ ] **Step 1: 在 `_scrape_single_account` 内容获取后插入 PDF 生成**

找到 `_scrape_single_account` 方法中获取内容后的循环（约 590-615 行）：

```python
for i, article in enumerate(articles_in_range):
    if self.is_cancelled:
        break

    self._trigger_content_progress(
        i + 1, total_content,
        f"{account_name}: 正在获取第 {i+1}/{total_content} 篇文章内容"
    )

    if article.get('link') in existing_links:
        continue

    try:
        article = self.scraper.get_article_content_by_url(article)

        # === 新增：PDF 生成（利用请求间隔时间）===
        self._trigger_account_status(account_name, "pdf_generating",
            f"正在生成PDF: {article.get('title', '')[:30]}")
        try:
            from spider.wechat.pdf_generator import generate_article_pdf
            generate_article_pdf(
                article, account_name,
                config.get('download_dir', './download/')
            )
        except Exception as pdf_err:
            logger.warning(f"PDF生成失败: {pdf_err}")
        # ====================================

        if i < len(articles_in_range) - 1:
            delay = random.uniform(1, config.get('request_interval', 60) / 10)
            time.sleep(delay)

    except Exception as e:
        logger.error(f"获取文章内容失败: {e}")
        continue
```

注意：需要在文件顶部确保 `from spider.log.utils import logger` 已导入。

---

### Task 4: 账号管理页面

**Files:**
- Modify: `gui/pages/unified_scrape_page.py`
- Reference: `gui/styles.py` (COLORS)

- [ ] **Step 1: 重写 `unified_scrape_page.py` 为账号管理界面**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公众号管理页面 — CRUD + 后台日志
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QHeaderView, QTableWidgetItem,
    QTextEdit, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QTextCursor
from datetime import datetime

from qfluentwidgets import (
    TitleLabel, BodyLabel, CaptionLabel, CardWidget,
    PrimaryPushButton, PushButton, LineEdit, ComboBox,
    InfoBar, InfoBarPosition, FluentIcon,
)
from qfluentwidgets import TableWidget as FluentTable

from ..styles import COLORS
from spider.database import Database
from ..utils import DB_PATH


LOG_COLORS = {
    'info': '#CCCCCC',
    'success': '#07C160',
    'warning': '#FFC300',
    'error': '#FA5151',
}


class UnifiedScrapePage(QWidget):

    account_status_changed = pyqtSignal(str, str, str)

    def __init__(self, login_manager, parent=None):
        super().__init__(parent)
        self.login_manager = login_manager
        self.setObjectName("unifiedScrapePage")
        self.setStyleSheet("background-color: #1a1a1a;")
        self._setup_ui()
        self._refresh_table()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)

        title = TitleLabel("公众号管理")
        layout.addWidget(title)

        # === 添加栏 ===
        add_card = CardWidget()
        add_layout = QHBoxLayout(add_card)
        add_layout.setContentsMargins(16, 12, 16, 12)
        add_layout.setSpacing(8)

        self.account_input = LineEdit()
        self.account_input.setPlaceholderText("输入公众号名称...")
        add_layout.addWidget(self.account_input, 1)

        self.date_combo = ComboBox()
        self.date_combo.addItems(["最近7天", "本月", "本季度", "本年", "最近3年", "全部"])
        self.date_combo.setCurrentIndex(0)
        self.date_combo.setMinimumWidth(120)
        add_layout.addWidget(self.date_combo)

        self.add_btn = PrimaryPushButton("添加", icon=FluentIcon.ADD)
        self.add_btn.setFixedWidth(100)
        self.add_btn.clicked.connect(self._on_add_account)
        add_layout.addWidget(self.add_btn)

        self.account_input.returnPressed.connect(self.add_btn.click)
        layout.addWidget(add_card)

        # === 账号表格 ===
        table_card = CardWidget()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(16, 12, 16, 12)
        table_layout.setSpacing(8)

        table_header = QHBoxLayout()
        table_title = BodyLabel("已添加的公众号")
        table_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #0078d4;")
        table_header.addWidget(table_title)
        table_header.addStretch()
        self.table_count_label = CaptionLabel("共 0 个")
        self.table_count_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        table_header.addWidget(self.table_count_label)
        table_layout.addLayout(table_header)

        self.account_table = FluentTable()
        self.account_table.setColumnCount(5)
        self.account_table.setHorizontalHeaderLabels(["公众号", "状态", "文章数", "时间范围", "操作"])
        self.account_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.account_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.setMinimumHeight(100)
        self.account_table.verticalHeader().setVisible(False)
        table_layout.addWidget(self.account_table, 1)

        layout.addWidget(table_card, 1)

        # === 日志面板 ===
        log_card = CardWidget()
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(16, 12, 16, 12)
        log_layout.setSpacing(6)

        log_header = QHBoxLayout()
        log_title = BodyLabel("运行日志")
        log_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #0078d4;")
        log_header.addWidget(log_title)
        log_header.addStretch()
        self.log_clear_btn = PushButton("清空", icon=FluentIcon.DELETE)
        self.log_clear_btn.setFixedWidth(80)
        self.log_clear_btn.clicked.connect(self._clear_log)
        log_header.addWidget(self.log_clear_btn)
        log_layout.addLayout(log_header)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: #111111;
                color: #CCCCCC;
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 10px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
            }}
        """)
        self.log_text.setMaximumHeight(180)
        log_layout.addWidget(self.log_text)

        layout.addWidget(log_card)

    def _refresh_table(self):
        try:
            db = Database(DB_PATH)
            accounts = db.get_accounts()
            db.close()
        except Exception:
            accounts = []

        self.account_table.setRowCount(len(accounts))
        for i, acc in enumerate(accounts):
            name_item = QTableWidgetItem(acc.get('name', ''))
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.account_table.setItem(i, 0, name_item)

            status = acc.get('status', '')
            status_map = {
                'pending': ('等待中', COLORS['text_secondary']),
                'processing': ('处理中', COLORS['primary']),
                'completed': ('已完成', COLORS['success']),
                'error': ('失败', COLORS['error']),
            }
            status_text, status_color = status_map.get(status, (status, COLORS['text_secondary']))
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setForeground(QColor(status_color))
            self.account_table.setItem(i, 1, status_item)

            count_item = QTableWidgetItem(str(acc.get('total_articles', 0)))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.account_table.setItem(i, 2, count_item)

            date_item = QTableWidgetItem(acc.get('date_range', ''))
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.account_table.setItem(i, 3, date_item)

            container = QWidget()
            btn_layout = QHBoxLayout(container)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(4)

            delete_btn = PushButton("删除")
            delete_btn.setFixedSize(60, 26)
            account_name = acc.get('name', '')
            delete_btn.clicked.connect(lambda checked, n=account_name: self._on_delete_account(n))
            btn_layout.addWidget(delete_btn)

            if status == 'error':
                retry_btn = PushButton("重试")
                retry_btn.setFixedSize(60, 26)
                retry_btn.clicked.connect(lambda checked, n=account_name: self._on_retry_account(n))
                btn_layout.addWidget(retry_btn)

            self.account_table.setCellWidget(i, 4, container)

        self.table_count_label.setText(f"共 {len(accounts)} 个")

    def _on_add_account(self):
        name = self.account_input.text().strip()
        if not name:
            InfoBar.warning(title="提示", content="请输入公众号名称", parent=self, position=InfoBarPosition.TOP, duration=2000)
            return
        if not self.login_manager.is_logged_in():
            InfoBar.warning(title="未登录", content="请先登录", parent=self, position=InfoBarPosition.TOP, duration=3000)
            return

        date_range = self.date_combo.currentText()
        try:
            db = Database(DB_PATH)
            ok = db.add_account(name, date_range)
            db.close()
        except Exception as e:
            InfoBar.error(title="添加失败", content=str(e), parent=self, position=InfoBarPosition.TOP, duration=3000)
            return

        if ok:
            self.account_input.clear()
            self._refresh_table()
            InfoBar.success(title="添加成功", content=f"已添加公众号: {name}", parent=self, position=InfoBarPosition.TOP, duration=2000)
        else:
            InfoBar.warning(title="重复", content=f"公众号已存在: {name}", parent=self, position=InfoBarPosition.TOP, duration=2000)

    def _on_delete_account(self, name):
        try:
            db = Database(DB_PATH)
            db.delete_account(name)
            db.close()
            self._refresh_table()
            InfoBar.info(title="已删除", content=name, parent=self, position=InfoBarPosition.TOP, duration=2000)
        except Exception as e:
            InfoBar.error(title="删除失败", content=str(e), parent=self, position=InfoBarPosition.TOP, duration=3000)

    def _on_retry_account(self, name):
        try:
            db = Database(DB_PATH)
            db.update_account_status(name, 'pending')
            db.close()
            self._refresh_table()
            InfoBar.info(title="已重试", content=name, parent=self, position=InfoBarPosition.TOP, duration=2000)
        except Exception as e:
            InfoBar.error(title="重试失败", content=str(e), parent=self, position=InfoBarPosition.TOP, duration=3000)

    def append_log(self, message: str, level: str = 'info'):
        """供后台线程调用的日志追加方法"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = LOG_COLORS.get(level, LOG_COLORS['info'])
        html = f'<span style="color: {color};">[{timestamp}] {message}</span><br>'
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
        self.log_text.insertHtml(html)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _clear_log(self):
        self.log_text.clear()

    def on_account_status_changed(self, account_name: str, status: str, message: str):
        """从后台线程接收账号状态变更，刷新表格"""
        self._refresh_table()
```

---

### Task 5: 后台守护线程

**Files:**
- Modify: `gui/workers.py`

- [ ] **Step 1: 在 `gui/workers.py` 末尾添加 `BackgroundScrapeDaemon`**

```python
class BackgroundScrapeDaemon(QThread):

    log_message = pyqtSignal(str, str)       # (message, level)
    account_status_changed = pyqtSignal(str, str, str)  # (name, status, message)

    def __init__(self, login_manager):
        super().__init__()
        self.login_manager = login_manager
        self._is_running = True
        self._current_account = None

    def stop(self):
        self._is_running = False
        if self._current_account:
            self._current_account.cancel_batch_scrape()

    def run(self):
        self.log_message.emit("后台线程已启动，等待登录...", "info")

        while self._is_running:
            # 等待登录就绪
            if not self.login_manager.is_logged_in():
                self.msleep(5000)
                continue

            token = self.login_manager.get_token()
            headers = self.login_manager.get_headers()
            if not token or not headers:
                self.msleep(5000)
                continue

            try:
                from spider.database import Database
                from gui.utils import DB_PATH
                db = Database(DB_PATH)
                pending = db.get_pending_account()
                db.close()
            except Exception as e:
                self.log_message.emit(f"查询数据库失败: {e}", "error")
                self.msleep(30000)
                continue

            if not pending:
                self.msleep(30000)
                continue

            account_name = pending['name']
            date_range = pending.get('date_range', '最近7天')

            self.log_message.emit(f"开始处理公众号: {account_name} (时间范围: {date_range})", "info")
            self._process_account(account_name, date_range, token, headers)

        self.log_message.emit("后台线程已停止", "info")

    def _process_account(self, account_name: str, date_range: str, token: str, headers: dict):
        from spider.database import Database
        from spider.wechat.scraper import BatchWeChatScraper
        from gui.utils import DB_PATH
        from datetime import datetime, timedelta

        # 日期范围 → 起止日期
        today = datetime.now()
        if date_range == "最近7天":
            start = today - timedelta(days=6)
        elif date_range == "本月":
            start = today.replace(day=1)
        elif date_range == "本季度":
            q = ((today.month - 1) // 3) * 3 + 1
            start = today.replace(month=q, day=1)
        elif date_range == "本年":
            start = today.replace(month=1, day=1)
        elif date_range == "最近3年":
            start = today.replace(year=today.year - 3, month=1, day=1)
        else:
            start = today.replace(year=today.year - 10, month=1, day=1)

        config = {
            'accounts': [account_name],
            'start_date': start.strftime("%Y-%m-%d"),
            'end_date': today.strftime("%Y-%m-%d"),
            'token': token,
            'headers': headers,
            'request_interval': 10,
            'include_content': True,
            'content_keyword_filter': '',
            'db_path': DB_PATH,
            'download_dir': os.path.join(os.getcwd(), 'download'),
        }

        scraper = BatchWeChatScraper()
        scraper.set_callback('account_status', self._on_scraper_status)
        scraper.set_callback('error_occurred', self._on_scraper_error)
        scraper.set_callback('article_progress', self._on_article_progress)
        scraper.set_callback('content_progress', self._on_content_progress)

        try:
            # 更新状态为 processing
            db = Database(DB_PATH)
            db.update_account_status(account_name, 'processing')
            db.close()
            self.account_status_changed.emit(account_name, 'processing', '')

            self.log_message.emit(f"正在搜索公众号: {account_name}", "info")

            articles = scraper.start_batch_scrape(config)

            if not self._is_running:
                return

            total = len(articles)
            db = Database(DB_PATH)
            db.update_account_status(account_name, 'completed', total_articles=total)
            db.close()
            self.account_status_changed.emit(account_name, 'completed', '')

            self.log_message.emit(f"完成！{account_name}: 共 {total} 篇文章", "success")

        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            self.log_message.emit(f"处理失败 {account_name}: {e}", "error")

            db = Database(DB_PATH)
            db.update_account_status(account_name, 'error', error_message=str(e))
            db.close()
            self.account_status_changed.emit(account_name, 'error', str(e))

    def _on_scraper_status(self, account_name, status, message):
        self.account_status_changed.emit(account_name, status, message)
        level = 'error' if status == 'error' else 'info'
        self.log_message.emit(f"{account_name}: {message}", level)

    def _on_scraper_error(self, account_name, error_message):
        self.log_message.emit(f"{account_name} 出错: {error_message}", "error")

    def _on_article_progress(self, count, message):
        self.log_message.emit(message, "info")

    def _on_content_progress(self, current, total, message):
        self.log_message.emit(message, "info")
```

在文件顶部添加 `import os` 如果还没有的话。

---

### Task 6: 全局状态指示器 + 预览加载 PDF

**Files:**
- Modify: `gui/widgets.py`

- [ ] **Step 1: 添加 `ProcessingIndicator` 类（在文件末尾 `HistoryTagsContainer` 之后）**

```python
class ProcessingIndicator(QWidget):
    """右下角悬浮状态指示器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 3, 10, 3)
        layout.setSpacing(6)

        self.dot = QLabel("●")
        self.dot.setStyleSheet("font-size: 10px; color: #888;")
        layout.addWidget(self.dot)

        self.label = BodyLabel("等待中")
        self.label.setStyleSheet("font-size: 11px; color: #aaa; background: transparent; border: none;")
        layout.addWidget(self.label)

        self.setStyleSheet(f"""
            ProcessingIndicatorsssss {{
                background-color: rgba(30, 30, 30, 0.92);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
            }}
        """)
        self._update_style()

    def _update_style(self):
        self.setStyleSheet(f"""
            #{self.objectName()} {{
                background-color: rgba(30, 30, 30, 0.92);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
            }}
        """)

    def set_idle(self, text="等待中"):
        self.dot.setStyleSheet("font-size: 10px; color: #888;")
        self.label.setText(text)

    def set_processing(self, text):
        self.dot.setStyleSheet("font-size: 10px; color: #07C160;")
        self.label.setText(text)

    def set_error(self, text):
        self.dot.setStyleSheet("font-size: 10px; color: #FA5151;")
        self.label.setText(text)

    def set_success(self, text):
        self.dot.setStyleSheet("font-size: 10px; color: #07C160;")
        self.label.setText(text)
```

注意：为了样式生效，需要在实例化后设置 `setObjectName("processingIndicator")`。

在文件顶部 imports 添加 `from PyQt6.QtWidgets import QLabel`（如果还没有）。

- [ ] **Step 2: 修改 `ArticlePreviewDialog._update_display()` 加载 PDF**

找到 `_update_display` 方法，修改内容渲染部分：

```python
def _update_display(self):
    if not self.articles:
        # ... existing empty state ...
        return

    article = self.articles[self.current_index]

    # 更新标题、元信息（保持不变）
    title = article.get('标题', '无标题')
    self.title_label.setText(title)
    self.setWindowTitle(f"文章预览 - {title}")

    account = article.get('公众号', '-')
    self.account_label.setText(f"公众号: {account}")

    pub_time = article.get('发布时间', '-')
    self.time_label.setText(f"发布时间: {pub_time}")

    # === 修改：尝试加载本地 PDF，失败回退 HTML ===
    pdf_path = self._find_pdf(article)
    if pdf_path and os.path.exists(pdf_path):
        self.content_text.setUrl(QUrl.fromLocalFile(pdf_path))
    else:
        content = article.get('内容', '')
        if content:
            self.content_text.setHtml(content, QUrl("https://mp.weixin.qq.com"))
        else:
            self.content_text.setHtml(
                "<html><body style='color:#999;text-align:center;padding:40px;background:#1e1e1e;font-size:16px;'>无内容</body></html>")

    self.content_text.page().runJavaScript("window.scrollTo(0,0)")
    self.count_label.setText(f"{self.current_index + 1} / {len(self.articles)}")
    self.prev_btn.setEnabled(self.current_index > 0)
    self.next_btn.setEnabled(self.current_index < len(self.articles) - 1)
    link = article.get('链接', '')
    self.open_link_btn.setEnabled(bool(link))
```

添加 `_find_pdf` 辅助方法：

```python
def _find_pdf(self, article) -> str:
    """根据文章信息查找对应的本地 PDF 路径"""
    from spider.wechat.pdf_generator import _sanitize_filename
    account_name = article.get('公众号', '')
    title = article.get('标题', '')
    if not account_name or not title:
        return ''

    safe_account = _sanitize_filename(account_name)
    safe_title = _sanitize_filename(title)
    stem = f"{safe_account}_{safe_title}"

    candidates = [
        os.path.join(os.getcwd(), 'download', safe_account, f"{stem}.pdf"),
        os.path.join(os.getcwd(), 'download', f"{stem}.pdf"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return ''
```

在文件顶部添加 `import os`。

---

### Task 7: 主窗口集成

**Files:**
- Modify: `gui/main_window.py`

- [ ] **Step 1: 初始化后台线程、状态指示器、连接信号**

修改 `_create_pages` 方法，在后添加后台线程和指示器创建。注意：需要在 `super().__init__()` 之后、页面创建之前或之后都可以。

在 `_connect_signals` 中添加信号连接：

```python
def _create_pages(self):
    # ... existing page creation ...
    self.settings_page = SettingsPage(self)

    # 初始化后台守护线程
    from .workers import BackgroundScrapeDaemon
    self.daemon = BackgroundScrapeDaemon(self.login_page.get_login_manager())
    self.daemon.log_message.connect(self._on_daemon_log)
    self.daemon.account_status_changed.connect(self._on_account_daemon_status)

    # 全局状态指示器
    from .widgets import ProcessingIndicator
    self.processing_indicator = ProcessingIndicator(self)
    self.processing_indicator.setObjectName("processingIndicator")
    self.processing_indicator.show()

    # 延迟应用标签透明背景
    QTimer.singleShot(100, self._apply_label_transparency)
```

修改 `_connect_signals`：

```python
def _connect_signals(self):
    # 爬取完成信号（保留兼容，但后台模式可能不用）
    self.scrape_page.scrape_completed.connect(self._on_scrape_completed)
    self.results_page.data_discarded.connect(self._on_data_discarded)
    self.settings_page.settings_changed.connect(self._on_settings_changed)
```

添加新的信号处理方法：

```python
def _on_daemon_log(self, message: str, level: str):
    """后台线程日志 → 转发到爬取页面的日志面板"""
    self.scrape_page.append_log(message, level)

def _on_account_daemon_status(self, account_name: str, status: str, message: str):
    """后台线程账号状态变更 → 刷新表格 + 更新全局指示器"""
    self.scrape_page.on_account_status_changed(account_name, status, message)

    if status == 'processing':
        self.processing_indicator.set_processing(f"正在处理: {account_name}")
    elif status == 'completed':
        self.processing_indicator.set_success(f"完成: {account_name}")
    elif status == 'error':
        self.processing_indicator.set_error(f"失败: {account_name}")
    else:
        self.processing_indicator.set_idle()

def closeEvent(self, event: QCloseEvent):
    """关闭时停止后台线程"""
    if hasattr(self, 'daemon'):
        self.daemon.stop()
        self.daemon.wait(5000)
    event.accept()
```

添加 `resizeEvent` 更新指示器位置：

```python
def resizeEvent(self, event):
    super().resizeEvent(event)
    if hasattr(self, 'processing_indicator'):
        bar_width = 280
        bar_height = 28
        x = self.width() - bar_width - 16
        y = self.height() - bar_height - 12
        self.processing_indicator.setGeometry(x, y, bar_width, bar_height)
```

需要添加 `resizeEvent` 导入：检查 `from PyQt6.QtGui import QCloseEvent` — 已有 QCloseEvent。需要添加 `from PyQt6.QtGui import QResizeEvent` 或者使用 `event: QCloseEvent` 的类似方式。实际上，重写 `resizeEvent` 不需要特别导入，因为它是 QWidget 的方法。

---

### Task 8: 依赖更新

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: 添加 weasyprint**

```txt
weasyprint
```

如果有固定的版本号行，追加即可。

---

### Task 9: 移除旧的 ImageExtractDialog 中重复的 PDF 生成代码（可选清理）

如果 `ImageExtractDialog` 中生成 PDF 的部分与新的 `pdf_generator.py` 重复，可清理。但为稳妥，可以保留不动。
```
