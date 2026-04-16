# Changelog

## [3.1.0] - 2026-04-14

### Added
- **主图 iframe 真实上传**（`sz_client._upload_main_image`）：点 `#PicUpload_0` → 定位 photo choice iframe（URL 匹配 `d=choice&obj=PicUpload_0&iframe=1`）→ `set_input_files` 注入预处理过的方图 → 等 `PicPath[]` 被回填。SZ 的 "本地上传" 走 jQuery file_upload 插件，set 文件即触发 XHR 上传 + iframe 自动关闭，全程不需要点 `#button_add`
- **listing 图 HTTP 并发上传**（`sz_client._upload_listings_http`）：从 Playwright context 导出 cookies 到 `requests.Session`，POST 到 `?do_action=action.file_upload_plugin&size=editor`（这是 SZ 描述图的合法端点，油猴脚本 hook 的底层 XHR 也是它）→ 拿回 CDN URL 列表
- **描述 HTML 拼接**（`_compose_description`）：纯英文描述文本 + listing CDN URL 拼成 `<br/><br/><img src="..." alt="...">`，一次性塞进 CKEditor
- **image_processor.py**：从新品上架链 port 来的 PIL 图片处理。主图 500² 居中正方形 + SZ logo 水印（临时文件路径供 Playwright）；listing 850px 宽 + 水印（字节供 HTTP 上传）。`build_bundle(sku, site)` 一站式从桌面 `*<SKU>*/` 找原图目录（启发式优先 `原图/`）
- **GD 通道** (`--site gd`)：`SzConfig` 新增 `site` 字段，`base_url` / `upload_endpoint` 从 `add_product_url` 自动派生；`sz_upload.py` 的 `load_config(site)` 按前缀 `SZ_`/`GD_` 读取 `.env`；登录态持久化分文件 `session/{site}_storage.json` 避免串扰
- `--no-images` 开关：跳过图片处理只填文本（调试用）
- `.env.example` 新增 `GD_USERNAME` / `GD_PASSWORD` / `GD_LOGIN_URL` / `GD_ADD_PRODUCT_URL`

### Changed
- `fill_product` 签名：新增 `image_bundle: Optional[ImageBundle]` 参数，流程调整为「基础字段 → 主图上传 → listing 上传 → 描述 HTML 合成 → 价格/库存/尺寸 → AI 属性」
- SZ logo 跨项目引用：`../网站图片上传/logos/SZ_logo.png`（GD 用 `GD_logo.png`）
- `SzConfig` 不再硬编码 URL，全部从 `.env` 读取

### Fixed
- 主图 iframe 定位逻辑：原先想用"找 #button_add"启发式定位，但 SZ 的 "本地上传" 分支不渲染 `#button_add`，改用 URL 精确匹配 `d=choice&obj=<name>&iframe=1`，并通过不含 `save=_Detail` 来排除描述图 iframe

### 实测
- 2026-04-14 SKU=MS-B04A-TEST 端到端跑通：15 字段解析 + 主图注入 + 9 张 listing HTTP 上传 + CKEditor 描述拼接 + 8 类 AI 属性匹配，耗时 42 秒（v3.0.0 为 44.8 秒，图片上传几乎零额外开销因为走 HTTP 并发）

## [3.0.0] - 2026-04-13

### Added
- **Python + Playwright 有头上架通道**（对齐 ERP 自动上传文案的交互模型）
  - `parser.py` — 多产品 .docx 解析，按 SKU 定位列号，读取 18 字段
  - `sz_client.py` — Playwright 封装，登录态持久化（`session/storage.json`），自动登录，打开添加页，DOM 填充
  - `ai_matcher.py` — DeepSeek API 客户端 + 8 类 AI 属性配置（从油猴脚本完整 port 到 Python）
  - `sz_upload.py` — CLI 入口：`python3 sz_upload.py <SKU>` 或 `python3 sz_upload.py <docx> <SKU>`
  - 有头 Chromium `--start-maximized`，填充完成后**停在保存按钮前**，用户在浏览器里核对并手动点保存，关窗退出
  - 字段填充顺序和选择器与油猴脚本 v2.1.0 完全一致（Name_en/Number/SearchKeyword/PageUrl/SEO/Description(CKEditor)/Price_1/Stock/IsComing/IsPresale/PresalePrice/PreDiscount/IsBatteries/Cubage/Weight）
  - AI 属性：切到属性 tab 后，Availability 走规则，其余 8 项（Theme/Hot Categories/Product Type/Company/Character/Featured In/Size/Scale）逐个调 DeepSeek
- `.env.example` / `requirements.txt` / `.gitignore`
- `~/.claude/skills/website-upload` Claude Code skill

### Changed
- 项目职责：前台「Playwright 有头上架引擎（对外演示 + 日常上架）」
- 油猴脚本 v2.1.0 保留为浏览器端备用通道（GD/GKLoot 仍走油猴）
- DeepSeek API Key 从油猴脚本硬编码改为 Python 通道走 `.env`（油猴脚本的硬编码未清理，需单独处理）

### Security
- ⚠️ 发现 `自动上传文案.user.js:156` 存在硬编码 DeepSeek API Key，违反红线第 1 条，需要立即轮换并迁移到用户配置

## [2.1.0] - 2026-04

### Added
- DeepSeek AI 智能属性匹配（8 类：Theme、Hot Categories、Product Type 等）
- Availability 自动判断（PRE_ORDER / COMING_SOON / SOLD_OUT / IN_STOCK）
- 多站点 SEO 标题后缀自动添加

## [2.0.0] - 2026-03

### Changed
- 重构数据读取逻辑
- 支持 SZ / GD / GK 三站点

## [1.0.0] - 2026-03

### Added
- 初始版本
- Google Sheets CSV → 网站后台表单自动填充
- 18 字段映射
- CKEditor 详细介绍插入
- 进度条实时反馈
