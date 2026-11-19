# -*- coding: utf-8 -*-
"""发布适配器包：四平台统一 publish() 接口。"""
from .base import (PublishResult, ensure_login, build_caption, click_publish,
                   click_by_text, scroll_to_bottom, PUBLISH_TEXTS)
from .douyin import publish_douyin
from .xiaohongshu import publish_xiaohongshu
from .shipinhao import publish_shipinhao
from .kuaishou import publish_kuaishou

PLATFORMS = {
    "douyin": publish_douyin,
    "xiaohongshu": publish_xiaohongshu,
    "shipinhao": publish_shipinhao,
    "kuaishou": publish_kuaishou,
}

__all__ = ["PublishResult", "PLATFORMS", "ensure_login", "build_caption",
           "click_publish", "click_by_text", "scroll_to_bottom"]
