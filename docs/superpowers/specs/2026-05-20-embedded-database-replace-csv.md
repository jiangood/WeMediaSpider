# 嵌入式数据库替换 CSV 内部传输

## 背景

项目当前使用 CSV 文件作为爬虫（后端）与 GUI（前端）之间的数据传输层：爬虫将结果写入 CSV，GUI 再读取该 CSV 进行展示。这种方式导致多处重复的文件 I/O 和数据格式转换逻辑，且无法高效支持内容搜索。

## 目标

- 使用 SQLite 嵌入式数据库替换 CSV 作为内部存储
- 保留 CSV/JSON/Excel 作为用户手动导出格式
- 零新增依赖（Python 标准库 `sqlite3`）
- 支持全文搜索文章内容

## 数据模型

### 主表 `articles`

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | 自增主键 |
| `account_name` | TEXT | NOT NULL | 公众号名称 |
| `title` | TEXT | NOT NULL | 文章标题 |
| `publish_time` | TEXT | | 发布时间 |
| `link` | TEXT | UNIQUE | 链接，用于去重 |
| `content` | TEXT | | 正文 |
| `created_at` | TEXT | DEFAULT CURRENT_TIMESTAMP | 入库时间 |

### FTS 虚拟表 `articles_fts`

- 覆盖 `title` 和 `content` 两列
- 使用 `content=` 外部内容表指向 `articles`，数据与主表自动同步

## 架构

### DAO 层：`spider/database.py`

一个类封装所有数据库操作，上层代码不接触 SQL：

```
Database(db_path)
├── save_articles(articles: List[Dict]) → int  # 批量写入，按link去重
├── get_articles(account: str | None) → List[Dict]
├── search_articles(keyword: str) → List[Dict]  # FTS全文搜索
├── get_accounts() → List[str]                  # 获取所有公众号列表
├── get_articles_count() → int
├── delete_article(link: str) → bool
├── clear() → bool
├── close()
```

- 默认路径：用户数据目录下 `wechat_spider.db`
- WAL 模式 + 单连接（爬虫和 GUI 同进程）
- 返回数据格式为 `List[Dict]`，与现有代码兼容

### 流程图

```
改造前：
  爬虫 → 写 CSV → GUI 读 CSV → 展示
  (多处文件I/O，格式转换，全文搜索需遍历CSV)

改造后：
  爬虫 → 写 SQLite ──→ GUI 读 SQLite → 展示
               └──→ CSV导出（用户手动）
               └──→ JSON导出（用户手动）
```

## 改动清单

| 文件 | 改动 |
|------|------|
| `spider/database.py` | **新增** DAO 层，建表 + CRUD + FTS |
| `spider/wechat/scraper.py` | 替换 `save_articles_to_csv` 为 DB 写入 |
| `spider/wechat/run.py` | 返回路径改为 db_path |
| `spider/wechat/utils.py` | 保留 `save_to_csv` 仅用于导出 |
| `gui/workers.py` | 信号参数 csv_path → db_path |
| `gui/pages/unified_scrape_page.py` | 配置传 db_path，爬完从 DB 读 |
| `gui/pages/results_page.py` | 默认从 DB 加载，CSV 导入保留为手动功能 |
| `gui/pages/content_search_page.py` | 数据加载走 DB，搜索走 FTS |
| `gui/main_window.py` | 关闭保存逻辑简化 |

## 不变的部分

- 登录缓存（JSON）
- 账号历史记录（JSON）
- 配置文件（config.json）
- 所有导出功能（CSV / JSON / Excel）
- 用户手动导入 CSV（兼容旧数据）

## 注意事项

- 使用 `INSERT OR IGNORE` 按 `link` 去重避免重复入库
- FTS 使用 `content=` 外部内容表模式，确保数据同步
- 数据库文件默认在用户数据目录，可通过 `gui.utils.get_db_path()` 获取
- 单连接足够（非多进程场景），不做连接池
