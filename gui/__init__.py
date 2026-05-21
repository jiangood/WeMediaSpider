#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
寰俊鍏紬鍙风埇铏?GUI 妯″潡

鏈ā鍧楁彁渚涘熀浜?PyQt6 鍜?qfluentwidgets 鐨勫浘褰㈢敤鎴风晫闈紝閲囩敤 Fluent Design 璁捐椋庢牸銆?
鐣岄潰鏁翠綋浣跨敤寰俊椋庢牸鐨勬殫榛戜富棰橀厤鑹诧紝涓昏壊璋冧负寰俊缁?(#07C160)銆?

妯″潡缁撴瀯:
    - app.py: 搴旂敤绋嬪簭鍏ュ彛锛岃礋璐ｅ垵濮嬪寲 QApplication 鍜屼富棰樿缃?
    - main_window.py: 涓荤獥鍙ｅ疄鐜帮紝鍩轰簬 FluentWindow 鐨勫鑸紡甯冨眬
    - pages/: 鍚勫姛鑳介〉闈㈢殑瀹炵幇
        - welcome_page.py: 娆㈣繋椤甸潰
        - login_page.py: 寰俊鐧诲綍椤甸潰
        - account_management_page.py: 鍏紬鍙风鐞嗛〉闈?
        - articles_page.py: 鏂囩珷鍒楄〃椤甸潰锛堝惈鎼滅储锛?
        - article_downloader.py: 鏂囩珷鍥剧墖涓嬭浇
        - settings_page.py: 璁剧疆椤甸潰
    - widgets.py: 鑷畾涔夋帶浠讹紙杩涘害鏉°€佸崱鐗囥€佸巻鍙叉爣绛剧瓑锛?
    - workers.py: 鍚庡彴宸ヤ綔绾跨▼锛堝悓姝?寮傛鐖彇锛?
    - styles.py: 鍏ㄥ眬鏍峰紡瀹氫箟
    - utils.py: 宸ュ叿鍑芥暟锛堣矾寰勫鐞嗐€侀煶棰戞挱鏀剧瓑锛?
    - history_manager.py: 鍏紬鍙峰巻鍙茶褰曠鐞?

浣跨敤绀轰緥:
    >>> from gui import run_app
    >>> run_app()  # 鍚姩 GUI 搴旂敤

鎶€鏈爤:
    - PyQt6: Qt6 鐨?Python 缁戝畾
    - qfluentwidgets: Fluent Design 椋庢牸鐨?Qt 缁勪欢搴?
    - QMediaPlayer: 闊抽鎾斁鏀寔

浣滆€? WeChatSpider Team
鐗堟湰: 1.0
"""

__version__ = "1.0"

from .app import run_app

__all__ = ['run_app']

