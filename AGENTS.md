# WeMediaSpider — Agent Guide

## What this is

A single-file Python CLI tool (`wx_cli.py`) that logs into 微信公众平台, scrapes articles from a given account, and exports them as PDFs. No package structure, no tests, no CI, no linter.

## Active branch

`cli` — this is the current refactored single-file version. `main` has the old PyQt6 GUI. Always work on `cli`.

## Setup

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

Or double-click `安装依赖.bat` (uses CN mirrors).

## Run

```bash
python wx_cli.py 公众号名称 [天数] [-o 输出目录] [--no-cache]
```

Or double-click `启动公众号下载器.bat` (interactive, remembers last account name via `.last_name`).

## Key facts

- **No test/lint/typecheck commands exist** — do not try to run any.
- **Login cache:** stored at `%APPDATA%/WeChatSpider/wechat_cache.json` (Win), `~/Library/Application Support/WeChatSpider/` (macOS), `~/.local/share/WeChatSpider/` (Linux). Expires after 96h. Use `--no-cache` to force re-login.
- **CJK font required** for PDF. Auto-detects: Windows → Microsoft YaHei, macOS → PingFang/STHeiti. Linux will fail without a manual font.
- **Output:** `./download/<公众号名称>/YYYY-MM-DD_标题.pdf` (`download/` is gitignored).
- **Anti-scraping defaults:** 1‑2s page delay, 2‑4s article delay, 3 retries with exponential backoff (2s→3s→4.5s, capped 10s).
- **Dependencies:** `playwright`, `requests`, `beautifulsoup4`, `lxml`, `markdownify`, `fpdf2` (all in `requirements.txt`).
- **No build system, no tests, no type checking, no CI.**
