# -*- coding: utf-8 -*-
"""
响星 mini2.0 - 网页版主入口（星海主题）
3步流程：输入 → 灵感 → 提示词
运行方式：streamlit run app.py
"""

import streamlit as st
import json
import os
import hashlib
import random
import re as _re
from datetime import datetime

import config
from modules import llm_client
from modules.memory import (
    save_planning, update_template_usage, add_pitfall, delete_pitfall,
    load_pitfall_rules, get_pitfall_rules_list, get_ringtone_boundary,
    get_tianyi_avoidance_rules,
    load_history_index, rebuild_index, index_exists,
    rename_in_index, delete_record, load_record_file,
    save_record_content, update_index_after_edit
)
from modules.theme_analyzer import (
    load_star_map, get_dimensions_for_theme, get_cold_dimensions,
    get_random_dimensions, update_dimension_usage,
    yinxing_generate, xingtu_generate, liuxing_generate,
    get_font_for_style, get_material_lib_summary
)
from modules.storage import sync_pull_all, is_sync_enabled
from modules.prompt_writer import (
    generate_prompts_from_inspiration, check_pitfall,
    get_all_template_names, get_template, get_template_shot_count,
    get_template_description, generate_subtitle_instruction
)

# ============================================================
# GitHub 持久化同步（启动时拉取）
# ============================================================
if "github_sync_done" not in st.session_state:
    try:
        sync_pull_all()
        st.session_state.github_sync_done = True
    except Exception as _e:
        st.session_state.github_sync_done = False
        st.session_state.github_sync_error = str(_e)

