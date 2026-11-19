# -*- coding: utf-8 -*-
"""四平台差异化风格档案。

基于各平台推荐逻辑与用户心理设计（不是简单加字幕）：
- 抖音：算法赛马、陌生人、前3秒定生死、强视觉冲击、快节奏、高完播
- 小红书：封面标题决定点击、搜索SEO、种草氛围感、女性向、精致
- 视频号：社交推荐+熟人关系、中年用户、正能量/知识、适合转发、私域
- 快手：老铁文化、下沉市场、真实接地气、绝活/信任感

题材：夜间商业街「机器狮/醒狮」表演（科技×传统民俗）。
每条视频都有：独立选段、独立色调、独立字幕样式、独立营销文案分镜、
独立封面文字、独立BGM策略、独立发布标题/话题。

剪映资源接入（v2）：
- bgm_file 指向 assets/bgm/jianying/jy_XX.mp3（导入自本机剪映音乐库缓存）
- jy_font 用剪映特色字体（新青年体/悠然体/后现代体）做封面与计数器
- jy_transition 用剪映中文转场名，经 jianying_fx.resolve_transition 映射成 ffmpeg
- 段内爆点特效由 jianying_fx.in_clip_effect 复刻剪映闪屏/故障效果
"""
from __future__ import annotations

# ASS颜色是 &HAABBGGRR；这里用 helper 从 RGB 转
def ass_color(r: int, g: int, b: int, a: int = 0) -> str:
    return f"&H{a:02X}{b:02X}{g:02X}{r:02X}"


