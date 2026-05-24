#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号爬虫 CLI - 单文件独立版
=================================
用法:
     python wx_cli.py 公众号名称 [天数] [-o 输出目录]

示例:
     python wx_cli.py 人民日报
     python wx_cli.py 人民日报 7
     python wx_cli.py "腾讯科技" 30 -o ./data
"""

import argparse
import hashlib

import json
import os
import random
import re
import shutil
import sys
import time
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag
from fpdf import FPDF
from markdownify import MarkdownConverter
from playwright.sync_api import sync_playwright

__version__ = "1.0.0"


# ============================================================
# 日志工具 - 普通 print 实现
# ============================================================
def _now():
    return datetime.now().strftime('%H:%M:%S')


def _log(level, icon, msg):
    print(f" [{_now()}] {icon} {msg}")


def log_info(msg):
    _log('INFO', ' ', msg)


def log_ok(msg):
    _log('OK', '  OK', msg)


def log_warn(msg):
    _log('WARN', ' !!', msg)


def log_error(msg):
    _log('ERROR', ' XXX', msg)


def log_step(cur, total, msg):
    sep = '=' * 38
    print(f"\n {sep}")
    print(f"  STEP [{cur}/{total}] {msg}")
    print(f" {sep}")


def log_substep(msg):
    print(f"    -> {msg}")


# ============================================================
# 平台感知路径
# ============================================================
def _get_app_data_dir():
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
    elif sys.platform == 'darwin':
        base = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support')
    else:
        base = os.path.join(os.path.expanduser('~'), '.local', 'share')
    return os.path.join(base, 'WeChatSpider')


def _get_cache_file():
    return os.path.join(_get_app_data_dir(), 'wechat_cache.json')


CACHE_FILE = _get_cache_file()
CACHE_EXPIRE_HOURS = 96


# ============================================================
# 登录模块
# ============================================================
class WeChatLogin:
    def __init__(self):
        self.token = None
        self.cookies = None

    def _get_cache_data(self):
        if not os.path.exists(CACHE_FILE):
            return None
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def _save_cache_data(self, data):
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _clear_cache(self):
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)

    def load_cache(self):
        data = self._get_cache_data()
        if not data:
            return False
        cache_time = datetime.fromtimestamp(data['timestamp'])
        hours = (datetime.now() - cache_time).total_seconds() / 3600
        if hours > CACHE_EXPIRE_HOURS:
            log_info(f"登录缓存已过期（{hours:.1f} 小时前），需要重新登录")
            return False
        self.token = data['token']
        self.cookies = data['cookies']
        log_info(f"从缓存加载登录信息（{hours:.1f} 小时前保存）")
        return True

    def save_cache(self):
        if self.token and self.cookies:
            self._save_cache_data({
                'token': self.token,
                'cookies': self.cookies,
                'timestamp': datetime.now().timestamp()
            })
            log_ok("登录信息已保存到缓存文件")

    def validate_cache(self):
        if not self.token or not self.cookies:
            return False
        try:
            headers = {
                "HOST": "mp.weixin.qq.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            params = {
                'action': 'search_biz', 'token': self.token, 'lang': 'zh_CN',
                'f': 'json', 'ajax': '1', 'random': random.random(),
                'query': 'test', 'begin': '0', 'count': '1',
            }
            resp = requests.get(
                'https://mp.weixin.qq.com/cgi-bin/searchbiz',
                cookies=self.cookies, headers=headers, params=params, timeout=10
            )
            resp.raise_for_status()
            result = resp.json()
            if 'base_resp' in result:
                ret = result['base_resp'].get('ret')
                if ret == 0:
                    log_ok("登录缓存验证有效")
                    return True
                elif ret in (-6, 200013):
                    log_warn("登录缓存已失效")
                    return False
                else:
                    log_warn(f"验证失败: {result['base_resp'].get('err_msg', '未知')}")
                    return False
            return False
        except Exception as e:
            log_warn(f"验证缓存异常: {e}")
            return False

    def login(self):
        log_info("开始登录微信公众号平台 ...")

        if self.load_cache() and self.validate_cache():
            log_ok("使用缓存登录信息，跳过扫码")
            return True

        self._clear_cache()

        try:
            log_info("正在启动浏览器 ...")
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            log_ok("浏览器启动成功")

            log_info("正在访问微信公众平台 https://mp.weixin.qq.com/ ...")
            page.goto('https://mp.weixin.qq.com/')
            log_ok("页面加载完成")

            print()
            print(" " + "=" * 50)
            print("   请在浏览器窗口中，使用微信扫描二维码登录")
            print("   等待最长 5 分钟 ...")
            print(" " + "=" * 50)
            print()

            page.wait_for_url(lambda url: 'token' in url, timeout=300000)

            current_url = page.url
            log_ok("检测到登录成功！正在获取认证信息 ...")

            token_match = re.search(r'token=(\d+)', current_url)
            if not token_match:
                log_error("无法从 URL 提取 token")
                return False
            self.token = token_match.group(1)

            raw_cookies = context.cookies()
            self.cookies = {item['name']: item['value'] for item in raw_cookies}
            log_ok(f"Token 和 Cookies 获取成功（共 {len(self.cookies)} 个 cookie）")

            self.save_cache()
            log_ok("微信公众平台登录完成！")
            return True

        except Exception as e:
            log_error(f"登录过程出错: {e}")
            return False

        finally:
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass
            try:
                playwright.stop()
            except Exception:
                pass

    def get_token(self):
        if not self.token:
            if not (self.load_cache() and self.validate_cache()):
                return None
        return self.token

    def get_headers(self):
        if not self.cookies:
            if not (self.load_cache() and self.validate_cache()):
                return None
        cookie_str = '; '.join([f"{k}={v}" for k, v in self.cookies.items()])
        return {
            "cookie": cookie_str,
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36"
        }


# ============================================================
# 文章内容提取 - MarkdownConverter 子类
# ============================================================
class _ImageBlockConverter(MarkdownConverter):
    def convert_img(self, el, text, parent_tags):
        alt = el.attrs.get('alt', None) or ''
        src = el.attrs.get('src', None) or ''
        if not src:
            src = el.attrs.get('data-src', None) or ''
        title = el.attrs.get('title', None) or ''
        title_part = ' "%s"' % title.replace('"', r'\"') if title else ''
        if ('_inline' in parent_tags
                and el.parent.name not in self.options.get('keep_inline_images_in', [])):
            return alt
        return '\n![%s](%s%s)\n' % (alt, src, title_part)


def _md(soup, **options):
    return _ImageBlockConverter(**options).convert_soup(soup)


# ============================================================
# 内容提取辅助函数
# ============================================================
def _decode_html_entities(text):
    import html
    if not text:
        return text
    text = html.unescape(text)

    def replace_hex(m):
        try:
            return chr(int(m.group(1), 16))
        except Exception:
            return m.group(0)

    text = re.sub(r'\\x([0-9a-fA-F]{2})', replace_hex, text)
    text = html.unescape(text)
    return text


def _preprocess_lazy_images(soup):
    for img in soup.find_all('img'):
        src = img.get('src', '')
        data_src = img.get('data-src', '')
        if data_src and (not src or 'data:image/svg' in src or 'pic_blank' in src):
            img['src'] = data_src


def _extract_fallback_content(soup, content_ele):
    return str(content_ele) if content_ele else None


def _extract_all_text_content(soup):
    parts = []
    title_ele = soup.select_one('.rich_media_title, #activity-name, h1')
    if title_ele and title_ele.get_text(strip=True):
        parts.append(f"# {title_ele.get_text(strip=True)}\n")
    selectors = [
        '.rich_media_content', '#js_content', '.rich_media_area_primary',
        'article', '.article-content'
    ]
    for sel in selectors:
        ele = soup.select_one(sel)
        if ele:
            text = ele.get_text(separator='\n', strip=True)
            if text and len(text) > 20:
                parts.append(f"\n{text}\n")
                break
    images = soup.select('img[data-src], img[src*="mmbiz.qpic.cn"]')
    if images:
        parts.append("\n## 图片\n")
        for i, img in enumerate(images[:20], 1):
            src = img.get('data-src') or img.get('src') or ''
            if src and 'mmbiz.qpic.cn' in src and 'data:image' not in src:
                alt = img.get('alt') or f'图片{i}'
                parts.append(f"\n![{alt}]({src})\n")
    return ''.join(parts) if parts else ""


def _extract_image_article_content(soup):
    parts = []
    seen = set()

    def add_image(src, alt=''):
        if not src:
            return
        src = _decode_html_entities(src)
        base = src.split('?')[0] if '?' in src else src
        if base in seen:
            return
        if 'mmbiz.qpic.cn' not in src:
            return
        if 'pic_blank' in src or 'data:image' in src:
            return
        seen.add(base)
        alt = alt or f'图片{len(seen)}'
        parts.append(f"\n![{alt}]({src})\n")

    for sel in ['.rich_media_title', '#activity-name', '#js_image_content h1', 'h1']:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            parts.append(f"# {_decode_html_entities(el.get_text(strip=True))}\n")
            break

    for sel in ['#js_image_desc', '.share_notice', 'meta[name="description"]']:
        if sel.startswith('meta'):
            el = soup.select_one(sel)
            if el and el.get('content'):
                parts.append(f"\n{_decode_html_entities(el.get('content'))}\n")
                break
        else:
            el = soup.select_one(sel)
            if el and el.get_text(strip=True):
                parts.append(f"\n{_decode_html_entities(el.get_text(strip=True))}\n")
                break

    js_found = False
    for script in soup.find_all('script'):
        text = script.string or ''
        if 'picture_page_info_list' in text:
            m = re.search(r'var\s+picture_page_info_list\s*=\s*(\[[\s\S]*?\]);', text)
            if m:
                try:
                    json_str = _decode_html_entities(m.group(1))
                    pic_list = json.loads(json_str)
                    if pic_list:
                        parts.append("\n## 图片内容\n")
                        for p in pic_list:
                            add_image(p.get('cdn_url', ''))
                        js_found = True
                except Exception:
                    pass

    if not js_found or len(seen) == 0:
        for item in soup.select('.swiper_item[data-src], div[data-src*="mmbiz.qpic.cn"]'):
            src = item.get('data-src', '')
            if src:
                add_image(src)
        for img in soup.select('.swiper_item_img img'):
            src = img.get('src') or img.get('data-src') or ''
            add_image(src, img.get('alt', ''))
        if len(seen) == 0:
            for sel in ['#js_image_content img', '.image_content img', '.wx_img_swiper img', '.img_swiper_wrp img']:
                images = soup.select(sel)
                if images:
                    for img in images:
                        src = img.get('src') or img.get('data-src') or ''
                        add_image(src, img.get('alt', ''))
                    if len(seen) > 0:
                        break

    if len(seen) == 0:
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src') or img.get('data-original') or ''
            add_image(src, img.get('alt', ''))
        for el in soup.find_all(attrs={'data-src': True}):
            add_image(el.get('data-src', ''))
        for el in soup.find_all(style=True):
            for bg_url in re.findall(r'url\(["\']?(https?://mmbiz\.qpic\.cn[^"\')\s]+)["\']?\)', el.get('style', '')):
                add_image(bg_url)

    return ''.join(parts) if parts else None


# ============================================================
# API 请求函数
# ============================================================
def search_account(headers, token, query):
    url = 'https://mp.weixin.qq.com/cgi-bin/searchbiz'
    data = {
        'action': 'search_biz', 'scene': 1, 'begin': 0, 'count': 10,
        'query': query, 'token': token, 'lang': 'zh_CN', 'f': 'json', 'ajax': '1',
    }
    r = requests.get(url, headers=headers, params=data)
    dic = r.json()
    return [
        {'wpub_name': item['nickname'], 'wpub_fakid': item['fakeid']}
        for item in dic.get('list', [])
    ]


def get_articles_list(page_num, start_page, fakeid, token, headers):
    url = 'https://mp.weixin.qq.com/cgi-bin/appmsg'
    titles, links, times = [], [], []
    for i in range(page_num):
        data = {
            'action': 'list_ex', 'begin': start_page + i * 5, 'count': '5',
            'fakeid': fakeid, 'type': '9', 'query': '', 'token': token,
            'lang': 'zh_CN', 'f': 'json', 'ajax': '1',
        }
        time.sleep(random.uniform(1.0, 2.0))
        r = requests.get(url, headers=headers, params=data)
        dic = r.json()
        if 'app_msg_list' not in dic:
            break
        for item in dic['app_msg_list']:
            titles.append(item['title'])
            links.append(item['link'])
            times.append(item['update_time'])
    return titles, links, times


def get_article_content(url, headers, max_retries=3, retry_delay=2):
    CONTENT_SELECTORS = [
        ".rich_media_content", "#js_content",
        "#js_image_content", ".image_content", "#js_image_desc", ".share_notice",
        ".swiper_item_img", "#img_swiper_content", ".share_media_swiper_content", ".img_swiper_area",
        "#js_video_content", ".video_content", ".rich_media_video",
        ".rich_media_area_primary", ".rich_media_area_primary_inner",
        "#js_article_content", "#js_content_container",
        "#page-content", ".rich_media_inner", ".rich_media_wrp",
        "article", ".article", "#article",
    ]
    MIN_LEN = 10

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                log_warn(f"请求文章失败 HTTP {resp.status_code}，重试 {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return f"请求失败，状态码: {resp.status_code}"

            soup = BeautifulSoup(resp.text, 'lxml')
            _preprocess_lazy_images(soup)

            body_classes = soup.body.get('class', []) if soup.body else []
            is_img_article = 'page_share_img' in body_classes
            has_swiper = bool(soup.select('.swiper_item, .swiper_item_img, .share_media_swiper'))

            if is_img_article or has_swiper:
                content = _extract_image_article_content(soup)
                if content and len(content.strip()) >= MIN_LEN:
                    return content

            content_ele = None
            for sel in CONTENT_SELECTORS:
                result = soup.select(sel)
                if result:
                    content_ele = result[0]
                    break

            content = ""
            if content_ele:
                content = _md(content_ele, keep_inline_images_in=["section", "span"])
                if len(content.strip()) < MIN_LEN:
                    fallback = _extract_fallback_content(soup, content_ele)
                    if fallback and len(fallback.strip()) > len(content.strip()):
                        content = fallback

            if content and len(content.strip()) >= MIN_LEN:
                return content

            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, 10)
            else:
                if not content:
                    content = _extract_all_text_content(soup)
                return content

        except requests.exceptions.Timeout:
            log_warn(f"请求超时，重试 {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                return "获取失败: 请求超时"
        except requests.exceptions.RequestException as e:
            log_warn(f"请求异常: {e}，重试 {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                return f"获取失败: {e}"
        except Exception as e:
            log_error(f"解析异常: {e}")
            return f"获取失败: {e}"
    return ""


def format_time(timestamp):
    try:
        return datetime.fromtimestamp(int(timestamp)).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return ''


# ============================================================
# PDF 生成
# ============================================================
def _find_cjk_font():
    candidates = [
        ('C:/Windows/Fonts/msyh.ttc', 0),
        ('C:/Windows/Fonts/simhei.ttf', None),
        ('C:/Windows/Fonts/simsun.ttc', 0),
        ('C:/Windows/Fonts/msyhbd.ttc', 0),
    ]
    for path, idx in candidates:
        if os.path.exists(path):
            return path, idx
    # 尝试系统字体目录
    if sys.platform == 'darwin':
        mac_fonts = [
            '/System/Library/Fonts/PingFang.ttc',
            '/System/Library/Fonts/STHeiti Light.ttc',
        ]
        for path in mac_fonts:
            if os.path.exists(path):
                return path, 0
    return None, None


def _download_images(markdown_text, image_dir):
    os.makedirs(image_dir, exist_ok=True)
    url_to_local = {}

    def _replace_img(match):
        alt = match.group(1)
        url = match.group(2)
        if not url or 'mmbiz.qpic.cn' not in url:
            return match.group(0)
        try:
            ext = '.jpg'
            fmt_m = re.search(r'wx_fmt=(\w+)', url)
            if fmt_m and fmt_m.group(1).lower() in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
                ext = '.' + fmt_m.group(1).lower()
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
            log_warn(f"下载图片失败: {url[:60]}... {e}")
            return match.group(0)

    processed = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', _replace_img, markdown_text)
    html = _md_to_html(processed)
    return html


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


def _escape_html(text):
    if not text:
        return ''
    return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;'))


def _html_to_pdf(html, pdf_path):
    soup = BeautifulSoup(html, 'html.parser')
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    font_path, collection_idx = _find_cjk_font()
    if font_path:
        pdf.add_font('CJK', '', font_path, uni=True, collection_font_number=collection_idx or 0)
        pdf.set_font('CJK', '', 12)
    else:
        raise RuntimeError("未找到中文字体，PDF 导出需要 Microsoft YaHei 或 SimHei 字体")

    epw = pdf.w - pdf.l_margin - pdf.r_margin

    for element in soup.body.children:
        if not isinstance(element, Tag):
            continue
        if element.name == 'h1':
            pdf.set_text_color(7, 193, 96)
            pdf.set_font('CJK', '', 22)
            pdf.multi_cell(0, 10, element.get_text(), align='C')
            pdf.ln(4)
        elif element.name == 'div' and 'meta' in element.get('class', []):
            pdf.set_text_color(136, 136, 136)
            pdf.set_font('CJK', '', 13)
            pdf.multi_cell(0, 8, element.get_text(), align='C')
            pdf.ln(6)
        elif element.name == 'h2':
            pdf.set_text_color(51, 51, 51)
            pdf.set_font('CJK', '', 18)
            pdf.multi_cell(0, 10, element.get_text(), align='L')
            pdf.ln(3)
        elif element.name == 'p':
            pdf.set_text_color(51, 51, 51)
            pdf.set_font('CJK', '', 12)
            pdf.multi_cell(0, 7, element.get_text(), align='L')
            pdf.ln(2)
        elif element.name == 'img':
            src = element.get('src', '')
            if src.startswith('file:///'):
                src = src[8:]
            if os.path.exists(src):
                try:
                    pdf.image(src, x=pdf.l_margin, w=epw)
                    pdf.ln(4)
                except Exception as e:
                    log_warn(f"插入图片失败: {os.path.basename(src)}... {e}")

    pdf.output(pdf_path)


def generate_article_pdf(article_title, account_name, publish_date_str, markdown_content, output_dir):
    safe_account = re.sub(r'[\\/:*?"<>|]', '', account_name).strip()[:50] or 'unknown'
    safe_account_dir = os.path.join(output_dir, safe_account)
    os.makedirs(safe_account_dir, exist_ok=True)

    safe_title = re.sub(r'[\\/:*?"<>|]', '', article_title).strip()[:100] or 'untitled'
    date_str = publish_date_str or datetime.now().strftime('%Y-%m-%d')
    pdf_name = f"{date_str}_{safe_title}.pdf"
    pdf_path = os.path.join(safe_account_dir, pdf_name)
    image_dir = os.path.join(safe_account_dir, f".images_{date_str}_{safe_title[:30]}")

    log_substep("正在下载文章图片 ...")
    html = _download_images(markdown_content, image_dir)

    log_substep("正在生成 PDF ...")
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
<div class="meta">公众号: {_escape_html(account_name)} | 发布于: {date_str} | 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
{html}
</body></html>'''

    _html_to_pdf(full_html, pdf_path)
    log_ok(f"PDF 已保存: {pdf_path}")

    # Cleanup temp images
    if os.path.exists(image_dir):
        try:
            shutil.rmtree(image_dir, ignore_errors=True)
        except Exception:
            pass

    return pdf_path


# ============================================================
# 主函数
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description='微信公众号文章爬虫 - 下载文章并导出为 PDF',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python wx_cli.py 人民日报
  python wx_cli.py 人民日报 7
  python wx_cli.py "腾讯科技" 30 -o ./data
  python wx_cli.py 人民日报 --no-cache
        """
    )
    parser.add_argument('account', help='微信公众号名称')
    parser.add_argument('days', nargs='?', type=int, default=7,
                        help='爬取最近 N 天的文章（默认 7 天）')
    parser.add_argument('-o', '--output', default=os.path.join(os.getcwd(), 'download'),
                        help='输出目录（默认 ./download）')
    parser.add_argument('--no-cache', action='store_true',
                        help='忽略缓存，强制重新扫码登录')
    args = parser.parse_args()

    start_time = time.time()

    print()
    print(" " + "=" * 54)
    print("    微信公众号文章下载器 v{}".format(__version__))
    print(" " + "=" * 54)
    print()
    log_info(f"目标公众号: {args.account}")
    log_info(f"时间范围:   最近 {args.days} 天")
    log_info(f"输出目录:   {args.output}")
    print()

    # ---- Step 1: 登录 ----
    log_step(1, 4, "登录微信公众平台")
    login = WeChatLogin()
    if args.no_cache:
        login._clear_cache()
        log_info("已清除缓存（--no-cache）")

    if not login.login():
        log_error("登录失败，程序退出")
        sys.exit(1)

    token = login.get_token()
    headers = login.get_headers()
    if not token or not headers:
        log_error("无法获取登录凭证，程序退出")
        sys.exit(1)
    log_ok("登录凭证获取成功")
    print()

    # ---- Step 2: 搜索公众号 ----
    log_step(2, 4, "搜索公众号")
    log_info(f"正在搜索: {args.account}")
    results = search_account(headers, token, args.account)

    if not results:
        log_error(f"未找到公众号: {args.account}")
        sys.exit(1)

    account_info = results[0]
    account_name = account_info['wpub_name']
    fakeid = account_info['wpub_fakid']
    log_ok(f"找到公众号: {account_name} (fakeid: {fakeid})")
    print()

    # ---- Step 3: 获取文章列表 ----
    log_step(3, 4, "获取文章列表")

    cutoff_date = datetime.now() - timedelta(days=args.days)
    cutoff_ts = int(cutoff_date.timestamp())
    log_info(f"截止日期: {cutoff_date.strftime('%Y-%m-%d')}")

    all_articles = []
    page = 0
    max_empty_pages = 3
    empty_pages = 0

    while True:
        page += 1
        log_substep(f"正在获取第 {page} 页文章 ...")
        titles, links, times = get_articles_list(1, (page - 1) * 5, fakeid, token, headers)

        if not titles:
            empty_pages += 1
            if empty_pages >= max_empty_pages:
                log_info("连续多页无数据，停止翻页")
                break
            continue
        empty_pages = 0

        page_all_before = True
        for t, l, ts in zip(titles, links, times):
            ts_int = int(ts)
            if ts_int >= cutoff_ts:
                page_all_before = False
                all_articles.append({
                    'name': account_name,
                    'title': t,
                    'link': l,
                    'publish_timestamp': ts_int,
                    'publish_time': format_time(ts),
                })

        if page_all_before:
            log_info("检测到文章已超出日期范围，停止翻页")
            break

        # Delay between pages
        time.sleep(random.uniform(1.0, 2.0))

    if not all_articles:
        log_warn(f"最近 {args.days} 天内没有找到文章")
        sys.exit(0)

    log_ok(f"共获取到 {len(all_articles)} 篇文章（最近 {args.days} 天内）")
    print()

    # ---- Step 4: 下载文章并导出 PDF ----
    log_step(4, 4, "下载文章并导出 PDF")
    output_dir = os.path.abspath(args.output)
    pdf_count = 0
    skip_count = 0
    fail_count = 0

    total = len(all_articles)
    safe_account = re.sub(r'[\\/:*?"<>|]', '', account_name).strip()[:50] or 'unknown'
    for i, article in enumerate(all_articles):
        title = article['title']
        date_str = datetime.fromtimestamp(article['publish_timestamp']).strftime('%Y-%m-%d')
        safe_title = re.sub(r'[\\/:*?"<>|]', '', title).strip()[:100] or 'untitled'
        pdf_path = os.path.join(output_dir, safe_account, f"{date_str}_{safe_title}.pdf")

        if os.path.exists(pdf_path):
            log_substep(f"[{i + 1}/{total}] {title[:50]}（已存在，跳过）")
            skip_count += 1
            continue

        article_start = time.time()
        log_substep(f"[{i + 1}/{total}] {title[:50]}")

        try:
            content = get_article_content(article['link'], headers)
            log_ok(f"  内容获取成功（{len(content)} 字符），正在导出 PDF ...")
            generate_article_pdf(
                article_title=title,
                account_name=account_name,
                publish_date_str=date_str,
                markdown_content=content,
                output_dir=output_dir,
            )
            article_elapsed = time.time() - article_start
            log_ok(f"  PDF 已保存: {date_str}_{title[:30]}.pdf（本次耗时 {article_elapsed:.0f} 秒）")
            pdf_count += 1
        except Exception as e:
            article_elapsed = time.time() - article_start
            log_warn(f"  处理失败: {e}（本次耗时 {article_elapsed:.0f} 秒）")
            fail_count += 1

        if i < total - 1:
            log_substep("等待 10 秒后继续 ...")
            time.sleep(10)

    # ---- Summary ----
    print()
    print(" " + "=" * 54)
    print("    任务完成！")
    print(" " + "=" * 54)
    print(f"   公众号:     {account_name}")
    print(f"   文章:       {total} 篇")
    print(f"   新增:       {pdf_count} 篇")
    if skip_count:
        print(f"   跳过:       {skip_count} 篇")
    if fail_count:
        print(f"   失败:       {fail_count} 篇")
    print(f"   保存路径:   {os.path.join(output_dir, account_name)}")
    elapsed = time.time() - start_time
    print(f"   用时:       {elapsed:.0f} 秒")
    print(" " + "=" * 54)
    print()


if __name__ == "__main__":
    main()
