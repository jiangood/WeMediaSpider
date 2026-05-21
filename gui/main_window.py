#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
主窗口模块 - Fluent Design 风格

本模块实现了应用程序的主窗口，基于 qfluentwidgets 的 FluentWindow 构建。
采用侧边导航栏加内容区域的经典布局，支持多页面切换。

主要功能:
    - 自适应屏幕分辨率的窗口大小设置
    - 侧边导航栏管理（支持折叠和展开）
    - 多页面路由和切换
    - 页面间信号通信

屏幕适配策略:
    - 小屏幕 (宽度小于1600px): 最小 1100x700，默认 85% 屏幕宽度
    - 中等屏幕 (1600-1920px): 最小 1200x750，默认 80% 屏幕宽度
    - 大屏幕 (大于1920px): 最小 1400x870，默认 75% 屏幕宽度

类说明:
    - MainWindow: 主窗口类，管理所有页面和导航
"""

from PyQt6.QtWidgets import QApplication, QHBoxLayout, QWidget, QFileDialog
from PyQt6.QtCore import Qt, QSize, QTimer, QEvent
from PyQt6.QtGui import QIcon, QCloseEvent, QScreen, QResizeEvent

from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon,
    setTheme, Theme, SplashScreen
)

from .pages import LoginPage, AccountManagementPage, ArticlesPage, SettingsPage
from .app import apply_label_transparent_background


class MainWindow(FluentWindow):
    """主窗口类 - 基于 Fluent Design 的导航式布局
    
    继承自 qfluentwidgets 的 FluentWindow，实现了完整的应用程序主界面。
    包含侧边导航栏和多个功能页面，支持页面间的信号通信和数据传递。
    
    页面列表:
        - login_page: 登录页面，管理微信登录状态
        - scrape_page: 爬取页面，配置和执行公众号爬取任务
        - articles_page: 文章列表页面，查看、搜索和导出爬取结果
        - settings_page: 设置页面，配置应用参数
    
    Attributes:
        _screen_width: 屏幕宽度
        _screen_height: 屏幕高度
        _is_small_screen: 是否为小屏幕（宽度小于1600px）
    """
    
    def __init__(self):
        """初始化主窗口，执行窗口设置、页面创建和信号连接"""
        super().__init__()
        
        # 窗口设置
        self.setWindowTitle("微信公众号爬虫")
        
        # 强制设置暗黑主题背景
        self._apply_dark_theme()
        
        # 根据屏幕分辨率自适应窗口大小
        self._setup_window_size()
        
        # 设置侧边栏宽度（根据屏幕大小调整）
        self._setup_navigation()
        
        # 创建页面
        self._create_pages()
        
        # 初始化导航
        self._init_navigation()
        
        # 连接信号
        self._connect_signals()
    
    def _apply_dark_theme(self):
        """强制应用暗黑主题到所有内部组件
        
        FluentWindow 的某些内部组件可能不会自动继承暗黑主题，
        需要手动设置样式表来确保一致的暗黑背景。
        """
        dark_bg = "#1a1a1a"
        
        # 设置主窗口背景
        self.setStyleSheet(f"""
            FluentWindow {{
                background-color: {dark_bg};
            }}
        """)
        
        # 设置 stackedWidget 背景（FluentWindow 的核心内容区域）
        if hasattr(self, 'stackedWidget'):
            self.stackedWidget.setStyleSheet(f"""
                QStackedWidget {{
                    background-color: {dark_bg};
                    border: none;
                }}
                QStackedWidget > QWidget {{
                    background-color: {dark_bg};
                }}
            """)
    
    def _setup_window_size(self):
        """根据屏幕分辨率自适应设置窗口大小
        
        根据主屏幕的可用区域大小，动态计算合适的窗口尺寸。
        采用三档适配策略，确保在不同分辨率下都有良好的显示效果。
        窗口会自动居中显示在屏幕上。
        """
        screen = QApplication.primaryScreen()
        if screen:
            screen_size = screen.availableGeometry()
            screen_width = screen_size.width()
            screen_height = screen_size.height()
            
            # 根据屏幕大小计算合适的窗口尺寸
            # 小屏幕（宽度<1600）：使用较小的最小尺寸
            # 中等屏幕（1600-1920）：使用标准尺寸
            # 大屏幕（>1920）：使用较大尺寸
            
            if screen_width < 1600:
                # 小屏幕适配
                min_width = min(1100, int(screen_width * 0.9))
                min_height = min(700, int(screen_height * 0.85))
                default_width = min(1200, int(screen_width * 0.85))
                default_height = min(750, int(screen_height * 0.85))
            elif screen_width < 1920:
                # 中等屏幕
                min_width = 1200
                min_height = 750
                default_width = min(1400, int(screen_width * 0.8))
                default_height = min(870, int(screen_height * 0.85))
            else:
                # 大屏幕
                min_width = 1400
                min_height = 870
                default_width = min(1600, int(screen_width * 0.75))
                default_height = min(950, int(screen_height * 0.85))
            
            self.setMinimumSize(min_width, min_height)
            self.resize(default_width, default_height)
            
            # 将窗口居中显示
            x = (screen_width - default_width) // 2 + screen_size.x()
            y = (screen_height - default_height) // 2 + screen_size.y()
            self.move(x, y)
            
            # 保存屏幕信息供其他组件使用
            self._screen_width = screen_width
            self._screen_height = screen_height
            self._is_small_screen = screen_width < 1600
        else:
            # 无法获取屏幕信息时使用默认值
            self.setMinimumSize(1100, 700)
            self.resize(1400, 870)
            self._screen_width = 1920
            self._screen_height = 1080
            self._is_small_screen = False
            # 尝试居中（使用备用方法）
            self._center_window_fallback()
    
    def _center_window_fallback(self):
        """备用的窗口居中方法
        
        当主要的居中逻辑无法获取屏幕信息时使用此方法。
        """
        screen = QApplication.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
            window_geometry = self.frameGeometry()
            center_point = screen_geometry.center()
            window_geometry.moveCenter(center_point)
            self.move(window_geometry.topLeft())
    
    def _setup_navigation(self):
        """配置侧边导航栏
        
        根据屏幕大小调整导航栏的展开宽度，小屏幕使用较窄的宽度。
        导航栏默认展开显示，但允许用户手动折叠。
        """
        # 根据屏幕大小调整侧边栏宽度
        if hasattr(self, '_is_small_screen') and self._is_small_screen:
            self.navigationInterface.setExpandWidth(120)
            self.navigationInterface.setMinimumExpandWidth(120)
        else:
            self.navigationInterface.setExpandWidth(170)
            self.navigationInterface.setMinimumExpandWidth(170)
        
        # 默认展开侧边栏
        self.navigationInterface.setCollapsible(True)  # 允许折叠
        self.navigationInterface.expand(useAni=False)  # 默认展开，不使用动画
    
    def _create_pages(self):
        """创建所有功能页面
        
        实例化各个功能页面并保存为实例属性。
        爬取页面需要传入登录管理器以获取登录凭证。
        创建完成后会延迟应用标签透明背景。
        """
        self.login_page = LoginPage(self)
        self.results_page = ArticlesPage(self)
        self.scrape_page = AccountManagementPage(
            self.login_page.get_login_manager(), self
        )
        self.settings_page = SettingsPage(self)
        
        # 延迟应用标签透明背景，确保所有组件都已创建
        QTimer.singleShot(100, self._apply_label_transparency)
    
    def _apply_label_transparency(self):
        """为所有页面的标签组件应用透明背景
        
        遍历所有页面，处理 qfluentwidgets 标签组件的背景透明问题。
        """
        pages = [
            self.login_page,
            self.results_page,
            self.scrape_page,
            self.settings_page
        ]
        for page in pages:
            apply_label_transparent_background(page)
    
    def _connect_signals(self):
        self.scrape_page.scrape_completed.connect(self._on_scrape_completed)
        self.settings_page.settings_changed.connect(self._on_settings_changed)

        from .workers import BackgroundScrapeDaemon
        from .widgets import ProcessingIndicator

        self.daemon = BackgroundScrapeDaemon(self.login_page.get_login_manager())
        self.daemon.log_message.connect(self._on_daemon_log)
        self.daemon.account_status_changed.connect(self._on_account_status_changed)
        self.daemon.phase_changed.connect(self._on_phase_changed)
        self.daemon.start()

        self.processing_indicator = ProcessingIndicator(self)
        self.processing_indicator.show()

        self.scrape_page.account_added.connect(lambda name: self.daemon.wake())
    
    def _on_settings_changed(self, config: dict):
        self.scrape_page.apply_settings(config)
    
    def _on_scrape_completed(self, articles: list, source_info: str):
        self.results_page.load_articles_data(articles, source_info)
        self.switchTo(self.results_page)
    
    def _on_daemon_log(self, message: str):
        self.scrape_page.append_log(message)

    def _on_account_status_changed(self, account_name: str, status: str):
        self.scrape_page._update_account_row(account_name, status)

    def _on_phase_changed(self, phase: str):
        labels = {'idle': '就绪', 'list': '爬取列表中', 'content': '爬取内容中', 'error': '出错'}
        self.processing_indicator.set_phase(phase, labels.get(phase, ''))

    def _init_navigation(self):
        """初始化侧边导航项
        
        将所有页面添加到导航栏，设置图标和显示名称。
        设置页面放置在底部位置。
        """
        self.addSubInterface(
            self.login_page, FluentIcon.FINGERPRINT, "账号登录"
        )
        
        self.addSubInterface(
            self.scrape_page, FluentIcon.DOWNLOAD, "公众号爬取"
        )
        self.addSubInterface(
            self.results_page, FluentIcon.PIE_SINGLE, "文章列表"
        )

        
        self.addSubInterface(
            self.settings_page, FluentIcon.SETTING, "设置",
            NavigationItemPosition.BOTTOM
        )
    
    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if hasattr(self, 'processing_indicator'):
            ind = self.processing_indicator
            ind.setGeometry(self.width() - ind.width() - 16, self.height() - ind.height() - 40, ind.width(), ind.height())

    def closeEvent(self, event: QCloseEvent):
        if hasattr(self, 'daemon'):
            self.daemon.stop()
            self.daemon.wait(1000)
        event.accept()
