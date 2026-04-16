"""DeepSeek 属性匹配 —— 从油猴脚本 AI_ATTRIBUTE_CONFIGS port 到 Python。

流程与 `自动上传文案.user.js` 完全一致：
1. 从页面 DOM 读取选项（.choice_btn 的第一行文本）
2. 拼装 system + user prompt 送 DeepSeek
3. 收到建议后匹配页面选项并点击对应 checkbox
4. 匹配失败时回退到配置里的 defaultValue

Availability 不走 AI（纯规则），单独函数处理。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"


# AI 属性配置表，内容与油猴脚本 AI_ATTRIBUTE_CONFIGS 一致
AI_ATTRIBUTE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "Theme": {
        "systemPrompt": "你是一个专业的玩具和模型分类专家。根据产品标题和描述，从给定的主题选项中选择最合适的一项。只返回选项列表中存在的完整名称，不要包含任何解释。",
        "userPromptPrefix": "请分析以下产品信息并选择最合适的主题：",
        "rules": (
            "注意事项：\n"
            "1. 必须从上述列表中精确选择一个名称\n"
            "2. 优先匹配产品标题中的系列名称\n"
            "3. 考虑品牌与系列的对应关系（如 Bandai 通常对应 Gundam）\n"
            "4. 注意第三方品牌的产品归属（如 Cang-Toys 通常属于 Transformers）\n"
            "5. 如果没有明确对应，返回 \"Other Toys\"\n"
            "6. 返回时必须使用与列表中完全相同的名称"
        ),
        "inputFields": [
            {"key": "product_title", "label": "产品标题"},
            {"key": "description_en", "label": "产品描述", "truncate": 200},
        ],
        "defaultValue": "Other Toys",
    },
    "Product Type": {
        "systemPrompt": "你是一个专业的玩具和模型分类专家。根据产品标题和搜索关键词，从给定的产品类型选项中选择最合适的一项。只返回选项列表中存在的完整名称，不要包含任何解释。",
        "userPromptPrefix": "请分析以下产品信息并选择最合适的产品类型：",
        "rules": (
            "注意事项：\n"
            "1. 必须从上述列表中精确选择一个名称\n"
            "2. 如果是变形金刚相关，注意区分 TF: General / TF: Movie / TF: Beast Wars 等子类型\n"
            "3. 如果标题包含 Model Kit, MG, RG, HG 等字样，选择 Model Kit\n"
            "4. 如果是可动人偶且不属于其他特定类别，选择 Action Figure\n"
            "5. 如果没有明确对应，返回 \"Action Figure\"\n"
            "6. 返回时必须使用与列表中完全相同的名称"
        ),
        "inputFields": [
            {"key": "product_title", "label": "产品标题"},
            {"key": "search_keyword", "label": "搜索关键词"},
        ],
        "defaultValue": "Action Figure",
    },
    "Company": {
        "systemPrompt": "你是一个玩具和模型品牌专家。根据产品分类，从给定的品牌列表中选择一个最合适的制造商。只返回列表中存在的完整品牌名称，不要添加任何其他内容或解释。",
        "userPromptPrefix": "请根据以下产品信息，从品牌列表中选择一个最合适的制造商：",
        "rules": (
            "注意事项：\n"
            "1. 必须从上述列表中精确选择一个品牌名称\n"
            "2. 不要推荐列表之外的品牌\n"
            "3. 如果没有明确对应的品牌，返回 \"Others\"\n"
            "4. 返回时必须使用与列表中完全相同的品牌名称"
        ),
        "inputFields": [{"key": "category", "label": "产品分类"}],
        "defaultValue": "Others",
    },
    "Character": {
        "systemPrompt": "你是一个玩具和模型角色专家。根据产品标题，从给定的角色列表中选择最合适的角色。只返回列表中存在的完整角色名称，不要添加任何其他内容或解释。",
        "userPromptPrefix": "请根据以下产品信息，从角色列表中选择一个最合适的角色：",
        "rules": (
            "注意事项：\n"
            "1. 必须从上述列表中精确选择一个角色名称\n"
            "2. 不要推荐列表之外的角色\n"
            "3. 如果没有明确对应的角色，返回 \"Others\"\n"
            "4. 返回时必须使用与列表中完全相同的角色名称"
        ),
        "inputFields": [{"key": "product_title", "label": "产品标题"}],
        "defaultValue": "Others",
    },
    "Featured In": {
        "systemPrompt": "你是一个玩具和模型系列专家。根据产品标题和搜索关键词，从给定的系列列表中选择最合适的系列。只返回列表中存在的完整系列名称，不要添加任何其他内容或解释。",
        "userPromptPrefix": "请根据以下产品信息，从系列列表中选择一个最合适的系列：",
        "rules": (
            "注意事项：\n"
            "1. 必须从上述列表中精确选择一个系列名称\n"
            "2. 不要推荐列表之外的系列\n"
            "3. 如果没有明确对应的系列，返回 \"Others\"\n"
            "4. 返回时必须使用与列表中完全相同的系列名称"
        ),
        "inputFields": [
            {"key": "product_title", "label": "产品标题"},
            {"key": "search_keyword", "label": "搜索关键词"},
        ],
        "defaultValue": "Others",
    },
    "Size": {
        "systemPrompt": "你是一个玩具和模型尺寸专家。根据产品描述中提到的高度(Height)或尺寸信息，从给定的尺寸列表中选择最合适的尺寸。只返回列表中存在的完整尺寸名称，不要添加任何其他内容或解释。",
        "userPromptPrefix": "请根据以下产品描述，从尺寸列表中选择一个最合适的尺寸：",
        "rules": (
            "注意事项：\n"
            "1. 必须从上述列表中精确选择一个尺寸名称\n"
            "2. 列表中的选项格式为 \"Xin / Y.Zcm\"（如 \"7in / 17.8cm\"），返回时必须包含完整的 \"Xin / Y.Zcm\" 格式\n"
            "3. 从产品描述中提取高度(Height)数值，找到最接近的选项\n"
            "4. 如果描述中只有厘米数值，换算为英寸后匹配最接近的选项（1in ≈ 2.54cm）\n"
            "5. 如果描述中同时出现多个尺寸，选择产品整体高度（通常是最大值）\n"
            "6. 如果没有明确对应，返回列表中的第一个选项\n"
            "7. 返回时必须使用与列表中完全相同的名称"
        ),
        "inputFields": [{"key": "description_en", "label": "产品描述"}],
        "defaultValue": None,
    },
    "Scale": {
        "systemPrompt": "你是一个玩具和模型比例专家。根据产品描述中提到的比例(Scale)信息，从给定的比例列表中选择最合适的比例。只返回列表中存在的完整比例名称，不要添加任何其他内容或解释。",
        "userPromptPrefix": "请根据以下产品描述，从比例列表中选择一个最合适的比例：",
        "rules": (
            "注意事项：\n"
            "1. 必须从上述列表中精确选择一个比例名称\n"
            "2. 优先匹配描述中明确提到的比例信息（如 1/60、1/144、1/100 等）\n"
            "3. 优先匹配 MP Scale、Leader Class 等特殊系列名称\n"
            "4. 如果没有明确对应，返回 \"Others\"\n"
            "5. 返回时必须使用与列表中完全相同的比例名称"
        ),
        "inputFields": [{"key": "description_en", "label": "产品描述"}],
        "defaultValue": "Others",
    },
    "Hot Categories": {
        "systemPrompt": "你是一个专业的玩具和模型分类专家。根据产品标题和描述，从给定的热门分类选项中选择最合适的一项。只返回选项列表中存在的完整名称，不要包含任何解释。",
        "userPromptPrefix": "请分析以下产品信息并选择最合适的热门分类：",
        "rules": (
            "注意事项：\n"
            "1. 必须从上述列表中精确选择一个名称\n"
            "2. 变形金刚/高达/机甲等机器人类产品选择 \"Mecha Robot\"\n"
            "3. 动漫周边选择 \"Anime/Comics\"\n"
            "4. 美少女手办/机娘选择 \"Bishoujo & Mecha Girl\"\n"
            "5. 漫威/DC 等超级英雄选择 \"Superheroes\"\n"
            "6. 军事模型选择 \"Military\"\n"
            "7. 怪兽/恐怖类选择 \"Monsters/Myth & Horror\"\n"
            "8. 游戏周边选择 \"Games\"\n"
            "9. 电影/电视剧周边选择 \"Movies & TV\"\n"
            "10. 原创设计师玩具选择 \"Original/Designer Toys\"\n"
            "11. 如果没有明确对应，返回 \"Mecha Robot\"\n"
            "12. 返回时必须使用与列表中完全相同的名称"
        ),
        "inputFields": [
            {"key": "product_title", "label": "产品标题"},
            {"key": "description_en", "label": "产品描述", "truncate": 200},
        ],
        "defaultValue": "Mecha Robot",
    },
}


# 标签别名，SZ/GD 属性标签不同（如 Company↔Brand、Theme↔Theme[IP]）
LABEL_ALIASES: Dict[str, List[str]] = {
    "Theme": ["Theme"],
    "Hot Categories": ["Hot Categories"],
    "Product Type": ["Product Type"],
    "Company": ["Company", "Brand"],
    "Character": ["Character"],
    "Featured In": ["Featured In"],
    "Size": ["Size"],
    "Scale": ["Scale"],
    "Availability": ["Availability"],
}


def call_deepseek(
    api_key: str,
    config: Dict[str, Any],
    data: Dict[str, str],
    available_options: List[str],
    timeout: int = 30,
) -> str:
    """调用 DeepSeek，返回建议的选项文本。"""
    user_input_parts = []
    for field in config["inputFields"]:
        value = data.get(field["key"], "") or ""
        if field.get("truncate"):
            value = value[: field["truncate"]]
        user_input_parts.append(f"{field['label']}：{value}")

    options_list = "\n".join(
        f"{i + 1}. {opt}" for i, opt in enumerate(available_options)
    )
    user_content = (
        f"{config['userPromptPrefix']}\n\n"
        f"{chr(10).join(user_input_parts)}\n\n"
        f"可选列表（共 {len(available_options)} 个选项）：\n{options_list}\n\n"
        f"{config['rules']}"
    )

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": config["systemPrompt"]},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.01,
        "max_tokens": 50,
        "top_p": 0.1,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    resp = requests.post(DEEPSEEK_URL, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data_json = resp.json()
    return data_json["choices"][0]["message"]["content"].strip()


def decide_availability(data: Dict[str, str]) -> str:
    """按油猴脚本规则决定 Availability。"""
    is_coming = data.get("is_coming", "") == "打开"
    presale_raw = (data.get("presale_price") or "").strip()
    try:
        is_presale = bool(presale_raw) and float(presale_raw) > 0
    except ValueError:
        is_presale = False
    try:
        stock = int((data.get("stock") or "0").strip() or "0")
    except ValueError:
        stock = 0

    if is_presale:
        return "Pre-Order"
    if is_coming:
        return "Coming Soon"
    if stock <= 0:
        return "Sold Out"
    return "In Stock"
