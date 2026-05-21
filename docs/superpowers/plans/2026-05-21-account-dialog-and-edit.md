# Account Add/Edit Dialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace inline account add bar with a popup dialog, add edit button in action column (date range only).

**Architecture:** Single `AccountEditDialog` class with add/edit mode. Dialog validates input, emits accepted signal, caller reads fields. Database gets a new `update_account_date_range` method that also resets status to `'pending'`.

**Tech Stack:** PyQt6, qfluentwidgets, SQLite

---

### Task 1: Database — add `update_account_date_range`

**Files:**
- Modify: `spider/database.py:176-181`

- [ ] **Add method after `update_account_status`**

In `spider/database.py`, after `update_account_status` (line 181), add:

```python
def update_account_date_range(self, name: str, date_range: str):
    self.conn.execute(
        "UPDATE wechat_account SET date_range = ?, status = 'pending', updated_at = datetime('now','localtime') WHERE name = ?",
        (date_range, name)
    )
    self.conn.commit()
```

---

### Task 2: AccountEditDialog — create the shared dialog

**Files:**
- Create: `gui/pages/account_edit_dialog.py`

- [ ] **Create `gui/pages/account_edit_dialog.py`**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit
from PyQt6.QtCore import Qt
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
```

---

### Task 3: AccountManagementPage — wire up dialog, add edit support

**Files:**
- Modify: `gui/pages/account_management_page.py`

- [ ] **Add import for `AccountEditDialog`**

At the top, after existing imports, add:

```python
from .account_edit_dialog import AccountEditDialog
```

- [ ] **Remove the inline add bar**

Delete lines 40-58 (the `add_card` block from `add_card = CardWidget()` to `layout.addWidget(add_card)`).

Replace with a single button in the table title area.

- [ ] **Add "添加公众号" button in table header**

Change the table title section (currently lines 65-67) from:

```python
table_title = BodyLabel("已添加的公众号")
table_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #0078d4;")
table_layout.addWidget(table_title)
```

To:

```python
table_header = QHBoxLayout()
table_title = BodyLabel("已添加的公众号")
table_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #0078d4;")
table_header.addWidget(table_title)
table_header.addStretch()
add_btn = PrimaryPushButton("添加公众号", icon=FluentIcon.ADD)
add_btn.clicked.connect(self._on_add_account)
table_header.addWidget(add_btn)
table_layout.addLayout(table_header)
```

Also remove `self.name_input.returnPressed.connect(...)` and `self.add_btn.clicked.connect(...)` lines (lines 119-120).

- [ ] **Rewrite `_on_add_account` to use dialog**

Replace `_on_add_account` method (lines 122-138) with:

```python
def _on_add_account(self):
    dialog = AccountEditDialog(parent=self, mode='add')
    if dialog.exec() == QDialog.DialogCode.Accepted:
        name = dialog.get_name()
        date_range = dialog.get_date_range()
        db = Database(DB_PATH)
        try:
            if db.add_account(name, date_range):
                InfoBar.success(title="已添加", content=f"{name} 已加入爬取队列", parent=self, position=InfoBarPosition.TOP, duration=2000)
                self.account_added.emit(name)
                self._refresh_table()
            else:
                InfoBar.warning(title="提示", content=f"{name} 已存在", parent=self, position=InfoBarPosition.TOP, duration=2000)
        finally:
            db.close()
```

- [ ] **Add import for QDialog**

Add to the PyQt6.QtWidgets import line:
```python
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QHeaderView, QTableWidgetItem, QTextEdit, QAbstractItemView, QDialog
```

- [ ] **Add `_on_edit_account` method**

Add after `_on_retry_account` (after line 213):

```python
def _on_edit_account(self, name):
    db = Database(DB_PATH)
    try:
        accounts = db.get_wechat_accounts()
        account_data = next((a for a in accounts if a['name'] == name), None)
        if not account_data:
            return
    finally:
        db.close()

    dialog = AccountEditDialog(parent=self, mode='edit', account_data=account_data)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        new_date_range = dialog.get_date_range()
        db = Database(DB_PATH)
        try:
            db.update_account_date_range(name, new_date_range)
            InfoBar.success(title="已更新", content=f"{name} 时间范围已更新为 {new_date_range}", parent=self, position=InfoBarPosition.TOP, duration=2000)
            self._refresh_table()
        finally:
            db.close()
```

- [ ] **Add "编辑" button in `_refresh_table` action column**

In the `_refresh_table` method, in the action column section (around line 186), add an edit button before the delete button:

```python
edit_btn = PushButton("编辑")
edit_btn.setFixedSize(50, 26)
edit_btn.clicked.connect(lambda checked, n=name: self._on_edit_account(n))
btn_layout.addWidget(edit_btn)
```

And also in the `_update_account_row` method's error case (around line 238), add the same:

```python
edit_btn = PushButton("编辑")
edit_btn.setFixedSize(50, 26)
edit_btn.clicked.connect(lambda checked, n=name: self._on_edit_account(n))
btn_layout.addWidget(edit_btn)
```

---

### Self-Review / Verification

- [ ] **Run the app** — `python run_gui.py` — navigate to account management page
- [ ] **Verify**: no inline add bar at top, "添加公众号" button in table header opens dialog
- [ ] **Verify**: add dialog — type name, select range, confirm → account appears in table
- [ ] **Verify**: "编辑" button visible in action column, click opens edit dialog with read-only name and pre-selected range
- [ ] **Verify**: editing range → account status resets to `'pending'` (the scraper will re-fetch)
- [ ] **Verify**: delete and retry still work
