#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公众号管理页面 — CRUD + 后台日志
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QHeaderView, QTableWidgetItem,
    QTextEdit, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QTextCursor
from datetime import datetime

from qfluentwidgets import (
    TitleLabel, BodyLabel, CaptionLabel, CardWidget,
    PrimaryPushButton, PushButton, LineEdit, ComboBox,
    InfoBar, InfoBarPosition, FluentIcon,
)
from qfluentwidgets import TableWidget as FluentTable

from ..styles import COLORS
from spider.database import Database
from ..utils import DB_PATH


LOG_COLORS = {
    'info': '#CCCCCC',
    'success': '#07C160',
    'warning': '#FFC300',
    'error': '#FA5151',
}


class UnifiedScrapePage(QWidget):

    account_status_changed = pyqtSignal(str, str, str)

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

        # === 添加栏 ===
        add_card = CardWidget()
        add_layout = QHBoxLayout(add_card)
        add_layout.setContentsMargins(16, 12, 16, 12)
        add_layout.setSpacing(8)

        self.account_input = LineEdit()
        self.account_input.setPlaceholderText("输入公众号名称...")
        add_layout.addWidget(self.account_input, 1)

        self.date_combo = ComboBox()
        self.date_combo.addItems(["最近7天", "本月", "本季度", "本年", "最近3年", "全部"])
        self.date_combo.setCurrentIndex(0)
        self.date_combo.setMinimumWidth(120)
        add_layout.addWidget(self.date_combo)

        self.add_btn = PrimaryPushButton("添加", icon=FluentIcon.ADD)
        self.add_btn.setFixedWidth(100)
        self.add_btn.clicked.connect(self._on_add_account)
        add_layout.addWidget(self.add_btn)

        self.account_input.returnPressed.connect(self.add_btn.click)
        layout.addWidget(add_card)

        # === 账号表格 ===
        table_card = CardWidget()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(16, 12, 16, 12)
        table_layout.setSpacing(8)

        table_header = QHBoxLayout()
        table_title = BodyLabel("已添加的公众号")
        table_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #0078d4;")
        table_header.addWidget(table_title)
        table_header.addStretch()
        self.table_count_label = CaptionLabel("共 0 个")
        self.table_count_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        table_header.addWidget(self.table_count_label)
        table_layout.addLayout(table_header)

        self.account_table = FluentTable()
        self.account_table.setColumnCount(5)
        self.account_table.setHorizontalHeaderLabels(["公众号", "状态", "文章数", "时间范围", "操作"])
        self.account_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.account_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.setMinimumHeight(100)
        self.account_table.verticalHeader().setVisible(False)
        table_layout.addWidget(self.account_table, 1)

        layout.addWidget(table_card, 1)

        # === 日志面板 ===
        log_card = CardWidget()
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(16, 12, 16, 12)
        log_layout.setSpacing(6)

        log_header = QHBoxLayout()
        log_title = BodyLabel("运行日志")
        log_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #0078d4;")
        log_header.addWidget(log_title)
        log_header.addStretch()
        self.log_clear_btn = PushButton("清空", icon=FluentIcon.DELETE)
        self.log_clear_btn.setFixedWidth(80)
        self.log_clear_btn.clicked.connect(self._clear_log)
        log_header.addWidget(self.log_clear_btn)
        log_layout.addLayout(log_header)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: #111111;
                color: #CCCCCC;
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 10px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
            }}
        """)
        self.log_text.setMaximumHeight(180)
        log_layout.addWidget(self.log_text)

        layout.addWidget(log_card)

    def _refresh_table(self):
        try:
            db = Database(DB_PATH)
            accounts = db.get_accounts()
            db.close()
        except Exception:
            accounts = []

        self.account_table.setRowCount(len(accounts))
        for i, acc in enumerate(accounts):
            name_item = QTableWidgetItem(acc.get('name', ''))
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.account_table.setItem(i, 0, name_item)

            status = acc.get('status', '')
            status_map = {
                'pending': ('等待中', COLORS['text_secondary']),
                'processing': ('处理中', COLORS['primary']),
                'completed': ('已完成', COLORS['success']),
                'error': ('失败', COLORS['error']),
            }
            status_text, status_color = status_map.get(status, (status, COLORS['text_secondary']))
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setForeground(QColor(status_color))
            self.account_table.setItem(i, 1, status_item)

            count_item = QTableWidgetItem(str(acc.get('total_articles', 0)))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.account_table.setItem(i, 2, count_item)

            date_item = QTableWidgetItem(acc.get('date_range', ''))
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.account_table.setItem(i, 3, date_item)

            container = QWidget()
            btn_layout = QHBoxLayout(container)
            btn_layout.setContentsMargins(4, 2, 4, 2)
            btn_layout.setSpacing(4)

            delete_btn = PushButton("删除")
            delete_btn.setFixedSize(60, 26)
            account_name = acc.get('name', '')
            delete_btn.clicked.connect(lambda checked, n=account_name: self._on_delete_account(n))
            btn_layout.addWidget(delete_btn)

            if status == 'error':
                retry_btn = PushButton("重试")
                retry_btn.setFixedSize(60, 26)
                retry_btn.clicked.connect(lambda checked, n=account_name: self._on_retry_account(n))
                btn_layout.addWidget(retry_btn)

            self.account_table.setCellWidget(i, 4, container)

        self.table_count_label.setText(f"共 {len(accounts)} 个")

    def _on_add_account(self):
        name = self.account_input.text().strip()
        if not name:
            InfoBar.warning(title="提示", content="请输入公众号名称", parent=self, position=InfoBarPosition.TOP, duration=2000)
            return
        if not self.login_manager.is_logged_in():
            InfoBar.warning(title="未登录", content="请先登录", parent=self, position=InfoBarPosition.TOP, duration=3000)
            return

        date_range = self.date_combo.currentText()
        try:
            db = Database(DB_PATH)
            ok = db.add_account(name, date_range)
            db.close()
        except Exception as e:
            InfoBar.error(title="添加失败", content=str(e), parent=self, position=InfoBarPosition.TOP, duration=3000)
            return

        if ok:
            self.account_input.clear()
            self._refresh_table()
            InfoBar.success(title="添加成功", content=f"已添加公众号: {name}", parent=self, position=InfoBarPosition.TOP, duration=2000)
        else:
            InfoBar.warning(title="重复", content=f"公众号已存在: {name}", parent=self, position=InfoBarPosition.TOP, duration=2000)

    def _on_delete_account(self, name):
        try:
            db = Database(DB_PATH)
            db.delete_account(name)
            db.close()
            self._refresh_table()
            InfoBar.info(title="已删除", content=name, parent=self, position=InfoBarPosition.TOP, duration=2000)
        except Exception as e:
            InfoBar.error(title="删除失败", content=str(e), parent=self, position=InfoBarPosition.TOP, duration=3000)

    def _on_retry_account(self, name):
        try:
            db = Database(DB_PATH)
            db.update_account_status(name, 'pending')
            db.close()
            self._refresh_table()
            InfoBar.info(title="已重试", content=name, parent=self, position=InfoBarPosition.TOP, duration=2000)
        except Exception as e:
            InfoBar.error(title="重试失败", content=str(e), parent=self, position=InfoBarPosition.TOP, duration=3000)

    def append_log(self, message: str, level: str = 'info'):
        """供后台线程调用的日志追加方法"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = LOG_COLORS.get(level, LOG_COLORS['info'])
        html = f'<span style="color: {color};">[{timestamp}] {message}</span><br>'
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)
        self.log_text.insertHtml(html)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _clear_log(self):
        self.log_text.clear()

    def on_account_status_changed(self, account_name: str, status: str, message: str):
        """从后台线程接收账号状态变更，刷新表格"""
        self._refresh_table()