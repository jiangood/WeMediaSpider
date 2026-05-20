# 后台爬虫 + Markdown 存储 + 按需 PDF — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将爬取页面改为公众号 CRUD，后台守护线程两阶段自动爬取，内容以 Markdown 存储，预览时渲染 Markdown，PDF 按需导出。

**Architecture:** 新增 `wechat_account` 表跟踪处理状态；恢复 `markdownify` 做 HTML→Markdown 转换；`BackgroundScrapeDaemon` 实现两阶段循环（优先列表、次之内容）；`ArticlePreviewDialog` 增加"下载PDF"按钮调用 `pdf_generator` 按需导出。

**Tech Stack:** Python 3.8+, PyQt6, qfluentwidgets, weasyprint, markdownify, BeautifulSoup, SQLite

---

### Task 1: 数据库 — 新增 `wechat_account` 表

**Files:**
- Modify: `spider/database.py`

- [ ] **Step 1: Add wechat_account table schema to `_init_schema()`**

在 `_init_schema()` 的 `executescript` 中的 `CREATE TABLE IF NOT EXISTS articles` 后面追加：
```sql
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
```

- [ ] **Step 2: Add CRUD methods to Database class**

在 `clear()` 方法之前添加：

```python
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

def get_accounts(self, status: Optional[str] = None) -> List[Dict]:
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

def get_list_done_accounts(self) -> List[Dict]:
    rows = self.conn.execute(
        "SELECT * FROM wechat_account WHERE status = 'list_done' ORDER BY created_at ASC"
    ).fetchall()
    return [dict(r) for r in rows]

def get_article_without_content(self) -> Optional[Dict]:
    row = self.conn.execute(
        "SELECT id, account_name, title, link FROM articles WHERE content IS NULL OR content = '' LIMIT 1"
    ).fetchone()
    return dict(row) if row else None
```

- [ ] **Step 3: 验证**

```bash
python -c "from spider.database import Database; db=Database('/tmp/test.db'); db.add_account('测试号'); print(db.get_accounts()); db.delete_account('测试号')"
```
预期：打印包含 `[{'name': '测试号', 'status': 'pending', ...}]` 的字典列表。

---

### Task 2: 内容格式 — 恢复 `markdownify` + 返回 Markdown

**Files:**
- Modify: `spider/wechat/utils.py`
- Modify: `spider/wechat/async_utils.py`
- Modify: `spider/wechat/scraper.py`

- [ ] **Step 1: Restore `ImageBlockConverter` and `md()` in utils.py**

在 `from spider.log.utils import logger` 之后、`def get_fakid` 之前插入：

```python
from markdownify import MarkdownConverter

class ImageBlockConverter(MarkdownConverter):
    def convert_img(self, el, text, parent_tags):
        alt = el.attrs.get('alt', None) or ''
        src = el.attrs.get('src', None) or ''
        if not src:
            src = el.attrs.get('data-src', None) or ''
        title = el.attrs.get('title', None) or ''
        title_part = ' "%s"' % title.replace('"', r'\"') if title else ''
        if ('_inline' in parent_tags
                and el.parent.name not in self.options['keep_inline_images_in']):
            return alt
        return '\n![%s](%s%s)\n' % (alt, src, title_part)

def md(soup, **options):
    return ImageBlockConverter(**options).convert_soup(soup)
```

在 `_extract_image_article_content` 函数中，遇到 `page_share_img` 类型的文章时，其返回的 Markdown 已经被 `_md_to_html` 包过，不需要再改。该函数保持现有逻辑。

- [ ] **Step 2: Change `get_article_content()` to return Markdown**

在 `get_article_content()` 函数中找到 `if content_ele:` 分支，将：
```python
content = str(content_ele[0])
```
改为：
```python
content = md(content_ele[0], keep_inline_images_in=["section", "span"])
```