# ============================================================
# 页面配置
# ============================================================
st.set_page_config(
    page_title="响星  -  AI彩铃策划",
    page_icon="🌟",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# 工具函数
# ============================================================

def _html_escape(text: str) -> str:
    """将文本中的HTML特殊字符转义"""
    if not text:
        return ""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


def save_step(step_key, label, data):
    """保存当前步骤快照到 session_state.session_steps"""
    if "session_steps" not in st.session_state:
        st.session_state.session_steps = []
    st.session_state.session_steps = [
        s for s in st.session_state.session_steps if s["step_key"] != step_key
    ]
    st.session_state.session_steps.append({
        "step_key": step_key,
        "label": label,
        "data": data,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


def build_synthetic_steps(record):
    """从旧格式记录构建步骤列表（兼容历史数据）"""
    steps = []
    if record.get("主题"):
        steps.append({
            "step_key": "input", "label": "输入需求",
            "data": {
                "theme": record.get("主题", ""),
                "ai_play": record.get("AI玩法", ""),
                "target": record.get("目标人群", ""),
                "template": record.get("提示词模版", ""),
            }
        })
    if record.get("模式"):
        steps.append({
            "step_key": "mode", "label": "选择灵感模式",
            "data": {"mode": record.get("模式", "未知")}
        })
    if record.get("灵感"):
        steps.append({
            "step_key": "inspiration", "label": "灵感结果",
            "data": {"inspiration_result": record.get("灵感", ""), "mode": record.get("模式", "未知")}
        })
    if record.get("提示词"):
        steps.append({
            "step_key": "prompts", "label": "提示词",
            "data": {"prompts": record.get("提示词", {})}
        })
    return steps


def render_step_indicator(steps, current_idx):
    """渲染步骤进度指示器"""
    items = []
    for i, s in enumerate(steps):
        if i == current_idx:
            items.append(f'<span style="color:#90b8f8;font-weight:bold;">● {s["label"]}</span>')
        else:
            items.append(f'<span style="color:#5a6a8a;">○ {s["label"]}</span>')
    html = " → ".join(items)
    st.markdown(f'<div style="text-align:center;font-size:0.85rem;margin:0.5rem 0 1rem;">{html}</div>',
                unsafe_allow_html=True)


def render_step_content(step_key, data):
    """渲染某个步骤的内容（历史查看用，只读）"""
    if step_key == "input":
        st.markdown("#### 📥 输入需求")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**主题**：{data.get('theme', '')}")
            st.markdown(f"**提示词模版**：{data.get('template', '')}")
        with c2:
            st.markdown(f"**AI玩法**：{data.get('ai_play', '')}")
            st.markdown(f"**目标人群**：{data.get('target', '')}")

    elif step_key == "mode":
        mode = data.get("mode", "未知")
        _mi = _MODE_ICON.get(mode, "")
        _mi_html = f'<img src="{_mi}" style="height:1.1em;vertical-align:middle;margin-right:4px;">' if _mi else ''
        st.markdown(f"#### {_mi_html} 选择灵感模式：**{mode}**", unsafe_allow_html=True)
        if mode == "流星" and data.get("starfire"):
            sf = data["starfire"]
            st.markdown(f"**星火种子**：🌤 {sf.get('weather', '')}  -  💭 {sf.get('mood', '')}  -  🌲 {sf.get('place', '')}  -  🎲 {sf.get('random_word', '')}")
        elif mode == "引星" and data.get("member_framework"):
            st.markdown(f"**联想框架**：{data['member_framework']}")

    elif step_key == "inspiration":
        st.markdown("#### 💡 灵感结果")
        mode = data.get("mode", "")
        if mode:
            _mi = _MODE_ICON.get(mode, "")
            _mi_html = f'<img src="{_mi}" style="height:1.1em;vertical-align:middle;margin-right:4px;">' if _mi else ''
            st.markdown(f"{_mi_html} 模式：**{mode}**", unsafe_allow_html=True)
        st.markdown(f'<div class="result-box">{_html_escape(data.get("inspiration_result", ""))}</div>', unsafe_allow_html=True)

    elif step_key == "prompts":
        st.markdown("#### 📝 提示词")
        prompt_data = data.get("prompts", data)
        if isinstance(prompt_data, dict):
            prompt_text = prompt_data.get("prompt_text", "")
            if prompt_text:
                st.code(prompt_text, language=None)
            warnings = prompt_data.get("pitfall_warnings", [])
            for w in warnings:
                st.warning(f"⚠ {w}")
            # 显示模版类型和字数（如有）
            if prompt_data.get("template_type"):
                st.caption(f"模版：{prompt_data['template_type']}")
            if prompt_data.get("char_count"):
                st.caption(f"字数：{prompt_data['char_count']}/800")
        else:
            st.code(str(prompt_data), language=None)

    else:
        st.json(data)


def _parse_inspiration_items(text: str) -> list:
    """将灵感文本解析为结构化列表"""
    import re
    items = []
    lines = text.split("\n")
    current_title = None
    current_content_lines = []

    # 标准编号+维度：1.【维度名】xxx
    standard_pattern = re.compile(r'^\s*(\d+)[\.\、\)\）]\s*【[^】]+】')
    # 最终推荐标记
    recommend_pattern = re.compile(r'^\s*【最终推荐】')
    # 通用编号/符号标题行
    general_title_pattern = re.compile(
        r'^(\s*(\d+[\.\、\)\）])|'
        r'([一二三四五六七八九十百千]+[\.\、\)\）])|'
        r'([●◆■★☆▸►→])|'
        r'(-\s)|(\*\s))'
    )
    # 纯编号行（无特殊符号）：如 "1. xxx" "2. xxx"
    simple_number_pattern = re.compile(r'^\s*(\d+)[\.\、\)\）]\s*\S')
    # 包含【】的行（维度名等）
    bracket_pattern = re.compile(r'^\s*【[^】]+】')

    def _is_title_line(s):
        if standard_pattern.match(s):
            return True
        if recommend_pattern.match(s):
            return True
        if general_title_pattern.match(s):
            return True
        if bracket_pattern.match(s):
            return True
        if simple_number_pattern.match(s):
            return True
        return False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_title:
                current_content_lines.append("")
            continue

        if _is_title_line(stripped):
            if current_title:
                items.append({
                    "title": current_title,
                    "content": "\n".join(current_content_lines).strip()
                })
            current_title = stripped
            current_content_lines = []
        else:
            if current_title:
                current_content_lines.append(stripped)

    if current_title:
        items.append({
            "title": current_title,
            "content": "\n".join(current_content_lines).strip()
        })

    # Fallback 1: 如果无编号解析成功，尝试按空行分段
    if not items:
        paragraphs = re.split(r'\n{2,}', text.strip())
        for i, para in enumerate(paragraphs):
            para = para.strip()
            if para:
                first_line = para.split('\n', 1)[0]
                items.append({
                    "title": first_line[:60],
                    "content": para
                })

    # Fallback 2: 仍然为空，整段作为一个条目
    if not items:
        items.append({"title": text[:30] + "..." if len(text) > 30 else text, "content": text})

    return items


# ============================================================
# 星空水彩主题样式
# ============================================================
import base64 as _b64

_b64_cache = {}

def _img_to_base64_url(filepath):
    """将图片文件编码为base64 data URL，带缓存"""
    if filepath in _b64_cache:
        return _b64_cache[filepath]
    if os.path.exists(filepath):
        with open(filepath, "rb") as f:
            img_data = _b64.b64encode(f.read()).decode()
        ext = os.path.splitext(filepath)[1].lower()
        mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
        url = f"data:{mime};base64,{img_data}"
        _b64_cache[filepath] = url
        return url
    return None


def _load_bg_image(mode=None):
    """根据当前模式加载对应背景图"""
    bg_map = {
        "引星": "bg_yinxing.png",
        "星图": "bg_xingtu.png",
        "流星": "bg_liuxing.png",
    }
    if mode and mode in bg_map:
        bg_file = bg_map[mode]
    else:
        bg_file = "bg.png"
    bg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", bg_file)
    result = _img_to_base64_url(bg_path)
    if result:
        return result
    return None


def _load_static_image(filename):
    """加载static目录下图片为base64 URL"""
    img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", filename)
    return _img_to_base64_url(img_path)


# 动态背景
_current_step = st.session_state.get("step", 1)
_current_mode = st.session_state.get("mode", None)
if isinstance(_current_step, int) and _current_step <= 2:
    _bg_url = _load_bg_image(mode=None)
else:
    _bg_url = _load_bg_image(mode=_current_mode)

if _bg_url:
    _bg_css = f"background-image: url('{_bg_url}') !important; background-size: cover !important; background-position: center top !important; background-attachment: fixed !important; background-repeat: no-repeat !important;"
else:
    _bg_css = "background: linear-gradient(160deg, #0a1430, #0f1e4a, #081230) !important;"

st.markdown(f"""
<style>
    /* ========== 顶部工具栏（透明，不挡展开按钮） ========== */
    header[data-testid="stHeader"] {{
        background: transparent !important;
        min-height: 0 !important;
        padding: 0 !important;
    }}
    /* 顶部工具栏内所有按钮（侧边栏展开/收回）统一放大 */
    header[data-testid="stHeader"] button {{
        width: 48px !important;
        height: 48px !important;
        min-width: 48px !important;
        min-height: 48px !important;
        border-radius: 12px !important;
        background: rgba(15, 25, 55, 0.85) !important;
        border: 2px solid rgba(120, 160, 220, 0.40) !important;
        box-shadow: 0 2px 12px rgba(0,0,0,0.3) !important;
        margin: 4px !important;
    }}
    header[data-testid="stHeader"] button svg {{
        width: 24px !important;
        height: 24px !important;
    }}

    /* ========== 侧边栏分隔线隐藏 ========== */
    [data-testid="stSidebar"] > div:first-child {{
        border-right: none !important;
        box-shadow: none !important;
    }}
    section[data-testid="stSidebar"] {{
        border-right: none !important;
        box-shadow: none !important;
    }}
    /* 侧边栏内部容器可能产生的分隔线/阴影 */
    [data-testid="stSidebar"] > div:first-child::after,
    section[data-testid="stSidebar"] > div:first-child::after {{
        display: none !important;
        border: none !important;
        box-shadow: none !important;
    }}
    /* 针对 Streamlit 1.38+ 版本可能的 DOM 结构 */
    [data-testid="stSidebar"][aria-expanded="true"] > div:first-child,
    [data-testid="stSidebar"][aria-expanded="false"] > div:first-child {{
        border-right: none !important;
        box-shadow: none !important;
    }}

    /* ========== 全局背景 ========== */
    .stApp {{
        {_bg_css}
        color: #e8f0ff;
    }}
    .stApp::before {{
        content: '';
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(8, 16, 40, 0.55);
        pointer-events: none;
        z-index: 0;
    }}
    .stApp > * {{ position: relative; z-index: 1; }}

    /* ========== Logo ========== */
    .sidebar-logo {{
        width: 80px;
        height: 80px;
        border-radius: 16px;
        margin: 0 auto 0.5rem auto;
        display: block;
        mix-blend-mode: screen;
    }}

    /* ========== 启动弹窗 ========== */
    .splash-overlay {{
        position: fixed; inset: 0;
        background: rgba(6, 12, 30, 0.85);
        z-index: 99999;
        display: flex; align-items: center; justify-content: center;
        animation: splashFadeOut 1s ease-in-out 3.5s forwards;
        pointer-events: none;
    }}
    .splash-box {{
        background: linear-gradient(135deg, rgba(15, 25, 55, 0.95), rgba(20, 35, 70, 0.95));
        border: 1px solid rgba(120, 160, 220, 0.25);
        border-radius: 20px;
        padding: 24px 28px 18px 28px;
        text-align: center;
        box-shadow: 0 12px 48px rgba(0, 0, 0, 0.5), 0 0 80px rgba(80, 130, 220, 0.12);
        max-width: 520px; width: 90vw;
    }}
    .splash-image {{ width: 100%; border-radius: 12px; margin-bottom: 12px; }}
    .splash-title {{
        font-size: 1.6rem; font-weight: 800;
        background: linear-gradient(135deg, #90b8f8, #c8d8ff, #f0d0e8);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        letter-spacing: 2px; margin-bottom: 4px;
    }}
    .splash-sub {{ font-size: 0.8rem; color: #6a7a9a !important; letter-spacing: 3px; }}
    .splash-loading {{
        margin-top: 14px; height: 3px;
        background: rgba(120, 160, 220, 0.15);
        border-radius: 3px; overflow: hidden;
    }}
    .splash-loading-bar {{
        height: 100%; width: 0%;
        background: linear-gradient(90deg, #5080c0, #90b8f8);
        border-radius: 3px;
        animation: splashLoading 3s ease-in-out forwards;
    }}
    @keyframes splashFadeOut {{ 0% {{ opacity: 1; }} 80% {{ opacity: 1; }} 100% {{ opacity: 0; visibility: hidden; }} }}
    @keyframes splashLoading {{ 0% {{ width: 0%; }} 60% {{ width: 70%; }} 100% {{ width: 100%; }} }}

    /* ========== 模式卡片 ========== */
    .mode-illustration {{ width: 100%; max-height: 180px; object-fit: contain; margin-bottom: 0.8rem; border-radius: 12px; }}
    .func-icon {{ width: 22px; height: 22px; vertical-align: middle; margin-right: 6px; border-radius: 4px; }}

    /* ========== 侧边栏 ========== */
    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, rgba(10, 20, 50, 0.88) 0%, rgba(15, 30, 60, 0.85) 50%, rgba(8, 18, 45, 0.90) 100%) !important;
        border-right: 1px solid rgba(120, 160, 220, 0.15) !important;
        backdrop-filter: blur(12px);
    }}
    section[data-testid="stSidebar"] > div {{ overflow-y: auto !important; max-height: 100vh !important; }}
    section[data-testid="stSidebar"] * {{ color: #c8d8f8 !important; }}
    section[data-testid="stSidebar"] .stButton > button {{
        background: rgba(100, 150, 220, 0.15);
        border: 1px solid rgba(120, 160, 220, 0.25);
        color: #a0c0f0 !important;
        border-radius: 8px;
    }}
    section[data-testid="stSidebar"] .stButton > button:hover {{
        background: rgba(100, 150, 220, 0.30);
        border-color: rgba(120, 160, 220, 0.50);
    }}

    /* ========== 文字 ========== */
    h1, h2, h3, h4, h5, h6, .main-title {{ color: #e8f0ff !important; }}
    p, span, label, .stMarkdown {{ color: #c8d8f0 !important; }}
    .stCaption {{ color: #8898b8 !important; }}

    /* ========== 主标题 ========== */
    .hero-title {{
        font-size: 3rem; font-weight: 800; text-align: center;
        background: linear-gradient(135deg, #90b8f8 0%, #c8d8ff 40%, #f0d0e8 80%, #90b8f8 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem; letter-spacing: 2px;
    }}
    .hero-sub {{
        text-align: center; color: #8898c0 !important;
        font-size: 1rem; margin-bottom: 2rem; letter-spacing: 4px;
    }}

    /* ========== 步骤徽章 ========== */
    .step-badge {{
        display: inline-block;
        background: linear-gradient(135deg, #5880c8, #78a8e8);
        color: white !important;
        border-radius: 50%; width: 28px; height: 28px;
        text-align: center; line-height: 28px;
        font-weight: bold; margin-right: 8px; font-size: 0.85rem;
    }}

    /* ========== 卡片 ========== */
    .mode-card {{
        background: linear-gradient(135deg, rgba(20, 35, 70, 0.70), rgba(30, 50, 90, 0.50));
        border: 1px solid rgba(120, 160, 220, 0.20);
        border-radius: 16px; padding: 1.8rem 1.2rem; text-align: center;
        backdrop-filter: blur(10px); transition: all 0.3s ease;
    }}
    .mode-card:hover {{
        border-color: rgba(120, 160, 220, 0.45);
        transform: translateY(-2px);
        box-shadow: 0 6px 24px rgba(80, 130, 220, 0.15);
    }}
    .mode-icon {{ font-size: 2.5rem; margin-bottom: 0.5rem; }}
    .mode-title {{ font-size: 1.4rem; font-weight: 700; color: #c8d8f8 !important; margin-bottom: 0.3rem; }}
    .mode-desc {{ font-size: 0.85rem; color: #8898b8 !important; margin-bottom: 1rem; }}
    .mode-tag {{
        display: inline-block;
        background: rgba(100, 150, 220, 0.12);
        border: 1px solid rgba(120, 160, 220, 0.22);
        border-radius: 20px; padding: 2px 12px;
        font-size: 0.75rem; color: #a0c0f0 !important;
    }}

    /* ========== 结果框 ========== */
    .result-box {{
        background: linear-gradient(135deg, rgba(20, 35, 70, 0.55), rgba(30, 50, 90, 0.40));
        border: 1px solid rgba(120, 160, 220, 0.18);
        border-left: 4px solid #6a9ae0;
        border-radius: 8px; padding: 1.5rem; margin: 0.5rem 0;
        color: #c8d8f0; line-height: 1.8; white-space: pre-wrap;
    }}

    /* ========== 输入框 ========== */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stTextArea textarea,
    [data-testid="stTextArea"] textarea {{
        background: rgba(15, 25, 55, 0.60) !important;
        border: 1px solid rgba(120, 160, 220, 0.25) !important;
        color: #ffffff !important; border-radius: 8px !important;
    }}
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus,
    .stTextArea textarea:focus,
    [data-testid="stTextArea"] textarea:focus {{
        border-color: rgba(120, 160, 220, 0.50) !important;
        box-shadow: 0 0 0 2px rgba(100, 150, 220, 0.15) !important;
    }}
    .stTextInput > div > div > input::placeholder,
    .stTextArea > div > div > textarea::placeholder,
    .stTextArea textarea::placeholder,
    [data-testid="stTextArea"] textarea::placeholder {{ color: #7a8ab0 !important; }}
    .stSelectbox div[data-baseweb="select"] > div {{
        background: rgba(15, 25, 55, 0.60) !important;
        color: #ffffff !important;
        border: 1px solid rgba(120, 160, 220, 0.25) !important;
        border-radius: 8px !important;
    }}
    .stRadio label, .stRadio label div {{ color: #c8d8f0 !important; }}

    /* ========== 按钮 ========== */
    .stButton > button {{
        background: linear-gradient(135deg, #5080c0, #6aa0e0) !important;
        border: none !important; color: white !important;
        border-radius: 8px !important; transition: all 0.3s ease;
    }}
    .stButton > button:hover {{
        background: linear-gradient(135deg, #6a9ae0, #88b8f8) !important;
        box-shadow: 0 4px 16px rgba(80, 130, 220, 0.30);
    }}
    [data-testid="stSidebar"] .stButton > button {{
        background: rgba(100, 150, 220, 0.15) !important;
        border: 1px solid rgba(120, 160, 220, 0.25) !important;
        color: #a0c0f0 !important;
    }}

    /* ========== 分隔线/代码/Alert ========== */
    hr {{ border-color: rgba(120, 160, 220, 0.15) !important; }}
    code {{
        background: rgba(15, 25, 55, 0.60) !important;
        border: 1px solid rgba(120, 160, 220, 0.15) !important;
        color: #c8d8f0 !important; border-radius: 6px !important;
    }}
    pre {{
        background: rgba(10, 20, 50, 0.70) !important;
        border: 1px solid rgba(120, 160, 220, 0.15) !important;
        border-radius: 8px !important; color: #c8d8f0 !important;
    }}
    .stAlert {{
        background: rgba(15, 25, 55, 0.50) !important;
        border: 1px solid rgba(120, 160, 220, 0.20) !important;
    }}

    /* ========== 侧边栏记录列表 ========== */
    .rec-item {{
        background: rgba(15, 25, 55, 0.40);
        border: 1px solid rgba(120, 160, 220, 0.15);
        border-radius: 8px; padding: 0.5rem 0.8rem; margin: 0.3rem 0;
        cursor: pointer; transition: all 0.2s;
    }}
    .rec-item:hover {{
        border-color: rgba(120, 160, 220, 0.40);
        background: rgba(15, 25, 55, 0.60);
    }}
    .rec-name {{ font-size: 0.9rem; color: #c8d8f0; font-weight: 600; }}
    .rec-meta {{ font-size: 0.75rem; color: #6a7a9a; }}

    /* ========== 暗礁库面板 ========== */
    .pitfall-item {{
        background: rgba(15, 25, 55, 0.40);
        border: 1px solid rgba(120, 160, 220, 0.15);
        border-radius: 8px; padding: 0.5rem 0.8rem; margin: 0.3rem 0;
    }}
    .pitfall-category {{
        display: inline-block;
        background: rgba(100, 150, 220, 0.12);
        border: 1px solid rgba(120, 160, 220, 0.22);
        border-radius: 12px; padding: 1px 8px;
        font-size: 0.7rem; color: #a0c0f0 !important;
    }}

    /* ========== 加载弹窗 ========== */
    .loading-overlay {{
        position: fixed;
        inset: 0;
        background: rgba(6, 12, 30, 0.80);
        z-index: 99998;
        display: flex;
        align-items: center;
        justify-content: center;
        pointer-events: all;
    }}
    .loading-card {{
        background: linear-gradient(135deg, rgba(15, 25, 55, 0.97), rgba(20, 35, 70, 0.97));
        border: 1px solid rgba(120, 160, 220, 0.30);
        border-radius: 20px;
        padding: 28px 32px;
        text-align: center;
        box-shadow: 0 12px 48px rgba(0, 0, 0, 0.5), 0 0 80px rgba(80, 130, 220, 0.12);
        max-width: 360px;
        width: 85vw;
    }}
    .loading-icon {{
        width: 72px;
        height: 72px;
        margin: 0 auto 16px auto;
        animation: loadingPulse 2s ease-in-out infinite;
    }}
    .loading-title {{
        font-size: 1.2rem;
        font-weight: 700;
        color: #c8d8ff;
        margin-bottom: 6px;
    }}
    .loading-sub {{
        font-size: 0.85rem;
        color: #6a7a9a;
        margin-bottom: 18px;
    }}
    .loading-bar-track {{
        height: 6px;
        background: rgba(120, 160, 220, 0.15);
        border-radius: 6px;
        overflow: hidden;
    }}
    .loading-bar-fill {{
        height: 100%;
        background: linear-gradient(90deg, #5080c0, #90b8f8);
        border-radius: 6px;
        transition: width 0.4s ease;
    }}
    @keyframes loadingPulse {{
        0%, 100% {{ transform: scale(1); opacity: 0.9; }}
        50% {{ transform: scale(1.08); opacity: 1; }}
    }}
    @keyframes loadingBarProgress {{
        0% {{ width: 0%; }}
        15% {{ width: 15%; }}
        35% {{ width: 35%; }}
        60% {{ width: 60%; }}
        85% {{ width: 85%; }}
        100% {{ width: 100%; }}
    }}
    .loading-bar-fill-animated {{
        height: 100%;
        background: linear-gradient(90deg, #5080c0, #90b8f8);
        border-radius: 6px;
        animation: loadingBarProgress 12s ease-in-out forwards;
    }}
</style>
""", unsafe_allow_html=True)

# ============================================================
# 静态文件路径辅助
# ============================================================
_static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

def _static_path(filename):
    """返回static目录下文件的绝对路径"""
    p = os.path.join(_static_dir, filename)
    return p if os.path.exists(p) else None

# ============================================================
# 预加载小图标base64
# ============================================================
_logo_b64 = _load_static_image("logo_small.png")
_icon_b64_map = {
    "引星自定": _load_static_image("icons/01_引星自定_透明背景.png"),
    "星图不迷": _load_static_image("icons/02_星图不迷_透明背景.png"),
    "流星天降": _load_static_image("icons/03_流星天降_透明背景.png"),
    "暗礁不触": _load_static_image("icons/04_暗礁不触_透明背景.png"),
    "星火点亮": _load_static_image("icons/05_星火点亮_透明背景.png"),
}
# 模式自定义图标（用于模式卡片、标题、历史记录）
_MODE_ICON = {
    "引星": _load_static_image("icons/01_引星自定_透明背景.png"),
    "星图": _load_static_image("icons/02_星图不迷_透明背景.png"),
    "流星": _load_static_image("icons/03_流星天降_透明背景.png"),
}
_cover_b64 = _load_static_image("cover_small.jpg")

# ============================================================
# 启动弹窗（Splash Screen）
# ============================================================
if "splash_shown" not in st.session_state:
    st.session_state.splash_shown = True
    if _cover_b64:
        st.markdown(f"""
        <div id="splash-overlay" style="position:fixed;inset:0;background:rgba(6,12,30,0.85);z-index:99999;display:flex;align-items:center;justify-content:center;animation:splashFadeOut 1s ease-in-out 3.5s forwards;pointer-events:none;">
            <div style="background:linear-gradient(135deg,rgba(15,25,55,0.95),rgba(20,35,70,0.95));border:1px solid rgba(120,160,220,0.25);border-radius:20px;padding:24px 28px 18px 28px;text-align:center;box-shadow:0 12px 48px rgba(0,0,0,0.5),0 0 80px rgba(80,130,220,0.12);max-width:520px;width:90vw;">
                <img src="{_cover_b64}" style="width:100%;border-radius:12px;margin-bottom:12px;">
                <div style="font-size:1.6rem;font-weight:800;background:linear-gradient(135deg,#90b8f8,#c8d8ff,#f0d0e8);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:2px;">响星</div>
                <div style="font-size:0.8rem;color:#6a7a9a;letter-spacing:3px;">A I 彩 铃 策 划  -  mini2.0</div>
                <div style="margin-top:14px;height:3px;background:rgba(120,160,220,0.15);border-radius:3px;overflow:hidden;">
                    <div style="height:100%;background:linear-gradient(90deg,#5080c0,#90b8f8);border-radius:3px;animation:splashLoading 3s ease-in-out forwards;"></div>
                </div>
            </div>
        </div>
        <script>
            setTimeout(function() {{
                var el = document.getElementById('splash-overlay');
                if (el) el.remove();
            }}, 4500);
        </script>
        """, unsafe_allow_html=True)

# ============================================================
# 状态重置
# ============================================================

def _reset_all_state():
    """彻底重置所有策划流程相关的session_state"""
    st.session_state.step = 1
    st.session_state.user_input = {}
    st.session_state.inspiration_result = ""
    st.session_state.generated_prompt = None
    st.session_state.session_steps = []
    st.session_state.viewing_record = None
    st.session_state.viewing_step_idx = 0
    st.session_state.renaming_id = None
    st.session_state.deleting_id = None
    for key in ["mode", "starfire", "member_framework",
                "chosen_inspiration", "planning_saved",
                "planning_saved_hash",
                "negative_style_hint", "show_pitfall_form",
                "history_expanded", "pitfall_tab",
                "selected_inspirations"]:
        st.session_state.pop(key, None)

# ============================================================
# Session State 初始化
# ============================================================
if "step" not in st.session_state:
    st.session_state.step = 1
if "user_input" not in st.session_state:
    st.session_state.user_input = {}
if "inspiration_result" not in st.session_state:
    st.session_state.inspiration_result = ""
if "generated_prompt" not in st.session_state:
    st.session_state.generated_prompt = None
if "session_steps" not in st.session_state:
    st.session_state.session_steps = []
if "viewing_record" not in st.session_state:
    st.session_state.viewing_record = None
if "viewing_step_idx" not in st.session_state:
    st.session_state.viewing_step_idx = 0
if "renaming_id" not in st.session_state:
    st.session_state.renaming_id = None
if "deleting_id" not in st.session_state:
    st.session_state.deleting_id = None

# ============================================================
# 侧边栏
# ============================================================

with st.sidebar:
    # Logo
    if _logo_b64:
        st.markdown(f'<img src="{_logo_b64}" class="sidebar-logo">', unsafe_allow_html=True)
    st.markdown("### 响星")
    st.caption("AI彩铃策划 mini2.0")
    st.divider()
    st.markdown("**响星导航，星盘指路**")
    # 功能图标竖排
    for _func_name, _icon_b64 in _icon_b64_map.items():
        if _icon_b64:
            st.markdown(f'<div style="display:flex;align-items:center;margin:0.3rem 0;"><img src="{_icon_b64}" class="func-icon"><span style="color:#c8d8f0;font-size:0.9rem;">{_func_name}</span></div>', unsafe_allow_html=True)
        else:
            st.markdown(f"- {_func_name}")
    st.divider()

    # API提供商：灵感+提示词阶段固定用DeepSeek
    st.caption("API：DeepSeek")
    st.caption("天翼AI仅用于后续生成视频")

    # GitHub同步状态
    if st.session_state.get("github_sync_done"):
        st.caption("\U0001f4e6 数据已同步GitHub")
    else:
        _sync_err = st.session_state.get("github_sync_error", "")
        if _sync_err:
            st.caption(f"\u26a0\ufe0f GitHub同步失败")

    st.divider()

    if st.button("🔄 重新开始", use_container_width=True):
        _reset_all_state()
        st.rerun()

    # ---- 暗礁库（直接打开查看） ----
    st.divider()
    _pitfall_tab = st.expander("🪨 暗礁库", expanded=False)
    with _pitfall_tab:
        _pitfall_rules = get_pitfall_rules_list()
        if not _pitfall_rules:
            st.caption("暂无暗礁规则")
        else:
            for _pi, _pr in enumerate(_pitfall_rules):
                with st.container():
                    st.markdown(f'<div class="pitfall-item">', unsafe_allow_html=True)
                    _cat = _pr.get("归类", "未分类")
                    st.markdown(f'<span class="pitfall-category">{_cat}</span>', unsafe_allow_html=True)
                    st.caption(f"[{_pr.get('主题', '通用')}] {_pr.get('审核反馈', '')}")
                    _del_col1, _del_col2 = st.columns([4, 1])
                    with _del_col2:
                        if st.button("🗑", key=f"del_pitfall_{_pi}", help="删除此条"):
                            delete_pitfall(_pi)
                            st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)

        # 添加新暗礁
        st.markdown("---")
        st.markdown("**添加暗礁**")
        _new_pf_theme = st.text_input("关联主题", placeholder="如：通用、心情", key="new_pf_theme")
        _new_pf_feedback = st.text_input("反馈内容", placeholder="如：不允许出现外语", key="new_pf_feedback")
        _new_pf_category = st.selectbox("归类", ["风格约束", "内容违规", "文化合规", "结构约束", "格式问题", "其他"], key="new_pf_category")
        if st.button("✅ 添加暗礁", key="add_pitfall_btn", use_container_width=True):
            if _new_pf_feedback.strip():
                add_pitfall(theme=_new_pf_theme or "通用", feedback=_new_pf_feedback,
                           category=_new_pf_category, member="匿名")
                st.success("暗礁已添加！")
                st.rerun()
            else:
                st.warning("请输入反馈内容")

    # ---- 生成记录 ----
    st.divider()
    _history_index = load_history_index()
    if not _history_index and not index_exists():
        _cnt = rebuild_index()
        if _cnt > 0:
            _history_index = load_history_index()

    if not _history_index:
        st.markdown("#### 📋 生成记录")
        st.caption("暂无记录")
    else:
        if "history_expanded" not in st.session_state:
            st.session_state.history_expanded = False

        _records_rev = list(reversed(_history_index))
        _show_count = len(_records_rev) if st.session_state.history_expanded else 1

        _title_col, _toggle_col = st.columns([4, 1])
        with _title_col:
            st.markdown("#### 📋 生成记录")
        with _toggle_col:
            if len(_records_rev) > 1:
                _toggle_icon = "▼" if st.session_state.history_expanded else "▶"
                _toggle_label = f"{_toggle_icon} {len(_records_rev)}"
                if st.button(_toggle_label, key="toggle_history", use_container_width=True):
                    st.session_state.history_expanded = not st.session_state.history_expanded
                    st.rerun()

        for _ri, _rec in enumerate(_records_rev[:_show_count]):
            _rec_id = _rec["id"]
            _rec_label = f"{_rec['name']}（{_rec['mode']}）"

            if st.session_state.get("renaming_id") == _rec_id:
                _new_name = st.text_input("新名称", value=_rec.get("name", ""), key=f"rename_{_ri}")
                _rc1, _rc2 = st.columns(2)
                with _rc1:
                    if st.button("✅ 确认", key=f"confirm_rename_{_ri}", use_container_width=True):
                        rename_in_index(_rec_id, _new_name)
                        st.session_state.renaming_id = None
                        st.rerun()
                with _rc2:
                    if st.button("取消", key=f"cancel_rename_{_ri}", use_container_width=True):
                        st.session_state.renaming_id = None
                        st.rerun()
            else:
                _col_name, _col_edit = st.columns([3, 1])
                with _col_name:
                    if st.button(_rec_label, key=f"rec_btn_{_ri}", use_container_width=True):
                        st.session_state.viewing_record = _rec_id
                        st.session_state.viewing_step_idx = 999
                        st.session_state.step = "view_record"
                        st.rerun()
                with _col_edit:
                    if st.button("✏️", key=f"edit_btn_{_ri}", use_container_width=True):
                        st.session_state.renaming_id = _rec_id
                        st.rerun()

# ============================================================
# Step 1: 输入需求
# ============================================================
if st.session_state.step == 1:
    st.markdown('<p class="hero-title">响星</p>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">A I 彩 铃 策 划  -  响 星 导 航  -  星 盘 指 路</p>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### <span class='step-badge'>1</span> 输入本期需求", unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        theme = st.text_input("🎯 主题", placeholder="如：心情、节日、悦己")
        input_type = st.selectbox("📥 输入类型", ["文字", "图片", "文字+图片"])
        _template_names = get_all_template_names()
        prompt_template = st.selectbox("📝 提示词模版", _template_names,
                                       index=0,
                                       help="文生视频：天翼智铃文生视频入口，固定3镜头\n图生图：天翼智铃主体注入入口，1镜头")
        _template_desc = get_template_description(prompt_template)
        st.caption(f"{_template_desc}")
        _shot_count = get_template_shot_count(prompt_template)
        st.caption(f"镜头数：{_shot_count}")

    with col2:
        ai_play = st.text_input("🎨 AI玩法", placeholder="如：文生视频，治愈系文字独白，心情感受，整体风格文艺治愈")
        target_gender = st.selectbox("👤 目标性别", ["不限", "女性", "男性"])
        target_age = st.text_input("🎂 目标年龄段", placeholder="如：20-30岁", value="20-30岁")

    image_path = None
    if input_type in ["图片", "文字+图片"]:
        image_path = st.text_input("🖼 参考图片路径", placeholder="粘贴图片的完整路径")

    st.markdown("---")
    if st.button("✅ 确认需求，开始策划", type="primary", use_container_width=True):
        if not theme:
            st.error("请至少填写主题！")
        elif not ai_play:
            st.error("请填写AI玩法描述！")
        else:
            st.session_state.user_input = {
                "theme": theme,
                "input_type": input_type,
                "ai_play": ai_play,
                "target_gender": target_gender,
                "target_age": target_age,
                "prompt_template": prompt_template,
                "image_path": image_path
            }
            save_step("input", "输入需求", dict(st.session_state.user_input))
            st.session_state.session_steps = [st.session_state.session_steps[-1]]
            st.session_state.step = 2
            st.rerun()

# ============================================================
# Step 2: 选择灵感模式
# ============================================================
elif st.session_state.step == 2:
    ui = st.session_state.user_input
    st.markdown(f"### <span class='step-badge'>2</span> 选择灵感模式", unsafe_allow_html=True)
    st.caption(f"当前主题：**{ui['theme']}**  -  目标人群：**{ui['target_gender']}，{ui['target_age']}**  -  模版：**{ui['prompt_template']}**")

    st.markdown("---")

    col1, col2, col3 = st.columns(3)

    with col1:
        _illust_yx_p = _static_path("illust_yinxing.png")
        if _illust_yx_p:
            st.image(_illust_yx_p, use_container_width=True)
        _yx_icon = _MODE_ICON.get("引星", "")
        _yx_title = f'<img src="{_yx_icon}" style="height:1.4em;vertical-align:middle;margin-right:4px;">引星' if _yx_icon else '引星'
        st.markdown(f'''
        <div class="mode-card">
            <div class="mode-title">{_yx_title}</div>
            <div class="mode-desc">你引一颗星来引路</div>
            <div class="mode-tag">成员参与度最高</div>
        </div>
        ''', unsafe_allow_html=True)
        st.caption("成员自己定方向，LLM填充文化知识")
        if st.button("选择引星 →", key="btn_yinxing", use_container_width=True):
            st.session_state.mode = "引星"
            save_step("mode", "选择灵感模式", {"mode": "引星"})
            st.session_state.step = "yinxing_input"
            st.rerun()

    with col2:
        _illust_xt_p = _static_path("illust_xingtu.png")
        if _illust_xt_p:
            st.image(_illust_xt_p, use_container_width=True)
        _xt_icon = _MODE_ICON.get("星图", "")
        _xt_title = f'<img src="{_xt_icon}" style="height:1.4em;vertical-align:middle;margin-right:4px;">星图' if _xt_icon else '星图'
        st.markdown(f'''
        <div class="mode-card">
            <div class="mode-title">{_xt_title}</div>
            <div class="mode-desc">按图导航，全维度覆盖</div>
            <div class="mode-tag">3选1最精准</div>
        </div>
        ''', unsafe_allow_html=True)
        st.caption("维度框架知识库驱动，3条灵感选1条")
        if st.button("选择星图 →", key="btn_xingtu", use_container_width=True):
            st.session_state.mode = "星图"
            save_step("mode", "选择灵感模式", {"mode": "星图"})
            st.session_state.step = "generating"
            st.rerun()

    with col3:
        _illust_lx_p = _static_path("illust_liuxing.png")
        if _illust_lx_p:
            st.image(_illust_lx_p, use_container_width=True)
        _lx_icon = _MODE_ICON.get("流星", "")
        _lx_title = f'<img src="{_lx_icon}" style="height:1.4em;vertical-align:middle;margin-right:4px;">流星' if _lx_icon else '流星'
        st.markdown(f'''
        <div class="mode-card">
            <div class="mode-title">{_lx_title}</div>
            <div class="mode-desc">天降惊喜，不可预测</div>
            <div class="mode-tag">独特性最强</div>
        </div>
        ''', unsafe_allow_html=True)
        st.caption("星火种子+随机维度，推荐1条灵感")
        if st.button("选择流星 →", key="btn_liuxing", use_container_width=True):
            st.session_state.mode = "流星"
            save_step("mode", "选择灵感模式", {"mode": "流星"})
            st.session_state.step = "liuxing_input"
            st.rerun()

# ============================================================
# 引星模式：成员输入框架
# ============================================================
elif st.session_state.step == "yinxing_input":
    ui = st.session_state.user_input
    _yx_src = _MODE_ICON.get('引星', '')
    _yx_icon_h = f'<img src="{_yx_src}" style="height:1.4em;vertical-align:middle;margin-right:4px;">' if _yx_src else '🎯 '
    st.markdown(f"### {_yx_icon_h}引星 — 你引一颗星来引路", unsafe_allow_html=True)
    st.markdown("---")

    st.info("请按以下格式输入你的联想链：", icon="📝")
    st.markdown("**格式**：（主题）——（联想主题）——（作品名称）")
    st.markdown("**示例**：`节日 —— 团圆 —— 灯火可亲`  *(示例与当前主题无关，仅展示格式)*")
    st.markdown("---")

    framework = st.text_input(
        f"请输入你的联想链（以「{ui['theme']}」为起点）：",
        placeholder=f"{ui['theme']} —— （你的联想方向） —— （你的作品名称）"
    )

    st.markdown("---")
    col_back, col_go = st.columns(2)
    with col_back:
        if st.button("← 返回选择模式", use_container_width=True):
            st.session_state.step = 2
            st.rerun()
    with col_go:
        if st.button("生成灵感 ✨", type="primary", use_container_width=True):
            if not framework.strip():
                st.error("请输入你的联想链！")
            else:
                st.session_state.member_framework = framework
                save_step("mode", "选择灵感模式", {"mode": "引星", "member_framework": framework})
                st.session_state.step = "generating"
                st.rerun()

# ============================================================
# 流星模式：收集星火
# ============================================================
elif st.session_state.step == "liuxing_input":
    _lx_src = _MODE_ICON.get('流星', '')
    _lx_icon_h = f'<img src="{_lx_src}" style="height:1.4em;vertical-align:middle;margin-right:4px;">' if _lx_src else '☄️ '
    st.markdown(f"### {_lx_icon_h}流星 — 天降惊喜，不可预测", unsafe_allow_html=True)
    st.markdown("---")
    st.info("先收集一些星火（灵感种子），这些信息会渗透进生成但不直接出现", icon="🔥")

    col1, col2 = st.columns(2)
    with col1:
        weather = st.text_input("🌤 今天天气怎么样？", placeholder="晴天/下雨/多云...")
        mood = st.text_input("💭 现在心情如何？", placeholder="开心/平静/焦虑/期待...")
    with col2:
        place = st.text_input("🌲 森林还是海边？", placeholder="森林/海边/沙漠/城市...")
        random_word = st.text_input("🎲 随便说一个词", placeholder="随便什么都行...")

    st.markdown("---")
    col_back, col_go = st.columns(2)
    with col_back:
        if st.button("← 返回选择模式", use_container_width=True):
            st.session_state.step = 2
            st.rerun()
    with col_go:
        if st.button("播星火，生成灵感 ✨", type="primary", use_container_width=True):
            st.session_state.starfire = {
                "weather": weather or "晴天",
                "mood": mood or "平静",
                "place": place or "森林",
                "random_word": random_word or "蒲公英"
            }
            save_step("mode", "选择灵感模式", {"mode": "流星", "starfire": dict(st.session_state.starfire)})
            st.session_state.step = "generating"
            st.rerun()

# ============================================================
# 生成灵感（三种模式共用）
# ============================================================
elif st.session_state.step == "generating":
    ui = st.session_state.user_input
    mode = st.session_state.get("mode", "星图")
    target_audience = f"{ui['target_gender']}，{ui['target_age']}"
    _mode_icon_b64 = _MODE_ICON.get(mode, "")

    st.markdown(f'''
    <div class="loading-overlay">
        <div class="loading-card">
            <img src="{_mode_icon_b64}" class="loading-icon" style="display:{'block' if _mode_icon_b64 else 'none'};">
            <div class="loading-title">响星正在生成灵感</div>
            <div class="loading-sub">{mode}模式  -  {ui["theme"]}</div>
            <div class="loading-bar-track">
                <div class="loading-bar-fill-animated"></div>
            </div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

    # 图片理解
    image_context = ""
    if ui.get("image_path") and ui["image_path"].strip():
        image_desc = llm_client.understand_image(ui["image_path"])
        if not image_desc.startswith("["):
            image_context = f"\n\n【参考图片分析】{image_desc}"
            st.session_state.image_description = image_desc
        else:
            st.warning(f"图片理解失败：{image_desc}")

    enhanced_ai_play = ui["ai_play"] + image_context

    if mode == "引星":
        result = yinxing_generate(
            theme=ui["theme"],
            member_framework=st.session_state.member_framework,
            ai_play=enhanced_ai_play,
            target_audience=target_audience
        )
    elif mode == "星图":
        result, used_dims = xingtu_generate(
            theme=ui["theme"],
            ai_play=enhanced_ai_play,
            target_audience=target_audience
        )
    elif mode == "流星":
        sf = st.session_state.starfire
        result, used_dims = liuxing_generate(
            theme=ui["theme"],
            starfire=sf,
            ai_play=enhanced_ai_play,
            target_audience=target_audience
        )

    # API调用失败检测
    if isinstance(result, str) and result.startswith("[API调用失败]"):
        st.session_state.api_error_msg = result
        st.session_state.step = "inspiration_error"
        st.rerun()

    st.session_state.inspiration_result = result
    save_step("inspiration", "灵感结果", {"inspiration_result": result, "mode": mode})
    st.session_state.step = 3
    st.rerun()

# ============================================================
# 灵感生成API错误页面
# ============================================================
elif st.session_state.step == "inspiration_error":
    _err_msg = st.session_state.pop("api_error_msg", "未知错误")
    st.error(f"灵感生成失败：{_err_msg}")
    st.info("请检查网络连接和API配置后重试。")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← 返回选择模式", use_container_width=True):
            st.session_state.step = 2
            st.rerun()
    with col2:
        if st.button("🔄 重新生成", type="primary", use_container_width=True):
            st.session_state.step = "generating"
            st.rerun()

# ============================================================
# Step 3: 灵感结果 + 勾选/确认 + 生成提示词
# ============================================================
elif st.session_state.step == 3:
    st.markdown("### <span class='step-badge'>3</span> 灵感结果", unsafe_allow_html=True)

    _mode = st.session_state.get("mode", "星图")
    _mi = _MODE_ICON.get(_mode, "")
    _mi_html = f'<img src="{_mi}" style="height:1.1em;vertical-align:middle;margin-right:4px;">' if _mi else ''
    st.markdown(f"{_mi_html} 模式：**{_mode}**", unsafe_allow_html=True)

    st.markdown("---")

    # 解析灵感结果
    inspiration_text = st.session_state.inspiration_result
    _inspiration_items = _parse_inspiration_items(inspiration_text)

    # 流星模式：只展示【最终推荐】那一条
    if _mode == "流星":
        _meteor_recommended = [item for item in _inspiration_items if "最终推荐" in item.get("title", "")]
        if _meteor_recommended:
            _meteor_display_text = _meteor_recommended[0]["title"] + " " + _meteor_recommended[0]["content"]
        else:
            # 无最终推荐标记时，取最后一条（通常是推荐）
            _meteor_display_text = _inspiration_items[-1]["title"] + " " + _inspiration_items[-1]["content"] if _inspiration_items else inspiration_text
        st.markdown(f'<div class="result-box">{_html_escape(_meteor_display_text)}</div>', unsafe_allow_html=True)
        _inspiration_items = _meteor_recommended if _meteor_recommended else (_inspiration_items[-1:] if _inspiration_items else [])
    else:
        # 非流星模式：显示完整灵感结果（标准化换行，避免第2/3条多空行）
        _normalized_text = _re.sub(r'\n{2,}', '\n', inspiration_text.strip())
        st.markdown(f'<div class="result-box">{_html_escape(_normalized_text)}</div>', unsafe_allow_html=True)

    st.markdown("---")

    # ---- 灵感选择逻辑 ----
    _is_meteor = (_mode == "流星")

    if _is_meteor:
        # 流星模式：只有1条推荐灵感，直接用
        st.success("✅ 流星推荐灵感已自动选中")
        if _inspiration_items:
            selected_indices = [0]
            _chosen_inspiration = _inspiration_items[0]["title"] + "\n" + _inspiration_items[0]["content"]
        else:
            selected_indices = []
            _chosen_inspiration = inspiration_text
    elif _mode == "星图":
        # 星图模式：3选1
        st.markdown("#### 选择灵感（3选1）")
        st.caption("从3条灵感中选择1条最满意的，用于生成提示词")

        if len(_inspiration_items) <= 1:
            # 仅1条或0条灵感，无需radio选择
            if _inspiration_items:
                st.info("当前仅生成1条灵感，已自动选中")
                selected_indices = [0]
                _chosen_inspiration = _inspiration_items[0]["title"] + "\n" + _inspiration_items[0]["content"]
            else:
                selected_indices = []
                _chosen_inspiration = inspiration_text
        else:
            selected_idx = st.radio(
                "选择1条灵感",
                range(len(_inspiration_items)),
                format_func=lambda i: f"{_inspiration_items[i]['title']} — {_inspiration_items[i]['content'][:50]}...",
                key="xingtu_selection"
            )
            selected_indices = [selected_idx]
            _chosen_inspiration = _inspiration_items[selected_idx]["title"] + "\n" + _inspiration_items[selected_idx]["content"]
            st.success(f"✅ 已选中第 {selected_idx + 1} 条灵感")
    else:
        # 引星模式：多条灵感，选1条
        st.markdown("#### 选择灵感")
        st.caption("从灵感中选择1条最满意的")

        if len(_inspiration_items) <= 1:
            # 仅1条或0条灵感，无需radio选择
            if _inspiration_items:
                st.info("当前仅生成1条灵感，已自动选中")
                selected_indices = [0]
                _chosen_inspiration = _inspiration_items[0]["title"] + "\n" + _inspiration_items[0]["content"]
            else:
                selected_indices = []
                _chosen_inspiration = inspiration_text
        else:
            selected_idx = st.radio(
                "选择1条灵感",
                range(len(_inspiration_items)),
                format_func=lambda i: f"{_inspiration_items[i]['title']} — {_inspiration_items[i]['content'][:50]}...",
                key="yinxing_selection"
            )
            selected_indices = [selected_idx]
            _chosen_inspiration = _inspiration_items[selected_idx]["title"] + "\n" + _inspiration_items[selected_idx]["content"]

    st.markdown("---")

    # ---- 按钮区 ----
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← 返回选择模式", use_container_width=True):
            st.session_state.step = 2
            st.session_state.selected_inspirations = []
            st.rerun()
    with col2:
        if st.button("确认灵感，生成提示词 →", type="primary", use_container_width=True):
            st.session_state.chosen_inspiration = _chosen_inspiration
            st.session_state.step = "prompt_generating"
            st.rerun()

# ============================================================
# 生成提示词
# ============================================================
elif st.session_state.step == "prompt_generating":
    ui = st.session_state.user_input
    _template_type = ui.get("prompt_template", "文生视频")
    target_audience = f"{ui['target_gender']}，{ui['target_age']}"
    _mode = st.session_state.get("mode", "星图")
    _mode_icon_b64 = _MODE_ICON.get(_mode, "")

    st.markdown(f'''
    <div class="loading-overlay">
        <div class="loading-card">
            <img src="{_mode_icon_b64}" class="loading-icon" style="display:{'block' if _mode_icon_b64 else 'none'};">
            <div class="loading-title">响星正在生成提示词</div>
            <div class="loading-sub">{_template_type}  -  {_mode}模式</div>
            <div class="loading-bar-track">
                <div class="loading-bar-fill-animated"></div>
            </div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

    prompt_result = generate_prompts_from_inspiration(
        inspiration=st.session_state.chosen_inspiration,
        template_type=_template_type,
        ai_play=ui["ai_play"],
        target_audience=target_audience,
        theme=ui["theme"]
    )

    # API调用失败检测
    _prompt_text = prompt_result.get("prompt_text", "")
    if _prompt_text.startswith("[API调用失败]"):
        st.session_state.api_error_msg = _prompt_text
        st.session_state.step = "prompt_error"
        st.rerun()

    st.session_state.generated_prompt = prompt_result
    # 保存提示词步骤快照
    save_step("prompts", "提示词", prompt_result)
    st.session_state.step = 4
    st.rerun()

# ============================================================
# 提示词生成API错误页面
# ============================================================
elif st.session_state.step == "prompt_error":
    _err_msg = st.session_state.pop("api_error_msg", "未知错误")
    st.error(f"提示词生成失败：{_err_msg}")
    st.info("请检查网络连接和API配置后重试。")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← 返回灵感选择", use_container_width=True):
            st.session_state.step = 3
            st.rerun()
    with col2:
        if st.button("🔄 重新生成提示词", type="primary", use_container_width=True):
            st.session_state.step = "prompt_generating"
            st.rerun()

# ============================================================
# Step 4: 提示词结果 + 编辑 + 完成
# ============================================================
elif st.session_state.step == 4:
    st.markdown("### <span class='step-badge'>3</span> 提示词", unsafe_allow_html=True)

    ui = st.session_state.user_input
    prompt_result = st.session_state.generated_prompt

    if not prompt_result:
        st.error("提示词生成失败，请返回重试")
        if st.button("← 返回灵感选择"):
            st.session_state.step = 3
            st.rerun()
        st.stop()

    _template_type = prompt_result.get("template_type", ui.get("prompt_template", ""))
    _pitfall_warnings = prompt_result.get("pitfall_warnings", [])
    _char_count = prompt_result.get("char_count", 0)

    st.caption(f"模版：**{_template_type}**  -  字数：**{_char_count}**")

    st.markdown("---")

    # 可编辑的提示词
    # 方案：不使用key参数，每次rerun直接从prompt_result取value
    # 用户编辑通过on_change回调同步回prompt_result
    prompt_text = prompt_result.get("prompt_text", "")
    new_prompt = st.text_area(
        "提示词（可编辑修改）",
        value=prompt_text,
        height=350
    )
    st.session_state.generated_prompt["prompt_text"] = new_prompt

    # 字数校验
    _current_chars = len(new_prompt.replace(" ", "").replace("\n", ""))
    if _current_chars > 800:
        st.warning(f"⚠ 当前提示词共 **{_current_chars}** 字，超出800字上限，请手动精简后再使用")
    else:
        st.caption(f"字数：{_current_chars}/800")

    # 暗礁校验
    if _pitfall_warnings:
        for w in _pitfall_warnings:
            st.warning(f"⚠ {w}")

    # 复制按钮（用st.code的内置复制功能，避免HTML/JS被Streamlit过滤）
    with st.expander("📋 点击展开复制提示词", expanded=False):
        st.code(new_prompt, language=None)

    st.markdown("---")

    # 防重复保存：基于内容哈希去重（同一条策划只保存一次）
    _save_content_str = json.dumps({
        "theme": ui.get("theme", ""),
        "ai_play": ui.get("ai_play", ""),
        "prompt_text": prompt_result.get("prompt_text", ""),
    }, ensure_ascii=False, sort_keys=True)
    _save_hash = hashlib.md5(_save_content_str.encode("utf-8")).hexdigest()
    if st.session_state.get("planning_saved_hash") != _save_hash:
        st.session_state.planning_saved_hash = _save_hash
        save_planning(
            user_input=ui,
            inspiration=st.session_state.inspiration_result,
            prompts=st.session_state.generated_prompt,
            mode=st.session_state.get("mode", "未知"),
            steps=st.session_state.session_steps
        )
        update_template_usage(ui.get("prompt_template", "文生视频"))

    # 暗礁反馈
    st.markdown("### 🪨 暗礁反馈")
    pitfall_feedback = st.text_input("如审核不通过，请输入反馈原文（留空跳过）：", placeholder="如：不允许出现外语")
    if pitfall_feedback:
        add_pitfall(theme=ui["theme"], feedback=pitfall_feedback, category="内容违规", member="匿名")
        st.success("暗礁已记录！")

    st.markdown("---")
    st.markdown("### 🌟 策划方案生成完毕！")

    # 流星庆祝动画
    st.markdown("""
    <div style="position:fixed;inset:0;pointer-events:none;z-index:9999;overflow:hidden;">
      <div style="position:fixed;inset:0;animation:celebFade 5s ease-in-out forwards;">
        <svg style="position:absolute;right:5%;top:2%;width:120px;height:120px;" viewBox="0 0 100 100">
          <defs>
            <linearGradient id="mg" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" style="stop-color:#fff;stop-opacity:0"/>
              <stop offset="40%" style="stop-color:#ffe082;stop-opacity:0.9"/>
              <stop offset="100%" style="stop-color:#ffffff;stop-opacity:1"/>
            </linearGradient>
            <filter id="glow"><feGaussianBlur stdDeviation="2" result="blur"/>
              <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
          </defs>
          <g filter="url(#glow)" style="animation:meteorFlicker 0.25s ease-in-out infinite alternate;">
            <line x1="0" y1="0" x2="80" y2="80" stroke="url(#mg)" stroke-width="3" stroke-linecap="round"/>
            <circle cx="82" cy="82" r="4" fill="#fff" style="animation:meteorFlicker 0.3s ease-in-out infinite alternate;"/>
          </g>
        </svg>
        <svg style="position:absolute;right:25%;top:6%;width:80px;height:80px;" viewBox="0 0 100 100">
          <defs>
            <linearGradient id="mg2" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" style="stop-color:#fff;stop-opacity:0"/>
              <stop offset="35%" style="stop-color:#ffe082;stop-opacity:0.7"/>
              <stop offset="100%" style="stop-color:#ffffff;stop-opacity:0.9"/>
            </linearGradient>
          </defs>
          <g style="animation:meteorFlicker 0.35s ease-in-out infinite alternate;animation-delay:0.15s;">
            <line x1="5" y1="5" x2="70" y2="70" stroke="url(#mg2)" stroke-width="2" stroke-linecap="round"/>
            <circle cx="72" cy="72" r="3" fill="#fffbe8"/>
          </g>
        </svg>
      </div>
      <style>
        @keyframes celebFade {
          0% { opacity: 0; }
          6% { opacity: 1; }
          65% { opacity: 1; }
          100% { opacity: 0; }
        }
        @keyframes meteorFlicker {
          0% { opacity: 0.5; }
          100% { opacity: 1; }
        }
      </style>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← 返回修改灵感", use_container_width=True):
            st.session_state.generated_prompt = None
            st.session_state.planning_saved_hash = None
            st.session_state.step = 3
            st.rerun()
    with col2:
        if st.button("🔄 开始新一期策划", type="primary", use_container_width=True):
            _reset_all_state()
            st.rerun()

# ============================================================
# 查看历史记录
# ============================================================
elif st.session_state.step == "view_record":
    _record_id = st.session_state.get("viewing_record")
    if not _record_id:
        st.session_state.step = 1
        st.rerun()

    _record = load_record_file(_record_id)
    if not _record:
        st.error("记录文件不存在或已损坏")
        if st.button("← 返回主界面"):
            st.session_state.step = 1
            st.session_state.viewing_record = None
            st.rerun()
    else:
        _idx = load_history_index()
        _entry = next((r for r in _idx if r["id"] == _record_id), {})
        _rec_name = _entry.get("name", "未命名")

        _steps = _record.get("steps", [])
        if not _steps:
            _steps = build_synthetic_steps(_record)

        _total = len(_steps)
        if _total == 0:
            st.warning("该记录无步骤数据")
            if st.button("← 返回主界面"):
                st.session_state.step = 1
                st.session_state.viewing_record = None
                st.rerun()
            st.stop()

        _step_idx = st.session_state.get("viewing_step_idx", 0)
        if _step_idx >= _total:
            _step_idx = _total - 1
        st.session_state.viewing_step_idx = _step_idx

        st.markdown(f"### 📋 {_rec_name}")
        st.caption(f"{_record.get('日期', '')}  -  {_record.get('模式', '未知')}")

        render_step_indicator(_steps, _step_idx)

        st.markdown("---")

        _current = _steps[_step_idx]
        render_step_content(_current.get("step_key", ""), _current.get("data", {}))

        st.markdown("---")

        # 步骤导航
        nav1, nav2, nav3, nav4 = st.columns([1, 1, 1, 1])
        with nav1:
            if _step_idx > 0:
                if st.button("◀ 上一步", key="prev_step", use_container_width=True):
                    st.session_state.viewing_step_idx = _step_idx - 1
                    st.rerun()
        with nav2:
            if st.button("🪨 暗礁反馈", key="pitfall_feedback_btn", use_container_width=True):
                st.session_state.show_pitfall_form = True
        with nav3:
            st.caption(f"第 {_step_idx + 1} 步 / 共 {_total} 步")
        with nav4:
            if _step_idx < _total - 1:
                if st.button("下一步 ▶", key="next_step", use_container_width=True):
                    st.session_state.viewing_step_idx = _step_idx + 1
                    st.rerun()

        # 暗礁反馈表单
        if st.session_state.get("show_pitfall_form", False):
            st.markdown("---")
            st.markdown("#### 🪨 暗礁反馈")
            _pf_theme = st.text_input("关联主题", value=_record.get("主题", ""), key="pf_theme")
            _pf_feedback = st.text_input(
                "反馈内容",
                placeholder="例如：风格约束问题",
                key="pf_feedback"
            )
            _pf_category = st.selectbox("归类", ["风格约束", "内容违规", "文化合规", "结构约束", "格式问题", "其他"], key="pf_category")
            _pf1, _pf2 = st.columns(2)
            with _pf1:
                if st.button("✅ 提交反馈", key="submit_pitfall", use_container_width=True, type="primary"):
                    if _pf_feedback.strip():
                        add_pitfall(theme=_pf_theme, feedback=_pf_feedback, category=_pf_category, member="匿名")
                        st.success("✅ 暗礁已记录！")
                        st.session_state.show_pitfall_form = False
                        st.rerun()
                    else:
                        st.warning("请输入反馈内容")
            with _pf2:
                if st.button("取消", key="cancel_pitfall", use_container_width=True):
                    st.session_state.show_pitfall_form = False
                    st.rerun()

        st.markdown("---")
        nav1, nav2, nav3 = st.columns([1, 1, 1])
        with nav1:
            if st.button("← 返回主界面", use_container_width=True):
                st.session_state.step = 1
                st.session_state.viewing_record = None
                st.session_state.viewing_step_idx = 0
                st.session_state.confirm_delete = False
                st.rerun()
        with nav3:
            if st.button("🗑 删除此记录", key="btn_del_viewing", use_container_width=True):
                st.session_state.confirm_delete = True

        if st.session_state.get("confirm_delete", False):
            st.warning("⚠️ 您是否要删除此记录？删除后无法恢复。")
            dc1, dc2 = st.columns(2)
            with dc1:
                if st.button("确认删除", key="confirm_del_viewing", type="primary", use_container_width=True):
                    delete_record(_record_id)
                    st.session_state.confirm_delete = False
                    st.session_state.viewing_record = None
                    st.session_state.viewing_step_idx = 0
                    st.session_state.step = 1
                    st.success("✅ 记录已删除")
                    st.rerun()
            with dc2:
                if st.button("取消", key="cancel_del_viewing", use_container_width=True):
                    st.session_state.confirm_delete = False
                    st.rerun()
