# 后台爬虫 + PDF 自动生成

## Summary

爬取页面改为公众号 CRUD 管理，后台守护线程自动轮询数据库、爬取文章、下载图片并生成 PDF。预览直接加载本地 PDF。

---

## Design

### 1. 数据库：新增 `wechat_account` 表

`spider/database.py` 新增表和对应方法：

```sql
CREATE TABLE IF NOT EXISTS wechat_account (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'pending',       -- pending / processing / completed / error
    error_message TEXT DEFAULT '',
    total_articles INTEGER DEFAULT 0,
    date_range TEXT DEFAULT '最近7天',   -- 爬取时间范围
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
```

Database 类新增方法（操作 wechat_account 表）：
- `add_account(name, date_range='最近7天')` → 插入 pending 账号
- `delete_account(name)` → 删除账号
- `get_accounts(status=None)` → 查询账号列表
- `get_pending_account()` → 取一个 pending 账号（用于后台线程轮询）
- `update_account_status(name, status, error_msg='', articles=0)` → 更新状态

### 2. 公众号管理页面：`gui/pages/unified_scrape_page.py`

替换现有爬取界面为账号管理界面，三块区域：

**上：账号表格**
| 列 | 内容 |
|---|---|
| 公众号名称 | 文本 |
| 状态 | pending / processing / completed / error |
| 文章数 | 已爬取文章数 |
| 添加时间 | datetime |
| 操作 | 删除按钮（error 状态额外显示重试按钮） |

表格使用 qfluentwidgets FluentTable，刷新逻辑由 `account_status_changed` 信号驱动。

**中：添加栏**
- LineEdit（公众号名称）+ ComboBox（日期范围）+ "添加" PrimaryPushButton
- 日期范围选项：最近7天（默认）、本月、本季度、本年、最近3年、全部
- 回车或点击添加，调用 `add_account(name, date_range)` → 插入 `status='pending'` → 后台线程自动拾取
- 成功时 InfoBar 提示

**下：日志面板**
- QTextEdit（只读），暗黑背景，自动滚动到底部
- 后台线程的 `log_message` 信号追加日志行
- 格式：`[HH:MM:SS] 消息内容`
- 每行不同颜色：info（白色）、success（绿色）、warning（黄色）、error（红色）

### 3. 后台守护线程：`gui/workers.py`

新增 `BackgroundScrapeDaemon(QThread)`：

```
应用启动 → 线程自动 start()
  │
  ├─ 等待 login_manager 登录就绪（token 非空）
  │
  └─ 主循环（每30秒一轮）:
       ├─ 查询 wechat_account WHERE status='pending' LIMIT 1
       ├─ 无 pending → sleep 30s → 继续
       │
       └─ 有 pending → 处理单个账号:
             ├─ 1. 读取 date_range → 转换为起止日期
             ├─ 2. 更新 status='processing'
             ├─ 3. 搜索公众号 fakeid
             ├─ 4. 获取文章列表，按日期范围过滤（分页防反爬）
             ├─ 5. 逐篇获取正文 + 下载图片 + 生成PDF
             │     (间隔时间被PDF生成利用)
             ├─ 6. 保存到 articles 表
             ├─ 7. 更新 status='completed', total_articles
             │
             └─ 任意步骤失败 → 更新 status='error', error_message
```

信号：
- `log_message(str)` — 带颜色的日志行
- `account_status_changed(str name, str status, str msg)` — 刷新账号表格

反爬措施：
- 文章间延迟：`config.request_interval`（默认10秒）
- 图片下载：每张间隔 0.3~0.5 秒
- 账号间延迟：15~30 秒随机
- token 过期：检测到 401 时停等并发出 error log，等待用户重新扫码

### 4. PDF 生成器：`spider/wechat/pdf_generator.py`

纯 Python，无 Qt 依赖。

```python
def generate_article_pdf(
    article: dict,       # {title, content(HTML), name(account), link}
    account_name: str,
    output_root: str,    # ./download/
) -> dict:               # {pdf_path, images_dir}
```

