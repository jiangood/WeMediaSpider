#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel
from qfluentwidgets import (
    TitleLabel, BodyLabel, PrimaryPushButton, PushButton,
    ComboBox, LineEdit, InfoBar, InfoBarPosition,
)
from ..styles import COLORS


class AccountEditDialog(QDialog):
    DATE_RANGES = ["最近7天", "本月", "本季度", "本年", "最近3年", "全部"]

    def __init__(self, parent=None, mode='add', account_data=None):
        super().__init__(parent)
        self.mode = mode
        self.account_data = account_data or {}
        self._setup_window()
        self._setup_ui()

    def _setup_window(self):
        title = "编辑公众号" if self.mode == 'edit' else "添加公众号"
        self.setWindowTitle(title)
        self.setFixedSize(400, 220)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: #1a1a1a;
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
        """)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = TitleLabel(self.windowTitle())
        layout.addWidget(title)

        form_layout = QVBoxLayout()
        form_layout.setSpacing(8)

        name_label = BodyLabel("公众号名称")
        form_layout.addWidget(name_label)

        if self.mode == 'add':
            self.name_input = LineEdit()
            self.name_input.setPlaceholderText("输入公众号名称")
            form_layout.addWidget(self.name_input)
        else:
            self.name_label_readonly = BodyLabel(self.account_data.get('name', ''))
            self.name_label_readonly.setStyleSheet(f"""
                BodyLabel {{
                    background-color: #2d2d2d;
                    color: #aaa;
                    padding: 6px 12px;
                    border: 1px solid {COLORS['border']};
                    border-radius: 4px;
                }}
            """)
            form_layout.addWidget(self.name_label_readonly)

        range_label = BodyLabel("时间范围")
        form_layout.addWidget(range_label)

        self.date_combo = ComboBox()
        self.date_combo.addItems(self.DATE_RANGES)
        if self.mode == 'edit':
            current_range = self.account_data.get('date_range', '最近7天')
            if current_range in self.DATE_RANGES:
                self.date_combo.setCurrentIndex(self.DATE_RANGES.index(current_range))
        form_layout.addWidget(self.date_combo)

        layout.addLayout(form_layout)
        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addStretch()

        self.cancel_btn = PushButton("取消")
        self.cancel_btn.setFixedWidth(80)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.confirm_btn = PrimaryPushButton("确定")
        self.confirm_btn.setFixedWidth(80)
        self.confirm_btn.clicked.connect(self._on_confirm)
        btn_layout.addWidget(self.confirm_btn)

        layout.addLayout(btn_layout)

    def _on_confirm(self):
        if self.mode == 'add':
            name = self.name_input.text().strip()
            if not name:
                InfoBar.warning(title="提示", content="请输入公众号名称", parent=self, position=InfoBarPosition.TOP, duration=2000)
                return
        self.accept()

    def get_name(self) -> str:
        if self.mode == 'add':
            return self.name_input.text().strip()
        return self.account_data.get('name', '')

    def get_date_range(self) -> str:
        return self.date_combo.currentText()
