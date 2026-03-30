# 网站自动上传文案

Tampermonkey 油猴脚本，在电商后台产品编辑页一键填充产品信息。

## 功能

- **数据源**：从 Google Sheets 导出 CSV，自动解析产品数据
- **表单填充**：自动填写产品名称、编号、搜索关键词、URL、描述、SEO 信息、价格、库存、尺寸重量等字段
- **AI 智能匹配**：调用 DeepSeek API，动态读取页面选项，自动匹配 Theme、Product Type、Company、Character、Featured In、Size/Scale 等属性
- **多站点支持**：Showzstore / Gundamit / GKLoot，自动追加对应 SEO 标题后缀
- **预售处理**：自动设置预售状态、预售价格、预折扣等

## 支持网站

- `showzstore.com`
- `gundamit.com`
- `gkloot.com`

## 使用方法

1. 安装 Tampermonkey 浏览器扩展
2. 创建新脚本，粘贴 `自动上传文案.user.js` 的内容
3. 将脚本中 `sk-YOUR_DEEPSEEK_API_KEY` 替换为你的 DeepSeek API Key
4. 访问产品编辑页面，点击「自动上传文案」按钮

## 依赖

- [Papa Parse](https://www.papaparse.com/) — CSV 解析（通过 CDN 引入）
- [DeepSeek API](https://platform.deepseek.com/) — AI 属性匹配

## 文件说明

| 文件 | 说明 |
|---|---|
| `自动上传文案.user.js` | 主脚本 v2.0.0 |

## 更新日志

### 2.0.0
- AI 属性匹配重构：从硬编码选项列表改为动态读取页面 DOM 选项，网站后台改选项后脚本自动适配
- 提取通用 AI 匹配函数，6 个独立 handler 合并为统一配置驱动，代码量减少 75%
- 修复 SEO 标题后缀（Show.Z Store / GunDamit Store）
- Size/Scale 拆分为两个独立属性匹配（Size + Scale），适配页面实际标签结构
- Size 选项格式适配页面实际的 `Xin / Y.Zcm` 格式
- 修复标签查找逻辑，兼容带冒号和不带冒号的标签

### 1.3.6
- 修复网站标题连接符号问题
- 优化代码结构

### 1.3.5
- 初始版本
