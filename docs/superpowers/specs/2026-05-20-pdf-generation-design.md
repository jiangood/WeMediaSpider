# 后台爬虫 + Markdown 存储 + 按需 PDF

## Summary

- 爬取页面改为公众号 CRUD 管理
- 后台守护线程**两阶段爬取**：先全部列表，后全部内容
- 内容以 **Markdown** 格式存储（恢复 `markdownify` + `ImageBlockConverter`）
- 预览显示 Markdown 渲染为 HTML
- PDF **按需生成**：预览对话框增加"下载PDF"按钮，点击时才导出

---

## Design

### 1. 数据库：新增 `wechat_account` 表

`spider/database.py` 新增表和对应方法：

```sql
CREATE TABLE IF NOT EXISTS wechat_account (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'pending',       -- pending / list_done / processing / completed / error
    error_message TEXT DEFAULT '',
    total_articles INTEGER DEFAULT 0,
    date_range TEXT DEFAULT '最近7天',   -- 爬取时间范围
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
```

新增 `list_done` 状态表示"列表已爬完，等待爬内容"。

Database 类新增方法：
- `add_account(name, date_range='最近7天')`
- `delete_account(name)`
- `get_accounts(status=None)`
- `get_pending_account()` → 取一个 `status='pending'` 的账号
- `get_list_done_accounts_count()` → 统计 `status='list_done'` 的账号数
- `update_account_status(name, status, error_msg='', articles=0)`

现有 `articles` 表不变，content 字段存 **Markdown** 格式文本。

### 2. 内容格式：恢复 Markdown 存储

从 git 历史恢复 `markdownify` 相关内容：

**`spider/wechat/utils.py`**：
- 恢复 `from markdownify import MarkdownConverter`
- 恢复 `ImageBlockConverter(MarkdownConverter)` 类
- 恢复 `md(soup, **options)` 便捷函数
- `get_article_content()` 返回值改为 **Markdown** 而非 HTML

**`spider/wechat/async_utils.py`**：
- 同步恢复 `markdownify` 转换

**`requirements.txt`**：
- 加 `markdownify`
- 加 `weasyprint`（仅按需PDF使用）

### 3. 公众号管理页面：`gui/pages/unified_scrape_page.py`

替换为账号管理界面，三块区域：

**上：账号表格**
| 公众号 | 状态 | 文章数 | 时间范围 | 添加时间 | 操作 |
| 中文 | pending/list_done/processing/completed/error | N | 最近7天... | datetime | 删除/重试 |

**中：添加栏**
- LineEdit + ComboBox(日期范围) + "添加" PrimaryPushButton

**下：日志面板**
- QTextEdit 只读，自动滚动，彩色日志

### 4. 后台守护线程：`gui/workers.py`

两阶段设计：

```
应用启动 → 线程自动 start()
  │
  ├─ 等待登录就绪
  │
  └─ 主循环:
       │
       ├─ ⭐ 优先：爬取列表 ─────────────────────────
       │   ├─ 查 wechat_account WHERE status='pending' LIMIT 1
       │   ├─ 有 → 搜号 → 获取文章列表(按 date_range 过滤)
       │   │     → 批量插入 articles 表(content='')
       │   │     → 更新 status='list_done'
       │   │     → continue（回到循环头，继续处理下一个 pending）
       │   └─ 无 pending → 进入内容阶段
       │
       └─ 次之：爬取内容 ──────────────────────────
           ├─ 查 articles WHERE content IS NULL OR content='' LIMIT 1
           ├─ 有 → 获取正文(Markdown) → 更新 content
           │     → sleep(request_interval)
           │     → continue（回到循环头 → 再次检查 pending！）
           └─ 无 → sleep 30s → continue（回到循环头）
```

**进入阶段二的条件**：`wechat_account` 中没有 `status='pending'` 的记录。

**反爬措施**：
- 文章列表页：每页 1~2 秒延迟
- 正文获取：每篇 `request_interval`（默认10秒）间隔
- 账号间列表获取：无延迟（快速过所有账号）
- token 过期时停等，log 提示

