#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结果查看页面模块

提供爬取结果的查看、筛选和搜索功能。采用 Fluent Design 风格设计。

主要功能：
    - 从数据库加载和显示爬取结果数据
    - 关键词搜索标题和正文
    - 按公众号筛选文章
    - 双击预览文章内容
    - 右键菜单操作（预览、打开链接、图片提取、复制匹配内容）

界面布局：
    - 顶部：汇总信息
    - 筛选栏：搜索 + 公众号过滤
    - 主体：文章数据表格（含匹配内容列）
    - 底部：打开结果目录按钮
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QHeaderView, QTableWidgetItem, QAbstractItemView, QMenu, QApplication, QMessageBox
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import QDesktopServices, QAction
import os
import re

from qfluentwidgets import ScrollArea, BodyLabel, CardWidget, PushButton, LineEdit, ComboBox, InfoBar, InfoBarPosition, FluentIcon
from qfluentwidgets import TableWidget as FluentTable

from ..styles import COLORS
from .article_detail import ArticlePreviewDialog, ImageExtractDialog
from ..utils import DEFAULT_OUTPUT_DIR
from spider.database import Database
from gui.utils import DB_PATH


def wildcard_to_regex(pattern, is_url_pattern=False):
    regex_pattern = ""
    for char in pattern:
        if char == '*':
            if is_url_pattern:
                regex_pattern += r'[A-Za-z0-9_\-\.~:/?#\[\]@!$&\'()+,;=%]*'
            else:
                regex_pattern += '.*'
        elif char == '?':
            if is_url_pattern:
                regex_pattern += r'[A-Za-z0-9_\-\.~:/?#\[\]@!$&\'()+,;=%]'
            else:
                regex_pattern += '.'
        elif char in r'\[](){}|^$+.':
            regex_pattern += '\\' + char
        else:
            regex_pattern += char
    return re.compile(regex_pattern, re.IGNORECASE)


def extract_urls_from_text(text, url_pattern_regex):
    matches = []
    for match in url_pattern_regex.finditer(text):
        url = match.group()
        url = _clean_url(url)
        if url and url not in matches:
            matches.append(url)
    return matches


def _get_match_context(text, start, end, ctx=20):
    before = text[max(0, start - ctx):start]
    match = text[start:end]
    after = text[end:end + ctx]
    if start > ctx:
        before = '...' + before.replace('\n', ' ')
    if end + ctx < len(text):
        after = after.replace('\n', ' ') + '...'
    result = f"{before}{match}{after}"
    if len(result) > 150:
        result = result[:150] + '...'
    return result


def _clean_url(url):
    if not url:
        return url

    invalid_trailing = ['*', ')', ']', '>', '"', "'", '，', '。', '！', '？',
                        '、', '；', '：', '\u201c', '\u201d', '\u2018', '\u2019',
                        '）', '】', '》', '\n', '\r', '\t', ' ']

    changed = True
    while changed and url:
        changed = False
        for char in invalid_trailing:
            if url.endswith(char):
                url = url[:-1]
                changed = True
                break
    return url


