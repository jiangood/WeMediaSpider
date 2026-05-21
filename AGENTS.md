# WeMediaSpider 鈥?Agent Guide

## Quick start
```powershell
pip install -r requirements.txt
python run_gui.py
```
No test/lint/typecheck commands exist.

## Entry points
| Purpose | Command |
|---------|---------|
| GUI (dev) | `python run_gui.py` |
| GUI (packaged) | `dist\WeChatSpider\WeChatSpider.exe` |
| CLI scraping | `spider.wechat.run` module (`WeChatSpiderRunner`) |
| Build portable | `script\build.bat` |
| Build + installer | `script\build_installer.bat` (requires NSIS) |

## Architecture
```
run_gui.py 鈫?env detection 鈫?QApplication + Fluent dark theme
gui/
鈹溾攢鈹€ app.py                 # QApplication init, DARK_THEME_STYLESHEET, apply_label_transparent_background()
鈹溾攢鈹€ main_window.py         # FluentWindow, 5 nav pages + BackgroundScrapeDaemon
鈹溾攢鈹€ pages/
鈹?  鈹溾攢鈹€ welcome_page.py / login_page.py / unified_scrape_page.py
鈹?  鈹溾攢鈹€ results_page.py / settings_page.py
鈹?  鈹斺攢鈹€ article_downloader.py  # not in main nav, imported by widgets.py:1049
鈹溾攢鈹€ workers.py             # BackgroundScrapeDaemon (QThread) 鈥?emoji-prefixed logs
鈹溾攢鈹€ utils.py               # DB_PATH, WECHAT_CACHE_FILE, SoundPlayer, play_sound()
鈹溾攢鈹€ styles.py              # COLORS, QSS card/button/label templates
鈹溾攢鈹€ widgets.py             # Custom cards, progress, account list, references pdf_generator.py:914
鈹斺攢鈹€ history_manager.py     # AccountHistoryManager (singleton, JSON-backed)
spider/
鈹溾攢鈹€ __init__.py            # Exports WeChatSpiderLogin, WeChatScraper, BatchWeChatScraper (v3.8.0)
鈹溾攢鈹€ database.py            # SQLite + FTS5 (articles + wechat_account tables, sync triggers)
鈹斺攢鈹€ wechat/
    鈹溾攢鈹€ login.py           # Selenium Chrome 鈫?QR scan 鈫?token+cookies (cached ~4 days, validated via live API call)
    鈹溾攢鈹€ scraper.py         # WeChatScraper, BatchWeChatScraper, AsyncBatchWeChatScraper
    鈹溾攢鈹€ utils.py           # requests-based API wrappers, HTML鈫扢arkdown extraction
    鈹溾攢鈹€ async_utils.py     # aiohttp-based (AsyncWeChatClient)
    鈹溾攢鈹€ cache_codec.py     # zlib+base64 encode/decode for sharable login credentials
    鈹溾攢鈹€ run.py             # WeChatSpiderRunner 鈥?high-level wrapper
    鈹斺攢鈹€ pdf_generator.py   # generate_article_pdf() (fpdf2 + BeautifulSoup)
config.json                # {request_interval, include_content, cache_expire_hours}
mic/                       # login.mp3, daochu.mp3, over.mp3 鈥?must be co-located in packaged builds
```

## Important paths (platform-aware)
All under `gui.utils`: data dir is `~/.local/share/WeChatSpider` (Linux), `%LOCALAPPDATA%/WeChatSpider` (Windows), `~/Library/Application Support/WeChatSpider` (macOS).
- `DB_PATH` 鈫?`wechat_spider.db`
- `WECHAT_CACHE_FILE` 鈫?`wechat_cache.json` (login cache, valid ~4 days)
- `ACCOUNT_HISTORY_FILE` 鈫?`account_history.json`
- `DEFAULT_OUTPUT_DIR` 鈫?`~/WeChatSpider/`
- Packaged build logs 鈫?`%APPDATA%/WeChatSpider/logs/`

## Key conventions
- Dark theme everywhere 鈥?WeChat green `#07C160`, background `#1a1a1a`
- `apply_label_transparent_background()` called via `QTimer.singleShot(100, ...)` to fix qfluentwidgets label backgrounds
- `AA_ShareOpenGLContexts` must be set before QApplication creation (`run_gui.py:150`)
- Login cache validated via live API call (`login.py:validate_cache`), not just timestamp
- Async scraper falls back to sync if `aiohttp` import fails (`scraper.py:862-873`)
- Callback-driven: scraper reports via `account_status`, `article_progress`, `content_progress` 鈫?QThread signals 鈫?GUI
- `BackgroundScrapeDaemon` uses emoji-prefixed log levels: 鉁?/ 鈿狅笍 / 鉂?
- Audio files (`mic/`) must be co-located with executable in packaged builds

## Gotchas
- **No test infrastructure** 鈥?do not expect tests
- **Callback names differ**: `WeChatScraper` uses `progress`, `error`, `complete`, `status`; `BatchWeChatScraper`/`AsyncBatchWeChatScraper` use `progress_updated`, `account_status`, `batch_completed`, `error_occurred`, `article_progress`, `content_progress`
- **Circular import risk**: `spider/wechat/login.py` and `spider/wechat/run.py` both import from `gui.utils` 鈥?handle with care
- `PyQt6-Fluent-Widgets` needs `PyQt6.QtXml` (NOT excluded in spec)
- UPX compression skips `Qt6WebEngine*.dll` and `Qt6Quick*.dll`
- Date range in `unified_scrape_page.py` uses `ComboBox` presets, not a date picker
- `config.json` has only 3 keys (the README lists `max_pages`/`max_workers` but they are not present in actual config)


