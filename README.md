# layered-video-rebuild

**分层描改与视频重建**：一个中文 Codex skill，用于对照参考视频完成角色替换、分层描改、动效重建和制作返修。

核心方法是先识别共用原画与差分，再独立重建人物、镜头、文字、几何、光场和转场。保留已确认的栅格画风，通过统一时间线保持连续性。

## 适用范围

- 需要与参考构图、镜头运动和时序对应的描改或角色替换。
- 手部、服装结构、透明孔洞、模糊字幕和转场露馅等问题的定位与局部修复。
- 独立重建字幕、大字缓动、几何路径、聚光灯、粒子退场等效果。
- 分段制作后的全片衔接、音画检查和可移植工程交付。

普通裁剪转码、无参考的新视频创作和独立角色设计不需要这套流程。它提供制作判断与检查方法，不是自动生成整片视频的软件。

## 安装与使用

从 [Releases](https://github.com/meguru296/layered-video-rebuild/releases) 下载 `layered-video-rebuild-v1.0.0.zip`，解压得到 `layered-video-rebuild` 文件夹，放入自己的 Codex skills 目录：通常是 `~/.codex/skills/`；如设置了 `CODEX_HOME`，则使用其中的 `skills/`。已有同名版本时先保存所需改动，再替换。下一轮对话中即可使用。

调用示例：

```text
使用 $layered-video-rebuild 对照参考视频拆分镜头与共用画稿，
保留已确认画风，重建文字、几何和转场，检查全局时间线及交付工程。
```

也可以直接阅读 [SKILL.md](SKILL.md)，按当前任务选择需要的参考文档。

## 内容导航

| 文件 | 内容 |
| --- | --- |
| [SKILL.md](SKILL.md) | 工作流入口与关键判断 |
| [分析与运动](references/analysis-and-motion.md) | 时间戳、原画归组、配准、稀疏轨迹、镜像手性和完整几何 |
| [画稿与合成](references/art-and-compositing.md) | 局部修复、服装印花、透明素材、线稿、空间光照和微光 |
| [文字与效果](references/type-and-effects.md) | 字形排版、合成模型、缓动、粒子消散和转场 |
| [渲染与检查](references/render-and-qa.md) | 全局时钟、缓存、Blender 序列、音轨和三层验收 |
| [故障与交付](references/troubleshooting-and-handoff.md) | 症状定位、恢复、版本、交接和打包 |
| [记录与检查器](references/records-and-audits.md) | 可选清单格式、命令和检查边界 |

## 可选结构检查器

检查器只使用 Python 标准库。建议使用 Python 3.10 或更新版本。

```sh
python scripts/audit_project.py path/to/check-manifest.json --root path/to/project --require-native --verify-hashes
```

它检查清单声明的区间、媒体路径、素材状态、帧覆盖、矩阵手性、单调进度和复用范围，并可核对 PNG 头部尺寸及文件哈希。退出码 `0` 表示所声明的结构检查通过，`1` 表示发现错误。

**检查通过不能证明画面正确。** 此脚本不解码视频、不判断人物或字形内容，也不验证音画同步；参考对照、连续回放和实际交付文件检查仍需进行。详细格式见[记录与检查器](references/records-and-audits.md)。

## 测试与打包

在仓库根目录运行：

```sh
python -B -m unittest discover -s tests -v
python -B tools/build_release.py
```

29 项行为测试使用临时生成的小型图像与清单，不依赖私人素材或额外 Python 包。打包工具默认把 ZIP 和 SHA-256 文件写入仓库旁的 `release-assets/`，只收录技能所需的 9 个文件，读回核对后输出校验值。

仓库包含文档、测试和发布工具；Release 技能包只包含 `SKILL.md`、UI 元数据、6 篇参考文档和结构检查脚本。

参见[版本记录](CHANGELOG.md)和[公开内容审查范围](PRIVACY_REVIEW.md)。
