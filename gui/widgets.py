#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
自定义控件模块 - Fluent Design 风格

本模块提供了一系列自定义的 GUI 控件，基于 qfluentwidgets 扩展，
实现了微信风格的暗黑主题设计。

控件列表:
    基础控件:
        - CustomSpinBox: 带 Fluent 样式的数字输入框
        - CardWidget: 卡片容器控件
        - ProgressWidget: 进度显示控件（支持确定/不确定模式）

    状态指示:
        - ProcessingIndicator: 处理阶段指示器

工具函数:
    - create_fluent_spinbox(): 创建带样式的 SpinBox

样式常量:
    - SPINBOX_DARK_QSS: SpinBox 深色主题样式
    - SPINBOX_LIGHT_QSS: SpinBox 浅色主题样式

设计特点:
    1. 所有控件都适配暗黑主题
    2. 使用微信绿作为强调色
    3. 圆角设计，现代化外观
    4. 流畅的悬停和点击动画
"""

import re

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
)
from PyQt6.QtCore import pyqtSignal, Qt, QSize, QTimer
from PyQt6.QtGui import QCursor

from qfluentwidgets import (
    CardWidget as FluentCard, PushButton,
    ProgressBar, BodyLabel, StrongBodyLabel, CaptionLabel,
    SpinBox, setCustomStyleSheet
)

from .styles import COLORS


# SpinBox 深色主题样式 - Fluent Design 风格
# 注意：右侧需要预留 36px 给箭头按钮
SPINBOX_DARK_QSS = """
SpinBox {
    background-color: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 5px;
    padding: 5px 36px 5px 10px;
    color: rgba(255, 255, 255, 0.9);
    font-size: 14px;
    selection-background-color: #0078d4;
    min-height: 18px;
}
SpinBox:hover {
    background-color: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.12);
}
SpinBox:focus {
    border: 1px solid #0078d4;
    background-color: rgba(255, 255, 255, 0.05);
}
SpinBox:disabled {
    color: rgba(255, 255, 255, 0.36);
    background-color: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.05);
}
"""

SPINBOX_LIGHT_QSS = """
SpinBox {
    background-color: rgba(255, 255, 255, 0.7);
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 5px;
    padding: 5px 36px 5px 10px;
    color: rgba(0, 0, 0, 0.9);
    font-size: 14px;
    selection-background-color: #0078d4;
    min-height: 18px;
}
SpinBox:hover {
    background-color: rgba(249, 249, 249, 0.9);
    border: 1px solid rgba(0, 0, 0, 0.12);
}
SpinBox:focus {
    border: 1px solid #0078d4;
    background-color: white;
}
SpinBox:disabled {
    color: rgba(0, 0, 0, 0.36);
    background-color: rgba(249, 249, 249, 0.3);
    border: 1px solid rgba(0, 0, 0, 0.05);
}
"""


def create_fluent_spinbox(min_val=1, max_val=100, default_val=10, width=None):
    """创建带 Fluent Design 样式的 SpinBox
    
    这是创建数字输入框的推荐方式，会自动应用深色主题样式。
    
    Args:
        min_val: 最小值，默认为 1
        max_val: 最大值，默认为 100
        default_val: 默认值，默认为 10
        width: 固定宽度（像素），None 表示自动宽度
    
    Returns:
        配置好样式的 SpinBox 实例
    
    示例:
        >>> spinbox = create_fluent_spinbox(1, 50, 10, width=120)
        >>> layout.addWidget(spinbox)
    """
    spinbox = SpinBox()
    spinbox.setRange(min_val, max_val)
    spinbox.setValue(default_val)
    
    if width:
        spinbox.setFixedWidth(width)
    
    # 应用自定义深色主题样式
    setCustomStyleSheet(spinbox, SPINBOX_LIGHT_QSS, SPINBOX_DARK_QSS)
    
    return spinbox


class CustomSpinBox(SpinBox):
    """自定义 SpinBox 控件
    
    继承自 qfluentwidgets 的 SpinBox，自动应用 Fluent Design 深色主题样式。
    保留此类是为了向后兼容，新代码推荐使用 create_fluent_spinbox() 函数。
    
    Args:
        min_val: 最小值
        max_val: 最大值
        default_val: 默认值
        parent: 父控件
    """
    
    def __init__(self, min_val=1, max_val=100, default_val=10, parent=None):
        """初始化 SpinBox 并应用样式"""
        super().__init__(parent)
        self.setRange(min_val, max_val)
        self.setValue(default_val)
        # 应用自定义深色主题样式
        setCustomStyleSheet(self, SPINBOX_LIGHT_QSS, SPINBOX_DARK_QSS)
    
    def setMinimumWidth(self, width):
        """设置最小宽度"""
        super().setMinimumWidth(width)


class CardWidget(FluentCard):
    """卡片容器控件
    
    基于 qfluentwidgets 的 CardWidget，提供带标题的卡片布局。
    内部使用垂直布局，可以通过 addWidget/addLayout 添加内容。
    
    Args:
        title: 卡片标题，None 表示无标题
        parent: 父控件
    
    示例:
        >>> card = CardWidget("设置", parent)
        >>> card.addWidget(QLabel("选项1"))
        >>> card.addWidget(QCheckBox("启用"))
    """
    
    def __init__(self, title=None, parent=None):
        """初始化卡片，设置内边距和间距"""
        super().__init__(parent)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(12)
        
        if title:
            title_label = StrongBodyLabel(title)
            self.main_layout.addWidget(title_label)
    
    def addWidget(self, widget):
        self.main_layout.addWidget(widget)
    
    def addLayout(self, layout):
        self.main_layout.addLayout(layout)


class ProgressWidget(QWidget):
    """进度显示控件
    
    支持两种进度模式：
    1. 确定模式: 显示具体的百分比进度
    2. 不确定模式: 显示脉冲动画，用于无法预估进度的任务
    
    显示内容包括：
    - 状态文字（左侧）
    - 文章数量（右侧，绿色）
    - 百分比（右侧，仅确定模式）
    - 进度条（底部）
    
    Signals:
        cancel_clicked: 取消按钮点击信号（预留）
    
    Attributes:
        _indeterminate: 是否为不确定模式
        _article_count: 已获取的文章数量
        _current_account: 当前正在爬取的账号
    """
    
    cancel_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        """初始化进度控件"""
        super().__init__(parent)
        self._indeterminate = False
        self._pulse_value = 0
        self._pulse_direction = 1
        self._article_count = 0
        self._current_account = ""
        self._total_accounts = 0
        self._current_account_index = 0
        self._setup_ui()
        self._setup_timer()
    
    def _setup_ui(self):
        """设置 UI 布局，包含信息行和进度条"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        
        # 第一行：状态信息 + 文章数量 + 百分比
        info_layout = QHBoxLayout()
        info_layout.setSpacing(8)
        
        # 左侧：状态文字
        self.progress_label = BodyLabel("准备中...")
        self.progress_label.setMinimumWidth(200)
        info_layout.addWidget(self.progress_label)
        
        info_layout.addStretch()
        
        # 右侧：文章数量 + 百分比
        # 文章数量标签
        self.article_label = BodyLabel("")
        self.article_label.setStyleSheet(f"color: {COLORS['success']}; font-weight: 500;")
        info_layout.addWidget(self.article_label)
        
        # 百分比标签
        self.percent_label = StrongBodyLabel("")
        self.percent_label.setStyleSheet(f"color: {COLORS['primary']}; min-width: 50px;")
        info_layout.addWidget(self.percent_label)
        
        layout.addLayout(info_layout)
        
        # 进度条
        self.progress_bar = ProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(4)
        layout.addWidget(self.progress_bar)
    
    def _setup_timer(self):
        """设置不确定模式的动画定时器"""
        from PyQt6.QtCore import QTimer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pulse_animation)
        self._timer.setInterval(100)  # 100ms — reduces CPU waste vs 50ms while still smooth
    
    def _pulse_animation(self):
        """执行脉冲动画，在 20-80 之间来回变化"""
        if not self._indeterminate:
            return
        
        # Create a smooth pulse animation between 20-80
        self._pulse_value += self._pulse_direction * 2
        if self._pulse_value >= 80:
            self._pulse_direction = -1
        elif self._pulse_value <= 20:
            self._pulse_direction = 1
        
        self.progress_bar.setValue(self._pulse_value)
    
    def set_indeterminate(self, message="处理中...", count_text=""):
        """设置为不确定进度模式
        
        启动脉冲动画，适用于无法预估进度的任务。
        
        Args:
            message: 状态文字
            count_text: 计数文字（可选）
        """
        self._indeterminate = True
        self._pulse_value = 20
        self._pulse_direction = 1
        self.progress_label.setText(message)
        if count_text:
            self.article_label.setText(count_text)
        self._timer.start()
    
    def set_progress(self, current, total, message=None):
        """设置确定进度模式
        
        显示具体的百分比进度，会自动停止脉冲动画。
        
        Args:
            current: 当前进度值
            total: 总进度值
            message: 状态文字（可选）
        """
        # Stop animation if running
        if self._indeterminate:
            self._indeterminate = False
            self._timer.stop()
        
        if total > 0:
            percent = int(current / total * 100)
            self.progress_bar.setValue(percent)
            self.percent_label.setText(f"{percent}%")
        if message:
            self.progress_label.setText(message)
        else:
            self.progress_label.setText(f"进度: {current}/{total}")
    
    def set_article_progress(self, count, message):
        """设置文章进度（不确定模式）
        
        显示已获取的文章数量，同时启动脉冲动画。
        
        Args:
            count: 已获取的文章数量
            message: 状态文字
        """
        self._article_count = count
        
        if not self._indeterminate:
            self._indeterminate = True
            self._pulse_value = 20
            self._pulse_direction = 1
            self._timer.start()
        
        self.progress_label.setText(message)
        self.article_label.setText(f"📄 已获取 {count} 篇文章")
        # 不确定模式下不显示百分比
        self.percent_label.setText("")
    
    def set_scrape_progress(self, account_index, total_accounts, article_count, current_account=""):
        """设置爬取进度（确定模式）
        
        显示账号进度百分比和文章数量，适用于批量爬取任务。
        
        Args:
            account_index: 当前账号索引（从 1 开始）
            total_accounts: 总账号数
            article_count: 已获取的文章数量
            current_account: 当前正在爬取的账号名称
        """
        self._article_count = article_count
        self._current_account = current_account
        self._total_accounts = total_accounts
        self._current_account_index = account_index
        
        # 停止动画，使用确定进度
        if self._indeterminate:
            self._indeterminate = False
            self._timer.stop()
        
        # 计算百分比
        if total_accounts > 0:
            percent = int(account_index / total_accounts * 100)
            self.progress_bar.setValue(percent)
            self.percent_label.setText(f"{percent}%")
        
        # 更新状态文字
        if current_account:
            self.progress_label.setText(f"正在爬取: {current_account} ({account_index}/{total_accounts})")
        else:
            self.progress_label.setText(f"爬取进度: {account_index}/{total_accounts}")
        
        # 更新文章数量
        self.article_label.setText(f"📄 已获取 {article_count} 篇文章")
    
    def update_article_count(self, count):
        """仅更新文章数量显示，不改变进度模式"""
        self._article_count = count
        self.article_label.setText(f"📄 已获取 {count} 篇文章")
    
    def reset(self):
        """重置进度控件到初始状态"""
        self._indeterminate = False
        self._timer.stop()
        self._article_count = 0
        self._current_account = ""
        self._total_accounts = 0
        self._current_account_index = 0
        self.progress_bar.setValue(0)
        self.percent_label.setText("")
        self.article_label.setText("")
        self.progress_label.setText("准备中...")
    
    def set_complete(self, message="完成"):
        """设置为完成状态，显示 100% 进度"""
        self._indeterminate = False
        self._timer.stop()
        self.progress_bar.setValue(100)
        self.percent_label.setText("100%")
        self.article_label.setText(f"📄 共获取 {self._article_count} 篇文章")
        self.progress_label.setText(message)


class ProcessingIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 'idle'
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 3, 10, 3)
        layout.setSpacing(6)
        self.dot = QLabel("●")
        self.dot.setStyleSheet("color: #888; font-size: 10px;")
        self.label = BodyLabel("就绪")
        self.label.setStyleSheet("color: #aaa; font-size: 11px; background: transparent; border: none;")
        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        self.setStyleSheet("""
            ProcessingIndicator {
                background-color: rgba(30, 30, 30, 0.92);
                border: 1px solid #333;
                border-radius: 6px;
            }
        """)
        self.setFixedHeight(30)
        self.adjustSize()

    def set_phase(self, phase: str, message: str = ''):
        self._phase = phase
        colors = {'idle': '#888', 'list': '#5B9BD5', 'content': '#07C160', 'error': '#FA5151'}
        labels = {'idle': '就绪', 'list': '爬取列表中', 'content': '爬取内容中', 'error': '出错'}
        color = colors.get(phase, '#888')
        label = message or labels.get(phase, '')
        self.dot.setStyleSheet(f"color: {color}; font-size: 10px;")
        self.label.setText(label)
        self.adjustSize()

    def set_message(self, msg: str):
        self.label.setText(msg)
        self.adjustSize()
