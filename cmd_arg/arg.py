# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：  
# 1. 不得用于任何商业用途。  
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。  
# 3. 不得进行大规模爬取或对平台造成运营干扰。  
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。   
# 5. 不得用于任何非法或不当的用途。
#   
# 详细许可条款请参阅项目根目录下的LICENSE文件。  
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。  


import argparse

import config
from tools.utils import str2bool
import tools.utils as utils


async def parse_cmd():
    # 读取command arg
    parser = argparse.ArgumentParser(description='Media crawler program.')
    parser.add_argument('--platform', type=str, help='Media platform select (xhs | dy | ks | bili | wb | tieba | zhihu)',
                        choices=["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"], default=config.PLATFORM)
    parser.add_argument('--lt', type=str, help='Login type (qrcode | phone | cookie)',
                        choices=["qrcode", "phone", "cookie"], default=config.LOGIN_TYPE)
    parser.add_argument('--type', type=str, help='crawler type (search | detail | creator | question)',
                        choices=["search", "detail", "creator", "question"], default=config.CRAWLER_TYPE)
    parser.add_argument('--start', type=int,
                        help='number of start page', default=config.START_PAGE)
    parser.add_argument('--keywords', type=str,
                        help='please input keywords', default=config.KEYWORDS)
    parser.add_argument('--max_notes', type=int,
                        help='maximum number of notes to crawl', default=config.CRAWLER_MAX_NOTES_COUNT)
    parser.add_argument('--get_comment', type=str2bool,
                        help='''whether to crawl level one comment, supported values case insensitive ('yes', 'true', 't', 'y', '1', 'no', 'false', 'f', 'n', '0')''', default=config.ENABLE_GET_COMMENTS)
    parser.add_argument('--get_sub_comment', type=str2bool,
                        help=''''whether to crawl level two comment, supported values case insensitive ('yes', 'true', 't', 'y', '1', 'no', 'false', 'f', 'n', '0')''', default=config.ENABLE_GET_SUB_COMMENTS)
    parser.add_argument('--save_data_option', type=str,
                        help='where to save the data (csv or db or json or sqlite)', choices=['csv', 'db', 'json', 'sqlite'], default=config.SAVE_DATA_OPTION)
    parser.add_argument('--cookies', type=str,
                        help='cookies used for cookie login type', default=config.COOKIES)
    parser.add_argument('--QURL', type=str,
                        help='(zhihu only) question URL(s) to crawl, overrides ZHIHU_QUESTION_LIST. Multiple URLs can be separated by commas', default=None)
    parser.add_argument('--cdp', type=str2bool,
                        help='Enable CDP (Chrome DevTools Protocol) mode for better anti-detection', default=config.ENABLE_CDP_MODE)
    parser.add_argument('--cdp_headless', type=str2bool,
                        help='Enable headless mode when using CDP', default=config.CDP_HEADLESS)
    parser.add_argument('--headless', type=str2bool,
                        help='Enable headless mode for standard browser mode', default=config.HEADLESS)

    args = parser.parse_args()

    # override config
    config.PLATFORM = args.platform
    config.LOGIN_TYPE = args.lt
    config.CRAWLER_TYPE = args.type
    config.START_PAGE = args.start
    config.KEYWORDS = args.keywords
    config.CRAWLER_MAX_NOTES_COUNT = args.max_notes
    config.ENABLE_GET_COMMENTS = args.get_comment
    config.ENABLE_GET_SUB_COMMENTS = args.get_sub_comment
    config.SAVE_DATA_OPTION = args.save_data_option
    config.COOKIES = args.cookies
    config.ENABLE_CDP_MODE = args.cdp
    config.CDP_HEADLESS = args.cdp_headless
    config.HEADLESS = args.headless
    
    # 记录重要参数设置
    utils.logger.info(f"[parse_cmd] CRAWLER_MAX_NOTES_COUNT set to {config.CRAWLER_MAX_NOTES_COUNT}")
    utils.logger.info(f"[parse_cmd] PLATFORM: {config.PLATFORM}, CRAWLER_TYPE: {config.CRAWLER_TYPE}")
    utils.logger.info(f"[parse_cmd] ENABLE_GET_COMMENTS: {config.ENABLE_GET_COMMENTS}")
    utils.logger.info(f"[parse_cmd] Browser mode - CDP: {config.ENABLE_CDP_MODE}, CDP_HEADLESS: {config.CDP_HEADLESS}, HEADLESS: {config.HEADLESS}")
    
    # 处理zhihu平台特定的--QURL参数
    if config.PLATFORM == "zhihu" and args.QURL is not None:
        # 支持逗号分隔的多个URL
        question_urls = [url.strip() for url in args.QURL.split(',') if url.strip()]
        
        # 验证URL格式
        valid_urls = []
        for url in question_urls:
            if "zhihu.com/question/" in url:
                valid_urls.append(url)
                utils.logger.info(f"[parse_cmd] Valid zhihu question URL: {url}")
            else:
                utils.logger.warning(f"[parse_cmd] Invalid zhihu question URL format (ignored): {url}")
        
        if valid_urls:
            config.ZHIHU_QUESTION_LIST = valid_urls
            utils.logger.info(f"[parse_cmd] ZHIHU_QUESTION_LIST overridden with {len(valid_urls)} valid URL(s)")
        else:
            utils.logger.error(f"[parse_cmd] No valid zhihu question URLs found in --QURL parameter")
            
    elif args.QURL is not None and config.PLATFORM != "zhihu":
        utils.logger.warning(f"[parse_cmd] --QURL parameter ignored for platform '{config.PLATFORM}' (only valid for zhihu)")
