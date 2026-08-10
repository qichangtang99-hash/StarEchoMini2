# -*- coding: utf-8 -*-
"""
响星 mini2.0 - 提示词撰写模块
2种模版：文生视频（3镜头合并）/ 图生图（主体注入，1镜头）
全中文、字幕由天翼智铃直接生成、风格100%一致
"""

import json
import os
import re
import config
from modules import llm_client
from modules import memory as mem


# ============================================================
# 模版加载
# ============================================================

def load_prompt_templates() -> dict:
    """加载提示词模版库"""
    path = os.path.join(config.KNOWLEDGE_BASE_DIR, "prompt_templates.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"模版列表": [{"名称": "文生视频", "镜头数": 3, "适用场景": "天翼智铃文生视频入口"}]}


def get_all_template_names() -> list:
    """获取所有模版名称列表"""
    templates_data = load_prompt_templates()
    templates = templates_data.get("模版列表", [])
    return [t["名称"] for t in templates]


def get_template(template_name: str) -> dict:
    """根据名称获取模版"""
    templates_data = load_prompt_templates()
    templates = templates_data.get("模版列表", [])

    for t in templates:
        if t["名称"] == template_name:
            return t

    return templates[0] if templates else {}


def get_template_description(template_name: str) -> str:
    """获取模版适用场景描述"""
    t = get_template(template_name)
    return t.get("适用场景", "")


def get_template_shot_count(template_name: str) -> int:
    """获取模版镜头数"""
    t = get_template(template_name)
    return t.get("镜头数", 1)


# ============================================================
# 暗礁校验
# ============================================================

def check_pitfall(prompt: str, theme: str = "") -> list:
    """暗礁校验：检查提示词是否命中避雷规则"""
    warnings = []
    pitfall_path = os.path.join(config.KNOWLEDGE_BASE_DIR, "pitfall_rules.json")

    try:
        with open(pitfall_path, "r", encoding="utf-8") as f:
            pitfall_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return warnings  # 暗礁库不可用时跳过校验

    rules = pitfall_data.get("规则列表", [])
    for rule in rules:
        keywords = rule.get("关键词", [])
        for kw in keywords:
            if kw.lower() in prompt.lower():
                warnings.append(
                    f"[暗礁警告] {rule.get('审核反馈', '未知原因')}"
                )
                break  # 每条规则只警告一次

    return warnings


# ============================================================
# 提示词生成核心
# ============================================================

def generate_prompts_from_inspiration(inspiration: str, template_type: str,
                                       ai_play: str, target_audience: str,
                                       theme: str) -> dict:
    """
    mini2.0核心函数：根据灵感生成完整提示词
    
    Args:
        inspiration: 选中的灵感文本
        template_type: "文生视频" 或 "图生图（主体注入）"
        ai_play: AI玩法描述
        target_audience: 目标人群
        theme: 主题
    
    Returns:
        {
            "prompt_text": str,        # 完整提示词文本
            "pitfall_warnings": list,  # 暗礁警告
            "char_count": int,         # 字数
            "template_type": str       # 模版类型
        }
    """
    # 获取素材库摘要供LLM参考
    from modules.theme_analyzer import get_material_lib_summary
    material_summary = get_material_lib_summary()

    # 调用LLM生成完整提示词
    prompt_text = llm_client.chat_generate_prompts(
        inspiration=inspiration,
        template_type=template_type,
        ai_play=ai_play,
        target_audience=target_audience,
        theme=theme,
        material_lib_summary=material_summary
    )

    # 硬截断：如果LLM不遵守800字限制，自动精简
    char_count = len(prompt_text.replace(" ", "").replace("\n", ""))
    if char_count > 800:
        # 第一轮尝试：让LLM精简到800字以内
        prompt_text = llm_client.chat(
            prompt=f"""以下提示词共{char_count}字，超出800字上限。请精简到800字以内，要求：
1. 删除冗余修饰、重复描述
2. 保留核心画面信息、风格、动作、背景
3. 保持分镜格式不变
4. 风格行完整保留但可精简负面锚定（只保留最关键的2个）
5. 只输出精简后的提示词，不要加任何解释

【原始提示词】
{prompt_text}""",
            system_prompt="你是AI彩铃提示词精简专家。只输出精简后的提示词，绝对不超过800字，不加任何解释。"
        )
        char_count = len(prompt_text.replace(" ", "").replace("\n", ""))

    # 最终保底：如果仍然超800字，硬截断
    if char_count > 800:
        # 逐步从末尾删减，保留格式完整性
        lines = prompt_text.split("\n")
        result_lines = []
        total = 0
        for line in lines:
            line_chars = len(line.replace(" ", ""))
            if total + line_chars <= 800:
                result_lines.append(line)
                total += line_chars
            else:
                break
        prompt_text = "\n".join(result_lines)
        char_count = len(prompt_text.replace(" ", "").replace("\n", ""))

    # 暗礁校验
    warnings = check_pitfall(prompt_text, theme)

    # 字数统计
    char_count = len(prompt_text.replace(" ", "").replace("\n", ""))

    return {
        "prompt_text": prompt_text,
        "pitfall_warnings": warnings,
        "char_count": char_count,
        "template_type": template_type
    }


# ============================================================
# 负面风格约束
# ============================================================

def get_negative_style_hint(theme: str, ai_play: str) -> str:
    """获取负面风格约束提示（带缓存）"""
    return llm_client.get_negative_style_hint(theme, ai_play)


# ============================================================
# 字幕字体匹配
# ============================================================

def match_font_for_style(style_description: str) -> str:
    """根据风格描述自动匹配字体"""
    from modules.theme_analyzer import get_font_for_style
    return get_font_for_style(style_description)


# ============================================================
# 字幕指令生成
# ============================================================

def generate_subtitle_instruction(content: str, font_name: str,
                                  position: str = "画面上方") -> str:
    """
    生成标准字幕指令
    
    Args:
        content: 字幕内容（不超过8字）
        font_name: 字体名
        position: 字幕位置（"画面上方" 或 "画面两侧"）
    
    Returns:
        标准字幕指令字符串
    """
    # 确保字幕不超过8字
    if len(content) > 8:
        content = content[:8]

    return f'配字幕"{content}"；字幕在{position}，{font_name}，笔画清晰不粘连；不要过小、不要不全、不要过大遮挡画面主体'