STYLE_PROFILES = {
    "douyin": {
        "label": "抖音 · 强钩子快节奏",
        "platform": "抖音",
        # 选段/时长：快切、短平快
        "target_duration": 22.0,
        "clip_len": 4.5,            # 每个片段长度
        "n_clips": 5,               # 快切片段数
        "fps": 30,
        "aspect": "9:16",
        # 画面色调：高对比高饱和，视觉冲击
        "color_filter": "eq=contrast=1.16:saturation=1.28:brightness=0.015",
        # 字幕样式：白字+亮黄描边、超大、居中偏下、加粗、醒目
        "sub_style": {
            "font": "Microsoft YaHei", "size": 68, "bold": True,
            "primary": ass_color(255, 255, 255),       # 白
            "outline": ass_color(255, 200, 0),          # 亮黄描边
            "back": ass_color(0, 0, 0, 55),             # 半透黑底
            "outline_w": 3.5, "shadow": 0, "alignment": 2, "margin_v": 240,
        },
        # 营销文案分镜（按片段顺序打点）：钩子→反差→信息→互动
        "beats": [
            "台上这个 是机器",
            "没人遥控 也没人扶",
            "看它腿 是这样动的",
            "台下小孩全追着跑",
            "下个节目更夸张",
        ],
        "tag_text": "现场实拍",
        # 封面文字
        "cover_text": "台上这个 是机器",
        "cover_sub": "现场实拍",
        # BGM：剪映音乐库真实曲目
        "bgm_mood": "upbeat/hot", "bgm_volume": 0.88, "bpm": 140, "bgm_style": "hot",
        "bgm_file": "jy_01.mp3", "bgm_start": 8,     # 剪映音乐库曲目(跳前奏)
        # 转场/动效（成片级包装）
        "transition": "fadewhite", "transition_dur": 0.12,  # 闪白快切(更短更爆)
        "jy_transition": "闪白", "jy_font": "新青年",        # 剪映转场名 + 剪映字体
        "zoom_step": 0.0010, "shake": 6,                     # 卡点推近+抖动幅度(px)
        "impact": "flash",                                   # 爆点:段首闪白+RGB故障+提亮冲击
        "mg_accent": "0xFFD700", "counter_label": "播放量",
        "counter_start": 128000, "counter_rate": 2400,       # 递增计数器
        # 发布文案
        "title": "这真的是机器做的？会舞狮的机器狗炸街了",
        "caption": "第一眼我以为是真人扮的，结果它是机器！传统醒狮+机器人，这波真的被科技惊艳到了。你觉得算非遗新玩法吗？",
        "hashtags": ["#机器人", "#醒狮", "#科技改变生活", "#非遗新玩法", "#街头表演", "#黑科技"],
    },
    "xiaohongshu": {
        "label": "小红书 · 氛围种草",
        "platform": "小红书",
        "target_duration": 32.0,
        "clip_len": 6.0,
        "n_clips": 5,
        "fps": 30,
        "aspect": "9:16",
        # 日系暖调、柔和、氛围感
        "color_filter": "eq=contrast=1.05:saturation=1.10:brightness=0.045,colorbalance=rs=0.035:gs=0.010:bs=-0.020",
        "sub_style": {
            "font": "Microsoft YaHei", "size": 46, "bold": False,
            "primary": ass_color(255, 255, 255),
            "outline": ass_color(30, 30, 30),           # 细黑描边
            "back": ass_color(0, 0, 0, 0),              # 无底
            "outline_w": 1.4, "shadow": 1, "alignment": 2, "margin_v": 280,
        },
        "beats": [
            "路过就走不动了",
            "它真的在跟小朋友互动",
            "动作一点不僵硬",
            "站了十分钟没看够",
            "下次还来蹲",
        ],
        "tag_text": "随手拍",
        "cover_text": "路过就走不动了",
        "cover_sub": "随手拍",
        "bgm_mood": "soft/aesthetic", "bgm_volume": 0.82, "bpm": 96, "bgm_style": "aesthetic",
        "bgm_file": "jy_05.mp3", "bgm_start": 12,
        # 转场/动效：柔和叠化 + 缓慢推近，轻柔爆点(不破坏氛围感)
        "transition": "fade", "transition_dur": 0.35,
        "jy_transition": "叠化", "jy_font": "悠然",      # 剪映叠化 + 悠然体(文艺)
        "zoom_step": 0.00035, "shake": 0,
        "impact": "soft",
        "mg_accent": "0xFF69B4", "counter_label": "点赞",
        "counter_start": 8600, "counter_rate": 180,
        "title": "被商场门口这只机器醒狮萌到了🦁",
        "caption": "下班路上偶遇的快闪表演✨ 一开始以为是传统醒狮，没想到是机器人控制的！红配白造型超好看，跟小朋友互动的时候真的超温柔～ 科技让传统文化变可爱了。周末带娃的姐妹可以冲！",
        "hashtags": ["#周末去哪儿", "#带娃日常", "#醒狮", "#机器人", "#国潮", "#亲子", "#街头快闪"],
    },
    "shipinhao": {
        "label": "视频号 · 正能量转发",
        "platform": "视频号",
        "target_duration": 42.0,
        "clip_len": 7.0,
        "n_clips": 6,
        "fps": 30,
        "aspect": "9:16",
        # 自然真实、不过度调色
        "color_filter": "eq=contrast=1.03:saturation=1.05:brightness=0.01",
        "sub_style": {
            "font": "Microsoft YaHei", "size": 50, "bold": True,
            "primary": ass_color(255, 255, 255),
            "outline": ass_color(0, 0, 0),
            "back": ass_color(0, 0, 0, 40),
            "outline_w": 2.0, "shadow": 0, "alignment": 2, "margin_v": 220,
        },
        "beats": [
            "这是现场的机器人表演",
            "台下围了很多人",
            "孩子们看得一直拍手",
            "动作是程序提前编好的",
            "技术做到这一步 不容易",
            "值得转给身边人看看",
        ],
        "tag_text": "现场记录",
        "cover_text": "现场的机器人表演",
        "cover_sub": "现场记录",
        "bgm_mood": "warm/inspiring", "bgm_volume": 0.80, "bpm": 108, "bgm_style": "inspiring",
        "bgm_file": "jy_04.mp3", "bgm_start": 10,
        # 转场/动效：平稳淡入淡出 + 极缓推近，稳重带轻度冲击点
        "transition": "fade", "transition_dur": 0.45,
        "jy_transition": "叠化", "jy_font": "后现代",      # 剪映叠化 + 后现代体(稳重)
        "zoom_step": 0.00020, "shake": 0,
        "impact": "soft",
        "mg_accent": "0x00A0D0", "counter_label": "转发",
        "counter_start": 3200, "counter_rate": 95,
        "title": "当传统醒狮遇上机器人，非遗有了新玩法",
        "caption": "科技与传统文化的碰撞，总能带来惊喜。当醒狮由机器人演绎，古老的非遗焕发了新的生命力。孩子们看得目不转睛，这就是传承最好的样子。值得转发给更多人看看。",
        "hashtags": ["#非遗传承", "#科技向善", "#传统文化", "#机器人", "#正能量"],
    },
    "kuaishou": {
        "label": "快手 · 老铁接地气",
        "platform": "快手",
        "target_duration": 28.0,
        "clip_len": 5.5,
        "n_clips": 5,
        "fps": 30,
        "aspect": "9:16",
        # 浓郁、热闹、保留现场烟火气
        "color_filter": "eq=contrast=1.10:saturation=1.18:brightness=0.02",
        "sub_style": {
            "font": "Microsoft YaHei", "size": 62, "bold": True,
            "primary": ass_color(255, 215, 0),          # 亮黄字
            "outline": ass_color(0, 0, 0),              # 黑粗描边
            "back": ass_color(0, 0, 0, 0),
            "outline_w": 4.0, "shadow": 0, "alignment": 2, "margin_v": 230,
        },
        "beats": [
            "老铁们 这可不是人扮的",
            "自己走 自己转 自己停",
            "一台一台排着队走",
            "这活儿 是真下功夫了",
            "想看的 评论区说一声",
        ],
        "tag_text": "现场直拍",
        "cover_text": "这可不是人扮的",
        "cover_sub": "现场直拍",
        "bgm_mood": "lively/folk", "bgm_volume": 0.88, "bpm": 128, "bgm_style": "folk",
        "bgm_file": "jy_11.mp3", "bgm_start": 6,
        # 转场/动效：热闹闪黑快切 + 明显推拉抖动 + 强爆点
        "transition": "fadeblack", "transition_dur": 0.12,
        "jy_transition": "闪黑", "jy_font": "新青年",      # 剪映闪黑 + 新青年体(粗犷)
        "zoom_step": 0.0013, "shake": 9,
        "impact": "hard",
        "mg_accent": "0xFFD700", "counter_label": "老铁在看",
        "counter_start": 666, "counter_rate": 66,
        "title": "老铁们开眼了！机器舞狮子 比真人还溜",
        "caption": "老铁们瞅瞅，这狮子是真机器啊，不是人扮的！走位稳、动作溜，大小朋友都看呆了。咱中国智造就是牛！双击666，关注我带你看更多绝活～",
        # 快手硬限制：话题标签最多 4 个（超了报「话题标签数量超过上限：4」整条失败）
        "hashtags": ["#老铁", "#中国智造", "#绝活", "#舞狮"],
    },
}


PLATFORM_ORDER = ["douyin", "xiaohongshu", "shipinhao", "kuaishou"]


# 发布文案统一从 captions.py 读（单一事实来源）。
# 改标题/文案/话题只改 captions.py，重新剪片或 sync_captions.py 都会带上。
from captions import CAPTIONS as _CAPTIONS
for _p, _c in _CAPTIONS.items():
    if _p in STYLE_PROFILES:
        STYLE_PROFILES[_p]["title"] = _c["title"]
        STYLE_PROFILES[_p]["caption"] = _c["caption"]
        STYLE_PROFILES[_p]["hashtags"] = list(_c["hashtags"])
