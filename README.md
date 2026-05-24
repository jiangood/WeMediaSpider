# WeMediaSpider — 微信公众号文章下载器

一款 Python 命令行工具，可自动登录微信公众平台，搜索指定公众号，抓取文章列表并导出为 **PDF** 文件。

## 功能

- **自动登录** — 使用 Playwright 打开浏览器，扫码即可登录，支持缓存（默认 96 小时）
- **公众号搜索** — 按名称搜索公众号，获取文章列表
- **文章抓取** — 支持标准图文和纯图片类文章，自动重试与反爬延迟
- **PDF 导出** — 生成排版工整的 PDF，支持中文字体（自动检测系统字体）
- **日期筛选** — 默认抓取近 30 天文章，可自定义天数

## 安装

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

或直接运行 `安装依赖.bat`（使用国内镜像）。

## 使用

```bash
python wx_cli.py 公众号名称 [天数] [-o 输出目录] [--no-cache]
```

### 示例

```bash
python wx_cli.py 人民日报
python wx_cli.py 人民日报 7
python wx_cli.py "腾讯科技" 30 -o ./data
python wx_cli.py 人民日报 --no-cache
```

也可运行 `启动公众号下载器.bat` 进入交互模式。

## 输出

```
输出目录/
└── 公众号名称/
    ├── 2025-01-01_文章标题.pdf
    └── 2025-01-02_另一篇文章.pdf
```

## 依赖

| 包 | 用途 |
|---|---|
| playwright | 浏览器自动化登录 |
| requests | HTTP 请求 |
| beautifulsoup4 / lxml | HTML 解析 |
| markdownify | HTML 转 Markdown |
| fpdf2 | PDF 生成 |

## 注意事项

- 首次使用需扫码登录微信公众平台
- 请合理控制抓取频率，避免触发微信反爬机制
- PDF 生成依赖系统中文字体（Windows 自动使用微软雅黑）
