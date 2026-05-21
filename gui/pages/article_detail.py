#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
文章详情对话框模块

提供全屏文章预览和图片提取/PDF导出功能。

控件列表:
    - ArticlePreviewDialog: 全屏文章预览对话框
    - ImageExtractDialog: 图片提取/PDF导出对话框

ArticlePreviewDialog:
    支持上一篇/下一篇切换、查看原文链接、Markdown 渲染。
    快捷键: ←/A 上一篇, →/D 下一篇, ESC 关闭。

ImageExtractDialog:
    支持从文章链接提取图片或导出为 PDF。
"""

import os
import re

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QDialog, QApplication, QWidget
)
from PyQt6.QtCore import pyqtSignal, Qt, QUrl, QTimer
from PyQt6.QtGui import QDesktopServices, QKeyEvent
from PyQt6.QtWebEngineWidgets import QWebEngineView

from qfluentwidgets import (
    CardWidget as FluentCard, PrimaryPushButton, PushButton,
    ProgressBar, BodyLabel, CaptionLabel,
    FluentIcon, PlainTextEdit, TitleLabel,
    LineEdit, TextEdit, InfoBar, InfoBarPosition
)

from ..styles import COLORS


class ArticlePreviewDialog(QDialog):
    """全屏文章预览对话框

    提供全屏预览文章内容的功能，支持：
    - 上一篇/下一篇切换（按钮或键盘快捷键）
    - 查看原文链接
    - 显示文章标题、公众号、发布时间
    - 滚动查看文章内容

    快捷键:
        - 左方向键/A: 上一篇
        - 右方向键/D: 下一篇
        - ESC: 关闭对话框

    Signals:
        article_changed: 文章切换信号，携带新的文章索引

    Attributes:
        articles: 文章列表
        current_index: 当前显示的文章索引
    """

    article_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.articles = []
        self.current_index = 0
        self._setup_ui()
        self._setup_shortcuts()
        self._warm_up_engine()

    def _warm_up_engine(self):
        self.content_text.setHtml(
            "<html><body style='background:#1e1e1e;'></body></html>"
        )

    def _setup_ui(self):
        self.setWindowTitle("文章详情")
        self.setModal(True)

        screen = QApplication.primaryScreen()
        if screen:
            screen_size = screen.availableGeometry()
            width = min(960, int(screen_size.width() * 0.9))
            height = int(screen_size.height() * 0.9)
            self.resize(width, height)
            x = (screen_size.width() - width) // 2
            y = (screen_size.height() - height) // 2
            self.move(x, y)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLORS['background']};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(10)

        self.prev_btn = PushButton("上一篇", icon=FluentIcon.LEFT_ARROW)
        self.prev_btn.setFixedWidth(120)
        self.prev_btn.clicked.connect(self._on_prev)
        toolbar_layout.addWidget(self.prev_btn)

        self.count_label = BodyLabel("0 / 0")
        self.count_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 14px;")
        toolbar_layout.addWidget(self.count_label)

        self.next_btn = PushButton("下一篇", icon=FluentIcon.RIGHT_ARROW)
        self.next_btn.setFixedWidth(120)
        self.next_btn.clicked.connect(self._on_next)
        toolbar_layout.addWidget(self.next_btn)

        toolbar_layout.addStretch()

        self.open_link_btn = PushButton("查看原文", icon=FluentIcon.LINK)
        self.open_link_btn.setFixedWidth(150)
        self.open_link_btn.clicked.connect(self._on_open_link)
        toolbar_layout.addWidget(self.open_link_btn)

        self.download_pdf_btn = PrimaryPushButton("下载PDF", icon=FluentIcon.SAVE)
        self.download_pdf_btn.setFixedWidth(120)
        self.download_pdf_btn.clicked.connect(self._on_download_pdf)
        toolbar_layout.addWidget(self.download_pdf_btn)

        layout.addWidget(toolbar)

        info_card = FluentCard()
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(20, 15, 20, 15)
        info_layout.setSpacing(8)

        self.title_label = TitleLabel("文章标题")
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(f"color: {COLORS['text']}; font-size: 24px; font-weight: bold;")
        info_layout.addWidget(self.title_label)

        meta_layout = QHBoxLayout()
        meta_layout.setSpacing(20)

        self.account_label = BodyLabel("公众号: -")
        self.account_label.setStyleSheet(f"color: {COLORS['primary']}; font-size: 14px;")
        meta_layout.addWidget(self.account_label)

        self.time_label = BodyLabel("发布时间: -")
        self.time_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 14px;")
        meta_layout.addWidget(self.time_label)

        meta_layout.addStretch()
        info_layout.addLayout(meta_layout)

        layout.addWidget(info_card)

        content_card = FluentCard()
        content_layout = QVBoxLayout(content_card)
        content_layout.setContentsMargins(0, 0, 0, 0)

        self.content_text = QWebEngineView()
        self.content_text.setStyleSheet(f"""
            QWebEngineView {{
                background-color: {COLORS['surface']};
                border: none;
            }}
        """)

        content_layout.addWidget(self.content_text)

        layout.addWidget(content_card, 1)

        hint_label = BodyLabel("提示: 使用 ← → 方向键或 A/D 键切换文章，按 ESC 关闭")
        hint_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint_label)

    def _setup_shortcuts(self):
        pass

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()

        if key == Qt.Key.Key_Left or key == Qt.Key.Key_A:
            self._on_prev()
            return

        if key == Qt.Key.Key_Right or key == Qt.Key.Key_D:
            self._on_next()
            return

        if key == Qt.Key.Key_Escape:
            self.close()
            return

        super().keyPressEvent(event)

    def set_articles(self, articles: list, current_index: int = 0):
        self.articles = articles
        self.current_index = max(0, min(current_index, len(articles) - 1)) if articles else 0
        self._update_display()

    def _update_display(self):
        if not self.articles:
            self.title_label.setText("无文章")
            self.account_label.setText("公众号: -")
            self.time_label.setText("发布时间: -")
            self.content_text.setText("")
            self.count_label.setText("0 / 0")
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            self.open_link_btn.setEnabled(False)
            return

        article = self.articles[self.current_index]

        title = article.get('标题', '无标题')
        self.title_label.setText(title)
        self.setWindowTitle(f"文章详情 - {title}")

        account = article.get('公众号', '-')
        self.account_label.setText(f"📱 公众号: {account}")

        pub_time = article.get('发布时间', '-')
        self.time_label.setText(f"📅 发布时间: {pub_time}")

        content = article.get('内容', '')
        if content:
            html = self._md_to_html(content)
            self.content_text.setHtml(html, QUrl("https://mp.weixin.qq.com"))
        else:
            self.content_text.setHtml("<html><body style='color:#999;text-align:center;padding:40px;background:#1e1e1e;font-size:16px;'>无内容</body></html>")

        self.content_text.page().runJavaScript("window.scrollTo(0,0)")

        self.count_label.setText(f"{self.current_index + 1} / {len(self.articles)}")

        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(self.current_index < len(self.articles) - 1)

        link = article.get('链接', '')
        self.open_link_btn.setEnabled(bool(link))

    def _on_prev(self):
        if self.current_index > 0:
            self.current_index -= 1
            self._update_display()
            self.article_changed.emit(self.current_index)

    def _on_next(self):
        if self.current_index < len(self.articles) - 1:
            self.current_index += 1
            self._update_display()
            self.article_changed.emit(self.current_index)

    def _on_open_link(self):
        if self.articles and 0 <= self.current_index < len(self.articles):
            link = self.articles[self.current_index].get('链接', '')
            if link:
                QDesktopServices.openUrl(QUrl(link))

    def go_to_article(self, index: int):
        if 0 <= index < len(self.articles):
            self.current_index = index
            self._update_display()

    def _md_to_html(self, text):
        if not text:
            return '<html><body style="color:#999;text-align:center;padding:40px;background:#1e1e1e;font-size:16px;">无内容</body></html>'
        text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'<img src="\2" alt="\1" style="max-width:100%;">', text)
        text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        parts = []
        for line in lines:
            if not line.startswith('<'):
                parts.append(f'<p>{line}</p>')
            else:
                parts.append(line)
        body = '\n'.join(parts)
        return f'''<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif; padding: 20px; line-height: 1.8; color: #333; background: #fff; }}
img {{ max-width: 100%; height: auto; }}
p {{ margin: 8px 0; }}
</style></head><body>
{body}
</body></html>'''

    def _on_download_pdf(self):
        if not self.articles or self.current_index >= len(self.articles):
            return
        article = self.articles[self.current_index]
        title = article.get('标题', '无标题')
        account = article.get('公众号', '')
        content = article.get('内容', '')

        from PyQt6.QtWidgets import QFileDialog
        safe_title = ''.join(c for c in title if c not in r'\/:*?"<>|')[:100] or 'untitled'
        safe_account = ''.join(c for c in account if c not in r'\/:*?"<>|')[:50] or 'unknown'
        default_name = f"{safe_account}_{safe_title}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出PDF", default_name, "PDF文件 (*.pdf)"
        )
        if not file_path:
            return

        from spider.wechat.pdf_generator import generate_article_pdf
        try:
            pdf_path = generate_article_pdf(
                article_title=title,
                account_name=account,
                markdown_content=content,
                output_dir=os.path.dirname(file_path),
            )
            import shutil
            if pdf_path != file_path:
                shutil.move(pdf_path, file_path)
            InfoBar.success(
                title="PDF导出成功",
                content=f"已保存到 {file_path}",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000
            )
        except Exception as e:
            InfoBar.error(
                title="PDF导出失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000
            )


class ImageExtractDialog(QDialog):
    def __init__(self, article_url, generate_pdf=True, parent=None):
        super().__init__(parent)
        self.generate_pdf = generate_pdf
        title_text = "导出PDF" if generate_pdf else "图片提取"
        self.setWindowTitle(title_text)
        self.setModal(True)
        self.resize(560, 420)
        self.worker = None
        self._output_folder = None
        self._image_urls = []

        screen = QApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            self.move((sg.width() - 560) // 2, (sg.height() - 420) // 2)

        self._setup_ui(title_text)
        self.url_input.setText(article_url)
        QTimer.singleShot(100, self._on_start_extract)

    def _setup_ui(self, title_text):
        self.setStyleSheet(f"""
            QDialog {{ background-color: {COLORS['background']}; }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title = TitleLabel(title_text)
        layout.addWidget(title)

        url_row = QHBoxLayout()
        url_label = BodyLabel("文章链接:")
        url_label.setFixedWidth(65)
        url_row.addWidget(url_label)
        self.url_input = LineEdit()
        self.url_input.setReadOnly(True)
        url_row.addWidget(self.url_input)
        layout.addLayout(url_row)

        info_row = QHBoxLayout()
        info_label = BodyLabel("文章标题:")
        info_label.setFixedWidth(65)
        info_row.addWidget(info_label)
        self.article_title_label = BodyLabel("等待下载...")
        self.article_title_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        info_row.addWidget(self.article_title_label, 1)
        layout.addLayout(info_row)

        count_row = QHBoxLayout()
        cnt_label = BodyLabel("图片数量:")
        cnt_label.setFixedWidth(65)
        count_row.addWidget(cnt_label)
        self.image_count_label = BodyLabel("0")
        count_row.addWidget(self.image_count_label)
        count_row.addStretch()
        layout.addLayout(count_row)

        list_label = BodyLabel("图片列表:")
        layout.addWidget(list_label)

        self.image_list_text = TextEdit()
        self.image_list_text.setReadOnly(True)
        self.image_list_text.setPlaceholderText("下载的图片链接将显示在这里...")
        self.image_list_text.setStyleSheet(f"""
            TextEdit {{
                background-color: {COLORS['surface']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 10px;
                font-size: 13px;
            }}
        """)
        layout.addWidget(self.image_list_text, 1)

        progress_layout = QHBoxLayout()
        self.progress_bar = ProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.hide()
        progress_layout.addWidget(self.progress_bar)
        layout.addLayout(progress_layout)

        self.status_label = CaptionLabel("")
        self.status_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        self.cancel_btn = PushButton("取消", icon=FluentIcon.CLOSE)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self.cancel_btn)

        self.open_folder_btn = PushButton("打开文件夹", icon=FluentIcon.FOLDER)
        self.open_folder_btn.clicked.connect(self._on_open_folder)
        self.open_folder_btn.hide()
        btn_row.addWidget(self.open_folder_btn)

        btn_row.addStretch()
        close_btn = PrimaryPushButton("关闭", icon=FluentIcon.CLOSE)
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _on_start_extract(self):
        from gui.pages.article_downloader import ImageExtractWorker
        from gui.utils import DEFAULT_OUTPUT_DIR

        url = self.url_input.text().strip()
        if not url:
            return

        output_dir = DEFAULT_OUTPUT_DIR
        os.makedirs(output_dir, exist_ok=True)

        self._image_urls = []
        self.article_title_label.setText("下载中...")
        self.image_list_text.clear()
        self.image_count_label.setText("0")
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.cancel_btn.show()
        self.open_folder_btn.hide()
        self.status_label.setText("正在下载...")

        self.worker = ImageExtractWorker(url=url, output_dir=output_dir, save_images=True, generate_pdf=self.generate_pdf)
        self.worker.progress_update.connect(self._on_progress_update)
        self.worker.image_found.connect(self._on_image_found)
        self.worker.extract_success.connect(self._on_extract_success)
        self.worker.extract_failed.connect(self._on_extract_failed)
        self.worker.download_progress.connect(self._on_download_progress)
        self.worker.download_complete.connect(self._on_download_complete)
        self.worker.start()

    def _on_cancel(self):
        if self.worker:
            self.worker.cancel()
            self.worker = None
        self.cancel_btn.hide()
        self.progress_bar.hide()
        self.status_label.setText("已取消")

    def _on_open_folder(self):
        if self._output_folder:
            os.startfile(self._output_folder)

    def _on_progress_update(self, current, total, message):
        if total > 0:
            self.progress_bar.setValue(int(current * 100 / total))
        self.status_label.setText(message)

    def _on_image_found(self, index, url, alt):
        self._image_urls.append((index, url, alt))
        self.image_count_label.setText(str(len(self._image_urls)))
        current_text = self.image_list_text.toPlainText()
        self.image_list_text.setPlainText(current_text + f"{index}. {url[:80]}{'...' if len(url) > 80 else ''}\n")

    def _on_download_progress(self, current, total, message):
        progress = 70 + int(current * 30 / total)
        self.progress_bar.setValue(progress)
        self.status_label.setText(message)

    def _on_extract_success(self, title, images, md_content):
        self.article_title_label.setText(title)
        self.article_title_label.setStyleSheet(f"color: {COLORS['success']};")
        self.image_count_label.setText(str(len(images)))
        self.cancel_btn.hide()
        self.progress_bar.setValue(100)

        InfoBar.success(title="下载完成", content=f"共提取 {len(images)} 张图片", parent=self, position=InfoBarPosition.TOP, duration=3000)

    def _on_extract_failed(self, error_msg):
        self.cancel_btn.hide()
        self.progress_bar.hide()
        self.status_label.setText(f"失败: {error_msg}")
        self.status_label.setStyleSheet(f"color: {COLORS['error']};")
        InfoBar.error(title="下载失败", content=error_msg, parent=self, position=InfoBarPosition.TOP, duration=5000)

    def _on_download_complete(self, folder_path):
        self._output_folder = folder_path
        self.open_folder_btn.show()
        self.status_label.setText(f"完成！保存到: {folder_path}")
        self.status_label.setStyleSheet(f"color: {COLORS['success']};")
