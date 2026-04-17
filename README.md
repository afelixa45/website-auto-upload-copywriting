# 网站自动上传文案

电商后台新品上架自动化，两个通道并存：

1. **Python + Playwright 有头通道**（v3.1.0，推荐日常使用）：`sz_upload.py` — 打开 Chromium 自动填完字段 + 上传主图（iframe）+ 上传 listing 图（HTTP）+ CKEditor 描述拼接 + AI 属性匹配，停在保存按钮前等你人工核对。支持 `--site sz|gd` 切换 ShowZ Store / GundamIT
2. **油猴脚本通道**（v2.1.0，浏览器端备用）：`自动上传文案.user.js` — Tampermonkey 在页面里一键填充，SZ/GD/GKLoot 三站点通用

## 通道一：Playwright 有头上架（SZ）

### 快速开始

```bash
cd "/Users/zuowenjian/Claude Code/网站自动上传文案"
cp .env.example .env            # 填写 SZ/GD 凭据 + DeepSeek API Key
pip3 install -r requirements.txt
python3 -m playwright install chromium

# 入口
python3 sz_upload.py <SKU>                    # SZ，桌面按 SKU 搜
python3 sz_upload.py "<docx>" <SKU>           # SZ，显式指定 docx
python3 sz_upload.py --site gd <SKU>          # GundamIT 站
python3 sz_upload.py <SKU> --no-images        # 跳过图片，调试用
python3 sz_upload.py <SKU> --headless         # ⚠️ 见下方"已知限制"，独立跑会卡死
```

### ⚠️ 已知限制：`--headless` 独立运行会卡死

本项目的独立入口 `sz_upload.py` 的流程设计是「填完字段 → 停在保存按钮前 → 等用户手动核对保存 → 关浏览器窗口退出」。无头模式下没有 UI，用户无法关窗口，脚本会**永久卡死在 `pause_for_manual_save()` 循环**。

**真正能无头跑的场景**：通过 `暗源新品上架链` 项目编排（`site_draft.py` 补齐了"点【后台】存草稿 + 搜 ProId"的自动提交闭环）。独立跑必须保持**有头 + 人工核对**。

如需独立无头自动提交草稿：要把 `site_draft.py` 里的闭环逻辑下沉到本项目（未完成，仅在暗源新品上架链里活着）。

### 输入约定

- **.docx 文案**：多产品表格，第 3 行放产品编号，每列一个产品。按 SKU 在第 3 行定位列号后读取该列的 18 个字段。
- 字段映射与油猴脚本 `cellIndexMappings` 完全一致：
  - 行 1 = product_title / 行 2 = category / 行 3 = number / 行 4 = search_keyword / 行 5 = page_url / 行 6 = description_en
  - 行 11 = seo_keyword_en / 行 12 = seo_description_en / 行 14 = price
  - 行 17 = stock / 行 18 = is_coming / 行 19 = presale_price / 行 20 = pre_discount
  - 行 21-24 = length/width/height/weight / 行 29 = is_batteries

### 输入约定（图片）

桌面需有文件夹 `*<SKU>*/`，内含：
- `<任意名>.docx` — 文案（18 字段，多产品共享，按 SKU 在第 3 行定位列）
- 图片子目录（优先名为 `原图/`）：`0.jpg/png` 主图 + `X1.jpg`…`XN.jpg` listing 图

### 流程

1. 启动 Chromium 有头模式（`--start-maximized`）
2. 图片预处理：主图 500² 居中+水印（临时文件），listing 850w+水印（字节）
3. 加载 `session/{site}_storage.json` 登录态；失效则自动用 `.env` 账密登录
4. 打开站点的 `ADD_PRODUCT_URL`
5. 填充基础字段：分类 / 标题 / 编号 / 关键词 / PageUrl / SEO（带站点后缀）
6. **主图上传**：点 `#PicUpload_0` → 定位 photo choice iframe → `set_input_files` 注入 → jQuery file_upload 插件自动上传 + iframe 自动关 + `PicPath[]` 回填
7. **listing 图上传**：Playwright context 的 cookies 导给 requests.Session → 并发 POST 到 `?do_action=action.file_upload_plugin&size=editor` → 拿 CDN URL 列表
8. 描述 HTML 合成：英文描述 wrap 成 SZ 富文本 span + 每张 listing 拼 `<br/><br/><img src="..." />` → 一次性塞进 CKEditor
9. 继续填充：价格 / 库存 / 预售 / 尺寸重量 / 电池
10. 切到属性 tab，Availability 按规则决定，其余 8 项调 DeepSeek 匹配
11. **停在保存按钮前**，你在浏览器里核对 → 手动点【保存】 → 关窗 → 脚本自动退出

