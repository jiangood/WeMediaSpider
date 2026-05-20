import os
import re
import time
import random
import requests

def generate_article_pdf(
    article: dict,
    account_name: str,
    output_root: str,
) -> dict:
    title = article.get('title', 'untitled')
    content_html = article.get('content', '')

    safe_account = _sanitize_filename(str(account_name))
    safe_title = _sanitize_filename(str(title))
    stem = f"{safe_account}_{safe_title}"
    pdf_dir = os.path.join(output_root, safe_account)
    images_dir = os.path.join(pdf_dir, stem)

    os.makedirs(images_dir, exist_ok=True)

    pdf_path = os.path.join(pdf_dir, f"{stem}.pdf")

    if not content_html or content_html.startswith('获取'):
        _write_text_pdf(content_html or '无内容', pdf_path)
        return {'pdf_path': pdf_path, 'images_dir': images_dir}

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(content_html, 'lxml')

    url_to_local = {}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    for i, img in enumerate(soup.find_all('img')):
        src = img.get('src') or img.get('data-src') or ''
        if not src or 'mmbiz.qpic.cn' not in src:
            img.decompose()
            continue

        try:
            ext = _get_image_extension(src)
            local_name = f"{i + 1}{ext}"
            local_path = os.path.join(images_dir, local_name)

            resp = requests.get(src, headers=headers, timeout=30)
            if resp.status_code == 200:
                raw = resp.content
                if ext == '.webp':
                    from io import BytesIO
                    from PIL import Image
                    pil_img = Image.open(BytesIO(raw)).convert('RGB')
                    local_name = f"{i + 1}.png"
                    local_path = os.path.join(images_dir, local_name)
                    pil_img.save(local_path, 'PNG')
                else:
                    with open(local_path, 'wb') as f:
                        f.write(raw)

                url_to_local[src] = local_path

            time.sleep(random.uniform(0.3, 0.5))

        except Exception:
            img.decompose()

    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or ''
        local = url_to_local.get(src)
        if local:
            local_url = local.replace('\\', '/')
            img['src'] = f"file:///{local_url}"
        else:
            img.decompose()

    html = str(soup)
    full_html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif; padding: 20px; line-height: 1.8; color: #333; }}
img {{ max-width: 100%; height: auto; }}
p {{ margin: 8px 0; }}
h1 {{ font-size: 22px; }}
</style></head><body>
<h1>{_escape_html(title)}</h1>
{html}
</body></html>'''

    _html_to_pdf(full_html, pdf_path)
    return {'pdf_path': pdf_path, 'images_dir': images_dir}


def _html_to_pdf(html: str, pdf_path: str):
    from weasyprint import HTML
    HTML(string=html).write_pdf(pdf_path)


def _write_text_pdf(text: str, pdf_path: str):
    html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>body {{ font-family: 'Microsoft YaHei', sans-serif; padding: 20px; }}</style>
</head><body><p>{_escape_html(text)}</p></body></html>'''
    _html_to_pdf(html, pdf_path)


def _get_image_extension(url: str) -> str:
    if 'wx_fmt=' in url:
        m = re.search(r'wx_fmt=(\w+)', url)
        if m:
            fmt = m.group(1).lower()
            if fmt in ['png', 'jpg', 'jpeg', 'gif', 'webp']:
                return f'.{fmt}'
    if '.png' in url.lower():
        return '.png'
    if '.jpg' in url.lower() or '.jpeg' in url.lower():
        return '.jpg'
    if '.gif' in url.lower():
        return '.gif'
    if '.webp' in url.lower():
        return '.webp'
    return '.jpg'


def _sanitize_filename(name: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|]', '', name).strip()
    return safe[:120] or 'untitled'


def _escape_html(text: str) -> str:
    if not text:
        return ''
    return (str(text).replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))