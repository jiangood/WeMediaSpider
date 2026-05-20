#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结果查看页面模块

提供爬取结果的查看、筛选、搜索和导出功能。采用 Fluent Design 风格设计。

主要功能：
    - 从数据库加载和显示爬取结果数据
    - 标题关键词搜索
    - 正文通配符搜索（支持 * 和 ?，含快捷网盘链接模式）
    - 按公众号筛选文章
    - 双击预览文章内容
    - 右键菜单操作（预览、打开链接、图片提取、复制匹配内容）
    - 多格式导出（CSV、JSON、Excel、Markdown、HTML）

界面布局：
    - 顶部：数据来源信息和操作按钮
    - 筛选栏：标题搜索 + 内容搜索 + 公众号过滤
    - 快捷搜索按钮：夸克、百度、阿里、蓝奏、115、迅雷
    - 主体：文章数据表格（含匹配内容列）
    - 底部：打开结果目录按钮
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QHeaderView, QFileDialog, QTableWidgetItem, QAbstractItemView, QMenu, QApplication
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QAction
import os
import csv
import json
import re

from qfluentwidgets import ScrollArea, TitleLabel, BodyLabel, CardWidget, PrimaryPushButton, PushButton, LineEdit, ComboBox, InfoBar, InfoBarPosition, FluentIcon, MessageBox
from qfluentwidgets import TableWidget as FluentTable

from ..styles import COLORS
from ..widgets import ArticlePreviewDialog, ImageExtractDialog
from ..utils import DEFAULT_OUTPUT_DIR
from spider.database import Database
from gui.utils import DB_PATH


SUPPORTED_FORMATS = {
    'csv': ('CSV文件', '.csv'),
    'json': ('JSON文件', '.json'),
    'xlsx': ('Excel文件', '.xlsx'),
    'md': ('Markdown文件', '.md'),
    'html': ('HTML文件', '.html'),
}


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