### 文件结构

```
网站自动上传文案/
├── sz_upload.py           ← 入口 CLI
├── sz_client.py           ← Playwright 封装（登录 / 字段填充 / 主图 iframe / listing HTTP / AI 属性）
├── image_processor.py     ← PIL 图片处理 + 桌面目录启发式搜索（v3.1.0）
├── ai_matcher.py          ← DeepSeek + 8 类 AI 属性配置
├── parser.py              ← .docx 多产品解析
├── 自动上传文案.user.js    ← 油猴版 v2.1.0
├── .env                   ← SZ/GD 凭据 + DeepSeek Key（不提交）
├── .env.example
├── requirements.txt
├── session/               ← Playwright 登录态 {sz,gd}_storage.json（不提交）
└── logs/                  ← 运行日志（不提交）
```

### Claude Code Skill

已注册 `website-upload` skill，对话中说「给 `MS-B04A-TEST` 上架到 SZ」或 `/website-upload MS-B04A-TEST` 即可触发。

---

## 通道二：油猴脚本（SZ/GD/GKLoot）

### 功能

- 从 Google Sheets 导出 CSV 解析产品数据
- 填充产品名称 / 编号 / 关键词 / URL / 描述 / SEO / 价格 / 库存 / 尺寸重量
- DeepSeek AI 动态属性匹配（Theme/Product Type/Company/Character/Featured In/Size/Scale）
- 多站点 SEO 标题后缀自动添加
- 预售自动处理

### 使用方法

1. 安装 Tampermonkey 浏览器扩展
2. 创建新脚本，粘贴 `自动上传文案.user.js` 的内容
3. ⚠️ **安全**：脚本中 `API_CONFIG.apiKey` 当前是硬编码，违反红线第 1 条，后续需要轮换 Key 并改为用户配置
4. 访问产品编辑页，点击「自动上传文案」按钮

---

## 更新日志

### 3.1.0 (2026-04-14)
- 主图上传：点 `#PicUpload_0` → 定位 photo choice iframe → `set_input_files` → jQuery 插件自动 XHR 上传 + iframe 自动关 + `PicPath[]` 回填
- listing 图上传：从 Playwright context 取 cookies，走 HTTP editor 端点并发上传，拿 CDN URL 拼进 CKEditor 描述
- `image_processor.py` 独立图片处理模块（主图 500²+水印 / listing 850w+水印）
- GD 通道：`--site sz|gd` 参数，`.env` 按前缀 `SZ_`/`GD_` 读取，session 按站点分文件
- 关键发现：SZ "本地上传" 分支自动完成，不需要点 `#button_add`；`#button_add` 只在"选择已有图库"分支用到
- MS-B04A-TEST 端到端实测通过：15 字段 + 主图 + 9 张 listing + 8 类 AI 属性，总耗时 42 秒

### 3.0.0 (2026-04-13)
- 新增 Python + Playwright 有头通道，对齐 ERP 自动上传文案的交互模型
- `parser.py` / `sz_client.py` / `ai_matcher.py` / `sz_upload.py` 四件套
- 注册 Claude Code skill `website-upload`
- 登录态持久化，首次登录后 session 免登
- AI 属性逻辑完整 port 到 Python（8 类 + Availability 规则）

### 2.1.0
- 油猴脚本兼容 GD 属性结构：标签别名映射（Theme↔Theme[IP]、Company↔Brand）
- 新增 Hot Categories AI 匹配
- SZ 独有属性在 GD 上自动跳过

### 2.0.0
- AI 属性匹配重构：动态读页面选项，后台改选项后脚本自适应
- 提取通用 AI 匹配函数
- 修复 SEO 标题后缀
- Size/Scale 拆分

### 1.3.6
- 修复网站标题连接符号问题

### 1.3.5
- 初始版本