同时更新图片类型文章的返回：
```python
# 原
if content and len(content.strip()) >= MIN_CONTENT_LENGTH:
    return _md_to_html(content)
# 改：图片类型文章本身输出的是简化的markdown格式，保留markdown
if content and len(content.strip()) >= MIN_CONTENT_LENGTH:
    return content
```

以及最后的兜底方法 `_extract_all_text_content` 恢复为 Markdown 输出：
```python
def _extract_all_text_content(soup):
    content_parts = []
    title_ele = soup.select_one('.rich_media_title, #activity-name, h1')
    if title_ele and title_ele.get_text(strip=True):
        content_parts.append(f"# {title_ele.get_text(strip=True)}\n")
    main_content_selectors = [
        '.rich_media_content', '#js_content', '.rich_media_area_primary',
        'article', '.article-content'
    ]
    for selector in main_content_selectors:
        ele = soup.select_one(selector)
        if ele:
            text = ele.get_text(separator='\n', strip=True)
            if text and len(text) > 20:
                content_parts.append(f"\n{text}\n")
                break
    images = soup.select('img[data-src], img[src*="mmbiz.qpic.cn"]')
    if images:
        content_parts.append("\n## 图片\n")
        for i, img in enumerate(images[:20], 1):
            src = img.get('data-src') or img.get('src') or ''
            if src and 'mmbiz.qpic.cn' in src and 'data:image' not in src:
                alt = img.get('alt') or f'图片{i}'
                content_parts.append(f"\n![{alt}]({src})\n")
    return ''.join(content_parts) if content_parts else ""
```

- [ ] **Step 3: Same restoration in async_utils.py**

在 `spider/wechat/async_utils.py` 中同样的位置恢复：
- `from markdownify import MarkdownConverter` 导入
- `ImageBlockConverter` 类
- `md()` 函数
- 修改 `AsyncWeChatClient` 中的 `_get_article_content` 方法，将 `str(content_ele[0])` 改为 `md(content_ele[0], keep_inline_images_in=["section", "span"])`
- 恢复 `_extract_all_text_content` 为 Markdown 版本（同上）

- [ ] **Step 4: Verify Markdown output**

```bash
python -c "
from spider.wechat.utils import get_article_content, md
from bs4 import BeautifulSoup
# md() test
html = '<div><p>Hello</p><img src=\"https://mmbiz.qpic.cn/test.jpg\"></div>'
soup = BeautifulSoup(html, 'lxml')
result = md(soup)
print(result)
assert '![' in result, 'Markdown should contain image syntax'
print('OK')
"
```
预期：输出包含 `![` (Markdown 图片语法) 和 `Hello` 的文本。

---

### Task 3: PDF 生成器 — `spider/wechat/pdf_generator.py`

**Files:**
- Create: `spider/wechat/pdf_generator.py`

- [ ] **Step 1: Create pdf_generator.py**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import re
import hashlib
import requests
from datetime import datetime

from spider.log.utils import logger


def _md_to_html(text):
    if not text:
        return text
    text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'<img src="\2" alt="\1">', text)
    text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    parts = []
    for line in lines:
        if not line.startswith('<'):
            parts.append(f'<p>{line}</p>')
        else:
            parts.append(line)
    return '\n'.join(parts)


