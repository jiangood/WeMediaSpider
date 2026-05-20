# WeMediaSpider — Agent Guide

## Quick start
```powershell
pip install -r requirements.txt
python run_gui.py          # dev mode (GUI only)
```
No test/lint/typecheck commands exist — none configured.

## Entry points
| Purpose | Command |
|---------|---------|
| GUI (dev) | `python run_gui.py` |
| GUI (packaged) | `dist\WeChatSpider\WeChatSpider.exe` |
| CLI scraping | `spider.wechat.run` module (WeChatSpiderRunner) |
| Build portable | `script\build.bat` |
| Build + installer | `script\build_installer.bat` (requires [NSIS](https://nsis.sourceforge.io/)) |

## Architecture

```
run_gui.py                 → env detection → gui.app (QApplication + Fluent dark theme)
gui/
├── app.py                 # QApplication init, dark theme stylesheet (DARK_THEME_STYLESHEET)
├── main_window.py         # FluentWindow with nav sidebar (5 pages)
├── pages/                 # Welcome, Login, UnifiedScrape, Results, Settings
├── workers.py             # BatchScrapeWorker / AsyncBatchScrapeWorker (QThread)
├── utils.py               # Paths, SoundPlayer (QMediaPlayer), DB_PATH
├── styles.py              # Color consts, card/button/label QSS
├── widgets.py             # Custom cards, progress, account list
└── history_manager.py     # AccountHistoryManager (singleton, JSON-backed)
spider/
├── __init__.py            # Exports WeChatSpiderLogin, WeChatScraper, BatchWeChatScraper (v3.8.0)
├── database.py            # SQLite + FTS5 (articles table, triggers for sync)
└── wechat/
    ├── login.py           # Selenium Chrome WebDriver → QR scan → token+cookies (cached 4 days)
    ├── scraper.py         # WeChatScraper, BatchWeChatScraper, AsyncBatchWeChatScraper
    ├── utils.py           # requests-based API wrappers, HTML→Markdown content extraction
    ├── async_utils.py     # aiohttp-based async client (AsyncWeChatClient)
    ├── cache_codec.py     # zlib+base64 encode/decode for sharable login credentials
    └── run.py             # WeChatSpiderRunner — high-level convenience wrapper
config.json                # request_interval, include_content, cache_expire_hours
mic/                       # Audio feedback: login.mp3, daochu.mp3, over.mp3
WeChatSpider.spec          # PyInstaller spec (see excludes to avoid bloat)
```

## Important paths (platform-aware)
| Constant | Typical location |
|----------|-----------------|
| `gui.utils.DB_PATH` | `%APPDATA%/WeChatSpider/wechat_spider.db` |
| `gui.utils.WECHAT_CACHE_FILE` | `%APPDATA%/WeChatSpider/wechat_cache.json` |
| Login cache | Same as WECHAT_CACHE_FILE, valid ~4 days |
| `gui.utils.ACCOUNT_HISTORY_FILE` | `%APPDATA%/WeChatSpider/account_history.json` |
| `gui.utils.DEFAULT_OUTPUT_DIR` | `~/WeChatSpider/` |

On PyInstaller builds, the log dir is `%APPDATA%/WeChatSpider/logs/`.

## Config
`config.json` at project root controls runtime settings. Defaults:
```json
{"request_interval": 10, "include_content": true, "cache_expire_hours": 96}
```

## Key conventions
- Dark theme everywhere — `DARK_THEME_STYLESHEET` in `gui/app.py:38`, WeChat green `#07C160`
- `gui.utils.play_sound(type)` for audio feedback on login / export / complete
- `apply_label_transparent_background()` must be called 100ms after page creation to fix qfluentwidgets label backgrounds
- QML/WebEngine requires `AA_ShareOpenGLContexts` before QApplication creation (see `run_gui.py:150`)
- Login cache is validated by a live API call, not just timestamp
- The async scraper (aiohttp) falls back to sync (requests) if import fails
- Callback-driven: scraper reports via `account_status`, `article_progress`, `content_progress` callbacks → QThread signals → GUI
- Audio files (`mic/`) must be co-located with the executable in packaged builds

## Gotchas
- No test infrastructure exists — if tests appear unexpected, they were not part of the project
- The `BatchWeChatScraper` and `AsyncBatchWeChatScraper` have slightly different callback names (e.g. `error_occurred` vs `error`)
- `PyQt6-Fluent-Widgets` needs PyQt6.QtXml (excluded at your own risk in spec)
- UPX compression skips Qt6WebEngine and Qt6Quick DLLs in build scripts
- `spider/wechat/login.py` imports from `gui.utils` (circular import risk — handle with care)
- The date range in `unified_scrape_page.py` uses preset combo box, not custom date picker
