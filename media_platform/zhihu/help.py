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
import json
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import execjs
from parsel import Selector

from constant import zhihu as zhihu_constant
from model.m_zhihu import ZhihuComment, ZhihuContent, ZhihuCreator, ZhihuQuestionTopic
from tools import utils
from tools.crawler_util import extract_text_from_html

ZHIHU_SGIN_JS = None


def sign(url: str, cookies: str) -> Dict:
    """
    zhihu sign algorithm
    Args:
        url: request url with query string
        cookies: request cookies with d_c0 key

    Returns:

    """
    global ZHIHU_SGIN_JS
    if not ZHIHU_SGIN_JS:
        with open("libs/zhihu.js", mode="r", encoding="utf-8-sig") as f:
            ZHIHU_SGIN_JS = execjs.compile(f.read())

    return ZHIHU_SGIN_JS.call("get_sign", url, cookies)


class ZhihuExtractor:
    def __init__(self):
        pass

    def extract_contents_from_search(self, json_data: Dict) -> List[ZhihuContent]:
        """
        extract zhihu contents
        Args:
            json_data: zhihu json data

        Returns:

        """
        if not json_data:
            return []

        search_result: List[Dict] = json_data.get("data", [])
        search_result = [s_item for s_item in search_result if s_item.get("type") in ['search_result', 'zvideo']]
        return self._extract_content_list([sr_item.get("object") for sr_item in search_result if sr_item.get("object")])


    def _extract_content_list(self, content_list: List[Dict]) -> List[ZhihuContent]:
        """
        extract zhihu content list
        Args:
            content_list:

        Returns:

        """
        if not content_list:
            return []

        res: List[ZhihuContent] = []
        for content in content_list:
            if content.get("type") == zhihu_constant.ANSWER_NAME:
                res.append(self._extract_answer_content(content))
            elif content.get("type") == zhihu_constant.ARTICLE_NAME:
                res.append(self._extract_article_content(content))
            elif content.get("type") == zhihu_constant.VIDEO_NAME:
                res.append(self._extract_zvideo_content(content))
            else:
                continue
        return res

    def _extract_answer_content(self, answer: Dict) -> ZhihuContent:
        """
        extract zhihu answer content
        Args:
            answer: zhihu answer

        Returns:
        """
        res = ZhihuContent()
        res.content_id = answer.get("id")
        res.content_type = answer.get("type")
        res.content_text = extract_text_from_html(answer.get("content", ""))
        res.question_id = answer.get("question").get("id")
        res.content_url = f"{zhihu_constant.ZHIHU_URL}/question/{res.question_id}/answer/{res.content_id}"
        res.title = extract_text_from_html(answer.get("title", ""))
        res.desc = extract_text_from_html(answer.get("description", "") or answer.get("excerpt", ""))
        res.created_time = answer.get("created_time")
        res.updated_time = answer.get("updated_time")
        res.voteup_count = answer.get("voteup_count", 0)
        res.comment_count = answer.get("comment_count", 0)

        # extract author info
        author_info = self._extract_content_or_comment_author(answer.get("author"))
        res.user_id = author_info.user_id
        res.user_link = author_info.user_link
        res.user_nickname = author_info.user_nickname
        res.user_avatar = author_info.user_avatar
        res.user_url_token = author_info.url_token
        return res

    def _extract_article_content(self, article: Dict) -> ZhihuContent:
        """
        extract zhihu article content
        Args:
            article: zhihu article

        Returns:

        """
        res = ZhihuContent()
        res.content_id = article.get("id")
        res.content_type = article.get("type")
        res.content_text = extract_text_from_html(article.get("content"))
        res.content_url = f"{zhihu_constant.ZHIHU_ZHUANLAN_URL}/p/{res.content_id}"
        res.title = extract_text_from_html(article.get("title"))
        res.desc = extract_text_from_html(article.get("excerpt"))
        res.created_time = article.get("created_time", 0) or article.get("created", 0)
        res.updated_time = article.get("updated_time", 0) or article.get("updated", 0)
        res.voteup_count = article.get("voteup_count", 0)
        res.comment_count = article.get("comment_count", 0)

        # extract author info
        author_info = self._extract_content_or_comment_author(article.get("author"))
        res.user_id = author_info.user_id
        res.user_link = author_info.user_link
        res.user_nickname = author_info.user_nickname
        res.user_avatar = author_info.user_avatar
        res.user_url_token = author_info.url_token
        return res

    def _extract_zvideo_content(self, zvideo: Dict) -> ZhihuContent:
        """
        extract zhihu zvideo content
        Args:
            zvideo:

        Returns:

        """
        res = ZhihuContent()

        if "video" in zvideo and isinstance(zvideo.get("video"), dict): # 说明是从创作者主页的视频列表接口来的
            res.content_url = f"{zhihu_constant.ZHIHU_URL}/zvideo/{res.content_id}"
            res.created_time = zvideo.get("published_at")
            res.updated_time = zvideo.get("updated_at")
        else:
            res.content_url = zvideo.get("video_url")
            res.created_time = zvideo.get("created_at")
        res.content_id = zvideo.get("id")
        res.content_type = zvideo.get("type")
        res.title = extract_text_from_html(zvideo.get("title"))
        res.desc = extract_text_from_html(zvideo.get("description"))
        res.voteup_count = zvideo.get("voteup_count")
        res.comment_count = zvideo.get("comment_count")

        # extract author info
        author_info = self._extract_content_or_comment_author(zvideo.get("author"))
        res.user_id = author_info.user_id
        res.user_link = author_info.user_link
        res.user_nickname = author_info.user_nickname
        res.user_avatar = author_info.user_avatar
        res.user_url_token = author_info.url_token
        return res

    @staticmethod
    def _extract_content_or_comment_author(author: Dict) -> ZhihuCreator:
        """
        extract zhihu author
        Args:
            author:

        Returns:

        """
        res = ZhihuCreator()
        try:
            if not author:
                return res
            if not author.get("id"):
                author = author.get("member")
            res.user_id = author.get("id")
            res.user_link = f"{zhihu_constant.ZHIHU_URL}/people/{author.get('url_token')}"
            res.user_nickname = author.get("name")
            res.user_avatar = author.get("avatar_url")
            res.url_token = author.get("url_token")
            
        except Exception as e :
            utils.logger.warning(
                f"[ZhihuExtractor._extract_content_or_comment_author] User Maybe Blocked. {e}"
            )
        return res

    def extract_comments(self, page_content: ZhihuContent, comments: List[Dict]) -> List[ZhihuComment]:
        """
        extract zhihu comments
        Args:
            page_content: zhihu content object
            comments: zhihu comments

        Returns:

        """
        if not comments:
            return []
        res: List[ZhihuComment] = []
        for comment in comments:
            if comment.get("type") != "comment":
                continue
            res.append(self._extract_comment(page_content, comment))
        return res

    def _extract_comment(self, page_content: ZhihuContent, comment: Dict) -> ZhihuComment:
        """
        extract zhihu comment
        Args:
            page_content: comment with content object
            comment: zhihu comment

        Returns:

        """
        res = ZhihuComment()
        res.comment_id = str(comment.get("id", ""))
        res.parent_comment_id = comment.get("reply_comment_id")
        res.content = extract_text_from_html(comment.get("content"))
        res.publish_time = comment.get("created_time")
        res.ip_location = self._extract_comment_ip_location(comment.get("comment_tag", []))
        res.sub_comment_count = comment.get("child_comment_count")
        res.like_count = comment.get("like_count") if comment.get("like_count") else 0
        res.dislike_count = comment.get("dislike_count") if comment.get("dislike_count") else 0
        res.content_id = page_content.content_id
        res.content_type = page_content.content_type

        # extract author info
        author_info = self._extract_content_or_comment_author(comment.get("author"))
        res.user_id = author_info.user_id
        res.user_link = author_info.user_link
        res.user_nickname = author_info.user_nickname
        res.user_avatar = author_info.user_avatar
        return res

    @staticmethod
    def _extract_comment_ip_location(comment_tags: List[Dict]) -> str:
        """
        extract comment ip location
        Args:
            comment_tags:

        Returns:

        """
        if not comment_tags:
            return ""

        for ct in comment_tags:
            if ct.get("type") == "ip_info":
                return ct.get("text")

        return ""

    @staticmethod
    def extract_offset(paging_info: Dict) -> str:
        """
        extract offset
        Args:
            paging_info:

        Returns:

        """
        # https://www.zhihu.com/api/v4/comment_v5/zvideos/1424368906836807681/root_comment?limit=10&offset=456770961_10125996085_0&order_by=score
        next_url = paging_info.get("next")
        if not next_url:
            return ""

        parsed_url = urlparse(next_url)
        query_params = parse_qs(parsed_url.query)
        offset = query_params.get('offset', [""])[0]
        return offset

    @staticmethod
    def _foramt_gender_text(gender: int) -> str:
        """
        format gender text
        Args:
            gender:

        Returns:

        """
        if gender == 1:
            return "男"
        elif gender == 0:
            return "女"
        else:
            return "未知"


    def extract_creator(self, user_url_token: str, html_content: str) -> Optional[ZhihuCreator]:
        """
        extract zhihu creator
        Args:
            user_url_token : zhihu creator url token
            html_content: zhihu creator html content

        Returns:

        """
        if not html_content:
            return None

        js_init_data = Selector(text=html_content).xpath("//script[@id='js-initialData']/text()").get(default="").strip()
        if not js_init_data:
            return None

        js_init_data_dict: Dict = json.loads(js_init_data)
        users_info: Dict = js_init_data_dict.get("initialState", {}).get("entities", {}).get("users", {})
        if not users_info:
            return None

        creator_info: Dict = users_info.get(user_url_token)
        if not creator_info:
            return None

        res = ZhihuCreator()
        res.user_id = creator_info.get("id")
        res.user_link = f"{zhihu_constant.ZHIHU_URL}/people/{user_url_token}"
        res.user_nickname = creator_info.get("name")
        res.user_avatar = creator_info.get("avatarUrl")
        res.url_token = creator_info.get("urlToken") or user_url_token
        res.gender = self._foramt_gender_text(creator_info.get("gender"))
        res.ip_location = creator_info.get("ipInfo")
        res.follows = creator_info.get("followingCount")
        res.fans = creator_info.get("followerCount")
        res.anwser_count = creator_info.get("answerCount")
        res.video_count = creator_info.get("zvideoCount")
        res.question_count = creator_info.get("questionCount")
        res.article_count = creator_info.get("articlesCount")
        res.column_count = creator_info.get("columnsCount")
        res.get_voteup_count = creator_info.get("voteupCount")
        return res


    def extract_content_list_from_creator(self, anwser_list: List[Dict]) -> List[ZhihuContent]:
        """
        extract content list from creator
        Args:
            anwser_list:

        Returns:

        """
        if not anwser_list:
            return []

        return self._extract_content_list(anwser_list)




    def extract_answer_content_from_html(self, html_content: str) -> Optional[ZhihuContent]:
        """
        extract zhihu answer content from html
        Args:
            html_content:

        Returns:

        """
        js_init_data: str = Selector(text=html_content).xpath("//script[@id='js-initialData']/text()").get(default="")
        if not js_init_data:
            return None
        json_data: Dict = json.loads(js_init_data)
        answer_info: Dict = json_data.get("initialState", {}).get("entities", {}).get("answers", {})
        if not answer_info:
            return None

        answer_content = self._extract_answer_content(answer_info.get(list(answer_info.keys())[0]))
        
        # 如果从JSON中获取的voteup_count为0，尝试从HTML元素中提取
        if answer_content and answer_content.voteup_count == 0:
            voteup_count = self._extract_voteup_count_from_html(html_content)
            if voteup_count > 0:
                answer_content.voteup_count = voteup_count
        
        # 如果从JSON中获取的comment_count为0，尝试从HTML元素中提取
        if answer_content and answer_content.comment_count == 0:
            comment_count = self._extract_comment_count_from_html(html_content)
            if comment_count > 0:
                answer_content.comment_count = comment_count
                
        return answer_content

    def _extract_voteup_count_from_html(self, html_content: str) -> int:
        """
        从HTML元素中提取赞同数的备用方法
        Args:
            html_content: HTML内容

        Returns:
            int: 赞同数，提取失败返回0
        """
        try:
            selector = Selector(text=html_content)
            
            # 方法1: 尝试从投票按钮的aria-label属性中提取
            # 如: <button aria-label="赞同 897 " ...>
            vote_button = selector.xpath('//button[contains(@class, "VoteButton")]/@aria-label').get()
            if vote_button:
                import re
                match = re.search(r'赞同\s*(\d+)', vote_button)
                if match:
                    return int(match.group(1))
            
            # 方法2: 尝试从按钮文本中提取
            # 如: <button>赞同 897</button>
            vote_text = selector.xpath('//button[contains(@class, "VoteButton")]//text()').getall()
            if vote_text:
                full_text = ''.join(vote_text)
                import re
                match = re.search(r'赞同\s*(\d+)', full_text)
                if match:
                    return int(match.group(1))
            
            # 方法3: 尝试从其他可能的选择器中提取
            selectors_to_try = [
                '//span[contains(text(), "赞同")]/following-sibling::text()',
                '//span[contains(text(), "赞同")]/text()',
                '//*[contains(@class, "vote") or contains(@class, "Vote")]/text()',
            ]
            
            for selector_xpath in selectors_to_try:
                texts = selector.xpath(selector_xpath).getall()
                for text in texts:
                    import re
                    match = re.search(r'(\d+)', text.strip())
                    if match and int(match.group(1)) > 0:
                        return int(match.group(1))
            
            return 0
            
        except Exception as e:
            utils.logger.warning(f"[ZhihuExtractor._extract_voteup_count_from_html] 提取赞同数失败: {e}")
            return 0

    def _extract_comment_count_from_html(self, html_content: str) -> int:
        """
        从HTML元素中提取评论数的备用方法
        Args:
            html_content: HTML内容

        Returns:
            int: 评论数，提取失败返回0
        """
        try:
            selector = Selector(text=html_content)
            import re
            
            # 方法1: 从评论按钮中提取，格式如 "17 条评论"
            comment_selectors = [
                '//button[contains(@class, "ContentItem-action")]//text()',
                '//button[contains(@class, "Button")]//text()',
                '//*[contains(@class, "Comment") or contains(@class, "comment")]//text()',
                '//span[contains(text(), "条评论")]//text()',
                '//span[contains(text(), "评论")]//text()',
            ]
            
            for selector_xpath in comment_selectors:
                texts = selector.xpath(selector_xpath).getall()
                for text in texts:
                    text = text.strip()
                    # 匹配 "17 条评论" 格式
                    match = re.search(r'(\d+)\s*条评论', text)
                    if match:
                        return int(match.group(1))
                    # 匹配纯数字后跟评论的格式
                    match = re.search(r'(\d+)\s*评论', text)
                    if match:
                        return int(match.group(1))
            
            # 方法2: 从SVG图标附近的文本提取
            # 查找包含评论图标的按钮
            comment_buttons = selector.xpath('//button[.//svg[contains(@class, "Zi--Comment")]]//text()').getall()
            for text in comment_buttons:
                text = text.strip()
                match = re.search(r'(\d+)\s*条评论', text)
                if match:
                    return int(match.group(1))
                match = re.search(r'(\d+)\s*评论', text)
                if match:
                    return int(match.group(1))
            
            # 方法3: 从按钮的完整文本中提取
            full_button_texts = selector.xpath('//button//text()').getall()
            full_text = ''.join(full_button_texts)
            match = re.search(r'(\d+)\s*条评论', full_text)
            if match:
                return int(match.group(1))
            
            return 0
            
        except Exception as e:
            utils.logger.warning(f"[ZhihuExtractor._extract_comment_count_from_html] 提取评论数失败: {e}")
            return 0

    def extract_article_content_from_html(self, html_content: str) -> Optional[ZhihuContent]:
        """
        extract zhihu article content from html
        Args:
            html_content:

        Returns:

        """
        js_init_data: str = Selector(text=html_content).xpath("//script[@id='js-initialData']/text()").get(default="")
        if not js_init_data:
            return None
        json_data: Dict = json.loads(js_init_data)
        article_info: Dict = json_data.get("initialState", {}).get("entities", {}).get("articles", {})
        if not article_info:
            return None

        article_content = self._extract_article_content(article_info.get(list(article_info.keys())[0]))
        
        # 如果从JSON中获取的voteup_count为0，尝试从HTML元素中提取
        if article_content and article_content.voteup_count == 0:
            voteup_count = self._extract_voteup_count_from_html(html_content)
            if voteup_count > 0:
                article_content.voteup_count = voteup_count
        
        # 如果从JSON中获取的comment_count为0，尝试从HTML元素中提取
        if article_content and article_content.comment_count == 0:
            comment_count = self._extract_comment_count_from_html(html_content)
            if comment_count > 0:
                article_content.comment_count = comment_count
                
        return article_content

    def extract_zvideo_content_from_html(self, html_content: str) -> Optional[ZhihuContent]:
        """
        extract zhihu zvideo content from html
        Args:
            html_content:

        Returns:

        """
        js_init_data: str = Selector(text=html_content).xpath("//script[@id='js-initialData']/text()").get(default="")
        if not js_init_data:
            return None
        json_data: Dict = json.loads(js_init_data)
        zvideo_info: Dict = json_data.get("initialState", {}).get("entities", {}).get("zvideos", {})
        users: Dict = json_data.get("initialState", {}).get("entities", {}).get("users", {})
        if not zvideo_info:
            return None

        # handler user info and video info
        video_detail_info: Dict = zvideo_info.get(list(zvideo_info.keys())[0])
        if not video_detail_info:
            return None
        if isinstance(video_detail_info.get("author"), str):
            author_name: str = video_detail_info.get("author")
            video_detail_info["author"] = users.get(author_name)

        zvideo_content = self._extract_zvideo_content(video_detail_info)
        
        # 如果从JSON中获取的voteup_count为0，尝试从HTML元素中提取
        if zvideo_content and zvideo_content.voteup_count == 0:
            voteup_count = self._extract_voteup_count_from_html(html_content)
            if voteup_count > 0:
                zvideo_content.voteup_count = voteup_count
        
        # 如果从JSON中获取的comment_count为0，尝试从HTML元素中提取
        if zvideo_content and zvideo_content.comment_count == 0:
            comment_count = self._extract_comment_count_from_html(html_content)
            if comment_count > 0:
                zvideo_content.comment_count = comment_count
                
        return zvideo_content


    def extract_question_topic_from_html(self, html_content: str, question_url: str) -> Optional[ZhihuQuestionTopic]:
        """
        从HTML中提取问题主题信息
        Args:
            html_content: HTML内容
            question_url: 问题链接

        Returns:
            ZhihuQuestionTopic: 问题主题信息
        """
        try:
            import time
            selector = Selector(text=html_content)
            
            # 提取问题ID
            question_id = ""
            if "/question/" in question_url:
                question_id = question_url.split("/question/")[-1].split("/")[0]
            
            # 提取问题标题
            title_selectors = [
                '//h1[@class="QuestionHeader-title"]//text()',
                '//h1[contains(@class, "QuestionHeader-title")]//text()',
                '//div[contains(@class, "QuestionHeader-main")]//h1//text()',
                '//title/text()'
            ]
            
            title = ""
            for title_selector in title_selectors:
                title_texts = selector.xpath(title_selector).getall()
                if title_texts:
                    title = ''.join(title_texts).strip()
                    # 清理标题，移除知乎相关后缀
                    if " - 知乎" in title:
                        title = title.split(" - 知乎")[0]
                    break
            
            # 提取问题详情 - 需要处理"显示全部"的情况
            detail = self._extract_question_detail(selector)
            
            # 提取统计数据
            answer_count = self._extract_count_from_text(selector, ["个回答", "个答案"])
            follower_count = self._extract_count_from_text(selector, ["人关注", "关注者"])
            visit_count = self._extract_count_from_text(selector, ["次浏览", "被浏览"])
            
            # 提取话题标签
            topics = self._extract_topics(selector)
            
            # 提取创建者信息
            author_info = self._extract_question_author(selector)
            
            # 创建问题主题对象
            question_topic = ZhihuQuestionTopic(
                question_id=question_id,
                question_url=question_url,
                title=title,
                detail=detail,
                answer_count=answer_count,
                follower_count=follower_count,
                visit_count=visit_count,
                topics=topics,
                author_id=author_info.get("author_id", ""),
                author_name=author_info.get("author_name", ""),
                author_url_token=author_info.get("author_url_token", ""),
                crawl_time=int(time.time())
            )
            
            return question_topic
            
        except Exception as e:
            utils.logger.error(f"[ZhihuExtractor.extract_question_topic_from_html] 提取问题主题失败: {e}")
            return None

    def _extract_question_detail(self, selector: Selector) -> str:
        """
        提取问题详情，从QuestionRichText QuestionRichText--expandable中获取
        """
        # 首先尝试获取完整的HTML内容
        detail_html_selectors = [
            '//div[contains(@class, "QuestionRichText") and contains(@class, "QuestionRichText--expandable")]',
            '//div[@class="QuestionRichText QuestionRichText--expandable"]',
            '//div[contains(@class, "QuestionRichText")]',
            '//span[@id="content"]'
        ]
        
        detail = ""
        
        # 首先尝试获取HTML内容并提取文本
        for i, html_selector in enumerate(detail_html_selectors):
            elements = selector.xpath(html_selector)
            if elements:
                utils.logger.info(f"[ZhihuExtractor._extract_question_detail] Found element with selector {i}: {html_selector}")
                
                # 获取该元素下的所有文本，但排除按钮等不需要的内容
                text_parts = []
                
                # 获取所有文本节点，但跳过按钮内的文本
                all_texts = elements[0].xpath('.//text()[not(ancestor::button)]').getall()
                
                for text in all_texts:
                    text = text.strip()
                    if text and text not in ['显示全部', '展开', '收起', '编辑', '​', '︎']:
                        text_parts.append(text)
                
                if text_parts:
                    detail = ' '.join(text_parts)
                    # 清理多余的空格
                    import re
                    detail = re.sub(r'\s+', ' ', detail).strip()
                    if detail:
                        utils.logger.info(f"[ZhihuExtractor._extract_question_detail] Extracted detail length: {len(detail)}")
                        utils.logger.info(f"[ZhihuExtractor._extract_question_detail] Detail preview: {detail[:200]}...")
                        break
        
        # 如果上面的方法没有获取到内容，使用备用方法
        if not detail:
            utils.logger.warning(f"[ZhihuExtractor._extract_question_detail] No detail found with primary selectors, trying backup")
            backup_selectors = [
                '//div[contains(@class, "QuestionHeader-detail")]//text()',
                '//div[contains(@class, "RichText")]//text()'
            ]
            
            for backup_selector in backup_selectors:
                detail_texts = selector.xpath(backup_selector).getall()
                if detail_texts:
                    filtered_texts = [text.strip() for text in detail_texts 
                                    if text.strip() and text.strip() not in ['显示全部', '展开', '收起', '编辑', '​']]
                    if filtered_texts:
                        detail = ' '.join(filtered_texts)
                        utils.logger.info(f"[ZhihuExtractor._extract_question_detail] Found detail with backup selector: {backup_selector}")
                        break
        
        return detail

    def _extract_count_from_text(self, selector: Selector, keywords: list) -> int:
        """
        从文本中提取计数信息
        """
        import re
        for keyword in keywords:
            xpath = f'//*[contains(text(), "{keyword}")]//text()'
            texts = selector.xpath(xpath).getall()
            for text in texts:
                match = re.search(r'(\d+(?:,\d+)*)\s*' + re.escape(keyword), text)
                if match:
                    return int(match.group(1).replace(',', ''))
        return 0

    def _extract_topics(self, selector: Selector) -> str:
        """
        提取问题话题标签
        """
        topic_selectors = [
            '//div[contains(@class, "QuestionHeader-topics")]//a//text()',
            '//div[contains(@class, "QuestionTopic")]//a//text()',
            '//*[contains(@class, "Tag")]//text()'
        ]
        
        topics = []
        for topic_selector in topic_selectors:
            topic_texts = selector.xpath(topic_selector).getall()
            topics.extend([text.strip() for text in topic_texts if text.strip()])
        
        return ', '.join(list(set(topics)))  # 去重并合并

    def _extract_question_author(self, selector: Selector) -> dict:
        """
        提取问题创建者信息
        """
        author_info = {
            "author_id": "",
            "author_name": "",
            "author_url_token": ""
        }
        
        # 提取作者链接和信息
        author_links = selector.xpath('//div[contains(@class, "QuestionHeader")]//a[contains(@href, "/people/")]/@href').getall()
        if author_links:
            author_link = author_links[0]
            if "/people/" in author_link:
                author_info["author_url_token"] = author_link.split("/people/")[-1]
        
        # 提取作者姓名
        author_names = selector.xpath('//div[contains(@class, "QuestionHeader")]//a[contains(@href, "/people/")]//text()').getall()
        if author_names:
            author_info["author_name"] = author_names[0].strip()
        
        return author_info


def judge_zhihu_url(note_detail_url: str) -> str:
    """
    judge zhihu url type
    Args:
        note_detail_url:
            eg1: https://www.zhihu.com/question/123456789/answer/123456789 # answer
            eg2: https://www.zhihu.com/p/123456789 # article
            eg3: https://www.zhihu.com/zvideo/123456789 # zvideo

    Returns:

    """
    if "/answer/" in note_detail_url:
        return zhihu_constant.ANSWER_NAME
    elif "/p/" in note_detail_url:
        return zhihu_constant.ARTICLE_NAME
    elif "/zvideo/" in note_detail_url:
        return zhihu_constant.VIDEO_NAME
    else:
        return ""