def _download_images(markdown_text, image_dir):
    url_to_local = {}
    os.makedirs(image_dir, exist_ok=True)

    def _replace_img(match):
        alt = match.group(1)
        url = match.group(2)
        if not url or 'mmbiz.qpic.cn' not in url:
            return match.group(0)
        try:
            ext = '.jpg'
            if 'wx_fmt=' in url:
                fmt = re.search(r'wx_fmt=(\w+)', url)
                if fmt and fmt.group(1).lower() in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
                    ext = '.' + fmt.group(1).lower()
            filename = hashlib.md5(url.encode()).hexdigest()[:16] + ext
            filepath = os.path.join(image_dir, filename)
            if not os.path.exists(filepath):
                resp = requests.get(url, timeout=30, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                if resp.status_code == 200:
                    with open(filepath, 'wb') as f:
                        f.write(resp.content)
            url_to_local[url] = filepath
            return f'<img src="file:///{filepath}" alt="{alt}" style="max-width:100%;">'
        except Exception as e:
            logger.warning(f"下载图片失败: {url[:60]}... {e}")
            return match.group(0)

    html = _md_to_html(markdown_text)
    html = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', _replace_img, html)
    return html


def generate_article_pdf(
    article_title: str,
    account_name: str,
    markdown_content: str,
    output_dir: str,
    progress_callback=None
) -> str:
    safe_title = re.sub(r'[\\/:*?"<>|]', '', article_title).strip()[:100] or 'untitled'
    safe_account = re.sub(r'[\\/:*?"<>|]', '', account_name).strip()[:50] or 'unknown'
    pdf_name = f"{safe_account}_{safe_title}.pdf"
    pdf_path = os.path.join(output_dir, pdf_name)
    image_dir = os.path.join(output_dir, f"{safe_account}_{safe_title}")

    if progress_callback:
        progress_callback(0, 3, "正在下载图片...")
    html = _download_images(markdown_content, image_dir)

    if progress_callback:
        progress_callback(1, 3, "正在生成HTML...")
    full_html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif; padding: 30px; line-height: 1.8; color: #333; }}
h1 {{ font-size: 22px; text-align: center; color: #07C160; }}
h2 {{ font-size: 18px; margin-top: 20px; }}
img {{ max-width: 100%; height: auto; display: block; margin: 10px 0; }}
p {{ margin: 8px 0; }}
.meta {{ color: #888; font-size: 13px; text-align: center; margin-bottom: 20px; }}
</style></head><body>
<h1>{_escape_html(article_title)}</h1>
<div class="meta">公众号: {_escape_html(account_name)} | 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
{html}
</body></html>'''

    if progress_callback:
        progress_callback(2, 3, "正在导出PDF...")
    try:
        from weasyprint import HTML as WeasyHTML
        WeasyHTML(string=full_html).write_pdf(pdf_path)
        if progress_callback:
            progress_callback(3, 3, "PDF导出完成")
        return pdf_path
    except Exception as e:
        logger.error(f"PDF生成失败: {e}")
        raise


def _escape_html(text):
    if not text:
        return ''
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;'))
```

---

### Task 4: 后台守护线程 — `BackgroundScrapeDaemon`

**Files:**
- Modify: `gui/workers.py`

- [ ] **Step 1: Add `BackgroundScrapeDaemon` class**

在 `spider/database` import 之后、`class BatchScrapeWorker` 之前添加：

```python
class BackgroundScrapeDaemon(QThread):
    log_message = pyqtSignal(str)
    account_status_changed = pyqtSignal(str, str)
    phase_changed = pyqtSignal(str)

    def __init__(self, login_manager, parent=None):
        super().__init__(parent)
        self.login_manager = login_manager
        self.is_running = True
        self.request_interval = 10
        self._load_config()

    def _load_config(self):
        import json
        try:
            with open('config.json', 'r') as f:
                cfg = json.load(f)
                self.request_interval = int(cfg.get('request_interval', 10))
        except:
            pass

    def stop(self):
        self.is_running = False

    def _log(self, msg, level='info'):
        from datetime import datetime
        prefix = {'info': '', 'success': '✅ ', 'warning': '⚠️ ', 'error': '❌ '}
        self.log_message.emit(f"[{datetime.now().strftime('%H:%M:%S')}] {prefix.get(level, '')}{msg}")

    def run(self):
        while self.is_running:
            # 等待登录
            if not self.login_manager.is_logged_in():
                self.phase_changed.emit('idle')
                self._log("等待登录...")
                for _ in range(60):
                    if not self.is_running:
                        return
                    self.msleep(1000)
                    if self.login_manager.is_logged_in():
                        break
                if not self.login_manager.is_logged_in():
                    self.msleep(30000)
                    continue

            token = self.login_manager.get_token()
            headers = self.login_manager.get_headers()
            if not token or not headers:
                self._log("登录凭证无效，等待重新登录", 'warning')
                self.msleep(30000)
                continue

            from spider.database import Database
            from gui.utils import DB_PATH

            db = Database(DB_PATH)

            try:
                # === 阶段一：爬取列表 ===
                account = db.get_pending_account()
                if account:
                    self.phase_changed.emit('list')
                    name = account['name']
                    date_range = account.get('date_range', '最近7天')
                    self._log(f"开始爬取列表: {name} ({date_range})")
                    self.account_status_changed.emit(name, 'processing')

                    try:
                        # 计算起止日期
                        from datetime import datetime, timedelta
                        today = datetime.now()
                        if date_range == "最近7天":
                            start = today - timedelta(days=6)
                        elif date_range == "本月":
                            start = today.replace(day=1)
                        elif date_range == "本季度":
                            quarter_start_month = ((today.month - 1) // 3) * 3 + 1
                            start = today.replace(month=quarter_start_month, day=1)
                        elif date_range == "本年":
                            start = today.replace(month=1, day=1)
                        elif date_range == "最近3年":
                            start = today.replace(year=today.year - 3, month=1, day=1)
                        elif date_range == "全部":
                            start = today.replace(year=today.year - 10, month=1, day=1)
                        else:
                            start = today - timedelta(days=6)
                        start_timestamp = int(start.timestamp())

                        from spider.wechat.utils import get_fakid, get_articles_list, format_time

                        search_results = get_fakid(headers, token, name)
                        if not search_results:
                            raise Exception(f"未找到公众号: {name}")

                        fakeid = search_results[0]['wpub_fakid']

                        all_articles = []
                        page_start = 0
                        for page in range(100):
                            if not self.is_running:
                                break
                            titles, links, update_times = get_articles_list(
                                page_num=1, start_page=page_start,
                                fakeid=fakeid, token=token, headers=headers
                            )
                            if not titles:
                                break
                            page_has_valid = False
                            for title, link, utime in zip(titles, links, update_times):
                                ts = int(utime)
                                if ts >= start_timestamp:
                                    page_has_valid = True
                                    all_articles.append({
                                        'name': name, 'title': title, 'link': link,
                                        'publish_timestamp': ts,
                                        'publish_time': format_time(utime),
                                        'content': ''
                                    })
                            if not page_has_valid:
                                break
                            page_start += 5
                            self.msleep(random.randint(1000, 2000))

                        # 批量保存到数据库
                        if all_articles:
                            saved = db.save_articles(all_articles)
                        else:
                            saved = 0

                        db.update_account_status(name, 'list_done', total_articles=saved)
                        self._log(f"{name}: 列表完成，{saved} 篇文章", 'success')
                        self.account_status_changed.emit(name, 'list_done')
                        continue  # 回到循环头，继续处理下一个pending账号

                    except Exception as e:
                        db.update_account_status(name, 'error', error_message=str(e))
                        self._log(f"{name}: 列表爬取失败 - {e}", 'error')
                        self.account_status_changed.emit(name, 'error')
                        continue

                # === 阶段二：爬取内容 ===
                article = db.get_article_without_content()
                if article:
                    self.phase_changed.emit('content')
                    article_id = article['id']
                    article_title = article['title']
                    article_link = article['link']
                    account_name = article['account_name']
                    self._log(f"获取正文: {account_name} - {article_title[:40]}")

                    from spider.wechat.utils import get_article_content
                    # 确保使用正确的headers
                    content_headers = headers
                    article_data = {'link': article_link}
                    from spider.wechat.scraper import WeChatScraper
                    scraper = WeChatScraper(token, headers)
                    result = scraper.get_article_content_by_url(article_data)
                    markdown_content = result.get('content', '')

                    if markdown_content and not markdown_content.startswith('获取内容失败'):
                        db.conn.execute(
                            "UPDATE articles SET content = ? WHERE id = ?",
                            (markdown_content, article_id)
                        )
                        db.conn.commit()
                        self._log(f"正文完成: {account_name} - {article_title[:40]}", 'success')

                    # 请求间隔（反爬）
                    import random
                    delay = random.uniform(self.request_interval * 0.8, self.request_interval * 1.2)
                    for _ in range(int(delay * 10)):
                        if not self.is_running:
                            break
                        self.msleep(100)
                    continue  # 回到循环头 → 再次检查pending账号

                # === 无事可做 ===
                self.phase_changed.emit('idle')
                self._log("等待新任务...")
                for _ in range(300):
                    if not self.is_running:
                        break
                    self.msleep(100)

            except Exception as e:
                self._log(f"守护线程异常: {e}", 'error')
                self.msleep(5000)
            finally:
                db.close()
```

---

### Task 5: 全局状态指示器 — `ProcessingIndicator`

**Files:**
- Modify: `gui/widgets.py`

- [ ] **Step 1: Add `ProcessingIndicator` class**

在 `gui/widgets.py` 文件末尾（`HistoryTagsContainer` 类之后）添加：

```python
class ProcessingIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 'idle'
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 3, 10, 3)
        layout.setSpacing(6)
        self.dot = QLabel("●")
        self.dot.setStyleSheet("color: #888; font-size: 10px;")
        self.label = BodyLabel("就绪")
        self.label.setStyleSheet("color: #aaa; font-size: 11px; background: transparent; border: none;")
        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        self.setStyleSheet("""
            ProcessingIndicator {
                background-color: rgba(30, 30, 30, 0.92);
                border: 1px solid #333;
                border-radius: 6px;
            }
        """)
        self.setFixedHeight(30)
        self.adjustSize()

    def set_phase(self, phase: str, message: str = ''):
        self._phase = phase
        colors = {'idle': '#888', 'list': '#5B9BD5', 'content': '#07C160', 'error': '#FA5151'}
        labels = {'idle': '就绪', 'list': '爬取列表中', 'content': '爬取内容中', 'error': '出错'}
        color = colors.get(phase, '#888')
        label = message or labels.get(phase, '')
        self.dot.setStyleSheet(f"color: {color}; font-size: 10px;")
        self.label.setText(label)
        self.adjustSize()

    def set_message(self, msg: str):
        self.label.setText(msg)
        self.adjustSize()
```

确保导入 `QHBoxLayout`、`QLabel`（已有）。

---

### Task 6: 公众号管理页面 — 重写 `unified_scrape_page.py`

**Files:**
- Rewrite: `gui/pages/unified_scrape_page.py`

- [ ] **Step 1: Rewrite the entire file**

用以下内容替换 `gui/pages/unified_scrape_page.py`：

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QHeaderView, QTableWidgetItem, QTextEdit
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from datetime import datetime

from qfluentwidgets import (
    TitleLabel, BodyLabel, CaptionLabel, CardWidget,
    PrimaryPushButton, PushButton, LineEdit, ComboBox,
    InfoBar, InfoBarPosition, FluentIcon,
)
from qfluentwidgets import TableWidget as FluentTable

from ..styles import COLORS
from spider.database import Database
from gui.utils import DB_PATH


class UnifiedScrapePage(QWidget):
    scrape_completed = pyqtSignal(list, str, str)
    account_added = pyqtSignal(str)

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

        self.name_input = LineEdit()
        self.name_input.setPlaceholderText("输入公众号名称，回车添加")
        add_layout.addWidget(self.name_input, 1)

        self.date_combo = ComboBox()
        self.date_combo.addItems(["最近7天", "本月", "本季度", "本年", "最近3年", "全部"])
        self.date_combo.setCurrentIndex(0)
        self.date_combo.setMinimumWidth(120)
        add_layout.addWidget(self.date_combo)

        self.add_btn = PrimaryPushButton("添加", icon=FluentIcon.ADD)
        self.add_btn.setFixedWidth(100)
        add_layout.addWidget(self.add_btn)
        layout.addWidget(add_card)

        # === 账号表格 ===
        table_card = CardWidget()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(16, 12, 16, 12)
        table_layout.setSpacing(6)

        table_title = BodyLabel("已添加的公众号")
        table_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #0078d4;")
        table_layout.addWidget(table_title)

        self.account_table = FluentTable()
        self.account_table.setColumnCount(6)
        self.account_table.setHorizontalHeaderLabels(["公众号", "状态", "文章数", "时间范围", "添加时间", "操作"])
        self.account_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.account_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.verticalHeader().setVisible(False)
        table_layout.addWidget(self.account_table, 1)
        layout.addWidget(table_card, 1)

        # === 日志面板 ===
        log_card = CardWidget()
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(16, 8, 16, 8)
        log_layout.setSpacing(4)

        log_header = QHBoxLayout()
        log_title = BodyLabel("运行日志")
        log_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #0078d4;")
        log_header.addWidget(log_title)
        log_header.addStretch()

        self.clear_log_btn = PushButton("清空日志", icon=FluentIcon.DELETE)
        self.clear_log_btn.setFixedHeight(26)
        self.clear_log_btn.clicked.connect(lambda: self.log_text.clear())
        log_header.addWidget(self.clear_log_btn)

        log_layout.addLayout(log_header)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: #111;
                color: #ccc;
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
            }}
        """)
        self.log_text.setMinimumHeight(120)
        self.log_text.setMaximumHeight(200)
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_card)

        self.name_input.returnPressed.connect(self._on_add_account)
        self.add_btn.clicked.connect(self._on_add_account)

    def _on_add_account(self):
        name = self.name_input.text().strip()
        if not name:
            InfoBar.warning(title="提示", content="请输入公众号名称", parent=self, position=InfoBarPosition.TOP, duration=2000)
            return
        date_range = self.date_combo.currentText()
        db = Database(DB_PATH)
        try:
            if db.add_account(name, date_range):
                InfoBar.success(title="已添加", content=f"{name} 已加入爬取队列", parent=self, position=InfoBarPosition.TOP, duration=2000)
                self.name_input.clear()
                self.account_added.emit(name)
                self._refresh_table()
            else:
                InfoBar.warning(title="提示", content=f"{name} 已存在", parent=self, position=InfoBarPosition.TOP, duration=2000)
        finally:
            db.close()

    def _refresh_table(self):
        db = Database(DB_PATH)
        try:
            accounts = db.get_accounts()
            status_map = {
                'pending': '等待列表', 'list_done': '列表完成',
                'processing': '处理中', 'completed': '已完成', 'error': '出错'
            }
            self.account_table.setRowCount(len(accounts))
            for i, acc in enumerate(accounts):
                self.account_table.setItem(i, 0, QTableWidgetItem(acc.get('name', '')))
                status = acc.get('status', '')
                status_item = QTableWidgetItem(status_map.get(status, status))
                color_map = {'completed': COLORS['success'], 'error': COLORS['error'],
                             'processing': COLORS['warning'], 'list_done': COLORS['success']}
                status_item.setForeground(QColor(color_map.get(status, COLORS['text_secondary'])))
                self.account_table.setItem(i, 1, status_item)
                self.account_table.setItem(i, 2, QTableWidgetItem(str(acc.get('total_articles', 0))))
                self.account_table.setItem(i, 3, QTableWidgetItem(acc.get('date_range', '')))
                created = acc.get('created_at', '')
                if created:
                    try:
                        created = datetime.strptime(created, '%Y-%m-%d %H:%M:%S').strftime('%m-%d %H:%M')
                    except:
                        pass
                self.account_table.setItem(i, 4, QTableWidgetItem(created))
                container = QWidget()
                btn_layout = QHBoxLayout(container)
                btn_layout.setContentsMargins(2, 2, 2, 2)
                btn_layout.setSpacing(4)
                del_btn = PushButton("删除")
                del_btn.setFixedSize(50, 26)
                name = acc['name']
                del_btn.clicked.connect(lambda checked, n=name: self._on_delete_account(n))
                btn_layout.addWidget(del_btn)
                if status == 'error':
                    retry_btn = PushButton("重试")
                    retry_btn.setFixedSize(50, 26)
                    retry_btn.clicked.connect(lambda checked, n=name: self._on_retry_account(n))
                    btn_layout.addWidget(retry_btn)
                self.account_table.setCellWidget(i, 5, container)
        finally:
            db.close()

    def _on_delete_account(self, name):
        db = Database(DB_PATH)
        try:
            db.delete_account(name)
            self._refresh_table()
        finally:
            db.close()

    def _on_retry_account(self, name):
        db = Database(DB_PATH)
        try:
            db.update_account_status(name, 'pending')
            self._refresh_table()
        finally:
            db.close()

    def append_log(self, message: str):
        self.log_text.append(message)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
```

---

### Task 7: 预览对话框 — Markdown 渲染 + "下载PDF"按钮

**Files:**
- Modify: `gui/widgets.py` (ArticlePreviewDialog)

- [ ] **Step 1: Update `ArticlePreviewDialog`**

找到 `ArticlePreviewDialog._setup_ui()` 方法，在 `toolbar_layout` 的"在浏览器中打开"按钮之后、`close_btn` 之前添加：

```python
# 下载PDF按钮
self.download_pdf_btn = PrimaryPushButton("下载PDF", icon=FluentIcon.SAVE)
self.download_pdf_btn.setFixedWidth(120)
self.download_pdf_btn.clicked.connect(self._on_download_pdf)
toolbar_layout.addWidget(self.download_pdf_btn)
```

更新 `_update_display()` 方法的"更新内容"部分，将：
```python
content = article.get('内容', '')
if content:
    self.content_text.setHtml(content, QUrl("https://mp.weixin.qq.com"))
else:
    self.content_text.setHtml(...)
```
改为：
```python
content = article.get('内容', '')
if content:
    html = self._md_to_html(content)
    self.content_text.setHtml(html, QUrl("https://mp.weixin.qq.com"))
else:
    self.content_text.setHtml(...)
```

同时更新 "打开链接按钮" 的状态检查，添加下载按钮状态：
```python
self.download_pdf_btn.setEnabled(True)
```

在类中添加 `_md_to_html` 方法和 `_on_download_pdf` 方法：

```python
def _md_to_html(self, text):
    if not text:
        return '<html><body style="color:#999;text-align:center;padding:40px;background:#1e1e1e;font-size:16px;">无内容</body></html>'
    import re
    text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'<img src="\2" alt="\1" style="max-width:100%;">', text)
    text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    parts = []
    for line in lines:
        if not line.startswith('<'):
            parts.append(f'<p>{line}</p>')
        else:
            parts.append(line)
    body = '\n'.join(parts)
    return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif; padding: 20px; line-height: 1.8; color: #333; background: #fff; }}
img {{ max-width: 100%; height: auto; }}
p {{ margin: 8px 0; }}
</style></head><body>
{body}
</body></html>'''

def _on_download_pdf(self):
    if not self.articles or self.current_index >= len(self.articles):
        return
    article = self.articles[self.current_index]
    title = article.get('标题', '无标题')
    account = article.get('公众号', '')
    content = article.get('内容', '')

    from PyQt6.QtWidgets import QFileDialog
    safe_title = ''.join(c for c in title if c not in r'\/:*?"<>|')[:100] or 'untitled'
    safe_account = ''.join(c for c in account if c not in r'\/:*?"<>|')[:50] or 'unknown'
    default_name = f"{safe_account}_{safe_title}.pdf"
    file_path, _ = QFileDialog.getSaveFileName(
        self, "导出PDF", default_name, "PDF文件 (*.pdf)"
    )
    if not file_path:
        return

    from spider.wechat.pdf_generator import generate_article_pdf
    try:
        pdf_path = generate_article_pdf(
            article_title=title,
            account_name=account,
            markdown_content=content,
            output_dir=os.path.dirname(file_path),
        )
        import shutil
        if pdf_path != file_path:
            shutil.move(pdf_path, file_path)
        InfoBar.success(
            title="PDF导出成功",
            content=f"已保存到 {file_path}",
            parent=self,
            position=InfoBarPosition.TOP,
            duration=3000
        )
    except Exception as e:
        InfoBar.error(
            title="PDF导出失败",
            content=str(e),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=5000
        )
```

---

### Task 8: 主窗口 — 初始化后台线程和状态指示器

**Files:**
- Modify: `gui/main_window.py`

- [ ] **Step 1: 在 `_create_pages()` 之后初始化守护线程和指示器**

在 `_connect_signals()` 方法中或末尾添加：

```python
from .workers import BackgroundScrapeDaemon
from .widgets import ProcessingIndicator

# 后台守护线程
self.daemon = BackgroundScrapeDaemon(self.login_page.get_login_manager())
self.daemon.log_message.connect(self._on_daemon_log)
self.daemon.account_status_changed.connect(self._on_account_status_changed)
self.daemon.phase_changed.connect(self._on_phase_changed)
self.daemon.start()

# 全局状态指示器
self.processing_indicator = ProcessingIndicator(self)
self.processing_indicator.show()

# 连接scrape_page的account_added信号
self.scrape_page.account_added.connect(self._on_account_added)
```

添加对应的槽方法：

```python
def _on_daemon_log(self, message: str):
    self.scrape_page.append_log(message)

def _on_account_status_changed(self, account_name: str, status: str):
    self.scrape_page._refresh_table()

def _on_phase_changed(self, phase: str):
    labels = {'idle': '就绪', 'list': '爬取列表中', 'content': '爬取内容中', 'error': '出错'}
    self.processing_indicator.set_phase(phase, labels.get(phase, ''))

def _on_account_added(self, name: str):
    pass  # 表格已自动刷新

def resizeEvent(self, event):
    super().resizeEvent(event)
    if hasattr(self, 'processing_indicator'):
        ind = self.processing_indicator
        ind.setGeometry(self.width() - ind.width() - 16, self.height() - ind.height() - 40, ind.width(), ind.height())
```

修改 `closeEvent` 确保守护线程退出：

```python
def closeEvent(self, event: QCloseEvent):
    if hasattr(self, 'daemon'):
        self.daemon.stop()
        self.daemon.wait(3000)
    event.accept()
```

---

### Task 9: 依赖项

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add dependencies**

在 `requirements.txt` 中追加：
```
markdownify
weasyprint
```

---

### Task 10: 清理 `scraper.py` 旧版 PDF 代码

**Files:**
- Modify: `spider/wechat/scraper.py`

- [ ] **Step 1: 移除之前添加的 PDF 生成逻辑**

在 `_scrape_single_account()` 方法中，删除以下代码（如果存在）：
```python
from spider.wechat.pdf_generator import generate_article_pdf
generate_article_pdf(article, account_name, ...)
```

确保 `_scrape_single_account()` 中只保留内容获取 + sleep 间隔逻辑。

---

## 自检清单

1. **Spec coverage**:
   - ✅ `wechat_account` 表 (Task 1)
   - ✅ Markdown 存储恢复 (Task 2)
   - ✅ 两阶段爬取：列表优先 (Task 4)
   - ✅ 新增/修改公众号优先爬列表 (Task 4 主循环设计)
   - ✅ `ProcessingIndicator` 全局状态指示 (Task 5)
   - ✅ 账号管理页面 (Task 6)
   - ✅ 预览 Markdown 渲染 (Task 7)
   - ✅ "下载PDF"按钮 (Task 7)
   - ✅ PDF 生成器按需调用 (Task 3)
   - ✅ 后台线程日志面板 (Task 6 + 8)

2. **Placeholder check**: 无占位符，所有代码完整。

3. **Type consistency**: `generate_article_pdf` 签名在 Task 3 和 Task 7 一致。`Database` 方法签名在 Task 1 和 Task 4/6 一致。
