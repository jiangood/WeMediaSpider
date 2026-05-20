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
