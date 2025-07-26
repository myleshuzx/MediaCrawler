# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。


# -*- coding: utf-8 -*-
import asyncio
import os
import random
from asyncio import Task
from typing import Dict, List, Optional, Tuple, cast

from playwright.async_api import (
    BrowserContext,
    BrowserType,
    Page,
    Playwright,
    async_playwright,
)

import config
from constant import zhihu as constant
from base.base_crawler import AbstractCrawler
from model.m_zhihu import ZhihuContent, ZhihuCreator
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from store import zhihu as zhihu_store
from tools import utils
from tools.cdp_browser import CDPBrowserManager
from var import crawler_type_var, source_keyword_var

from .client import ZhiHuClient
from .exception import DataFetchError
from .help import ZhihuExtractor, judge_zhihu_url
from .login import ZhiHuLogin


class ZhihuCrawler(AbstractCrawler):
    context_page: Page
    zhihu_client: ZhiHuClient
    browser_context: BrowserContext
    cdp_manager: Optional[CDPBrowserManager]

    def __init__(self) -> None:
        self.index_url = "https://www.zhihu.com"
        # self.user_agent = utils.get_user_agent()
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        self._extractor = ZhihuExtractor()
        self.cdp_manager = None

    async def start(self) -> None:
        """
        Start the crawler
        Returns:

        """
        playwright_proxy_format, httpx_proxy_format = None, None
        if config.ENABLE_IP_PROXY:
            ip_proxy_pool = await create_ip_pool(
                config.IP_PROXY_POOL_COUNT, enable_validate_ip=True
            )
            ip_proxy_info: IpInfoModel = await ip_proxy_pool.get_proxy()
            playwright_proxy_format, httpx_proxy_format = self.format_proxy_info(
                ip_proxy_info
            )

        async with async_playwright() as playwright:
            # 根据配置选择启动模式
            if config.ENABLE_CDP_MODE:
                utils.logger.info("[ZhihuCrawler] 使用CDP模式启动浏览器")
                self.browser_context = await self.launch_browser_with_cdp(
                    playwright,
                    playwright_proxy_format,
                    self.user_agent,
                    headless=config.CDP_HEADLESS,
                )
            else:
                utils.logger.info("[ZhihuCrawler] 使用标准模式启动浏览器")
                # Launch a browser context.
                chromium = playwright.chromium
                self.browser_context = await self.launch_browser(
                    chromium, None, self.user_agent, headless=config.HEADLESS
                )
            # stealth.min.js is a js script to prevent the website from detecting the crawler.
            await self.browser_context.add_init_script(path="libs/stealth.min.js")

            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url, wait_until="domcontentloaded")

            # Create a client to interact with the zhihu website.
            self.zhihu_client = await self.create_zhihu_client(httpx_proxy_format)
            if not await self.zhihu_client.pong():
                login_obj = ZhiHuLogin(
                    login_type=config.LOGIN_TYPE,
                    login_phone="",  # input your phone number
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=config.COOKIES,
                )
                await login_obj.begin()
                await self.zhihu_client.update_cookies(
                    browser_context=self.browser_context
                )

            # 知乎的搜索接口需要打开搜索页面之后cookies才能访问API，单独的首页不行
            utils.logger.info(
                "[ZhihuCrawler.start] Zhihu跳转到搜索页面获取搜索页面的Cookies，该过程需要5秒左右"
            )
            await self.context_page.goto(
                f"{self.index_url}/search?q=python&search_source=Guess&utm_content=search_hot&type=content"
            )
            await asyncio.sleep(5)
            await self.zhihu_client.update_cookies(browser_context=self.browser_context)

            crawler_type_var.set(config.CRAWLER_TYPE)
            if config.CRAWLER_TYPE == "search":
                # Search for notes and retrieve their comment information.
                await self.search()
            elif config.CRAWLER_TYPE == "detail":
                # Get the information and comments of the specified post
                await self.get_specified_notes()
            elif config.CRAWLER_TYPE == "creator":
                # Get creator's information and their notes and comments
                await self.get_creators_and_notes()
            elif config.CRAWLER_TYPE == "question":
                # Get answers from specified questions
                await self.get_question_answers()
            else:
                pass

            utils.logger.info("[ZhihuCrawler.start] Zhihu Crawler finished ...")

    async def search(self) -> None:
        """Search for notes and retrieve their comment information."""
        utils.logger.info("[ZhihuCrawler.search] Begin search zhihu keywords")
        zhihu_limit_count = 20  # zhihu limit page fixed value
        if config.CRAWLER_MAX_NOTES_COUNT < zhihu_limit_count:
            config.CRAWLER_MAX_NOTES_COUNT = zhihu_limit_count
        start_page = config.START_PAGE
        for keyword in config.KEYWORDS.split(","):
            source_keyword_var.set(keyword)
            utils.logger.info(
                f"[ZhihuCrawler.search] Current search keyword: {keyword}"
            )
            page = 1
            while (
                page - start_page + 1
            ) * zhihu_limit_count <= config.CRAWLER_MAX_NOTES_COUNT:
                if page < start_page:
                    utils.logger.info(f"[ZhihuCrawler.search] Skip page {page}")
                    page += 1
                    continue

                try:
                    utils.logger.info(
                        f"[ZhihuCrawler.search] search zhihu keyword: {keyword}, page: {page}"
                    )
                    content_list: List[ZhihuContent] = (
                        await self.zhihu_client.get_note_by_keyword(
                            keyword=keyword,
                            page=page,
                        )
                    )
                    utils.logger.info(
                        f"[ZhihuCrawler.search] Search contents :{content_list}"
                    )
                    if not content_list:
                        utils.logger.info("No more content!")
                        break

                    page += 1
                    for content in content_list:
                        await zhihu_store.update_zhihu_content(content)

                    await self.batch_get_content_comments(content_list)
                except DataFetchError:
                    utils.logger.error("[ZhihuCrawler.search] Search content error")
                    return

    async def batch_get_content_comments(self, content_list: List[ZhihuContent]):
        """
        Batch get content comments
        Args:
            content_list:

        Returns:

        """
        if not config.ENABLE_GET_COMMENTS:
            utils.logger.info(
                f"[ZhihuCrawler.batch_get_content_comments] Crawling comment mode is not enabled"
            )
            return

        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        task_list: List[Task] = []
        for content_item in content_list:
            task = asyncio.create_task(
                self.get_comments(content_item, semaphore), name=content_item.content_id
            )
            task_list.append(task)
        await asyncio.gather(*task_list)

    async def get_comments(
        self, content_item: ZhihuContent, semaphore: asyncio.Semaphore
    ):
        """
        Get note comments with keyword filtering and quantity limitation
        Args:
            content_item:
            semaphore:

        Returns:

        """
        async with semaphore:
            utils.logger.info(
                f"[ZhihuCrawler.get_comments] Begin get note id comments {content_item.content_id}"
            )
            await self.zhihu_client.get_note_all_comments(
                content=content_item,
                crawl_interval=random.random(),
                callback=zhihu_store.batch_update_zhihu_note_comments,
            )

    async def get_creators_and_notes(self) -> None:
        """
        Get creator's information and their notes and comments
        Returns:

        """
        utils.logger.info(
            "[ZhihuCrawler.get_creators_and_notes] Begin get xiaohongshu creators"
        )
        for user_link in config.ZHIHU_CREATOR_URL_LIST:
            utils.logger.info(
                f"[ZhihuCrawler.get_creators_and_notes] Begin get creator {user_link}"
            )
            user_url_token = user_link.split("/")[-1]
            # get creator detail info from web html content
            createor_info: ZhihuCreator = await self.zhihu_client.get_creator_info(
                url_token=user_url_token
            )
            if not createor_info:
                utils.logger.info(
                    f"[ZhihuCrawler.get_creators_and_notes] Creator {user_url_token} not found"
                )
                continue

            utils.logger.info(
                f"[ZhihuCrawler.get_creators_and_notes] Creator info: {createor_info}"
            )
            await zhihu_store.save_creator(creator=createor_info)

            # 默认只提取回答信息，如果需要文章和视频，把下面的注释打开即可

            # Get all anwser information of the creator
            all_content_list = await self.zhihu_client.get_all_anwser_by_creator(
                creator=createor_info,
                crawl_interval=random.random(),
                callback=zhihu_store.batch_update_zhihu_contents,
            )

            # Get all articles of the creator's contents
            # all_content_list = await self.zhihu_client.get_all_articles_by_creator(
            #     creator=createor_info,
            #     crawl_interval=random.random(),
            #     callback=zhihu_store.batch_update_zhihu_contents
            # )

            # Get all videos of the creator's contents
            # all_content_list = await self.zhihu_client.get_all_videos_by_creator(
            #     creator=createor_info,
            #     crawl_interval=random.random(),
            #     callback=zhihu_store.batch_update_zhihu_contents
            # )

            # Get all comments of the creator's contents
            await self.batch_get_content_comments(all_content_list)

    async def get_question_answers(self) -> None:
        """
        Get answers from specified questions
        Returns:

        """
        utils.logger.info(
            "[ZhihuCrawler.get_question_answers] Begin get zhihu questions answers"
        )
        utils.logger.info(f"[ZhihuCrawler.get_question_answers] Configured questions: {config.ZHIHU_QUESTION_LIST}")
        
        all_answer_urls = []
        
        for question_url in config.ZHIHU_QUESTION_LIST:
            utils.logger.info(
                f"[ZhihuCrawler.get_question_answers] Processing question: {question_url}"
            )
            
            # 首先提取并保存问题主题信息
            await self._extract_and_save_question_topic(question_url)
            
            # 收集该问题下的回答链接
            answer_urls = await self.scroll_and_collect_answers(question_url)
            all_answer_urls.extend(answer_urls)
            utils.logger.info(
                f"[ZhihuCrawler.get_question_answers] Collected {len(answer_urls)} answers from question"
            )
        
        utils.logger.info(
            f"[ZhihuCrawler.get_question_answers] Total collected {len(all_answer_urls)} answer URLs"
        )
        
        # 批量获取回答详情
        semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY_NUM)
        get_answer_detail_tasks = []
        for answer_url in all_answer_urls:
            task = self.get_note_detail(
                full_note_url=answer_url,
                semaphore=semaphore
            )
            get_answer_detail_tasks.append(task)
        
        need_get_comment_answers: List[ZhihuContent] = []
        answer_details = await asyncio.gather(*get_answer_detail_tasks)
        for index, answer_detail in enumerate(answer_details):
            if not answer_detail:
                utils.logger.info(
                    f"[ZhihuCrawler.get_question_answers] Answer {all_answer_urls[index]} not found"
                )
                continue
            
            answer_detail = cast(ZhihuContent, answer_detail)
            need_get_comment_answers.append(answer_detail)
            await zhihu_store.update_zhihu_content(answer_detail)
        
        # 获取评论
        await self.batch_get_content_comments(need_get_comment_answers)

    async def scroll_and_collect_answers(self, question_url: str) -> List[str]:
        """
        Scroll the question page and collect answer URLs
        Args:
            question_url: The question URL to crawl

        Returns:
            List of answer URLs
        """
        utils.logger.info(
            f"[ZhihuCrawler.scroll_and_collect_answers] Start collecting answers from {question_url}"
        )
        
        # 打开问题页面
        await self.context_page.goto(question_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)  # 等待页面加载
        
        collected_answers = set()  # 使用set避免重复
        max_answers = config.CRAWLER_MAX_NOTES_COUNT
        no_new_content_count = 0  # 连续没有新内容的次数
        max_no_new_content = 10    # 增加最大连续没有新内容次数，从3改为10
        
        utils.logger.info(
            f"[ZhihuCrawler.scroll_and_collect_answers] Target max answers: {max_answers}"
        )
        
        while len(collected_answers) < max_answers and no_new_content_count < max_no_new_content:
            # 首先滚动和加载更多内容
            if len(collected_answers) > 0:  # 第一次不滚动，从第二次开始
                await self._scroll_to_load_more()
                await asyncio.sleep(2)  # 等待内容稳定
                
                # 尝试点击"更多"按钮（如果存在）
                await self._try_click_load_more_button()
            
            # 获取当前页面上的回答链接（在滚动和点击后）
            # 增加稳定性检测，等待DOM完全稳定
            await self._wait_for_content_stability()
            
            current_answers = await self.context_page.evaluate("""
                () => {
                    const links = [];
                    // 查找所有回答链接，使用更全面的选择器
                    const selectors = [
                        'a[href*="/question/"][href*="/answer/"]',
                        '[data-za-detail-view-element="answer"] a[href*="/answer/"]',
                        '.ContentItem-title a[href*="/answer/"]',
                        '.QuestionAnswer-content a[href*="/answer/"]'
                    ];
                    
                    selectors.forEach(selector => {
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(element => {
                            const href = element.href;
                            if (href && href.includes('/question/') && href.includes('/answer/')) {
                                // 移除查询参数
                                const cleanUrl = href.split('?')[0];
                                if (cleanUrl.match(/\/question\/\\d+\/answer\/\\d+$/)) {
                                    links.push(cleanUrl);
                                }
                            }
                        });
                    });
                    
                    // 另外尝试从页面上直接查找回答元素
                    const answerItems = document.querySelectorAll('[data-za-detail-view-id]');
                    answerItems.forEach(item => {
                        const zaId = item.getAttribute('data-za-detail-view-id');
                        if (zaId && zaId.includes('answer')) {
                            // 尝试从data属性构建链接
                            const match = zaId.match(/answer:(\\d+)/);
                            if (match) {
                                const answerId = match[1];
                                // 需要从当前URL获取问题ID
                                const currentUrl = window.location.pathname;
                                const questionMatch = currentUrl.match(/\/question\/(\\d+)/);
                                if (questionMatch) {
                                    const questionId = questionMatch[1];
                                    const answerUrl = `https://www.zhihu.com/question/${questionId}/answer/${answerId}`;
                                    links.push(answerUrl);
                                }
                            }
                        }
                    });
                    
                    return [...new Set(links)]; // 去重
                }
            """)
            
            previous_count = len(collected_answers)
            collected_answers.update(current_answers)
            new_answers_count = len(collected_answers) - previous_count
            
            utils.logger.info(
                f"[ZhihuCrawler.scroll_and_collect_answers] Found {new_answers_count} new answers, "
                f"total: {len(collected_answers)}/{max_answers}"
            )
            
            if new_answers_count == 0:
                no_new_content_count += 1
                utils.logger.info(
                    f"[ZhihuCrawler.scroll_and_collect_answers] No new content found, "
                    f"count: {no_new_content_count}/{max_no_new_content}"
                )
                
                # 如果连续几次没有新内容，尝试更激进的滚动策略
                if no_new_content_count >= 3:
                    utils.logger.info("[ZhihuCrawler.scroll_and_collect_answers] Trying aggressive scroll strategy")
                    await self._aggressive_scroll()
            else:
                no_new_content_count = 0  # 重置计数器
            
            # 如果已经收集够了，就停止
            if len(collected_answers) >= max_answers:
                utils.logger.info(
                    f"[ZhihuCrawler.scroll_and_collect_answers] Collected enough answers: {len(collected_answers)}"
                )
                break
        
        # 转换为列表并限制数量
        answer_urls = list(collected_answers)[:max_answers]
        
        utils.logger.info(
            f"[ZhihuCrawler.scroll_and_collect_answers] Final collected {len(answer_urls)} answer URLs"
        )
        
        return answer_urls

    async def _try_click_load_more_button(self):
        """
        尝试点击"更多"按钮加载更多内容
        """
        try:
            load_more_selectors = [
                'button:has-text("更多")',
                'button:has-text("加载更多")', 
                'button:has-text("查看全部")',
                '.Button--plain',
                'button[class*="LoadMore"]',
                'button[class*="Button"][class*="plain"]',
                '.QuestionMainAction button'
            ]
            
            load_more_button = None
            for selector in load_more_selectors:
                try:
                    load_more_button = await self.context_page.query_selector(selector)
                    if load_more_button:
                        # 检查按钮是否可见和可点击
                        is_visible = await load_more_button.is_visible()
                        is_enabled = await load_more_button.is_enabled()
                        if is_visible and is_enabled:
                            utils.logger.info(f"[ZhihuCrawler._try_click_load_more_button] Found load more button with selector: {selector}")
                            break
                except:
                    continue
            
            if load_more_button:
                await load_more_button.click()
                await asyncio.sleep(3)  # 等待内容加载
                utils.logger.info("[ZhihuCrawler._try_click_load_more_button] Clicked load more button")
                
        except Exception as e:
            utils.logger.debug(f"[ZhihuCrawler._try_click_load_more_button] No load more button found: {e}")

    async def _scroll_to_load_more(self):
        """
        优化的滚动策略，用于触发知乎页面的懒加载
        """
        # 1. 先获取当前页面高度
        current_height = await self.context_page.evaluate("document.body.scrollHeight")
        
        # 2. 直接滚动到底部，触发懒加载
        await self.context_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.5)  # 减少等待时间
        
        # 3. 检查页面高度是否有变化
        new_height = await self.context_page.evaluate("document.body.scrollHeight")
        
        if new_height > current_height:
            utils.logger.info(
                f"[ZhihuCrawler._scroll_to_load_more] Page height increased from {current_height} to {new_height}"
            )
        else:
            utils.logger.info(
                f"[ZhihuCrawler._scroll_to_load_more] Page height unchanged: {current_height}"
            )

    async def _aggressive_scroll(self):
        """
        更激进的滚动策略，用于在常规滚动无效时尝试
        """
        utils.logger.info("[ZhihuCrawler._aggressive_scroll] Starting aggressive scroll strategy")
        
        # 1. 快速上下滚动，模拟用户行为
        for _ in range(2):
            await self.context_page.evaluate("window.scrollTo(0, 0)")  # 滚动到顶部
            await asyncio.sleep(0.3)
            await self.context_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")  # 滚动到底部
            await asyncio.sleep(0.7)
        
        # 2. 尝试键盘操作 (Page Down)
        await self.context_page.keyboard.press("End")
        await asyncio.sleep(1)
        
        # 3. 尝试鼠标滚轮事件
        await self.context_page.evaluate("""
            () => {
                const event = new WheelEvent('wheel', {
                    deltaY: 1000,
                    bubbles: true,
                    cancelable: true
                });
                document.dispatchEvent(event);
            }
        """)
        await asyncio.sleep(1.5)
        
        utils.logger.info("[ZhihuCrawler._aggressive_scroll] Aggressive scroll strategy completed")

    async def _wait_for_content_stability(self):
        """
        等待页面内容稳定，确保DOM完全加载
        """
        # 连续检测页面高度，确保内容稳定
        stable_count = 0
        last_height = 0
        
        for _ in range(5):  # 最多检测5次
            current_height = await self.context_page.evaluate("document.body.scrollHeight")
            answer_count = await self.context_page.evaluate("""
                () => {
                    const selectors = [
                        'a[href*="/question/"][href*="/answer/"]',
                        '[data-za-detail-view-element="answer"]',
                        '.ContentItem-title a[href*="/answer/"]'
                    ];
                    let count = 0;
                    selectors.forEach(selector => {
                        count += document.querySelectorAll(selector).length;
                    });
                    return count;
                }
            """)
            
            if current_height == last_height:
                stable_count += 1
            else:
                stable_count = 0
                last_height = current_height
            
            # 如果连续2次高度相同，认为页面稳定
            if stable_count >= 2:
                utils.logger.info(f"[ZhihuCrawler._wait_for_content_stability] Content stable at height {current_height}, answers: {answer_count}")
                break
            
            await asyncio.sleep(0.8)  # 每次检测间隔0.8秒

    async def _extract_and_save_question_topic(self, question_url: str):
        """
        提取并保存问题主题信息
        Args:
            question_url: 问题链接
        """
        try:
            utils.logger.info(f"[ZhihuCrawler._extract_and_save_question_topic] Extracting question topic from: {question_url}")
            
            # 先用context_page展开问题详情
            await self._expand_question_detail_with_context_page(question_url)
            
            # 获取展开后的页面HTML内容
            page_html = await self.context_page.content()
            utils.logger.info(f"[ZhihuCrawler._extract_and_save_question_topic] Got page HTML with length: {len(page_html)}")
            
            # 直接从HTML提取问题主题信息
            question_topic = self.zhihu_client._extractor.extract_question_topic_from_html(page_html, question_url)
            
            if question_topic:
                utils.logger.info(f"[ZhihuCrawler._extract_and_save_question_topic] Successfully extracted question topic: {question_topic.title}")
                utils.logger.info(f"[ZhihuCrawler._extract_and_save_question_topic] Detail length: {len(question_topic.detail)}")
                
                # 导入存储模块并保存
                from store import zhihu as zhihu_store
                await zhihu_store.save_question_topic(question_topic)
                utils.logger.info(f"[ZhihuCrawler._extract_and_save_question_topic] Successfully saved question topic: {question_topic.title}")
            else:
                utils.logger.warning(f"[ZhihuCrawler._extract_and_save_question_topic] Failed to extract question topic from: {question_url}")
                
        except Exception as e:
            utils.logger.error(f"[ZhihuCrawler._extract_and_save_question_topic] Error extracting question topic: {e}")
            import traceback
            utils.logger.error(f"[ZhihuCrawler._extract_and_save_question_topic] Full traceback: {traceback.format_exc()}")

    async def _expand_question_detail_with_context_page(self, question_url: str):
        """
        使用context_page展开问题详情
        """
        try:
            utils.logger.info(f"[ZhihuCrawler._expand_question_detail_with_context_page] Expanding question details for: {question_url}")
            
            await self.context_page.goto(question_url, wait_until="domcontentloaded")
            await asyncio.sleep(3)  # 等待页面加载
            
            # 尝试找到并点击"显示全部"按钮
            expand_selectors = [
                'button:has-text("显示全部")',
                'button:has-text("展开")', 
                'button[class*="QuestionRichText-more"]',
                'button[class*="expand"]',
                '.QuestionRichText-more button',
                '.QuestionRichText .Button--plain'
            ]
            
            expanded = False
            for selector in expand_selectors:
                try:
                    expand_button = await self.context_page.query_selector(selector)
                    if expand_button:
                        is_visible = await expand_button.is_visible()
                        if is_visible:
                            # 记录点击前的内容长度
                            before_content = await self.context_page.evaluate("""
                                () => {
                                    const element = document.querySelector('.QuestionRichText, .QuestionRichText--expandable');
                                    return element ? element.textContent.length : 0;
                                }
                            """)
                            
                            await expand_button.click()
                            utils.logger.info(f"[ZhihuCrawler._expand_question_detail_with_context_page] Clicked expand button with selector: {selector}")
                            
                            # 等待内容加载，并检测内容是否真的展开了
                            max_wait_time = 10  # 最多等待10秒
                            wait_step = 1  # 每1秒检查一次
                            waited_time = 0
                            
                            while waited_time < max_wait_time:
                                await asyncio.sleep(wait_step)
                                waited_time += wait_step
                                
                                # 检查内容是否已经展开
                                after_content = await self.context_page.evaluate("""
                                    () => {
                                        const element = document.querySelector('.QuestionRichText, .QuestionRichText--expandable');
                                        return element ? element.textContent.length : 0;
                                    }
                                """)
                                
                                if after_content > before_content:
                                    utils.logger.info(f"[ZhihuCrawler._expand_question_detail_with_context_page] Content expanded from {before_content} to {after_content} chars after {waited_time}s")
                                    break
                                    
                                utils.logger.debug(f"[ZhihuCrawler._expand_question_detail_with_context_page] Waiting for content to expand... {waited_time}s")
                            
                            # 额外等待2秒确保内容完全加载
                            await asyncio.sleep(2)
                            
                            expanded = True
                            break
                except Exception as e:
                    utils.logger.debug(f"[ZhihuCrawler._expand_question_detail_with_context_page] Selector {selector} failed: {e}")
                    continue
            
            if not expanded:
                utils.logger.info(f"[ZhihuCrawler._expand_question_detail_with_context_page] No expand button found or clicked")
                
        except Exception as e:
            utils.logger.warning(f"[ZhihuCrawler._expand_question_detail_with_context_page] 展开问题详情失败: {e}")

    async def get_note_detail(
        self, full_note_url: str, semaphore: asyncio.Semaphore
    ) -> Optional[ZhihuContent]:
        """
        Get note detail
        Args:
            full_note_url: str
            semaphore:

        Returns:

        """
        async with semaphore:
            utils.logger.info(
                f"[ZhihuCrawler.get_specified_notes] Begin get specified note {full_note_url}"
            )
            # judge note type
            note_type: str = judge_zhihu_url(full_note_url)
            if note_type == constant.ANSWER_NAME:
                question_id = full_note_url.split("/")[-3]
                answer_id = full_note_url.split("/")[-1]
                utils.logger.info(
                    f"[ZhihuCrawler.get_specified_notes] Get answer info, question_id: {question_id}, answer_id: {answer_id}"
                )
                return await self.zhihu_client.get_answer_info(question_id, answer_id)

            elif note_type == constant.ARTICLE_NAME:
                article_id = full_note_url.split("/")[-1]
                utils.logger.info(
                    f"[ZhihuCrawler.get_specified_notes] Get article info, article_id: {article_id}"
                )
                return await self.zhihu_client.get_article_info(article_id)

            elif note_type == constant.VIDEO_NAME:
                video_id = full_note_url.split("/")[-1]
                utils.logger.info(
                    f"[ZhihuCrawler.get_specified_notes] Get video info, video_id: {video_id}"
                )
                return await self.zhihu_client.get_video_info(video_id)

    async def get_specified_notes(self):
        """
        Get the information and comments of the specified post
        Returns:

        """
        get_note_detail_task_list = []
        for full_note_url in config.ZHIHU_SPECIFIED_ID_LIST:
            # remove query params
            full_note_url = full_note_url.split("?")[0]
            crawler_task = self.get_note_detail(
                full_note_url=full_note_url,
                semaphore=asyncio.Semaphore(config.MAX_CONCURRENCY_NUM),
            )
            get_note_detail_task_list.append(crawler_task)

        need_get_comment_notes: List[ZhihuContent] = []
        note_details = await asyncio.gather(*get_note_detail_task_list)
        for index, note_detail in enumerate(note_details):
            if not note_detail:
                utils.logger.info(
                    f"[ZhihuCrawler.get_specified_notes] Note {config.ZHIHU_SPECIFIED_ID_LIST[index]} not found"
                )
                continue

            note_detail = cast(ZhihuContent, note_detail)  # only for type check
            need_get_comment_notes.append(note_detail)
            await zhihu_store.update_zhihu_content(note_detail)

        await self.batch_get_content_comments(need_get_comment_notes)

    @staticmethod
    def format_proxy_info(
        ip_proxy_info: IpInfoModel,
    ) -> Tuple[Optional[Dict], Optional[Dict]]:
        """format proxy info for playwright and httpx"""
        playwright_proxy = {
            "server": f"{ip_proxy_info.protocol}{ip_proxy_info.ip}:{ip_proxy_info.port}",
            "username": ip_proxy_info.user,
            "password": ip_proxy_info.password,
        }
        httpx_proxy = {
            f"{ip_proxy_info.protocol}": f"http://{ip_proxy_info.user}:{ip_proxy_info.password}@{ip_proxy_info.ip}:{ip_proxy_info.port}"
        }
        return playwright_proxy, httpx_proxy

    async def create_zhihu_client(self, httpx_proxy: Optional[str]) -> ZhiHuClient:
        """Create zhihu client"""
        utils.logger.info(
            "[ZhihuCrawler.create_zhihu_client] Begin create zhihu API client ..."
        )
        cookie_str, cookie_dict = utils.convert_cookies(
            await self.browser_context.cookies()
        )
        zhihu_client_obj = ZhiHuClient(
            proxies=httpx_proxy,
            headers={
                "accept": "*/*",
                "accept-language": "zh-CN,zh;q=0.9",
                "cookie": cookie_str,
                "priority": "u=1, i",
                "referer": "https://www.zhihu.com/search?q=python&time_interval=a_year&type=content",
                "user-agent": self.user_agent,
                "x-api-version": "3.0.91",
                "x-app-za": "OS=Web",
                "x-requested-with": "fetch",
                "x-zse-93": "101_3_3.0",
            },
            playwright_page=self.context_page,
            cookie_dict=cookie_dict,
        )
        return zhihu_client_obj

    async def launch_browser(
        self,
        chromium: BrowserType,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """Launch browser and create browser context"""
        utils.logger.info(
            "[ZhihuCrawler.launch_browser] Begin create browser context ..."
        )
        
        # 设置Chrome路径（如果配置了的话）
        launch_options = {
            "headless": headless,
            "proxy": playwright_proxy,
        }
        
        if config.CUSTOM_BROWSER_PATH:
            launch_options["executable_path"] = config.CUSTOM_BROWSER_PATH
            utils.logger.info(f"[ZhihuCrawler.launch_browser] 使用自定义浏览器路径: {config.CUSTOM_BROWSER_PATH}")
        
        if config.SAVE_LOGIN_STATE:
            # feat issue #14
            # we will save login state to avoid login every time
            user_data_dir = os.path.join(
                os.getcwd(), "browser_data", config.USER_DATA_DIR % config.PLATFORM
            )  # type: ignore
            browser_context = await chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                accept_downloads=True,
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent,
                **launch_options
            )
            return browser_context
        else:
            browser = await chromium.launch(**launch_options)  # type: ignore
            browser_context = await browser.new_context(
                viewport={"width": 1920, "height": 1080}, user_agent=user_agent
            )
            return browser_context

    async def launch_browser_with_cdp(
        self,
        playwright: Playwright,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        """
        使用CDP模式启动浏览器
        """
        try:
            self.cdp_manager = CDPBrowserManager()
            browser_context = await self.cdp_manager.launch_and_connect(
                playwright=playwright,
                playwright_proxy=playwright_proxy,
                user_agent=user_agent,
                headless=headless,
            )

            # 显示浏览器信息
            browser_info = await self.cdp_manager.get_browser_info()
            utils.logger.info(f"[ZhihuCrawler] CDP浏览器信息: {browser_info}")

            return browser_context

        except Exception as e:
            utils.logger.error(f"[ZhihuCrawler] CDP模式启动失败，回退到标准模式: {e}")
            # 确保清理CDP资源
            if self.cdp_manager:
                await self.cdp_manager.cleanup()
                self.cdp_manager = None
            # 回退到标准模式
            chromium = playwright.chromium
            return await self.launch_browser(
                chromium, playwright_proxy, user_agent, headless
            )

    async def close(self):
        """Close browser context"""
        try:
            # 关闭页面
            if hasattr(self, 'context_page') and self.context_page:
                await self.context_page.close()
                utils.logger.info("[ZhihuCrawler.close] Context page closed")
            
            # 如果使用CDP模式，需要特殊处理
            if self.cdp_manager:
                await self.cdp_manager.cleanup()
                self.cdp_manager = None
                utils.logger.info("[ZhihuCrawler.close] CDP manager cleaned up")
            else:
                # 关闭浏览器上下文
                if hasattr(self, 'browser_context') and self.browser_context:
                    await self.browser_context.close()
                    utils.logger.info("[ZhihuCrawler.close] Browser context closed")
        except Exception as e:
            utils.logger.error(f"[ZhihuCrawler.close] Error during cleanup: {e}")
        finally:
            utils.logger.info("[ZhihuCrawler.close] Browser cleanup completed")
