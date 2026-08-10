# -*- coding: utf-8 -*-
"""
响星 mini2.0 - LLM API调用模块
支持天翼AI开放平台（星辰自研模型）和 DeepSeek 双API
天翼AI开放平台兼容 OpenAI 协议
"""

import json
import base64
from openai import OpenAI
import config


def _load_avoidance_rules() -> str:
    """从暗礁库的'天翼智铃避坑规则'动态加载规避约束文本，拼成LLM可理解的规则"""
    try:
        pitfall_path = config.KNOWLEDGE_BASE_DIR + "/pitfall_rules.json"
        with open(pitfall_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        rules = data.get("天翼智铃避坑规则", {})
        if not rules:
            return ""
        lines = []
        for rule_name, rule_desc in rules.items():
            lines.append(f"- {rule_desc}")
        return "\n".join(lines)
    except Exception:
        return ""


def _get_avoidance_hint() -> str:
    """获取规避规则的简短提示（用于prompt中嵌入）"""
    return _load_avoidance_rules()


def get_client(provider=None):
    """获取OpenAI兼容客户端（根据provider选择API）"""
    api_config = config.get_api_config(provider)
    api_key = api_config["api_key"]
    if not api_key:
        raise ValueError(f"API Key未配置！请在Streamlit Cloud的Secrets中设置 {api_config['provider'].upper()}_API_KEY，或设置环境变量。")
    return OpenAI(
        api_key=api_key,
        base_url=api_config["base_url"]
    ), api_config["model_name"]


def chat(prompt: str, system_prompt: str = "", provider=None) -> str:
    """
    调用LLM生成回复

    Args:
        prompt: 用户输入的prompt
        system_prompt: 系统提示词（可选）
        provider: API提供商（None=使用默认）

    Returns:
        LLM生成的文本
    """
    client, model_name = get_client(provider)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.8,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[API调用失败] {str(e)}"


# ============================================================
# 彩铃风格边界通用指令（所有灵感生成共用）
# ============================================================

def _build_ringtone_boundary():
    """动态构建彩铃风格边界指令，规避规则从暗礁库读取"""
    avoidance = _get_avoidance_hint()
    avoidance_block = "\n" + avoidance if avoidance else ""
    return f"""【彩铃用户画像与风格边界（必须遵守）】
- 彩铃用户画像：爱音乐的人、喜欢可爱治愈风格、追求生活美好感。不是抖音吐槽党，不是丧文化受众。
- 彩铃本质：十几秒接电话前的休闲娱乐，来电时看到/听到的画面
- 联想方向必须是：积极向上、热爱生活、发现小美好、治愈暖心、可爱有趣、浪漫温馨、轻松幽默、正能量
- 坚决避免：吐槽生活、抱怨工作、消极摆烂、丧文化、躺平、社畜自嘲、职场怨气、人间不值得
- 即使主题带"热梗""表情包"等，也要往"生活里的可爱瞬间""发现身边的美好"方向联想，而非"打工人有多惨"
- 不适合恐怖/怪诞/颓废/压抑/冰冷风格{avoidance_block}"""

_RINGTONE_BOUNDARY = None  # 延迟初始化，改为函数调用

def _get_ringtone_boundary():
    """获取彩铃风格边界指令（每次调用动态读取暗礁库）"""
    avoidance = _get_avoidance_hint()
    avoidance_block = "\n" + avoidance if avoidance else ""
    return f"""【彩铃用户画像与风格边界（必须遵守）】
- 彩铃用户画像：爱音乐的人、喜欢可爱治愈风格、追求生活美好感。不是抖音吐槽党，不是丧文化受众。
- 彩铃本质：十几秒接电话前的休闲娱乐，来电时看到/听到的画面
- 联想方向必须是：积极向上、热爱生活、发现小美好、治愈暖心、可爱有趣、浪漫温馨、轻松幽默、正能量
- 坚决避免：吐槽生活、抱怨工作、消极摆烂、丧文化、躺平、社畜自嘲、职场怨气、人间不值得
- 即使主题带“热梗”“表情包”等，也要往“生活里的可爱瞬间”“发现身边的美好”方向联想，而非“打工人有多惨”
- 不适合恐怖/怪诞/颓废/压抑/冰冷风格{avoidance_block}"""


def _get_system_prompt_base():
    """获取系统提示词基础（每次调用动态读取暗礁库）"""
    avoidance = _get_avoidance_hint()
    if avoidance:
        return f"你是一个AI彩铃策划助手，擅长从多元文化维度发散联想。你深知彩铃用户是爱音乐、喜欢可爱治愈的人，所以联想方向永远是积极向上、热爱生活、发现美好、治愈暖心的，不会走向吐槽抱怨或丧文化。你同时注意以下规避规则：{avoidance}"
    return "你是一个AI彩铃策划助手，擅长从多元文化维度发散联想。你深知彩铃用户是爱音乐、喜欢可爱治愈的人，所以联想方向永远是积极向上、热爱生活、发现美好、治愈暖心的，不会走向吐槽抱怨或丧文化。"


# ============================================================
# 引星模式：成员自定框架，LLM填充知识
# ============================================================

def chat_free_creation(theme: str, member_framework: str, ai_play: str,
                       target_audience: str) -> str:
    """引星模式：按成员提供的框架填充文化知识"""
    prompt = f"""团队成员提供了以下联想框架，请根据这个框架填充具体的文化知识和意象。

主题：{theme}
成员框架：{member_framework}
AI玩法：{ai_play}
目标人群：{target_audience}

要求：
1. 严格按照成员的框架方向填充，不改变框架方向
2. 填充的内容要具体、有画面感
3. 可以引用相关的诗词、典故、哲学观点等文化知识
4. 最终输出格式：主题 → 中间关键词 → 具体意象/表达
5. 生成3条联想链，方向尽量差异明显
6. {_get_ringtone_boundary()}

【输出格式（严格遵守）】
直接输出3条灵感，每条以编号开头，不要写前言、后记、维度说明、总结等额外内容。
格式如下：

1. 主题 → 中间关键词 → 具体意象/表达（一段具体画面描述）
2. 主题 → 中间关键词 → 具体意象/表达（一段具体画面描述）
3. 主题 → 中间关键词 → 具体意象/表达（一段具体画面描述）

只输出这3条，不要输出其他任何内容。"""

    system_prompt = _get_system_prompt_base() + "你尊重成员的创作方向，只补充不改变。"

    return chat(prompt, system_prompt)


# ============================================================
# 星图模式：维度框架全量发散 → 3选1
# ============================================================

def chat_with_dimensions(theme: str, dimensions: list, ai_play: str,
                         target_audience: str) -> str:
    """星图模式：从全部维度中挑选3个最匹配维度，生成3条差异最大且最适配主题的联想链，用户3选1"""
    dimension_text = "\n".join([f"- {d}" for d in dimensions])

    prompt = f"""请围绕【{theme}】主题，从以下维度中挑选**最匹配AI玩法需求且彼此差异最大的3个维度**，每个选定维度各生成一条联想链。

可用维度：
{dimension_text}

AI玩法：{ai_play}
目标人群：{target_audience}

要求：
1. **先从全部维度中选出3个维度**：既要与AI玩法风格最契合，又要彼此差异最大（不同风格、不同感受方向）
2. 选维度的标准：与AI玩法的风格方向最贴合、最能产出可视觉化画面的维度，且3个维度之间风格差异尽可能大
3. 每个维度独立发散，不要互相重复
4. AI玩法中的举例仅为风格参考，请勿围绕该举例发散
5. 联想链格式：主题 → 中间关键词 → 具体意象/表达
6. 3条联想链方向必须差异明显，覆盖不同风格和感受
6. {_get_ringtone_boundary()}

【输出格式（严格遵守）】
直接输出3条灵感，每条以编号开头，不要写前言、后记、维度说明、总结等额外内容。
格式如下：

1. 主题 → 中间关键词 → 具体意象/表达（一段具体画面描述）
2. 主题 → 中间关键词 → 具体意象/表达（一段具体画面描述）
3. 主题 → 中间关键词 → 具体意象/表达（一段具体画面描述）

只输出这3条，不要输出其他任何内容。"""

    system_prompt = _get_system_prompt_base() + "你必须先精准判断哪些维度最匹配用户需求，再针对这些维度生成联想。你选出的3个维度必须彼此差异最大，覆盖不同风格方向。你的联想必须具体、有画面感、可转化为视觉表达。"

    return chat(prompt, system_prompt)


# ============================================================
# 流星模式：星火种子+随机维度+自由发散
# ============================================================

def chat_meteor(theme: str, dimensions: list, seed_context: str,
                ai_play: str, target_audience: str) -> str:
    """流星模式：星火种子+随机维度+自由发散→最终推荐1条"""
    dimension_text = "\n".join([f"- {d}" for d in dimensions])

    prompt = f"""请围绕【{theme}】主题，从以下维度生成联想链，同时让灵感种子的氛围自然渗透进联想方向。

灵感种子（当前氛围）：{seed_context}

可用维度：
{dimension_text}

AI玩法：{ai_play}
目标人群：{target_audience}

要求：
1. 每个维度独立发散，方向尽量差异明显
2. 灵感种子的信息不要直接出现在结果中，而是转化为意境和氛围
3. 联想链格式：主题 → 中间关键词 → 具体意象/表达
4. {_get_avoidance_hint() if _get_avoidance_hint() else '遵守暗礁库规避规则'}

请先按以上维度各生成一条联想链，最后额外生成一条完全自由的联想链（不限定任何维度，自由发散）。

**最重要**：在生成所有联想链之后，请根据「AI玩法」中用户描述的需求方向和风格偏好，从你生成的所有联想链中选出**最匹配用户需求的1条**，单独标注为【最终推荐】。只选1条，选择标准是：与AI玩法风格最契合、画面感最强、最可转化为视觉表达。

{_get_ringtone_boundary()}

【输出格式（严格遵守）】
直接按编号输出各维度的联想链，最后一条为【最终推荐】，不要写前言、后记、维度说明等额外内容。
格式如下：

1. 【维度名】主题 → 中间关键词 → 具体意象/表达（一段具体画面描述）
2. 【维度名】主题 → 中间关键词 → 具体意象/表达（一段具体画面描述）
...
5. 【自由发散】主题 → 中间关键词 → 具体意象/表达（一段具体画面描述）

【最终推荐】第X条：主题 → 中间关键词 → 具体意象/表达（一段具体画面描述）

只输出以上内容，不要输出其他任何内容。"""

    system_prompt = _get_system_prompt_base() + "你擅长在氛围引导下自由联想。你的联想有画面感、有意境、可转化为视觉表达。你会在所有联想中精准选出最匹配用户需求的那一条。"

    return chat(prompt, system_prompt)


# ============================================================
# 提示词生成：大灵感 → 三镜头/单镜头
# ============================================================

def chat_generate_prompts(inspiration: str, template_type: str, ai_play: str,
                          target_audience: str, theme: str,
                          material_lib_summary: str = "") -> str:
    """
    根据灵感生成完整提示词（核心函数）
    
    mini2.0核心变化：
    - 文生视频：1条大灵感 → 3个镜头，合并输出
    - 主体注入：1条灵感 → 1个镜头
    - 全中文，字幕由天翼智铃直接生成
    - 风格100%一致（文生视频3镜头完整复写）
    """
    if template_type == "文生视频":
        template_str = """【分镜1】:
【画面风格】[全中文风格描述+色调+光线+构图+负面风格锚定]
【画面主体】[中文场景/动作描述]
【画面背景】[中文场景描述，包含前景/中景/后景层次]+字幕指令
【运镜方式】[缓慢推进/固定机位/跟随移动/缓慢拉远等]
【环境动态】[风/光/水/雾/花瓣/泡沫等自然动态]

【分镜2】:
【画面风格】[与分镜1完全相同的风格描述，完整复写]
【画面主体】[中文场景/动作描述，不同场景]
【画面背景】[中文场景描述，包含前景/中景/后景层次]+字幕指令
【运镜方式】[缓慢推进/固定机位/跟随移动/缓慢拉远等]
【环境动态】[风/光/水/雾/花瓣/泡沫等自然动态]

【分镜3】:
【画面风格】[与分镜1完全相同的风格描述，完整复写]
【画面主体】[中文场景/动作描述，不同场景]
【画面背景】[中文场景描述，包含前景/中景/后景层次]+字幕指令
【运镜方式】[缓慢推进/固定机位/跟随移动/缓慢拉远等]
【环境动态】[风/光/水/雾/花瓣/泡沫等自然动态]"""

        rules = """核心规则：
1. 3镜头风格行【画面风格】必须完整复写同一组风格描述，一字不差
2. 禁止写"同上"（星小辰会忽略）
3. 3个镜头场景必须完全不同（不同地点/不同时段/不同场景）
4. 每镜只写一个核心动作
5. 字幕不超过8字，字体名必须指定，位置必须指定
6. 字幕格式：配字幕"XX"；字幕在画面上方，XX体，笔画清晰不粘连；不要过小、不要不全、不要过大遮挡画面主体
7. 全中文，不写英文风格词
8. 风格行加负面锚定：明确写不要XX风格
9. 只用配字幕一个指令，不要同时写配文字+字幕
10. 3个镜头总提示词不超过800字，这是硬性上限，超出将截断，请务必精炼用词、删除冗余修饰，确保总字数在800字以内
11. {_get_avoidance_hint() if _get_avoidance_hint() else '遵守暗礁库规避规则'}
12. 每镜字幕内容用引号标注
13. 不要写任何解释、说明、备注，只输出提示词本身，浪费字数
14. 负面风格锚定只写2-3个最关键的，不要罗列过多"""

    else:  # 主体注入
        template_str = """【画面风格】[全中文风格描述+色调+光线+构图]
【画面主体】参考图片中人物的形象，[中文动作/表情/构图描述]
【画面背景】[中文场景描述]"""

        rules = """核心规则：
1. 开头必须加：参考图片中人物的形象
2. 不重复描述人物外观/穿着（由参考图决定）
3. 不写台词/旁白/独白（会变成口型动画）
4. 只描述动作/表情/构图/场景
5. 全中文，不写英文风格词
6. 提示词严格不超过800字，这是硬性上限，超出将截断，请精炼用词
7. {_get_avoidance_hint() if _get_avoidance_hint() else '遵守暗礁库规避规则'}
8. 不要写任何解释、说明、备注，只输出纯提示词"""

    prompt = f"""请根据以下灵感，按模版格式生成完整的提示词。

【灵感方向】
{inspiration}

【模版类型】{template_type}

【AI玩法】
{ai_play}

【目标人群】
{target_audience}

【主题】
{theme}

{f"【可用素材参考】{material_lib_summary}" if material_lib_summary else ""}

【提示词模版格式】
{template_str}

{rules}

请直接输出填充好的完整提示词，不要加任何解释、前言、后记。"""

    system_prompt = """你是一个AI彩铃提示词工程师，擅长将灵感转化为天翼智铃可直接使用的提示词。你必须遵守以下规则：
1. 全中文，不用英文风格词
2. 字幕指令严格按格式：配字幕"XX"；字幕在画面上方，XX体，笔画清晰不粘连；不要过小、不要不全、不要过大遮挡画面主体
3. 文生视频3镜头风格行必须完整复写同一组风格描述
4. 3镜头场景必须完全不同
5. 字幕不超过8字
6. {_get_avoidance_hint() if _get_avoidance_hint() else '遵守暗礁库规避规则'}
7. 总字数严格不超过800字，超出将截断，请精炼用词
8. 风格行加入负面锚定（只写2-3个最关键的）
9. 你深知彩铃用户是爱音乐、喜欢可爱治愈的人，提示词方向永远是积极向上、热爱生活、发现美好
10. 不要写任何解释、说明、备注，只输出纯提示词"""

    return chat(prompt, system_prompt)


# ============================================================
# 负面风格约束生成
# ============================================================

def get_negative_style_hint(theme: str, ai_play: str, provider=None) -> str:
    """根据主题和AI玩法，调用LLM生成负面风格约束提示"""
    prompt = f"""请根据以下主题和AI玩法，判断需要追加的负面风格约束。

主题：{theme}
AI玩法：{ai_play}

彩铃用户画像：爱音乐的人、喜欢可爱治愈风格、追求生活美好感。

彩铃风格边界：
- 适合：积极向上、热爱生活、发现小美好、治愈、温馨、搞笑、可爱、幽默、趣味、浪漫、炫酷、正能量
- 不适合：恐怖、怪诞、颓废、压抑、冰冷、吐槽抱怨、消极摆烂、丧文化、职场怨气
{_get_avoidance_hint()}

请输出一条负面风格约束，格式示例：
"不要恐怖风格、怪诞风格、吐槽抱怨，要搞笑、幽默、热爱生活的可爱风格"

要求：
1. 根据主题判断哪些"不适合"的风格最容易被误触发，加入"不要"约束
2. 根据主题给出正向风格引导（"要xxx风格"），方向是积极向上、热爱生活、发现美好
3. 输出一句话即可，不要加任何解释"""

    system_prompt = "你是一个AI彩铃风格把关专家。你输出的约束简洁精准。"
    result = chat(prompt, system_prompt, provider=provider)
    return result.strip().strip('"').strip("'").strip()


# ============================================================
# 图片理解
# ============================================================

def understand_image(image_path: str, question: str = "请描述这张图片的风格、人物特征、色调和氛围，用于AI彩铃制作参考。", provider=None) -> str:
    """图片理解：使用多模态API分析参考图片"""
    try:
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return f"[图片读取失败] {str(e)}"

    ext = image_path.lower().split(".")[-1]
    mime_map = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}
    mime_type = mime_map.get(ext, "jpeg")

    client, model_name = get_client(provider)
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{mime_type};base64,{image_data}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.5,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[图片理解失败，该模型可能不支持图片输入] {str(e)}"
