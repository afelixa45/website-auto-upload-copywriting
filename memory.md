# 网站自动上传文案

## 项目概述

Tampermonkey 油猴脚本，在电商后台产品编辑页一键填充产品信息。从 Google Sheets 读取数据，调用 DeepSeek API 智能匹配产品属性。

## 核心文件

| 文件 | 说明 |
|------|------|
| `自动上传文案.user.js` | 主脚本 v2.1.0 |

## 功能

- **数据源**：Google Sheets 导出 CSV，自动解析产品数据
- **表单填充**：自动填写产品名称、编号、关键词、URL、描述、SEO、价格、库存、尺寸重量
- **AI 属性匹配**：调用 DeepSeek API 动态读取页面选项，自动匹配属性（SZ: Theme/Product Type/Company/Character/Featured In/Size/Scale，GD: Theme[IP]/Hot Categories/Brand/Size/Scale）
- **预售处理**：自动设置预售状态、预售价格、预折扣

## 支持网站

- ShowzStore (`showzstore.com`)
- GundamIT (`gundamit.com`)
- GKLoot (`gkloot.com`)

## 依赖

- Papa Parse — CSV 解析（CDN 引入）
- DeepSeek API — AI 属性匹配（需配置 API Key）

## 当前版本

v2.1.0 — 兼容 GD 属性结构（标签别名映射 + Hot Categories），SZ/GD 统一处理。
