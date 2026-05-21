#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QHeaderView, QTableWidgetItem, QTextEdit, QAbstractItemView
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from datetime import datetime

from qfluentwidgets import (
    TitleLabel, BodyLabel, CaptionLabel, CardWidget,
    PrimaryPushButton, PushButton, LineEdit, ComboBox,
    InfoBar, InfoBarPosition, FluentIcon,
)
from qfluentwidgets import TableWidget as FluentTable

from ..styles import COLORS
from spider.database import Database
from gui.utils import DB_PATH


class AccountManagementPage(QWidget):
    scrape_completed = pyqtSignal(list, str, str)
    account_added = pyqtSignal(str)

    def __init__(self, login_manager, parent=None):
        super().__init__(parent)
        self.login_manager = login_manager
        self.setObjectName("unifiedScrapePage")
        self.setStyleSheet("background-color: #1a1a1a;")
        self._setup_ui()
        self._refresh_table()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)

        title = TitleLabel("公众号管理")
        layout.addWidget(title)

        add_card = CardWidget()
        add_layout = QHBoxLayout(add_card)
        add_layout.setContentsMargins(16, 12, 16, 12)
        add_layout.setSpacing(8)

        self.name_input = LineEdit()
        self.name_input.setPlaceholderText("输入公众号名称，回车添加")
        add_layout.addWidget(self.name_input, 1)

        self.date_combo = ComboBox()
        self.date_combo.addItems(["最近7天", "本月", "本季度", "本年", "最近3年", "全部"])
        self.date_combo.setCurrentIndex(0)
        self.date_combo.setMinimumWidth(120)
        add_layout.addWidget(self.date_combo)

        self.add_btn = PrimaryPushButton("添加", icon=FluentIcon.ADD)
        self.add_btn.setFixedWidth(100)
        add_layout.addWidget(self.add_btn)
        layout.addWidget(add_card)

        table_card = CardWidget()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(16, 12, 16, 12)
        table_layout.setSpacing(6)

        table_title = BodyLabel("已添加的公众号")
        table_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #0078d4;")
        table_layout.addWidget(table_title)

        self.account_table = FluentTable()
        self.account_table.setColumnCount(6)
        self.account_table.setHorizontalHeaderLabels(["公众号", "状态", "文章数", "时间范围", "添加时间", "操作"])
        self.account_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.account_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.verticalHeader().setVisible(False)
        self.account_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table_layout.addWidget(self.account_table, 1)
        layout.addWidget(table_card, 1)

        log_card = CardWidget()
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(16, 8, 16, 8)
        log_layout.setSpacing(4)

        log_header = QHBoxLayout()
        log_title = BodyLabel("运行日志")
        log_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #0078d4;")
        log_header.addWidget(log_title)
        log_header.addStretch()

        self.clear_log_btn = PushButton("清空日志", icon=FluentIcon.DELETE)
        self.clear_log_btn.setFixedHeight(26)
        self.clear_log_btn.clicked.connect(lambda: self.log_text.clear())
        log_header.addWidget(self.clear_log_btn)

        log_layout.addLayout(log_header)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: #111;
                color: #ccc;
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
            }}
        """)
        self.log_text.setMinimumHeight(120)
        self.log_text.setMaximumHeight(200)
        log_layout.addWidget(self.log_text)
        layout.addWidget(log_card)

        self.name_input.returnPressed.connect(self._on_add_account)
        self.add_btn.clicked.connect(self._on_add_account)

    def _on_add_account(self):
        name = self.name_input.text().strip()
        if not name:
            InfoBar.warning(title="提示", content="请输入公众号名称", parent=self, position=InfoBarPosition.TOP, duration=2000)
            return
        date_range = self.date_combo.currentText()
        db = Database(DB_PATH)
        try:
            if db.add_account(name, date_range):
                InfoBar.success(title="已添加", content=f"{name} 已加入爬取队列", parent=self, position=InfoBarPosition.TOP, duration=2000)
                self.name_input.clear()
                self.account_added.emit(name)
                self._refresh_table()
            else:
                InfoBar.warning(title="提示", content=f"{name} 已存在", parent=self, position=InfoBarPosition.TOP, duration=2000)
        finally:
            db.close()

    def _refresh_table(self):
        db = Database(DB_PATH)
        try:
            accounts = db.get_wechat_accounts()
            status_map = {
                'pending': '等待列表', 'list_done': '列表完成',
                'processing': '处理中', 'completed': '已完成', 'error': '出错'
            }
            table = self.account_table
            table.setSortingEnabled(False)
            table.setUpdatesEnabled(False)
            table.setRowCount(len(accounts))
            for i, acc in enumerate(accounts):
                name_item = QTableWidgetItem(acc.get('name', ''))
                name_item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
                self.account_table.setItem(i, 0, name_item)
                status = acc.get('status', '')
                status_item = QTableWidgetItem(status_map.get(status, status))
                color_map = {'completed': COLORS['success'], 'error': COLORS['error'],
                             'processing': COLORS['warning'], 'list_done': COLORS['success'],
                             'pending': COLORS['text_secondary']}
                status_item.setForeground(QColor(color_map.get(status, COLORS['text_secondary'])))
                status_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                self.account_table.setItem(i, 1, status_item)
                art_item = QTableWidgetItem(str(acc.get('total_articles', 0)))
                art_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                self.account_table.setItem(i, 2, art_item)
                date_range_item = QTableWidgetItem(acc.get('date_range', ''))
                date_range_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                self.account_table.setItem(i, 3, date_range_item)
                created = acc.get('created_at', '')
                if created:
                    try:
                        created = datetime.strptime(created, '%Y-%m-%d %H:%M:%S').strftime('%m-%d %H:%M')
                    except Exception:
                        pass
                created_item = QTableWidgetItem(created)
                created_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                self.account_table.setItem(i, 4, created_item)
                container = QWidget()
                btn_layout = QHBoxLayout(container)
                btn_layout.setContentsMargins(2, 2, 2, 2)
                btn_layout.setSpacing(4)
                del_btn = PushButton("删除")
                del_btn.setFixedSize(50, 26)
                name = acc['name']
                del_btn.clicked.connect(lambda checked, n=name: self._on_delete_account(n))
                btn_layout.addWidget(del_btn)
                if status == 'error':
                    retry_btn = PushButton("重试")
                    retry_btn.setFixedSize(50, 26)
                    retry_btn.clicked.connect(lambda checked, n=name: self._on_retry_account(n))
                    btn_layout.addWidget(retry_btn)
                self.account_table.setCellWidget(i, 5, container)
            table.setUpdatesEnabled(True)
            table.setSortingEnabled(True)
        finally:
            db.close()

    def _on_delete_account(self, name):
        db = Database(DB_PATH)
        try:
            db.delete_account(name)
            self._refresh_table()
        finally:
            db.close()

    def _on_retry_account(self, name):
        db = Database(DB_PATH)
        try:
            db.update_account_status(name, 'pending')
            self._refresh_table()
        finally:
            db.close()

    def append_log(self, message: str):
        self.log_text.append(message)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def apply_settings(self, config: dict):
        pass