信号：
- `log_message(str)` — 日志
- `account_status_changed(str name, str status, str msg)` — 刷新表格
- `phase_changed(str phase)` — "list" / "content" / "idle"

### 5. 全局状态指示器：`gui/widgets.py` + `gui/main_window.py`

右下角悬浮小控件（28px高），显示当前阶段和状态：

```
┌─────────────────────────────────────┐
│  ● 爬取内容: 第 3/50 篇 人民日报    │
└─────────────────────────────────────┘
```

- idle: 灰色 ●
- list 阶段: 蓝色 ● "爬取列表: 人民日报 (2/5个公众号)"
- content 阶段: 绿色 ● "爬取内容: 第 15/120 篇"
- error: 红色 ●

### 6. 预览对话框：`gui/widgets.py`

**`ArticlePreviewDialog`** 改动：

- 顶部增加 "下载PDF" PrimaryPushButton
- 内容区域：读取 Markdown → `_md_to_html()` → QWebEngineView 渲染
- 点击"下载PDF" → 调用 `pdf_generator.generate_article_pdf()`[不带图片]或[带图片] 导出到用户选择路径
- PDF 生成改为临时一次性操作，不再预先创建

### 7. PDF 生成器：`spider/wechat/pdf_generator.py`

仅在预览对话框点击"下载PDF"时调用：

```python
def generate_article_pdf(
    article: dict,       # {title, content(Markdown), name(account)}
    account_name: str,
    output_path: str,    # 用户选择的保存路径
) -> str:                # pdf_path
```

- Markdown → HTML → weasyprint → PDF
- 下载文章内图片到临时目录，替换为本地路径（同原有逻辑）
- 进度通过回调报告

### 8. 爬虫恢复：`spider/wechat/scraper.py`

去掉之前添加的 PDF 生成逻辑。`BatchWeChatScraper` 的 `_scrape_single_account()` 仅在 `include_content=True` 时获取内容并保存为 Markdown。

内容获取方法改为返回 Markdown：`get_article_content_by_url()` 内部调用恢复后的 `get_article_content()`（返回 Markdown）。

---

## 受影响的文件

| 文件 | 改动 |
|------|------|
| `spider/database.py` | 新增 `wechat_account` 表 CRUD |
| `spider/wechat/utils.py` | 恢复 `markdownify` + `md()`，`get_article_content()` 返回 Markdown |
| `spider/wechat/async_utils.py` | 同步恢复 Markdown 转换 |
| `spider/wechat/pdf_generator.py` | **新文件** — 按需 PDF 导出 |
| `gui/pages/unified_scrape_page.py` | 改为账号管理 + 日志面板 |
| `gui/workers.py` | 新增 `BackgroundScrapeDaemon`（两阶段） |
| `gui/widgets.py` | `ProcessingIndicator` + 预览改Markdown + "下载PDF"按钮 |
| `gui/main_window.py` | 初始化守护线程、状态指示器 |
| `requirements.txt` | 加 `markdownify`、`weasyprint` |

## 不变的部分

- `gui/pages/results_page.py`
- `gui/pages/settings_page.py`
- `config.json`
- 数据库 `articles` 表结构
- 登录流程

## 用户流程

```
启动 → 扫码登录
  │
  ├─ 打开"公众号"页面 → 添加"人民日报"(最近7天)
  │    → 表格出现, status=pending
  │
  ├─ 后台自动: 爬列表 → status=list_done (瞬间完成)
  │
  ├─ 添加"新华社"(最近7天) → 同样快速完成列表
  │
  ├─ 所有 pending 都变 list_done → 进入内容爬取阶段
  │    → 逐篇获取正文(Markdown) → 10秒间隔
  │    → 右下角显示进度
  │    → 日志面板实时滚动
  │
  └─ 打开"文章列表" → 双击文章 → 预览(Markdown渲染)
       → 满意则点击"下载PDF" → 选择保存路径 → 导出
```
