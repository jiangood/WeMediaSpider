#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
后台工作线程模块

本模块提供 GUI 应用的后台工作线程，用于执行耗时的爬取任务，
避免阻塞主线程导致界面卡顿。

工作线程类型:
    1. BatchScrapeWorker: 同步爬取工作线程
       - 使用 ThreadPoolExecutor 实现并发
       - 适用于简单的批量爬取场景
    
    2. AsyncBatchScrapeWorker: 异步爬取工作线程
       - 使用 aiohttp 实现高效并发
       - 适用于大量公众号的批量爬取
       - 性能更好，资源占用更低

信号机制:
    两种工作线程都提供相同的信号接口，方便 GUI 层统一处理：
    - progress_update: 进度更新
    - account_status: 账号状态变化
    - scrape_success: 爬取成功
    - scrape_failed: 爬取失败
    - status_update: 状态文字更新
    - article_progress: 文章数量更新

使用方式:
    1. 创建工作线程实例，传入爬虫对象和配置
    2. 连接信号到 GUI 槽函数
    3. 调用 start() 启动线程
    4. 需要取消时调用 cancel()
"""

from PyQt6.QtCore import QThread, pyqtSignal
from datetime import datetime, timedelta
import time
import os
import random
import traceback


class BackgroundScrapeDaemon(QThread):
    log_message = pyqtSignal(str)
    account_status_changed = pyqtSignal(str, str)
    phase_changed = pyqtSignal(str)

    def __init__(self, login_manager, parent=None):
        super().__init__(parent)
        self.login_manager = login_manager
        self.is_running = True
        self._wake_flag = False
        self.request_interval = 10
        self._load_config()

    def _load_config(self):
        import json
        try:
            with open('config.json', 'r') as f:
                cfg = json.load(f)
                self.request_interval = int(cfg.get('request_interval', 10))
        except Exception:
            pass

    def wake(self):
        self._wake_flag = True

    def stop(self):
        self.is_running = False

    def _log(self, msg, level='info'):
        prefix = {'info': '', 'success': '✅ ', 'warning': '⚠️ ', 'error': '❌ '}
        self.log_message.emit(f"[{datetime.now().strftime('%H:%M:%S')}] {prefix.get(level, '')}{msg}")

    def run(self):
        from gui.utils import DB_PATH
        from spider.database import Database
        from spider.wechat.utils import get_fakid, get_articles_list, format_time, get_article_content
        from spider.wechat.scraper import WeChatScraper

        db = Database(DB_PATH)

        while self.is_running:
            if not self.login_manager.is_logged_in():
                self.phase_changed.emit('idle')
                self._log("等待登录...")
                for _ in range(60):
                    if not self.is_running:
                        db.close()
                        return
                    self.msleep(1000)
                    if self.login_manager.is_logged_in():
                        break
                if not self.login_manager.is_logged_in():
                    self.msleep(30000)
                    continue

            token = self.login_manager.get_token()
            headers = self.login_manager.get_headers()
            if not token or not headers:
                self._log("登录凭证无效，等待重新登录", 'warning')
                self.msleep(30000)
                continue

            try:
                pending = db.get_pending_account()
                if pending:
                    self.phase_changed.emit('list')
                    name = pending['name']
                    date_range = pending.get('date_range', '最近7天')
                    self._log(f"爬取列表: {name} ({date_range})")
                    self.account_status_changed.emit(name, 'processing')

                    try:
                        today = datetime.now()
                        if date_range == "最近7天":
                            start = today - timedelta(days=6)
                        elif date_range == "本月":
                            start = today.replace(day=1)
                        elif date_range == "本季度":
                            quarter_start_month = ((today.month - 1) // 3) * 3 + 1
                            start = today.replace(month=quarter_start_month, day=1)
                        elif date_range == "本年":
                            start = today.replace(month=1, day=1)
                        elif date_range == "最近3年":
                            start = today.replace(year=today.year - 3, month=1, day=1)
                        elif date_range == "全部":
                            start = today.replace(year=today.year - 10, month=1, day=1)
                        else:
                            start = today - timedelta(days=6)
                        start_timestamp = int(start.timestamp())

                        search_results = get_fakid(headers, token, name)
                        if not search_results:
                            raise Exception(f"未找到公众号: {name}")

                        fakeid = search_results[0]['wpub_fakid']

                        all_articles = []
                        page_start = 0
                        for page in range(100):
                            if not self.is_running:
                                break
                            titles, links, update_times = get_articles_list(
                                page_num=1, start_page=page_start,
                                fakeid=fakeid, token=token, headers=headers
                            )
                            if not titles:
                                break
                            page_has_valid = False
                            for title, link, utime in zip(titles, links, update_times):
                                ts = int(utime)
                                if ts >= start_timestamp:
                                    page_has_valid = True
                                    all_articles.append({
                                        'name': name, 'title': title, 'link': link,
                                        'publish_timestamp': ts,
                                        'publish_time': format_time(utime),
                                        'content': ''
                                    })
                            if not page_has_valid:
                                break
                            page_start += 5
                            self.msleep(random.randint(1000, 2000))

                        saved = db.save_articles(all_articles) if all_articles else 0
                        db.update_account_status(name, 'list_done', total_articles=saved)
                        self._log(f"{name}: 列表完成，{saved} 篇", 'success')
                        self.account_status_changed.emit(name, 'list_done')
                        continue

                    except Exception as e:
                        db.update_account_status(name, 'error', error_message=str(e))
                        self._log(f"{name}: 列表失败 - {e}", 'error')
                        self.account_status_changed.emit(name, 'error')
                        continue

                article = db.get_article_without_content()
                if article:
                    self.phase_changed.emit('content')
                    article_id = article['id']
                    article_title = article['title']
                    article_link = article['link']
                    account_name = article['account_name']
                    self._log(f"获取正文: {account_name} - {article_title[:40]}")

                    scraper = WeChatScraper(token, headers)
                    result = scraper.get_article_content_by_url({'link': article_link})
                    markdown_content = result.get('content', '')

                    if markdown_content and not markdown_content.startswith('获取内容失败'):
                        db.conn.execute(
                            "UPDATE articles SET content = ? WHERE id = ?",
                            (markdown_content, article_id)
                        )
                        db.conn.commit()
                        self._log(f"正文完成: {account_name} - {article_title[:40]}", 'success')

                    delay = random.uniform(self.request_interval * 0.8, self.request_interval * 1.2)
                    for _ in range(int(delay * 10)):
                        if not self.is_running:
                            break
                        self.msleep(100)
                    continue

                self.phase_changed.emit('idle')
                self._log("等待新任务...")
                for _ in range(300):
                    if not self.is_running:
                        break
                    if self._wake_flag:
                        self._wake_flag = False
                        self._log("收到新任务信号")
                        break
                    self.msleep(100)

            except Exception as e:
                self._log(f"守护线程异常: {e}", 'error')
                self.msleep(5000)

        db.close()


class BatchScrapeWorker(QThread):
    """同步批量爬取工作线程
    
    在后台线程中执行同步爬取任务，通过信号向 GUI 报告进度。
    
    Signals:
        progress_update(int, int, str): 进度更新，参数为 (当前值, 总值, 消息)
        account_status(str, str, str): 账号状态，参数为 (账号名, 状态, 消息)
        scrape_success(list, str): 爬取成功，参数为 (文章列表, 输出文件路径)
        scrape_failed(str): 爬取失败，参数为错误消息
        status_update(str): 状态文字更新
        article_progress(int, str): 文章进度，参数为 (文章数量, 消息)
    
    Attributes:
        batch_scraper: 批量爬虫实例
        config: 爬取配置字典
        is_cancelled: 是否已取消
        articles: 已爬取的文章列表
    """
    
    progress_update = pyqtSignal(int, int, str)
    account_status = pyqtSignal(str, str, str)
    scrape_success = pyqtSignal(list, str)
    scrape_failed = pyqtSignal(str)
    status_update = pyqtSignal(str)
    article_progress = pyqtSignal(int, str)
    
    def __init__(self, batch_scraper, config: dict):
        """初始化工作线程
        
        Args:
            batch_scraper: 批量爬虫实例，需要实现 start_batch_scrape 方法
            config: 爬取配置字典，包含公众号列表、文章数量等参数
        """
        super().__init__()
        self.batch_scraper = batch_scraper
        self.config = config
        self.is_cancelled = False
        self.articles = []  # 保存爬取的文章
    
    def cancel(self):
        """取消爬取任务
        
        设置取消标志并通知爬虫停止工作。
        已爬取的文章仍然可以通过 get_articles() 获取。
        """
        self.is_cancelled = True
        self.batch_scraper.cancel_batch_scrape()
    
    def get_articles(self) -> list:
        """获取已爬取的文章列表
        
        Returns:
            文章字典列表，即使任务被取消也会返回已获取的部分
        """
        return self.articles
    
    def run(self):
        """线程主函数，执行爬取任务"""
        try:
            # 设置回调
            def progress_callback(current, total):
                pass  # 不再使用公众号进度
            
            def account_status_callback(account_name, status, message):
                if not self.is_cancelled:
                    self.account_status.emit(account_name, status, message)
            
            def batch_completed_callback(total_articles):
                pass  # 由主线程处理
            
            def error_callback(account_name, error_message):
                if not self.is_cancelled:
                    self.account_status.emit(account_name, "error", error_message)
            
            def article_progress_callback(article_count, message):
                if not self.is_cancelled:
                    self.article_progress.emit(article_count, message)
                    # 使用文章数模式（total=0 表示不确定进度）
                    self.progress_update.emit(article_count, 0, message)
            
            def content_progress_callback(current, total, message):
                """ 真实百分比进度 """
                if not self.is_cancelled:
                    self.progress_update.emit(current, total, message)
            
            self.batch_scraper.set_callback('progress_updated', progress_callback)
            self.batch_scraper.set_callback('account_status', account_status_callback)
            self.batch_scraper.set_callback('batch_completed', batch_completed_callback)
            self.batch_scraper.set_callback('error_occurred', error_callback)
            self.batch_scraper.set_callback('article_progress', article_progress_callback)
            self.batch_scraper.set_callback('content_progress', content_progress_callback)
            
            # 开始爬取
            self.status_update.emit("开始爬取...")
            self.articles = self.batch_scraper.start_batch_scrape(self.config)
            
            if self.is_cancelled:
                self.scrape_failed.emit("已取消")
                return
            
            db_path = self.config.get('db_path', '')
            self.scrape_success.emit(self.articles, db_path)
            
        except Exception as e:
            traceback.print_exc()
            self.scrape_failed.emit(f"批量爬取出错: {str(e)}")


class AsyncBatchScrapeWorker(QThread):
    """异步批量爬取工作线程
    
    使用 aiohttp 实现高效的异步并发爬取，相比同步版本：
    - 更高的并发性能
    - 更低的资源占用
    - 更好的网络利用率
    
    信号接口与 BatchScrapeWorker 完全相同，可以无缝替换。
    
    Signals:
        progress_update(int, int, str): 进度更新
        account_status(str, str, str): 账号状态
        scrape_success(list, str): 爬取成功
        scrape_failed(str): 爬取失败
        status_update(str): 状态更新
        article_progress(int, str): 文章进度
    
    Attributes:
        async_scraper: 异步爬虫实例
        config: 爬取配置字典
        is_cancelled: 是否已取消
        articles: 已爬取的文章列表
    """
    
    progress_update = pyqtSignal(int, int, str)
    account_status = pyqtSignal(str, str, str)
    scrape_success = pyqtSignal(list, str)
    scrape_failed = pyqtSignal(str)
    status_update = pyqtSignal(str)
    article_progress = pyqtSignal(int, str)
    
    def __init__(self, async_scraper, config: dict):
        """初始化异步工作线程
        
        Args:
            async_scraper: 异步爬虫实例
            config: 爬取配置字典
        """
        super().__init__()
        self.async_scraper = async_scraper
        self.config = config
        self.is_cancelled = False
        self.articles = []
    
    def cancel(self):
        """取消爬取任务"""
        self.is_cancelled = True
        self.async_scraper.cancel_batch_scrape()
    
    def get_articles(self) -> list:
        """获取已爬取的文章列表
        
        优先返回已完成的文章列表，如果任务被取消，
        会尝试从爬虫获取已收集的部分结果。
        
        Returns:
            文章字典列表
        """
        # 优先返回已完成的文章列表
        if self.articles:
            return self.articles
        # 如果爬取被取消，尝试从爬虫获取已收集的文章
        if hasattr(self.async_scraper, 'get_collected_articles'):
            return self.async_scraper.get_collected_articles()
        if hasattr(self.async_scraper, 'collected_articles'):
            return self.async_scraper.collected_articles
        return []
    
    def run(self):
        """线程主函数，执行异步爬取任务"""
        try:
            # 设置回调
            def progress_callback(current, total):
                pass  # 不再使用公众号进度
            
            def account_status_callback(account_name, status, message):
                if not self.is_cancelled:
                    self.account_status.emit(account_name, status, message)
            
            def batch_completed_callback(total_articles):
                pass  # 由主线程处理
            
            def error_callback(account_name, error_message):
                if not self.is_cancelled:
                    self.account_status.emit(account_name, "error", error_message)
            
            def article_progress_callback(article_count, message):
                if not self.is_cancelled:
                    self.article_progress.emit(article_count, message)
                    # 使用文章数模式（total=0 表示不确定进度）
                    self.progress_update.emit(article_count, 0, message)
            
            def content_progress_callback(current, total, message):
                """真实百分比进度"""
                if not self.is_cancelled:
                    self.progress_update.emit(current, total, message)
            
            # 设置回调
            self.async_scraper.set_callback('progress_updated', progress_callback)
            self.async_scraper.set_callback('account_status', account_status_callback)
            self.async_scraper.set_callback('batch_completed', batch_completed_callback)
            self.async_scraper.set_callback('error_occurred', error_callback)
            self.async_scraper.set_callback('article_progress', article_progress_callback)
            self.async_scraper.set_callback('content_progress', content_progress_callback)
            
            # 开始异步爬取
            self.status_update.emit("开始异步爬取...")
            self.articles = self.async_scraper.start_batch_scrape(self.config)
            
            if self.is_cancelled:
                self.scrape_failed.emit("已取消")
                return
            
            db_path = self.config.get('db_path', '')
            self.scrape_success.emit(self.articles, db_path)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.scrape_failed.emit(f"异步爬取出错: {str(e)}")
