# 第三方资源与合规说明

## 本仓库不含版权素材

仓库里**没有**任何音乐、字体、视频素材文件。以下目录只放了说明文档：

| 目录 | 内容 | 获取方式 |
|---|---|---|
| `assets/bgm/` | 背景音乐 | 自行从已授权的素材库导入，或从本机剪映缓存导入（见下） |
| `assets/fonts/` | 中文字体 | 自行准备，或从本机剪映字体目录导入（见下） |
| `inbox/` `outbox/` `work/` `state/` `logs/` | 运行时目录 | 运行时自动创建与填充 |

`get_bgm()` 在找不到任何 BGM 文件时会回退到 `bgm_engine.py` 程序化合成的音乐，所以**空仓库也能直接出片**，
只是音乐是算法生成的，不如真实曲目好听。

## 从本机剪映导入（需你本人已获授权的安装）

```powershell
python import_jianying_assets.py --dry-run    # 先看能导入什么
python import_jianying_assets.py --music 12   # 导入 12 首 BGM
python import_jianying_assets.py --fonts-only # 只导入字体
```

脚本读取 `%LOCALAPPDATA%\JianyingPro\User Data\Cache\music\` 与 `User Data\Resources\Font\`。
剪映自带的字体与音乐授权范围仅限于剪映内使用，**商业发布前请自行确认授权**，
或替换为你自己购买/开源授权的资源（如思源系列字体、CC0 音乐库）。

## 内容平台合规

- 用本工具向抖音 / 小红书 / 视频号 / 快手发布内容时，遵守各平台的用户协议与社区规范。
- 小红书等平台要求对 AIGC 内容进行标识；脚本发布不等于可以省略标识。参见 README「自动发布」一节的合规提醒。
- 自动化发布可能与平台的风控策略冲突，账号风险由使用者自行承担；`publisher/` 目录下的选择器随平台改版会失效，
  用之前先用 `--dry-run` 空跑一遍。