class ArticlesPage(ScrollArea):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.articles = []
        self.source_info = ""
        self._page_size = 50
        self._current_page = 1
        self._total_pages = 1
        self._total_count = 0
        self._search_mode = False
        self._all_match_texts = []

        self.setObjectName("resultsPage")

        self.setStyleSheet("""
            QScrollArea#resultsPage {
                background-color: #1a1a1a;
                border: none;
            }
            QScrollArea#resultsPage > QWidget > QWidget {
                background-color: #1a1a1a;
            }
        """)

        self._setup_ui()
        QTimer.singleShot(1500, self._warmup_preview_dialog)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: self._load_from_db(silent=True) if self.isVisible() else None)

    def _setup_ui(self):
        self.setWidgetResizable(True)
        container = QWidget()
        self.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 20, 36, 36)
        layout.setSpacing(15)

        filter_card = CardWidget()
        filter_card_layout = QVBoxLayout(filter_card)
        filter_card_layout.setContentsMargins(15, 10, 15, 10)
        filter_card_layout.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(BodyLabel("搜索"))
        self.search_input = LineEdit()
        self.search_input.setPlaceholderText("关键词搜索标题和正文...")
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._on_search)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.setMaximumWidth(280)
        row1.addWidget(self.search_input)

        row1.addSpacing(16)
        row1.addWidget(BodyLabel("公众号"))
        self.account_filter = ComboBox()
        self.account_filter.addItem("全部")
        self.account_filter.currentTextChanged.connect(self._on_filter_changed)
        self.account_filter.setMinimumWidth(140)
        row1.addWidget(self.account_filter)

        row1.addStretch()
        self.count_label = BodyLabel("共 0 条记录")
        row1.addWidget(self.count_label)
        filter_card_layout.addLayout(row1)

        layout.addWidget(filter_card)

        self.data_table = FluentTable()
        self.data_table.setColumnCount(5)
        self.data_table.setHorizontalHeaderLabels(["公众号", "标题", "匹配内容", "发布时间", "状态"])
        self.data_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.data_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.data_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.data_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.data_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.data_table.setColumnWidth(2, 200)
        self.data_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.data_table.doubleClicked.connect(self._on_table_double_clicked)
        self.data_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.data_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.data_table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.data_table, 1)

        pagination_layout = QHBoxLayout()
        pagination_layout.setSpacing(8)
        pagination_layout.addStretch()
        self.prev_page_btn = PushButton("上一页", icon=FluentIcon.LEFT_ARROW)
        self.prev_page_btn.setFixedWidth(100)
        self.prev_page_btn.clicked.connect(self._on_prev_page)
        pagination_layout.addWidget(self.prev_page_btn)
        self.page_label = BodyLabel("第 1 / 1 页")
        self.page_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        pagination_layout.addWidget(self.page_label)
        self.next_page_btn = PushButton("下一页", icon=FluentIcon.RIGHT_ARROW)
        self.next_page_btn.setFixedWidth(100)
        self.next_page_btn.clicked.connect(self._on_next_page)
        pagination_layout.addWidget(self.next_page_btn)
        pagination_layout.addStretch()
        layout.addLayout(pagination_layout)

        self.preview_dialog = None

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        open_folder_btn = PushButton("打开结果目录", icon=FluentIcon.FOLDER)
        open_folder_btn.clicked.connect(self._on_open_folder)
        btn_layout.addWidget(open_folder_btn)
        layout.addLayout(btn_layout)

    def _load_from_db(self, account=None, source_info="数据库", silent=False, page=None):
        if page is not None:
            self._current_page = page
        self._search_mode = False
        db = Database(DB_PATH)
        filter_acct = account if account else None
        if filter_acct is None:
            combo_text = self.account_filter.currentText()
            if combo_text != "全部":
                filter_acct = combo_text
        self._total_count = db.get_articles_count(account=filter_acct)
        self._total_pages = max(1, (self._total_count + self._page_size - 1) // self._page_size)
        if self._current_page > self._total_pages:
            self._current_page = self._total_pages
        rows = db.get_articles_page(page=self._current_page, page_size=self._page_size, account=filter_acct)
        self.articles = []
        for row in rows:
            self.articles.append({
                '公众号': row.get('account_name', ''),
                '标题': row.get('title', ''),
                '发布时间': row.get('publish_time', ''),
                '链接': row.get('link', ''),
                '内容': row.get('content', '') or '',
                'has_content': bool(row.get('has_content', False))
            })
        accounts_list = db.get_accounts()
        db.close()
        self.source_info = source_info
        self.account_filter.blockSignals(True)
        self.account_filter.clear()
        self.account_filter.addItem("全部")
        for acct in accounts_list:
            self.account_filter.addItem(acct)
        if filter_acct:
            idx = self.account_filter.findText(filter_acct)
            if idx >= 0:
                self.account_filter.setCurrentIndex(idx)
        self.account_filter.blockSignals(False)
        self._display_articles(self.articles, [''] * len(self.articles))
        if not silent and self._total_count > 0:
            InfoBar.success(title="数据已加载", content=f"共 {self._total_count} 条记录", parent=self, position=InfoBarPosition.TOP, duration=3000)

    def _display_articles(self, articles, match_texts):
        self.articles = articles
        self._all_match_texts = match_texts
        if self._search_mode:
            self._total_count = len(articles)
            self._total_pages = max(1, (self._total_count + self._page_size - 1) // self._page_size)
            if self._current_page > self._total_pages:
                self._current_page = self._total_pages
        self._render_page()

    def _render_page(self):
        if self._search_mode:
            start = (self._current_page - 1) * self._page_size
            end = start + self._page_size
            page_articles = self.articles[start:end]
            page_matches = self._all_match_texts[start:end]
        else:
            page_articles = self.articles
            page_matches = [''] * len(page_articles)

        table = self.data_table
        table.setSortingEnabled(False)
        table.setUpdatesEnabled(False)
        table.setRowCount(len(page_articles))
        for i, article in enumerate(page_articles):
            item0 = QTableWidgetItem(article.get('公众号', ''))
            item0.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(i, 0, item0)
            item1 = QTableWidgetItem(article.get('标题', ''))
            item1.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(i, 1, item1)
            item2 = QTableWidgetItem(page_matches[i] if i < len(page_matches) else '')
            item2.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(i, 2, item2)
            item3 = QTableWidgetItem(article.get('发布时间', ''))
            item3.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(i, 3, item3)
            has_content = article.get('has_content', False)
            status_item = QTableWidgetItem("已爬取" if has_content else "未爬取")
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if has_content:
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            table.setItem(i, 4, status_item)
        table.setUpdatesEnabled(True)
        table.setSortingEnabled(True)
        self.count_label.setText(f"共 {self._total_count} 条记录")
        self.page_label.setText(f"第 {self._current_page} / {self._total_pages} 页")
        self.prev_page_btn.setEnabled(self._current_page > 1)
        self.next_page_btn.setEnabled(self._current_page < self._total_pages)

    def _on_search_text_changed(self, text):
        self._search_timer.start()

    def _on_search(self):
        text = self.search_input.text().strip()
        if text:
            self._current_page = 1
            self._search_mode = True
            db = Database(DB_PATH)
            rows = db.get_articles(include_content=True)
            db.close()
            all_articles = []
            for row in rows:
                all_articles.append({
                    '公众号': row.get('account_name', ''),
                    '标题': row.get('title', ''),
                    '发布时间': row.get('publish_time', ''),
                    '链接': row.get('link', ''),
                    '内容': row.get('content', '') or '',
                    'has_content': bool(row.get('has_content', False))
                })
            self.source_info = "数据库"
            self._apply_local_filter(all_articles)
        else:
            self._search_mode = False
            self._current_page = 1
            self._load_from_db(silent=True)

    def _on_filter_changed(self, account):
        if self._search_mode:
            db = Database(DB_PATH)
            rows = db.get_articles(include_content=True)
            db.close()
            all_articles = []
            for row in rows:
                all_articles.append({
                    '公众号': row.get('account_name', ''),
                    '标题': row.get('title', ''),
                    '发布时间': row.get('publish_time', ''),
                    '链接': row.get('link', ''),
                    '内容': row.get('content', '') or '',
                    'has_content': bool(row.get('has_content', False))
                })
            self._apply_local_filter(all_articles)
        else:
            self._current_page = 1
            self._load_from_db(silent=True)

    def _apply_local_filter(self, all_articles):
        search_text = self.search_input.text().strip().lower()
        account_filter = self.account_filter.currentText()

        filtered = all_articles
        if account_filter != "全部":
            filtered = [a for a in filtered if a.get('公众号', '') == account_filter]

        match_texts = []
        if search_text:
            matched = []
            for article in filtered:
                title = article.get('标题', '') or ''
                content = article.get('内容', '') or ''
                title_match = search_text in title.lower()
                content_lower = content.lower()
                pos = content_lower.find(search_text)
                if title_match or pos >= 0:
                    matched.append(article)
                    if pos >= 0:
                        match_texts.append(_get_match_context(content, pos, pos + len(search_text)))
                    else:
                        match_texts.append('')
            filtered = matched
        else:
            match_texts = [''] * len(filtered)

        self._display_articles(filtered, match_texts)

    def _on_selection_changed(self):
        pass

    def _on_table_double_clicked(self, index):
        col = index.column()
        if col == 2:
            item = self.data_table.item(index.row(), 2)
            if item and item.text():
                text = item.text()
                if text.startswith('http'):
                    QDesktopServices.openUrl(QUrl(text))
                    return
                QApplication.clipboard().setText(text)
                return
        self._on_fullscreen_preview()

    def _ensure_content_for_articles(self):
        need_load = [a for a in self.articles if not a.get('内容')]
        if not need_load:
            return
        db = Database(DB_PATH)
        links = [a.get('链接', '') for a in need_load if a.get('链接')]
        for link in links:
            row = db.conn.execute(
                "SELECT content FROM articles WHERE link = ?", (link,)
            ).fetchone()
            if row and row['content']:
                for a in self.articles:
                    if a.get('链接') == link and not a.get('内容'):
                        a['内容'] = row['content']
                        break
        db.close()

    def _on_prev_page(self):
        if self._current_page > 1:
            self._current_page -= 1
            if self._search_mode:
                self._render_page()
            else:
                self._load_from_db(silent=True, page=self._current_page)

    def _on_next_page(self):
        if self._current_page < self._total_pages:
            self._current_page += 1
            if self._search_mode:
                self._render_page()
            else:
                self._load_from_db(silent=True, page=self._current_page)

    def _on_fullscreen_preview(self):
        displayed_row = self.data_table.currentRow()
        if displayed_row < 0:
            return

        self._ensure_content_for_articles()

        if self._search_mode:
            filtered = self.articles
            real_row = (self._current_page - 1) * self._page_size + displayed_row
        else:
            filtered = self.articles
            real_row = displayed_row

        if real_row >= len(filtered) or not filtered:
            return

        if self.preview_dialog is None:
            self.preview_dialog = ArticlePreviewDialog(self.window())
            self.preview_dialog.article_changed.connect(self._on_preview_article_changed)

        self.preview_dialog.set_articles(filtered, real_row)
        self.preview_dialog.exec()

    def _warmup_preview_dialog(self):
        if self.preview_dialog is None:
            self.preview_dialog = ArticlePreviewDialog(self.window())
            self.preview_dialog.article_changed.connect(self._on_preview_article_changed)

    def _on_preview_article_changed(self, index):
        if self._search_mode:
            if 0 <= index < len(self.articles):
                page_of_index = index // self._page_size + 1
                if page_of_index != self._current_page:
                    self._current_page = page_of_index
                    self._render_page()
                displayed_row = index % self._page_size
                if displayed_row < self.data_table.rowCount():
                    self.data_table.selectRow(displayed_row)
        else:
            if 0 <= index < len(self.articles):
                self.data_table.selectRow(index)

    def _get_filtered_articles(self):
        return self.articles

    def _on_context_menu(self, pos):
        item = self.data_table.itemAt(pos)
        if item is None:
            return

        displayed_row = item.row()
        if displayed_row < 0:
            return

        if self._search_mode:
            real_row = (self._current_page - 1) * self._page_size + displayed_row
        else:
            real_row = displayed_row

        if real_row >= len(self.articles):
            return

        article = self.articles[real_row]
        link = article.get('链接', '')

        match_item = self.data_table.item(displayed_row, 2)
        match_text = match_item.text() if match_item else ''

        menu = QMenu(self)

        preview_action = QAction("查看文章", self)
        preview_action.triggered.connect(lambda r=real_row: self._preview_article_at_row(r))
        menu.addAction(preview_action)

        open_action = QAction("查看原文", self)
        open_action.setEnabled(bool(link))
        if not link:
            open_action.setToolTip("原文可能已删除")
        open_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(link)))
        menu.addAction(open_action)

        menu.addSeparator()

        extract_action = QAction("图片提取", self)
        extract_action.setEnabled(bool(link))
        if not link:
            extract_action.setToolTip("原文可能已删除")
        extract_action.triggered.connect(lambda: self._on_download_images(link))
        menu.addAction(extract_action)

        menu.addSeparator()

        pdf_action = QAction("下载PDF", self)
        pdf_action.setEnabled(article.get('has_content', False))
        if not article.get('has_content', False):
            pdf_action.setToolTip("文章内容未爬取，无法生成PDF")
        pdf_action.triggered.connect(lambda r=real_row: self._on_download_pdf(r))
        menu.addAction(pdf_action)

        menu.addSeparator()

        delete_action = QAction("删除", self)
        delete_action.triggered.connect(lambda d=displayed_row, l=link: self._on_delete_article(d, l))
        menu.addAction(delete_action)

        menu.exec(self.data_table.viewport().mapToGlobal(pos))

    def _on_delete_article(self, row, link):
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除文章「{self.data_table.item(row, 1).text()}」吗？\n此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        title = self.data_table.item(row, 1).text()
        db = Database(DB_PATH)
        deleted = db.delete_article(link)
        db.close()

        if deleted:
            InfoBar.success(title="已删除", content=f"文章「{title}」已删除", parent=self, position=InfoBarPosition.TOP, duration=3000)
            self._load_from_db(silent=True)
        else:
            InfoBar.error(title="删除失败", content="未找到该文章", parent=self, position=InfoBarPosition.TOP, duration=3000)

    def _preview_article_at_row(self, real_row):
        if self._search_mode:
            page = real_row // self._page_size + 1
            if page != self._current_page:
                self._current_page = page
                self._render_page()
            displayed = real_row % self._page_size
        else:
            displayed = real_row
            if displayed >= len(self.articles):
                return
        self.data_table.selectRow(displayed)
        self._on_fullscreen_preview()

    def _on_export_pdf(self, link):
        dialog = ImageExtractDialog(link, generate_pdf=True, parent=self.window())
        dialog.exec()

    def _on_download_images(self, link):
        dialog = ImageExtractDialog(link, generate_pdf=False, parent=self.window())
        dialog.exec()

    def _on_download_pdf(self, real_row):
        if real_row >= len(self.articles):
            return
        article = self.articles[real_row]
        title = article.get('标题', '')
        account = article.get('公众号', '')
        content = article.get('内容', '')
        if not content:
            if not article.get('链接'):
                InfoBar.error(title="下载失败", content="文章内容为空且无链接", parent=self, position=InfoBarPosition.TOP, duration=3000)
                return
            db = Database(DB_PATH)
            row = db.conn.execute("SELECT content FROM articles WHERE link = ?", (article['链接'],)).fetchone()
            db.close()
            if row and row['content']:
                content = row['content']
                article['内容'] = content
        if not content:
            InfoBar.error(title="下载失败", content="文章内容为空", parent=self, position=InfoBarPosition.TOP, duration=3000)
            return
        from gui.utils import export_article_pdf
        export_article_pdf(title=title, account=account, content=content, parent=self)

    def _on_open_folder(self):
        from gui.utils import DEFAULT_OUTPUT_DIR
        results_dir = os.path.abspath(DEFAULT_OUTPUT_DIR)
        if not os.path.exists(results_dir):
            os.makedirs(results_dir)
        QDesktopServices.openUrl(QUrl.fromLocalFile(results_dir))

    def load_articles_data(self, articles, source_info="爬取结果"):
        self._search_mode = False
        self.articles = []
        accounts = set()
        for article in articles:
            content = article.get('content', '') or ''
            row = {
                '公众号': article.get('name', ''),
                '标题': article.get('title', ''),
                '发布时间': article.get('publish_time', ''),
                '链接': article.get('link', ''),
                '内容': content,
                'has_content': bool(content)
            }
            self.articles.append(row)
            if row['公众号']:
                accounts.add(row['公众号'])

        self.source_info = source_info
        self._total_count = len(self.articles)
        self._current_page = 1
        self._total_pages = max(1, (self._total_count + self._page_size - 1) // self._page_size)

        self.account_filter.blockSignals(True)
        self.account_filter.clear()
        self.account_filter.addItem("全部")
        for account in sorted(accounts):
            self.account_filter.addItem(account)
        self.account_filter.blockSignals(False)

        self._render_page()

        InfoBar.success(title="数据已加载", content=f"共 {self._total_count} 条记录", parent=self, position=InfoBarPosition.TOP, duration=3000)