class ResultsPage(ScrollArea):

    data_discarded = pyqtSignal()

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

    def _setup_ui(self):
        self.setWidgetResizable(True)
        container = QWidget()
        self.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 20, 36, 36)
        layout.setSpacing(15)

        layout.addWidget(TitleLabel("结果查看"))

        self.source_card = CardWidget()
        source_layout = QHBoxLayout(self.source_card)
        source_layout.setContentsMargins(20, 15, 20, 15)
        self.source_label = BodyLabel("数据来源: 未加载")
        self.source_label.setStyleSheet(f"color: {COLORS['primary']}; font-weight: bold;")
        source_layout.addWidget(self.source_label)
        source_layout.addStretch()

        self.discard_btn = PushButton("清空数据", icon=FluentIcon.DELETE)
        self.discard_btn.setFixedWidth(120)
        self.discard_btn.clicked.connect(self._on_discard_data)
        self.discard_btn.hide()
        source_layout.addWidget(self.discard_btn)

        self.save_btn = PrimaryPushButton("导出数据", icon=FluentIcon.SAVE)
        self.save_btn.setFixedWidth(140)
        self.save_btn.clicked.connect(self._on_save_results)
        self.save_btn.hide()
        source_layout.addWidget(self.save_btn)
        self.source_card.hide()
        layout.addWidget(self.source_card)

        filter_card = CardWidget()
        filter_card_layout = QVBoxLayout(filter_card)
        filter_card_layout.setContentsMargins(15, 10, 15, 10)
        filter_card_layout.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(BodyLabel("标题:"))
        self.search_input = LineEdit()
        self.search_input.setPlaceholderText("输入关键词搜索标题...")
        self.search_input.textChanged.connect(self._on_search)
        self.search_input.setMaximumWidth(280)
        row1.addWidget(self.search_input)

        row1.addSpacing(12)
        row1.addWidget(BodyLabel("内容:"))
        self.content_search_input = LineEdit()
        self.content_search_input.setPlaceholderText("输入通配符模式搜索正文，支持 * 和 ?")
        self.content_search_input.textChanged.connect(self._on_content_search)
        row1.addWidget(self.content_search_input, 1)

        row1.addSpacing(12)
        row1.addWidget(BodyLabel("公众号:"))
        self.account_filter = ComboBox()
        self.account_filter.addItem("全部")
        self.account_filter.currentTextChanged.connect(self._on_filter_changed)
        self.account_filter.setMinimumWidth(140)
        row1.addWidget(self.account_filter)

        self.count_label = BodyLabel("共 0 条记录")
        row1.addWidget(self.count_label)
        filter_card_layout.addLayout(row1)

        layout.addWidget(filter_card)

        self.data_table = FluentTable()
        self.data_table.setColumnCount(5)
        self.data_table.setHorizontalHeaderLabels(["公众号", "标题", "匹配内容", "发布时间", "操作"])
        self.data_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.data_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.data_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.data_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.data_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.data_table.setColumnWidth(2, 200)
        self.data_table.setColumnWidth(4, 130)
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

    def _load_from_db(self, account=None, source_info="数据库"):
        db = Database(DB_PATH)
        if account:
            rows = db.get_articles(account)
        else:
            rows = db.get_articles()
        db.close()

        if not rows:
            self.source_label.setText("数据来源: 数据库 (无数据)")
            self.source_card.show()
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

        self.source_label.setText(f"数据来源: {source_info} | 共 {len(self.articles)} 条记录")
        self.source_card.show()
        self.save_btn.show()
        self.discard_btn.show()

        InfoBar.success(title="数据已加载", content=f"{source_info} - 共 {len(self.articles)} 条记录", parent=self, position=InfoBarPosition.TOP, duration=3000)

    def _set_content_pattern(self, pattern):
        self.content_search_input.setText(pattern)

    def _display_articles(self, articles, match_texts):
        self.data_table.setRowCount(len(articles))
        for i, article in enumerate(articles):
            self.data_table.setItem(i, 0, QTableWidgetItem(article.get('公众号', '')))
            self.data_table.setItem(i, 1, QTableWidgetItem(article.get('标题', '')))
            self.data_table.setItem(i, 2, QTableWidgetItem(match_texts[i] if i < len(match_texts) else ''))
            self.data_table.setItem(i, 3, QTableWidgetItem(article.get('发布时间', '')))
            link = article.get('链接', '')
            container = QWidget()
            btn_layout = QHBoxLayout(container)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.setSpacing(4)
            view_btn = PushButton("查看")
            view_btn.setFixedSize(50, 26)
            view_btn.clicked.connect(lambda checked, row=i: self._preview_article_at_row(row))
            btn_layout.addWidget(view_btn)
            if link:
                img_btn = PushButton("下载")
                img_btn.setFixedSize(50, 26)
                img_btn.clicked.connect(lambda checked, url=link: self._on_extract_images(url))
                btn_layout.addWidget(img_btn)
            self.data_table.setCellWidget(i, 4, container)
        self.count_label.setText(f"共 {len(articles)} 条记录")

    def _on_search(self, text):
        self._apply_filters()

    def _on_content_search(self, text):
        self._apply_filters()

    def _on_filter_changed(self, account):
        self._apply_filters()

    def _apply_filters(self):
        search_text = self.search_input.text().strip().lower()
        account_filter = self.account_filter.currentText()
        content_pattern = self.content_search_input.text().strip()

        filtered = self.articles
        if account_filter != "全部":
            filtered = [a for a in filtered if a.get('公众号', '') == account_filter]
        if search_text:
            filtered = [a for a in filtered if search_text in a.get('标题', '').lower()]

        match_texts = []
        if content_pattern:
            is_url = content_pattern.startswith('http://') or content_pattern.startswith('https://')
            try:
                regex = wildcard_to_regex(content_pattern, is_url)
            except re.error:
                self._display_articles([], [])
                return
            matched = []
            for article in filtered:
                content = article.get('内容', '') or ''
                if is_url:
                    for m in regex.finditer(content):
                        url = _clean_url(m.group())
                        if url:
                            matched.append(article)
                            match_texts.append(_get_match_context(content, m.start(), m.end()))
                            break
                else:
                    m = regex.search(content)
                    if m:
                        matched.append(article)
                        match_texts.append(_get_match_context(content, m.start(), m.end()))
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
        content_pattern = self.content_search_input.text().strip()

        filtered = self.articles
        if account_filter != "全部":
            filtered = [a for a in filtered if a.get('公众号', '') == account_filter]
        if search_text:
            filtered = [a for a in filtered if search_text in a.get('标题', '').lower()]

        match_texts = [None] * len(filtered)
        if content_pattern:
            is_url = content_pattern.startswith('http://') or content_pattern.startswith('https://')
            try:
                regex = wildcard_to_regex(content_pattern, is_url)
            except re.error:
                return [], []
            matched_articles = []
            matched_texts = []
            for article in filtered:
                content = article.get('内容', '') or ''
                if is_url:
                    for m in regex.finditer(content):
                        url = _clean_url(m.group())
                        if url:
                            matched_articles.append(article)
                            matched_texts.append(_get_match_context(content, m.start(), m.end()))
                            break
                else:
                    m = regex.search(content)
                    if m:
                        matched_articles.append(article)
                        matched_texts.append(_get_match_context(content, m.start(), m.end()))
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
            open_action = QAction("在浏览器中打开", self)
            open_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(link)))
            menu.addAction(open_action)

        if match_text:
            menu.addSeparator()
            copy_match_action = QAction("复制匹配内容", self)
            copy_match_action.triggered.connect(lambda: QApplication.clipboard().setText(match_text))
            menu.addAction(copy_match_action)

            if match_text.startswith('http'):
                open_match_action = QAction("在浏览器中打开匹配链接", self)
                open_match_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(match_text)))
                menu.addAction(open_match_action)

        menu.addSeparator()

        if link:
            extract_action = QAction("图片提取", self)
            extract_action.triggered.connect(lambda: self._on_extract_images(link))
            menu.addAction(extract_action)

        menu.exec(self.data_table.viewport().mapToGlobal(pos))

    def _preview_article_at_row(self, row):
        self.data_table.selectRow(row)
        self._on_fullscreen_preview()

    def _on_extract_images(self, link):
        dialog = ImageExtractDialog(link, self.window())
        dialog.exec()

    def _on_export_all(self):
        if not self.articles:
            InfoBar.warning(title="提示", content="没有数据可导出", parent=self, position=InfoBarPosition.TOP, duration=2000)
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "导出文件", "", "CSV文件 (*.csv)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
                    if self.articles:
                        writer = csv.DictWriter(f, fieldnames=self.articles[0].keys())
                        writer.writeheader()
                        writer.writerows(self.articles)
                InfoBar.success(title="导出成功", content=f"数据已导出到 {file_path}", parent=self, position=InfoBarPosition.TOP, duration=3000)
            except Exception as e:
                InfoBar.error(title="导出失败", content=str(e), parent=self, position=InfoBarPosition.TOP, duration=3000)

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

        self.source_label.setText(f"数据来源: {source_info} | 共 {len(self.articles)} 条记录")
        self.source_card.show()
        self.save_btn.show()
        self.discard_btn.show()

        InfoBar.success(title="数据已加载", content=f"{source_info} - 共 {len(self.articles)} 条记录", parent=self, position=InfoBarPosition.TOP, duration=3000)

    def _on_save_results(self):
        if not self.articles:
            InfoBar.warning(title="提示", content="没有数据可保存", parent=self, position=InfoBarPosition.TOP, duration=2000)
            return

        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        accounts = set()
        for article in self.articles:
            account_name = article.get('公众号', '')
            if account_name:
                accounts.add(account_name)

        if len(accounts) == 1:
            account_name = list(accounts)[0]
            safe_name = "".join(c for c in account_name if c not in r'\/:*?"<>|')
            base_name = f"{safe_name}_{timestamp}"
        elif len(accounts) > 1:
            base_name = f"批量爬取_{len(accounts)}个公众号_{timestamp}"
        else:
            base_name = f"爬取结果_{timestamp}"

        filter_parts = []
        for fmt_key, (fmt_name, fmt_ext) in SUPPORTED_FORMATS.items():
            filter_parts.append(f"{fmt_name} (*{fmt_ext})")
        filter_str = ";;".join(filter_parts)

        default_name = os.path.join(DEFAULT_OUTPUT_DIR, f"{base_name}.csv")

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "保存结果", default_name, filter_str
        )

        if file_path:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)

                _, ext = os.path.splitext(file_path)
                ext = ext.lower()

                if ext == '.csv':
                    self._save_as_csv(file_path)
                elif ext == '.json':
                    self._save_as_json(file_path)
                elif ext == '.xlsx':
                    self._save_as_excel(file_path)
                elif ext == '.md':
                    self._save_as_markdown(file_path)
                elif ext == '.html':
                    self._save_as_html(file_path)
                else:
                    if not ext:
                        file_path += '.csv'
                    self._save_as_csv(file_path)

                self.source_label.setText(f"数据来源: {self.source_info} | 已导出到 {os.path.basename(file_path)}")
                self.save_btn.hide()
                self.discard_btn.hide()

                InfoBar.success(title="导出成功", content=f"数据已保存到 {file_path}", parent=self, position=InfoBarPosition.TOP, duration=3000)
            except Exception as e:
                InfoBar.error(title="导出失败", content=str(e), parent=self, position=InfoBarPosition.TOP, duration=3000)

    def _save_as_csv(self, file_path):
        with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
            if self.articles:
                writer = csv.DictWriter(f, fieldnames=self.articles[0].keys())
                writer.writeheader()
                writer.writerows(self.articles)

    def _save_as_json(self, file_path):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.articles, f, ensure_ascii=False, indent=2)

    def _save_as_excel(self, file_path):
        try:
            import pandas as pd
            df = pd.DataFrame(self.articles)
            df.to_excel(file_path, index=False, engine='openpyxl')
        except ImportError:
            raise ImportError("保存Excel格式需要安装 pandas 和 openpyxl 库。\n请运行: pip install pandas openpyxl")

    def _save_as_markdown(self, file_path):
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("# 微信公众号文章爬取结果\n\n")
            f.write(f"共 {len(self.articles)} 篇文章\n\n")
            f.write("---\n\n")

            for i, article in enumerate(self.articles, 1):
                f.write(f"## {i}. {article.get('标题', '无标题')}\n\n")
                f.write(f"- **公众号**: {article.get('公众号', '未知')}\n")
                f.write(f"- **发布时间**: {article.get('发布时间', '未知')}\n")
                link = article.get('链接', '')
                if link:
                    f.write(f"- **链接**: [{link}]({link})\n")
                f.write("\n")

                content = article.get('内容', '')
                if content:
                    f.write("### 内容\n\n")
                    f.write(content)
                    f.write("\n\n")

                f.write("---\n\n")

    def _save_as_html(self, file_path):
        articles_json = []
        for i, article in enumerate(self.articles):
            articles_json.append({
                'index': i + 1,
                'title': self._escape_html(article.get('标题', '无标题')),
                'account': self._escape_html(article.get('公众号', '未知')),
                'pub_time': self._escape_html(article.get('发布时间', '未知')),
                'link': article.get('链接', ''),
                'content': self._markdown_to_html(article.get('内容', ''))
            })

        articles_data = json.dumps(articles_json, ensure_ascii=False)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>微信公众号文章爬取结果</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            margin: 0;
            padding: 0;
            background: #f5f5f5;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            background: linear-gradient(135deg, #07c160 0%, #05a14e 100%);
            color: white;
            padding: 15px 20px;
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        }
        .header h1 {
            margin: 0 0 10px 0;
            font-size: 20px;
            font-weight: 600;
        }
        .nav-controls {
            display: flex;
            align-items: center;
            gap: 15px;
            flex-wrap: wrap;
        }
        .nav-btn {
            background: rgba(255,255,255,0.2);
            border: none;
            color: white;
            padding: 8px 20px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            gap: 5px;
        }
        .nav-btn:hover:not(:disabled) {
            background: rgba(255,255,255,0.3);
            transform: translateY(-1px);
        }
        .nav-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .page-info {
            background: rgba(255,255,255,0.2);
            padding: 8px 15px;
            border-radius: 20px;
            font-size: 14px;
        }
        .article-select {
            padding: 8px 12px;
            border-radius: 20px;
            border: none;
            background: rgba(255,255,255,0.9);
            color: #333;
            font-size: 14px;
            max-width: 300px;
            cursor: pointer;
        }
        .article-container {
            flex: 1;
            max-width: 900px;
            margin: 20px auto;
            padding: 0 20px;
            width: 100%;
        }
        .article {
            background: white;
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            animation: fadeIn 0.3s ease;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .article h2 {
            color: #07c160;
            margin: 0 0 20px 0;
            font-size: 24px;
            line-height: 1.4;
        }
        .meta {
            color: #666;
            font-size: 14px;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 1px solid #eee;
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
        }
        .meta-item {
            display: flex;
            align-items: center;
            gap: 5px;
        }
        .content {
            line-height: 1.9;
            color: #333;
            font-size: 16px;
        }
        .content img {
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            margin: 15px 0;
        }
        .content p {
            margin: 0 0 15px 0;
        }
        .content a {
            color: #07c160;
            text-decoration: none;
        }
        .content a:hover {
            text-decoration: underline;
        }
        .no-content {
            color: #999;
            font-style: italic;
            text-align: center;
            padding: 40px;
        }
        .footer-nav {
            background: white;
            padding: 15px 20px;
            display: flex;
            justify-content: center;
            gap: 20px;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.05);
        }
        .footer-btn {
            background: #07c160;
            border: none;
            color: white;
            padding: 12px 30px;
            border-radius: 25px;
            cursor: pointer;
            font-size: 15px;
            transition: all 0.3s;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .footer-btn:hover:not(:disabled) {
            background: #05a14e;
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(7,193,96,0.3);
        }
        .footer-btn:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .keyboard-hint {
            text-align: center;
            color: #999;
            font-size: 12px;
            padding: 10px;
            background: #f9f9f9;
        }
        .keyboard-hint kbd {
            background: #eee;
            padding: 2px 8px;
            border-radius: 4px;
            border: 1px solid #ddd;
            font-family: monospace;
        }
        @media (max-width: 768px) {
            .header h1 { font-size: 18px; }
            .nav-controls { gap: 10px; }
            .nav-btn { padding: 6px 15px; font-size: 13px; }
            .article { padding: 20px; }
            .article h2 { font-size: 20px; }
            .content { font-size: 15px; }
            .article-select { max-width: 200px; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>📚 微信公众号文章爬取结果</h1>
        <div class="nav-controls">
            <button class="nav-btn" id="prevBtn" onclick="prevArticle()">
                ◀ 上一篇
            </button>
            <span class="page-info" id="pageInfo">1 / """ + str(len(self.articles)) + """</span>
            <button class="nav-btn" id="nextBtn" onclick="nextArticle()">
                下一篇 ▶
            </button>
            <select class="article-select" id="articleSelect" onchange="goToArticle(this.value)">
            </select>
        </div>
    </div>

    <div class="article-container">
        <div class="article" id="articleContent">
        </div>
    </div>

    <div class="footer-nav">
        <button class="footer-btn" id="footerPrevBtn" onclick="prevArticle()">
            ◀ 上一篇
        </button>
        <button class="footer-btn" id="footerNextBtn" onclick="nextArticle()">
            下一篇 ▶
        </button>
    </div>

    <div class="keyboard-hint">
        💡 快捷键: <kbd>←</kbd> 上一篇 | <kbd>→</kbd> 下一篇 | <kbd>Home</kbd> 第一篇 | <kbd>End</kbd> 最后一篇
    </div>

    <script>
        const articles = """ + articles_data + """;
        let currentIndex = 0;

        function init() {
            const select = document.getElementById('articleSelect');
            articles.forEach((article, index) => {
                const option = document.createElement('option');
                option.value = index;
                option.textContent = `${article.index}. ${article.title.substring(0, 30)}${article.title.length > 30 ? '...' : ''}`;
                select.appendChild(option);
            });

            showArticle(0);
        }

        function showArticle(index) {
            if (index < 0 || index >= articles.length) return;

            currentIndex = index;
            const article = articles[index];

            const container = document.getElementById('articleContent');
            let linkHtml = '';
            if (article.link) {
                linkHtml = `<span class="meta-item">🔗 <a href="${article.link}" target="_blank">原文链接</a></span>`;
            }

            let contentHtml = article.content || '<div class="no-content">暂无内容</div>';

            container.innerHTML = `
                <h2>${article.index}. ${article.title}</h2>
                <div class="meta">
                    <span class="meta-item">📱 公众号: ${article.account}</span>
                    <span class="meta-item">📅 发布时间: ${article.pub_time}</span>
                    ${linkHtml}
                </div>
                <div class="content">${contentHtml}</div>
            `;

            document.getElementById('pageInfo').textContent = `${index + 1} / ${articles.length}`;

            document.getElementById('articleSelect').value = index;

            updateButtons();

            window.scrollTo({ top: 0, behavior: 'smooth' });
        }

        function updateButtons() {
            const isFirst = currentIndex === 0;
            const isLast = currentIndex === articles.length - 1;

            document.getElementById('prevBtn').disabled = isFirst;
            document.getElementById('nextBtn').disabled = isLast;
            document.getElementById('footerPrevBtn').disabled = isFirst;
            document.getElementById('footerNextBtn').disabled = isLast;
        }

        function prevArticle() {
            if (currentIndex > 0) {
                showArticle(currentIndex - 1);
            }
        }

        function nextArticle() {
            if (currentIndex < articles.length - 1) {
                showArticle(currentIndex + 1);
            }
        }

        function goToArticle(index) {
            showArticle(parseInt(index));
        }

        document.addEventListener('keydown', function(e) {
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') {
                return;
            }

            switch(e.key) {
                case 'ArrowLeft':
                    prevArticle();
                    e.preventDefault();
                    break;
                case 'ArrowRight':
                    nextArticle();
                    e.preventDefault();
                    break;
                case 'Home':
                    showArticle(0);
                    e.preventDefault();
                    break;
                case 'End':
                    showArticle(articles.length - 1);
                    e.preventDefault();
                    break;
            }
        });

        document.addEventListener('DOMContentLoaded', init);
    </script>
</body>
</html>
""")

    def _escape_html(self, text):
        if not text:
            return ''
        return (str(text)
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))

    def _markdown_to_html(self, md_text):
        if not md_text:
            return ''

        try:
            import markdown
            return markdown.markdown(md_text, extensions=['tables', 'fenced_code'])
        except ImportError:
            html = self._escape_html(md_text)
            html = html.replace('\n\n', '</p><p>')
            html = html.replace('\n', '<br>')
            html = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'<img src="\2" alt="\1">', html)
            html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)
            return f'<p>{html}</p>'

    def _on_discard_data(self):
        if not self.articles:
            return

        msg_box = MessageBox(
            "确认清空数据",
            f"确定要清空当前显示的 {len(self.articles)} 条数据吗？\n\n仅清除界面显示，数据库中的数据不受影响。",
            self.window()
        )
        msg_box.yesButton.setText("清空数据")
        msg_box.cancelButton.setText("取消")

        if msg_box.exec():
            self._clear_data()
            InfoBar.info(title="已清空", content="当前显示数据已清除，数据库数据不受影响", parent=self, position=InfoBarPosition.TOP, duration=2000)
            self.data_discarded.emit()

    def _clear_data(self):
        self.articles = []
        self.source_info = ""

        self.data_table.setRowCount(0)
        self.count_label.setText("共 0 条记录")

        self.account_filter.clear()
        self.account_filter.addItem("全部")

        self.source_card.hide()
        self.save_btn.hide()
        self.discard_btn.hide()

        self.source_label.setText("数据来源: 未加载")
