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
# @Author  : relakkes@gmail.com
# @Time    : 2024/1/14 19:34
# @Desc    : B站存储实现类
import asyncio
import csv
import json
import os
import pathlib
from typing import Dict

import aiofiles

import config
from base.base_crawler import AbstractStore
from tools import utils, words
from var import crawler_type_var


def calculate_number_of_files(file_store_path: str) -> int:
    """计算数据保存文件的前部分排序数字，支持每次运行代码不写到同一个文件中
    Args:
        file_store_path;
    Returns:
        file nums
    """
    if not os.path.exists(file_store_path):
        return 1
    try:
        return max([int(file_name.split("_")[0])for file_name in os.listdir(file_store_path)])+1
    except ValueError:
        return 1

class BiliCsvStoreImplement(AbstractStore):
    csv_store_path: str = "data/bilibili"
    file_count:int=calculate_number_of_files(csv_store_path)
    def make_save_file_name(self, store_type: str) -> str:
        """
        make save file name by store type
        Args:
            store_type: contents or comments

        Returns: eg: data/bilibili/search_comments_20240114.csv ...

        """
        return f"{self.csv_store_path}/{self.file_count}_{crawler_type_var.get()}_{store_type}_{utils.get_current_date()}.csv"

    async def save_data_to_csv(self, save_item: Dict, store_type: str):
        """
        Below is a simple way to save it in CSV format.
        Args:
            save_item:  save content dict info
            store_type: Save type contains content and comments（contents | comments）

        Returns: no returns

        """
        pathlib.Path(self.csv_store_path).mkdir(parents=True, exist_ok=True)
        save_file_name = self.make_save_file_name(store_type=store_type)
        async with aiofiles.open(save_file_name, mode='a+', encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if await f.tell() == 0:
                await writer.writerow(save_item.keys())
            await writer.writerow(save_item.values())

    async def store_content(self, content_item: Dict):
        """
        Bilibili content CSV storage implementation
        Args:
            content_item: note item dict

        Returns:

        """
        await self.save_data_to_csv(save_item=content_item, store_type="contents")

    async def store_comment(self, comment_item: Dict):
        """
        Bilibili comment CSV storage implementation
        Args:
            comment_item: comment item dict

        Returns:

        """
        await self.save_data_to_csv(save_item=comment_item, store_type="comments")

    async def store_creator(self, creator: Dict):
        """
        Bilibili creator CSV storage implementation
        Args:
            creator: creator item dict

        Returns:

        """
        await self.save_data_to_csv(save_item=creator, store_type="creators")

    async def store_contact(self, contact_item: Dict):
        """
        Bilibili contact CSV storage implementation
        Args:
            contact_item: creator's contact item dict

        Returns:

        """

        await self.save_data_to_csv(save_item=contact_item, store_type="contacts")

    async def store_dynamic(self, dynamic_item: Dict):
        """
        Bilibili dynamic CSV storage implementation
        Args:
            dynamic_item: creator's dynamic item dict

        Returns:

        """

        await self.save_data_to_csv(save_item=dynamic_item, store_type="dynamics")


class BiliDbStoreImplement(AbstractStore):
    async def store_content(self, content_item: Dict):
        """
        Bilibili content DB storage implementation
        Args:
            content_item: content item dict

        Returns:

        """

        from .bilibili_store_sql import (add_new_content,
                                         query_content_by_content_id,
                                         update_content_by_content_id)
        video_id = content_item.get("video_id")
        video_detail: Dict = await query_content_by_content_id(content_id=video_id)
        if not video_detail:
            content_item["add_ts"] = utils.get_current_timestamp()
            await add_new_content(content_item)
        else:
            await update_content_by_content_id(video_id, content_item=content_item)

    async def store_comment(self, comment_item: Dict):
        """
        Bilibili content DB storage implementation
        Args:
            comment_item: comment item dict

        Returns:

        """

        from .bilibili_store_sql import (add_new_comment,
                                         query_comment_by_comment_id,
                                         update_comment_by_comment_id)
        comment_id = comment_item.get("comment_id")
        comment_detail: Dict = await query_comment_by_comment_id(comment_id=comment_id)
        if not comment_detail:
            comment_item["add_ts"] = utils.get_current_timestamp()
            await add_new_comment(comment_item)
        else:
            await update_comment_by_comment_id(comment_id, comment_item=comment_item)

    async def store_creator(self, creator: Dict):
        """
        Bilibili creator DB storage implementation
        Args:
            creator: creator item dict

        Returns:

        """

        from .bilibili_store_sql import (add_new_creator,
                                         query_creator_by_creator_id,
                                         update_creator_by_creator_id)
        creator_id = creator.get("user_id")
        creator_detail: Dict = await query_creator_by_creator_id(creator_id=creator_id)
        if not creator_detail:
            creator["add_ts"] = utils.get_current_timestamp()
            await add_new_creator(creator)
        else:
            await update_creator_by_creator_id(creator_id,creator_item=creator)

    async def store_contact(self, contact_item: Dict):
        """
        Bilibili contact DB storage implementation
        Args:
            contact_item: contact item dict

        Returns:

        """

        from .bilibili_store_sql import (add_new_contact,
                                         query_contact_by_up_and_fan,
                                         update_contact_by_id, )

        up_id = contact_item.get("up_id")
        fan_id = contact_item.get("fan_id")
        contact_detail: Dict = await query_contact_by_up_and_fan(up_id=up_id, fan_id=fan_id)
        if not contact_detail:
            contact_item["add_ts"] = utils.get_current_timestamp()
            await add_new_contact(contact_item)
        else:
            key_id = contact_detail.get("id")
            await update_contact_by_id(id=key_id, contact_item=contact_item)

    async def store_dynamic(self, dynamic_item):
        """
        Bilibili dynamic DB storage implementation
        Args:
            dynamic_item: dynamic item dict

        Returns:

        """

        from .bilibili_store_sql import (add_new_dynamic,
                                         query_dynamic_by_dynamic_id,
                                         update_dynamic_by_dynamic_id)

        dynamic_id = dynamic_item.get("dynamic_id")
        dynamic_detail = await query_dynamic_by_dynamic_id(dynamic_id=dynamic_id)
        if not dynamic_detail:
            dynamic_item["add_ts"] = utils.get_current_timestamp()
            await add_new_dynamic(dynamic_item)
        else:
            await update_dynamic_by_dynamic_id(dynamic_id, dynamic_item=dynamic_item)


class BiliJsonStoreImplement(AbstractStore):
    json_store_path: str = "data/bilibili/json"
    words_store_path: str = "data/bilibili/words"
    lock = asyncio.Lock()
    file_count:int=calculate_number_of_files(json_store_path)
    WordCloud = words.AsyncWordCloudGenerator()


    def make_save_file_name(self, store_type: str) -> (str,str):
        """
        make save file name by store type
        Args:
            store_type: Save type contains content and comments（contents | comments）

        Returns:

        """

        return (
            f"{self.json_store_path}/{crawler_type_var.get()}_{store_type}.json",
            f"{self.words_store_path}/{crawler_type_var.get()}_{store_type}_{utils.get_current_date()}"
        )

    async def save_data_to_json(self, save_item: Dict, store_type: str):
        """
        Below is a simple way to save it in json format.
        Args:
            save_item: save content dict info
            store_type: Save type contains content and comments（contents | comments）

        Returns:

        """
        pathlib.Path(self.json_store_path).mkdir(parents=True, exist_ok=True)
        pathlib.Path(self.words_store_path).mkdir(parents=True, exist_ok=True)
        save_file_name,words_file_name_prefix = self.make_save_file_name(store_type=store_type)
        save_data = []

        async with self.lock:
            if os.path.exists(save_file_name):
                async with aiofiles.open(save_file_name, 'r', encoding='utf-8') as file:
                    save_data = json.loads(await file.read())

            save_data.append(save_item)
            async with aiofiles.open(save_file_name, 'w', encoding='utf-8') as file:
                await file.write(json.dumps(save_data, ensure_ascii=False))

            if config.ENABLE_GET_COMMENTS and config.ENABLE_GET_WORDCLOUD:
                try:
                    await self.WordCloud.generate_word_frequency_and_cloud(save_data, words_file_name_prefix)
                except:
                    pass

    async def store_content(self, content_item: Dict):
        """
        content JSON storage implementation
        Args:
            content_item:

        Returns:

        """
        await self.save_data_to_json(content_item, "contents")

    async def store_comment(self, comment_item: Dict):
        """
        comment JSON storage implementation
        Args:
            comment_item:

        Returns:

        """
        await self.save_data_to_json(comment_item, "comments")

    async def store_creator(self, creator: Dict):
        """
        creator JSON storage implementation
        Args:
            creator:

        Returns:

        """
        await self.save_data_to_json(creator, "creators")

    async def store_contact(self, contact_item: Dict):
        """
        creator contact JSON storage implementation
        Args:
            contact_item: creator's contact item dict

        Returns:

        """

        await self.save_data_to_json(save_item=contact_item, store_type="contacts")

    async def store_dynamic(self, dynamic_item: Dict):
        """
        creator dynamic JSON storage implementation
        Args:
            dynamic_item: creator's contact item dict

        Returns:

        """

        await self.save_data_to_json(save_item=dynamic_item, store_type="dynamics")


class BiliSqliteStoreImplement(AbstractStore):
    async def store_content(self, content_item: Dict):
        """
        Bilibili content SQLite storage implementation
        Args:
            content_item: content item dict

        Returns:

        """

        from .bilibili_store_sql import (add_new_content,
                                         query_content_by_content_id,
                                         update_content_by_content_id)
        video_id = content_item.get("video_id")
        video_detail: Dict = await query_content_by_content_id(content_id=video_id)
        if not video_detail:
            content_item["add_ts"] = utils.get_current_timestamp()
            await add_new_content(content_item)
        else:
            await update_content_by_content_id(video_id, content_item=content_item)

    async def store_comment(self, comment_item: Dict):
        """
        Bilibili comment SQLite storage implementation
        Args:
            comment_item: comment item dict

        Returns:

        """

        from .bilibili_store_sql import (add_new_comment,
                                         query_comment_by_comment_id,
                                         update_comment_by_comment_id)
        comment_id = comment_item.get("comment_id")
        comment_detail: Dict = await query_comment_by_comment_id(comment_id=comment_id)
        if not comment_detail:
            comment_item["add_ts"] = utils.get_current_timestamp()
            await add_new_comment(comment_item)
        else:
            await update_comment_by_comment_id(comment_id, comment_item=comment_item)

    async def store_creator(self, creator: Dict):
        """
        Bilibili creator SQLite storage implementation
        Args:
            creator: creator item dict

        Returns:

        """

        from .bilibili_store_sql import (add_new_creator,
                                         query_creator_by_creator_id,
                                         update_creator_by_creator_id)
        creator_id = creator.get("user_id")
        creator_detail: Dict = await query_creator_by_creator_id(creator_id=creator_id)
        if not creator_detail:
            creator["add_ts"] = utils.get_current_timestamp()
            await add_new_creator(creator)
        else:
            await update_creator_by_creator_id(creator_id, creator_item=creator)

    async def store_contact(self, contact_item: Dict):
        """
        Bilibili contact SQLite storage implementation
        Args:
            contact_item: contact item dict

        Returns:

        """

        from .bilibili_store_sql import (add_new_contact,
                                         query_contact_by_up_and_fan,
                                         update_contact_by_id, )

        up_id = contact_item.get("up_id")
        fan_id = contact_item.get("fan_id")
        contact_detail: Dict = await query_contact_by_up_and_fan(up_id=up_id, fan_id=fan_id)
        if not contact_detail:
            contact_item["add_ts"] = utils.get_current_timestamp()
            await add_new_contact(contact_item)
        else:
            key_id = contact_detail.get("id")
            await update_contact_by_id(id=key_id, contact_item=contact_item)

    async def store_dynamic(self, dynamic_item):
        """
        Bilibili dynamic SQLite storage implementation
        Args:
            dynamic_item: dynamic item dict

        Returns:

        """

        from .bilibili_store_sql import (add_new_dynamic,
                                         query_dynamic_by_dynamic_id,
                                         update_dynamic_by_dynamic_id)

        dynamic_id = dynamic_item.get("dynamic_id")
        dynamic_detail = await query_dynamic_by_dynamic_id(dynamic_id=dynamic_id)
        if not dynamic_detail:
            dynamic_item["add_ts"] = utils.get_current_timestamp()
            await add_new_dynamic(dynamic_item)
        else:
            await update_dynamic_by_dynamic_id(dynamic_id, dynamic_item=dynamic_item)