- **PDF 路径**: `{output_root}/{account_name}_{safe_title}.pdf`
- **图片目录**: `{output_root}/{account_name}_{safe_title}/`
- 下载文章内图片 → 写入图片目录 → 替换 HTML 中 `<img src>` 为本地路径 → weasyprint 转 PDF
- 失败时不抛异常，仅 log warning（不中断爬取）

### 5. 爬虫改动：`spider/wechat/scraper.py`

`BatchWeChatScraper._scrape_single_account()` 获取内容后调用 PDF 生成：

```python
article = self.scraper.get_article_content_by_url(article)

from spider.wechat.pdf_generator import generate_article_pdf
generate_article_pdf(article, account_name, config.get('download_dir', './download/'))

time.sleep(delay)
```

新增回调状态：`pdf_generating`

### 6. 全局状态指示器：`gui/widgets.py` + `gui/main_window.py`

新增 `ProcessingIndicator(QWidget)` — 悬浮在窗口右下角的小控件，不随页面切换隐藏：

```
┌──────────────────────────────┐
│  ● 正在处理: 人民日报 (3/5)  │  ← 28px 高，半透明黑色背景
└──────────────────────────────┘
```

- 左侧圆点：idle=灰色、processing=绿色脉动、error=红色
- 中间文字：当前处理状态
- 右下角定位，窗口缩放时跟随

**MainWindow** 初始化时创建后台线程、状态指示器、连接信号：

```python
# 后台守护线程
self.daemon = BackgroundScrapeDaemon(self.login_manager)
self.daemon.log_message.connect(self._on_daemon_log)
self.daemon.account_status_changed.connect(self._on_account_status)
self.daemon.start()

# 全局状态指示器
self.processing_indicator = ProcessingIndicator(self)
self.processing_indicator.show()
```

`resizeEvent` 中更新指示器位置。

### 7. 预览对话框：`gui/widgets.py`

`ArticlePreviewDialog._update_display()`：

```python
pdf_path = self._derive_pdf_path(article)  # ./download/{account}_{safe_title}.pdf
if pdf_path and os.path.exists(pdf_path):
    self.content_text.setUrl(QUrl.fromLocalFile(pdf_path))
else:
    self.content_text.setHtml(content, QUrl("https://mp.weixin.qq.com"))
```

---

## 受影响的文件

| 文件 | 改动 |
|------|------|
| `spider/database.py` | 新增 `wechat_account` 表、CRUD 方法 |
| `spider/wechat/pdf_generator.py` | **新文件** — weasyprint PDF 生成 |
| `spider/wechat/scraper.py` | 内容获取后插入 PDF 生成 |
| `gui/pages/unified_scrape_page.py` | 改为账号管理 + 日志面板 |
| `gui/workers.py` | 新增 `BackgroundScrapeDaemon` |
| `gui/widgets.py` | 新增 `ProcessingIndicator` + 预览加载PDF |
| `gui/main_window.py` | 初始化守护线程、状态指示器，连接信号 |

| `requirements.txt` | 加 `weasyprint` |

## 不变的部分

- `gui/pages/results_page.py` — 无需改动，仍从 DB 加载数据
- `gui/pages/settings_page.py` — 无需改动
- `spider/wechat/utils.py` — 无需改动
- `spider/wechat/async_utils.py` — 无需改动
- `spider/__init__.py` — 导出按需
- `config.json` — 无需新增配置项
- 数据库 `articles` 表 — 结构不变

## 用户流程

```
启动应用 → 扫码登录 → 后台线程自动等待
    ↓
打开"公众号爬取"页面
    ↓
输入公众号名称 → 点击添加
    ↓
账号出现表格中（status=pending）
    ↓
后台线程自动拾取 → 爬取中（status=processing）
    ↓
日志实时滚动显示进度
    ↓
完成后状态更新为 completed
    ↓
结果页面查看 → 双击 → 预览PDF
```
