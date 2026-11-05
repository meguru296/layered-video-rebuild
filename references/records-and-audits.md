# 记录格式与检查器

## 最小生产记录

不强制替换既有项目结构。至少能从现有记录恢复以下关系：

| 记录 | 要回答的问题 |
| --- | --- |
| 源与时间线 | 哪个母版、实际帧数/帧率、时间戳和音轨偏移？ |
| 镜头与差分 | 哪些区间共用画稿，哪里是真切点、表情变化或用户例外？ |
| 素材状态与来源 | 当前采用哪一版，哪些是参考、候选、拒绝或推断？ |
| 图层与运动 | 画稿坐标、遮挡关系、全局区间、手性、几何完整路径和字形锚点？ |
| 参数与缓存 | 缓存对应哪个参数版本，改动会影响哪些输出帧？ |
| 直接复用 | 授权与无人证据、允许区间和实际用到的区间？ |
| 检查与交付 | 自动检查了什么、目视审查了什么、还有什么近似、当前入口在哪？ |

建议用可追踪的素材 ID 和稳定相对路径。分辨率、帧率、图层和几何数目均为任务参数；不要照搬某次项目的具体数值、人物命名、歌词或本机路径。

## 复杂返修的补充工作记录

按需要在现有格式中关联需求/反馈的来源、问题类别、参考观测、对象、影响区间、重复镜头族、修复、验收与证据。事件可记录进入/保持/离开、跨状态持续、主体占比、深度和稳定随机身份。缓存记录参数/素材版本、补丁暂存状态与发布入口。

审阅分别声明结构、编码音画、内容和实际运动回放的范围、方法与未覆盖部分；替代方案保留原要求、缺口与接受依据。工程能力分清影片缓存重放、参数再生和原生对象编辑。来源或计划文字与实际实现矛盾时，发布前对齐。

这些是可选的工作记录，不要求全部套新 schema，也没有被当前 `audit_project.py` 自动认证。结构脚本只能核对声明一致性，不能判断低透明度人物是否遗漏、动作是否有节奏或替代方案是否获接受。

## `audit_project.py`

此脚本只读检查项目清单，使用 Python 标准库，不需安装视频软件或图像库。它能发现区间缺口/越界、帧缺失/重复、路径越界/缺媒体、拒绝素材进入活跃层、不合要求的矩阵手性、进度折返、未达到指定完整值以及直接复用超白名单等问题。

它不能证明白名单画面确实无人、字形无描边、美术正确、视频完整解码或音画同步。未提供的检查项会列为警告，不能把 `ok: true` 当作完整成片验收。

```text
python scripts/audit_project.py path/to/check-manifest.json --root path/to/project
python scripts/audit_project.py path/to/check-manifest.json --root path/to/project --require-native --verify-hashes
```

默认输出 JSON 到标准输出，退出码 0 表示所声明的结构检查通过，1 表示发现错误。`--allow-partial` 允许制作过程中的镜头/帧覆盖不完整，但仍检查重复、越界和无效媒体。最终检查不要使用该选项。

最小示例（一个两帧的已完成小样，路径应替换为实际文件）：

```json
{
  "schema_version": 1,
  "timeline": {"frame_count": 2, "fps_num": 24, "fps_den": 1, "width": 1920, "height": 1080},
  "shots": [{"id": "shot-1", "start": 0, "end": 2}],
  "assets": [{"id": "approved-art", "path": "assets/art.png", "status": "approved"}],
  "layers": [{"id": "character", "asset_ids": ["approved-art"], "intervals": [[0, 2]]}],
  "native_frames": [
    {"frame": 0, "path": "output/native/f0001.png"},
    {"frame": 1, "path": "output/native/f0002.png"}
  ],
  "tracks": [
    {
      "id": "stable-mirrored-art",
      "kind": "affine",
      "expected_sign": -1,
      "samples": [{"frame": 0, "matrix": [[-1, 0, 1920], [0, 1, 0]]}]
    },
    {
      "id": "camera-correction",
      "kind": "affine",
      "role": "stabilization_correction",
      "samples": [{"frame": 0, "matrix": [[1, 0, 0], [0, 1, 0]]}]
    },
    {
      "id": "circle-draw",
      "kind": "progress",
      "monotonic": "increasing",
      "bounds": [0, 360],
      "required_value": 360,
      "samples": [{"frame": 0, "value": 0}, {"frame": 1, "value": 360}]
    }
  ],
  "source_reuse": {"approved_intervals": [], "used_intervals": []}
}
```

字段约定：

- `timeline` 必需；尺寸可省略，但提供时会检查原生 PNG 头部尺寸。fps 使用正整数分子/分母，不靠浮点近似或固定某个帧率。
- `shots` 可省略；提供时最终模式要求按顺序恰好覆盖 `[0, frame_count)`。有意黑场也应占一个有明确范围的镜头，而不是缺口。
- `assets` 使用唯一 `id`、根目录内可解析的相对 `path`，以及 `approved/reference/candidate/rejected` 状态。活跃 `layers` 只能引用 `approved` 素材；被批准直接复用的源素材也应有明确用途的 approved 条目。
- `layers` 的区间可互相重叠，也可留空；它们不是镜头覆盖表。可用 `intervals` 记录工程中的实际区间、`expected_intervals` 记录设计区间，检查追加图像后字幕虽仍在全片范围内却越过了本镜头结尾的错误。设置 `enabled: false` 的历史层不会按当前渲染素材检查。
- `native_frames` 提供显式全局帧号和路径。`--require-native` 要求这一项存在且非空；完整模式检查恰好每帧一个文件。PNG 只读签名和尺寸，完整解码需另行进行。
- `tracks` 的样本帧号严格递增，允许在 `frame_count` 放排他结束边界控制点，实际渲染帧只允许到 `frame_count - 1`。仿射矩阵为有限的 2×3 数组；镜像本身合法，只有声明的 `expected_sign` 或 `stabilization_correction` 约束会限制手性。目标工具只支持统一缩放/旋转时，声明 `representation: similarity` 可拦下不能由该表示表达的剪切和非等比变换。
- `progress` 可声明 `increasing` 或 `decreasing`，允许保持；不要把本来往返的真实动画整个错误地标成单调。`bounds` 和 `required_value` 用于验证所声明的控制点，不能替代对软件插值和真实渲染的检查。
- `source_reuse` 的已用区间必须被批准区间的并集完全覆盖。脚本检查的是声明一致性，图像与授权证据仍需另行核实。
- 任一资产或原生帧可附 `sha256`；使用 `--verify-hashes` 才实际读取并比对，避免每次简单检查都扫描大量帧文件。默认只检查哈希格式。

只记录真实证据。不要为了让检查通过，修改白名单、删掉发生问题的帧或把有反射的错误修正重新标记成合法画稿镜像。
