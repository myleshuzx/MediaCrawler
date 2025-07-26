# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。


import asyncio
import signal
import sys
from typing import Optional

import cmd_arg
import config
import db
from base.base_crawler import AbstractCrawler
from media_platform.bilibili import BilibiliCrawler
from media_platform.douyin import DouYinCrawler
from media_platform.kuaishou import KuaishouCrawler
from media_platform.tieba import TieBaCrawler
from media_platform.weibo import WeiboCrawler
from media_platform.xhs import XiaoHongShuCrawler
from media_platform.zhihu import ZhihuCrawler
import tools.utils as utils


class CrawlerFactory:
    CRAWLERS = {
        "xhs": XiaoHongShuCrawler,
        "dy": DouYinCrawler,
        "ks": KuaishouCrawler,
        "bili": BilibiliCrawler,
        "wb": WeiboCrawler,
        "tieba": TieBaCrawler,
        "zhihu": ZhihuCrawler,
    }

    @staticmethod
    def create_crawler(platform: str) -> AbstractCrawler:
        crawler_class = CrawlerFactory.CRAWLERS.get(platform)
        if not crawler_class:
            raise ValueError(
                "Invalid Media Platform Currently only supported xhs or dy or ks or bili ..."
            )
        return crawler_class()


crawler: Optional[AbstractCrawler] = None


async def main():
    # Init crawler
    global crawler

    # parse cmd
    await cmd_arg.parse_cmd()

    # init db
    if config.SAVE_DATA_OPTION in ["db", "sqlite"]:
        await db.init_db()

    crawler = CrawlerFactory.create_crawler(platform=config.PLATFORM)
    await crawler.start()


def cleanup():
    """Clean up resources when program exits"""
    utils.logger.info("[main.cleanup] Starting cleanup process...")
    if crawler:
        try:
            asyncio.run(crawler.close())
            utils.logger.info("[main.cleanup] Crawler closed successfully")
        except Exception as e:
            utils.logger.error(f"[main.cleanup] Error closing crawler: {e}")
    
    if config.SAVE_DATA_OPTION in ["db", "sqlite"]:
        try:
            asyncio.run(db.close())
            utils.logger.info("[main.cleanup] Database closed successfully")
        except Exception as e:
            utils.logger.error(f"[main.cleanup] Error closing database: {e}")
    
    utils.logger.info("[main.cleanup] Cleanup completed")


def signal_handler(signum, frame):
    """Handle interrupt signals"""
    utils.logger.info(f"[main.signal_handler] Received signal {signum}, initiating cleanup...")
    cleanup()
    sys.exit(0)


if __name__ == "__main__":
    # 注册信号处理器，确保程序被中断时也能正确清理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        asyncio.get_event_loop().run_until_complete(main())
    except KeyboardInterrupt:
        utils.logger.info("[main] Program interrupted by user")
    except Exception as e:
        utils.logger.error(f"[main] Unexpected error: {e}")
    finally:
        cleanup()
