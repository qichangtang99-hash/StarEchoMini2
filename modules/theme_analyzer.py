# -*- coding: utf-8 -*-
"""
响星 mini2.0 - 主题分析与灵感生成模块
三种灵感模式：引星 / 星图 / 流星🎲
mini2.0变化：星图改为3选1（生成7条，用户选3条）
"""

import json
import os
import random
from datetime import datetime
from modules import llm_client
import config


def load_star_map() -> dict:
    """加载星盘（维度框架知识库）"""
    path = os.path.join(config.KNOWLEDGE_BASE_DIR, "dimension_framework.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_dimensions_for_theme(theme: str) -> list:
    """根据主题获取可用维度列表"""
    star_map = load_star_map()
    all_dimensions = star_map.get("所有可用维度", [])
    theme_mapping = star_map.get("主题与维度映射", {})

    if theme in theme_mapping:
        theme_dims = theme_mapping[theme]
        return [d for d in all_dimensions if d["维度名"] in theme_dims]
    else:
        return all_dimensions


def get_cold_dimensions(dimensions: list, top_n: int = 1) -> list:
    """获取冷门维度（使用频次最低的）"""
    sorted_dims = sorted(dimensions, key=lambda d: d.get("使用频次", 0))
    return [d["维度名"] for d in sorted_dims[:top_n]]


def get_random_dimensions(dimensions: list, n: int = 3) -> list:
    """随机抽取n个维度"""
    sample = random.sample(dimensions, min(n, len(dimensions)))
    return [d["维度名"] for d in sample]


def update_dimension_usage(used_dimensions: list):
    """更新维度使用频次"""
    star_map = load_star_map()
    all_dimensions = star_map.get("所有可用维度", [])

    for dim in all_dimensions:
        if dim["维度名"] in used_dimensions:
            dim["使用频次"] = dim.get("使用频次", 0) + 1

    path = os.path.join(config.KNOWLEDGE_BASE_DIR, "dimension_framework.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(star_map, f, ensure_ascii=False, indent=2)


# ============================================================
# 引星模式：成员自定框架，LLM填充知识 → 3条灵感
# ============================================================

def yinxing_generate(theme: str, member_framework: str, ai_play: str,
                     target_audience: str) -> str:
    """引星模式：根据成员框架生成灵感"""
    return llm_client.chat_free_creation(
        theme=theme,
        member_framework=member_framework,
        ai_play=ai_play,
        target_audience=target_audience
    )


# ============================================================
# 星图模式：维度框架全量发散 → 3条灵感 → 3选1
# ============================================================

def xingtu_generate(theme: str, ai_play: str, target_audience: str) -> tuple:
    """
    星图模式：生成3条差异最大且最适配主题的灵感，供用户3选1
    
    Returns:
        (result_text, dim_names) - LLM生成的灵感文本 + 使用的维度列表
    """
    dimensions = get_dimensions_for_theme(theme)
    dim_names = [d["维度名"] for d in dimensions]

    result = llm_client.chat_with_dimensions(
        theme=theme,
        dimensions=dim_names,
        ai_play=ai_play,
        target_audience=target_audience
    )

    # 更新维度使用频次
    update_dimension_usage(dim_names)

    return result, dim_names


# ============================================================
# 流星模式：星火种子+随机维度+自由发散 → 最终推荐1条
# ============================================================

def liuxing_generate(theme: str, starfire: dict, ai_play: str,
                     target_audience: str) -> tuple:
    """
    流星模式：星火种子驱动灵感生成
    
    Args:
        starfire: dict with keys: weather, mood, place, random_word
    
    Returns:
        (result_text, used_dims) - LLM生成的灵感文本 + 使用的维度列表
    """
    today = datetime.now().strftime("%Y年%m月%d日")
    seed_context = f"天气：{starfire.get('weather', '晴天')}，心情：{starfire.get('mood', '平静')}，场景：{starfire.get('place', '森林')}，随机词：{starfire.get('random_word', '蒲公英')}，日期：{today}"

    # 获取维度并随机抽取
    dimensions = get_dimensions_for_theme(theme)
    random_dims = get_random_dimensions(dimensions, n=3)
    cold_dims = get_cold_dimensions(dimensions, top_n=1)
    all_dims = list(dict.fromkeys(random_dims + cold_dims))  # 去重保序

    result = llm_client.chat_meteor(
        theme=theme,
        dimensions=all_dims,
        seed_context=seed_context,
        ai_play=ai_play,
        target_audience=target_audience
    )

    # 更新维度使用频次
    update_dimension_usage(all_dims)

    return result, all_dims


# ============================================================
# 素材库加载
# ============================================================

def load_material_lib() -> dict:
    """加载素材库"""
    path = os.path.join(config.KNOWLEDGE_BASE_DIR, "material_lib.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_font_for_style(style_description: str) -> str:
    """根据风格描述匹配推荐字体"""
    lib = load_material_lib()
    font_map = lib.get("字体与风格映射", {})

    # 关键词匹配
    style_lower = style_description.lower()
    for key, font_name in font_map.items():
        if any(kw in style_lower for kw in key.split("/")):
            return font_name

    # 默认字体
    return "楷体"


def get_material_lib_summary() -> str:
    """获取素材库摘要（供LLM参考）"""
    lib = load_material_lib()

    parts = []

    # 画风风格
    styles = lib.get("D.1画风风格库", {})
    style_names = []
    for category, items in styles.items():
        if isinstance(items, list):
            for item in items:
                style_names.append(item.get("名称", ""))
    if style_names:
        parts.append(f"可用画风：{', '.join(style_names[:15])}")

    # 字体
    fonts = lib.get("D.4字体备用库", [])
    font_names = [f.get("字体名", "") for f in fonts]
    if font_names:
        parts.append(f"可用字体：{', '.join(font_names)}")

    # 景别
    shots = lib.get("D.2镜头景别库", [])
    shot_names = [s.get("名称", "") for s in shots]
    if shot_names:
        parts.append(f"可用景别：{', '.join(shot_names)}")

    # 构图
    composition = lib.get("D.3构图光影色调库", {})
    comp_items = composition.get("构图", [])
    comp_names = [c.get("名称", "") for c in comp_items]
    if comp_names:
        parts.append(f"可用构图：{', '.join(comp_names)}")

    # 光影
    light_items = composition.get("光影", [])
    light_names = [l.get("名称", "") for l in light_items]
    if light_names:
        parts.append(f"可用光影：{', '.join(light_names)}")

    # 色调
    tone_items = composition.get("色调", [])
    tone_names = [t.get("名称", "") for t in tone_items]
    if tone_names:
        parts.append(f"可用色调：{', '.join(tone_names)}")

    return "；".join(parts)
