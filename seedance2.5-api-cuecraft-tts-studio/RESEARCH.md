# CueCraft 选题与参考记录

调研日期：2026-11-19。星标为当日读取的 GitHub 页面显示值（四舍五入），不是精确计数或持续更新的排行榜。

## 现有项目与差异

检查了当前目录中的 README 和项目记录：

| 已有项目 | 主要输入与流程 | 结果 |
|---|---|---|
| Nano Banana API Studio / 蕉片 Studio | 提示词、参考图片 → 图片生成或编辑 → 预览 | 图片 |
| seedance2.0 api · ComfyUI Video Relay | ComfyUI 节点参数 → 视频任务 → 查询 | 视频 URL |
| VideoBridge · comfyui workflow api | 工作流/视频参数 → 防重复提交 → 任务 ID 恢复 | 云端视频与任务记录 |

## 三个候选方向

| 方向 | 用户 | 具体问题 | 输入 | 多模态能力 | 核心步骤 | 交付 |
|---|---|---|---|---|---|---|
| **分段配音交付（选定）** | 课程作者、导览制作人、视频剪辑师 | 修改一句时不想重做整段；交付音频与原稿容易错配 | 分段稿件、音色、语速 | 文本 → 语音 | 分段 → 单段生成 → 试听选版 → 校验一致性 → 打包 | 编号 MP3、原稿、参数清单 |
| 音效素材整理 | 独立游戏与播客作者 | 音效文件缺少可追溯的描述与分类 | 场景、氛围、素材标签 | 文本 → 音效/音乐 | 填写音效需求 → 生成候选 → 标签整理 → 导出 | 音效素材包 |
| 图片内容整理 | 教师、资料整理者 | 图文资料需要可检索的结构化摘要 | 图片与字段要求 | 图像理解/OCR | 上传 → 提取 → 人工核对 → 表格导出 | CSV/JSON |

选定配音：RunningHub 有可核实的标准 TTS 接口，输入到输出不需要额外模型衔接；可用一次短生成验证。音效与 OCR 候选未继续核实接口，因此没有宣称其已经可用。与已有项目的实质区别是**按稿件组织音频版本，并交付可追溯的配音包**，而非通用图片工作台或 ComfyUI 视频任务节点。

## 主要参考

### [ebook2audiobook](https://github.com/DrewThomasson/ebook2audiobook) — 约 20.6k stars

来源：上述 GitHub 仓库页面及实际 README，2026-11-19 查询。页面当日可访问，提供安装与更新记录；不据此保证维护频率。

面向电子书听众和制作人，流程是输入电子书/文本、选择语音引擎与音色、转换并输出有声书。README 包含目录、格式支持、系统安装入口及故障说明。借鉴输入到产物的清楚叙述，以及把格式和安装路径明确列出。CueCraft 不处理 EPUB/PDF，不复用其模型或代码，专注短稿件的逐段交付。

### [TTS-WebUI](https://github.com/rsxdalv/TTS-WebUI) — 约 3.3k stars

来源：GitHub 仓库页面及 README，2026-11-19 查询；旧地址 `rsxdalv/tts-generation-webui` 重定向到此仓库。

为语音、音乐与音频实验提供 Gradio/React 界面和扩展式模型选择。文档区分安装器、手动安装和 Docker，并说明模型与运行环境。借鉴音频试听、生成记录与清晰配置说明。CueCraft 用固定的一个云端模型减少本地安装与选型步骤，不提供模型扩展市场。

## 本次具体改进

1. 以 cue（稿件片段）为核心：每段可独立修改、生成多个 take 并试听选版。
2. 每个 take 保存不可变的文本/音色/语速快照。导出前核对快照与当前保存稿件；不匹配时阻止导出，避免音文错配。
3. ZIP 同时包含按段编号的 MP3、`script.md` 和 `manifest.json`，方便交给剪辑师。
4. 服务端先保存提交记录，再调用生成接口。同一 token 复用同一记录；未知结果锁定该片段，用户可从 RunningHub 找回任务 ID，仅恢复查询。
5. 无本地模型、GPU 或前端构建步骤。Flask 服务端与原生网页足够完成这个范围。

## API 核实

- [官方 speech-02-hd 文档](https://pre.runninghub.cn/runninghub-api-doc-cn/api-448183275)：实际读取页面及其内嵌 JSON Schema；页面标注修改时间 2026-07-30。
- [官方模型目录](https://www.runninghub.ai/page-api)：确认平台提供文本转音频能力；实际实现以单独接口文档为准。
- 文档确认 `POST /openapi/v2/rhart-audio/text-to-audio/speech-02-hd`、Bearer 鉴权、语速范围 0.5–2，以及 `POST /openapi/v2/query`、`taskId/status/results[].url/outputType`。
- 文档的文字描述提到长文本，但 schema 未声明 `text.maxLength`。本项目采用独立的保守本地限制 2,000 字符/段，不将其写成服务商上限。
- 不上传文件、不做声音克隆、不混音；无需媒体上传接口。官方响应示例为 MP3；下载后验证 MP3 文件头并保存在本机。
- 完整实现与验证边界见三语 README 与 [VALIDATION.md](VALIDATION.md)。

## 原创与素材

代码、页面布局和 SVG 封面/流程图独立实现，没有复制参考项目源码或截图。代码使用 MIT 许可证。RunningHub 正式 logo 和合作文案由用户提供，品牌素材权利归原权利人；两张参考预览图没有嵌入项目。商业合作数据按提供的宣传文档转述，不当作本项目性能或定价保证。

## 建议 GitHub 信息（尚未发布）

- Repository: `cuecraft-tts-studio`
- Description: `A local-first TTS narration kit: edit script cues, audition takes, and export matching audio with RunningHub API.`
- Topics: `text-to-speech`, `tts`, `narration`, `audio`, `runninghub`, `multimodal-api`, `flask`, `python`
