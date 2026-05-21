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

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QHeaderView, QTableWidgetItem, QAbstractItemView, QMenu, QApplication
from PyQt6.QtCore import Qt, QUrl
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
        self._load_from_db()

    def showEvent(self, event):
        super().showEvent(event)
        self._load_from_db(silent=True)

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
        self.search_input.textChanged.connect(self._on_search)
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
        self.data_table.setColumnCount(4)
        self.data_table.setHorizontalHeaderLabels(["公众号", "标题", "匹配内容", "发布时间"])
        self.data_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.data_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.data_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.data_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.data_table.setColumnWidth(2, 200)
        self.data_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.data_table.doubleClicked.connect(self._on_table_double_clicked)
        self.data_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.data_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.data_table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.data_table, 1)

        self.preview_dialog = None

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        open_folder_btn = PushButton("打开结果目录", icon=FluentIcon.FOLDER)
        open_folder_btn.clicked.connect(self._on_open_folder)
        btn_layout.addWidget(open_folder_btn)
        layout.addLayout(btn_layout)

    def _load_from_db(self, account=None, source_info="数据库", silent=False):
        db = Database(DB_PATH)
        if account:
            rows = db.get_articles(account)
        else:
            rows = db.get_articles()
        db.close()

        if not rows:
            if not silent:
                InfoBar.warning(title="提示", content="数据库中没有数据", parent=self, position=InfoBarPosition.TOP, duration=2000)
            return

        self.articles = []
        accounts_set = set()
        for row in rows:
            article = {
                '公众号': row.get('account_name', ''),
                '标题': row.get('title', ''),
                '发布时间': row.get('publish_time', ''),
                '链接': row.get('link', ''),
                '内容': row.get('content', '')
            }
            self.articles.append(article)
            if article['公众号']:
                accounts_set.add(article['公众号'])

        self.source_info = source_info

        self.account_filter.clear()
        self.account_filter.addItem("全部")
        for account in sorted(accounts_set):
            self.account_filter.addItem(account)

        self._apply_filters()

        if not silent:
            InfoBar.success(title="数据已加载", content=f"共 {len(self.articles)} 条记录", parent=self, position=InfoBarPosition.TOP, duration=3000)

    def _display_articles(self, articles, match_texts):
        self.data_table.setRowCount(len(articles))
        for i, article in enumerate(articles):
            self.data_table.setItem(i, 0, QTableWidgetItem(article.get('公众号', '')))
            self.data_table.setItem(i, 1, QTableWidgetItem(article.get('标题', '')))
            self.data_table.setItem(i, 2, QTableWidgetItem(match_texts[i] if i < len(match_texts) else ''))
            self.data_table.setItem(i, 3, QTableWidgetItem(article.get('发布时间', '')))
        self.count_label.setText(f"共 {len(articles)} 条记录")

    def _on_search(self, text):
        self._apply_filters()

    def _on_filter_changed(self, account):
        self._apply_filters()

    def _apply_filters(self):
        search_text = self.search_input.text().strip().lower()
        account_filter = self.account_filter.currentText()

        filtered = self.articles
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

    def _on_fullscreen_preview(self):
        row = self.data_table.currentRow()
        if row < 0:
            return

        filtered = self._get_filtered_articles()
        if not filtered:
            return

        if self.preview_dialog is None:
            self.preview_dialog = ArticlePreviewDialog(self.window())
            self.preview_dialog.article_changed.connect(self._on_preview_article_changed)

        self.preview_dialog.set_articles(filtered, row)
        self.preview_dialog.exec()

    def _on_preview_article_changed(self, index):
        if 0 <= index < self.data_table.rowCount():
            self.data_table.selectRow(index)

    def _get_filtered_with_matches(self):
        search_text = self.search_input.text().strip().lower()
        account_filter = self.account_filter.currentText()

        filtered = self.articles
        if account_filter != "全部":
            filtered = [a for a in filtered if a.get('公众号', '') == account_filter]

        match_texts = [None] * len(filtered)
        if search_text:
            matched_articles = []
            matched_texts = []
            for article in filtered:
                title = article.get('标题', '') or ''
                content = article.get('内容', '') or ''
                title_match = search_text in title.lower()
                content_lower = content.lower()
                pos = content_lower.find(search_text)
                if title_match or pos >= 0:
                    matched_articles.append(article)
                    if pos >= 0:
                        matched_texts.append(_get_match_context(content, pos, pos + len(search_text)))
                    else:
                        matched_texts.append('')
            return matched_articles, matched_texts
        return filtered, match_texts

    def _get_filtered_articles(self):
        articles, _ = self._get_filtered_with_matches()
        return articles

    def _on_context_menu(self, pos):
        item = self.data_table.itemAt(pos)
        if item is None:
            return

        row = item.row()
        if row < 0:
            return

        filtered = self._get_filtered_articles()
        if row >= len(filtered):
            return

        article = filtered[row]
        link = article.get('链接', '')

        match_item = self.data_table.item(row, 2)
        match_text = match_item.text() if match_item else ''

        menu = QMenu(self)

        preview_action = QAction("全屏预览", self)
        preview_action.triggered.connect(lambda: self._preview_article_at_row(row))
        menu.addAction(preview_action)

        if link:
            open_action = QAction("查看原文", self)
            open_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(link)))
            menu.addAction(open_action)

        if match_text:
            menu.addSeparator()
            copy_match_action = QAction("复制匹配内容", self)
            copy_match_action.triggered.connect(lambda: QApplication.clipboard().setText(match_text))
            menu.addAction(copy_match_action)

            if match_text.startswith('http'):
                open_match_action = QAction("查看原文匹配链接", self)
                open_match_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(match_text)))
                menu.addAction(open_match_action)

        menu.addSeparator()

        if link:
            extract_action = QAction("图片提取", self)
            extract_action.triggered.connect(lambda: self._on_download_images(link))
            menu.addAction(extract_action)

        menu.exec(self.data_table.viewport().mapToGlobal(pos))

    def _preview_article_at_row(self, row):
        self.data_table.selectRow(row)
        self._on_fullscreen_preview()

    def _on_export_pdf(self, link):
        dialog = ImageExtractDialog(link, generate_pdf=True, parent=self.window())
        dialog.exec()

    def _on_download_images(self, link):
        dialog = ImageExtractDialog(link, generate_pdf=False, parent=self.window())
        dialog.exec()

    def _on_open_folder(self):
        from gui.utils import DEFAULT_OUTPUT_DIR
        results_dir = os.path.abspath(DEFAULT_OUTPUT_DIR)
        if not os.path.exists(results_dir):
            os.makedirs(results_dir)
        QDesktopServices.openUrl(QUrl.fromLocalFile(results_dir))

    def load_articles_data(self, articles, source_info="爬取结果"):
        self.articles = []
        accounts = set()
        for article in articles:
            row = {
                '公众号': article.get('name', ''),
                '标题': article.get('title', ''),
                '发布时间': article.get('publish_time', ''),
                '链接': article.get('link', ''),
                '内容': article.get('content', '')
            }
            self.articles.append(row)
            if row['公众号']:
                accounts.add(row['公众号'])

        self.source_info = source_info

        self.account_filter.clear()
        self.account_filter.addItem("全部")
        for account in sorted(accounts):
            self.account_filter.addItem(account)

        self._apply_filters()

        InfoBar.success(title="数据已加载", content=f"共 {len(self.articles)} 条记录", parent=self, position=InfoBarPosition.TOP, duration=3000)


