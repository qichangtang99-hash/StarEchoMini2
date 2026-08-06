# -*- coding: utf-8 -*-
"""
响星 mini2.0 - 配置文件
支持双API提供商：天翼AI开放平台（星辰自研模型）/ DeepSeek
API Key 优先从 Streamlit Secrets 读取，其次从环境变量读取
"""

import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE_BASE_DIR = os.path.join(PROJECT_ROOT, "knowledge_base")
HISTORY_DIR = os.path.join(PROJECT_ROOT, "history")
STATS_DIR = os.path.join(PROJECT_ROOT, "stats")

# ============================================================
# API 提供商配置
# ============================================================
# 支持两种提供商：tianyi（天翼AI开放平台）/ deepseek
# 默认用deepseek（灵感+提示词阶段）；天翼AI仅后续生成视频时使用

API_PROVIDER = "deepseek"  # 灵感+提示词阶段固定用DeepSeek；天翼AI仅后续生成视频时使用

# ---- 天翼AI开放平台（星辰自研模型） ----
# API Base URL 兼容 OpenAI 协议
TIANYI_API_BASE = "https://ai.ctaigw.cn/v1/"
TIANYI_MODEL_NAME = "xingchen-pro"  # 星辰自研模型

# ---- DeepSeek ----
DEEPSEEK_API_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL_NAME = "deepseek-v4-flash"

# ---- 读取 API Key（优先级：Streamlit Secrets > 环境变量） ----
_tianyi_key = ""
_deepseek_key = ""
try:
    import streamlit as st
    try:
        _tianyi_key = st.secrets.get("TIANYI_API_KEY", "")
    except Exception:
        pass
    try:
        _deepseek_key = st.secrets.get("DEEPSEEK_API_KEY", "")
    except Exception:
        pass
except Exception:
    pass

TIANYI_API_KEY = _tianyi_key or os.environ.get("TIANYI_API_KEY", "")
DEEPSEEK_API_KEY = _deepseek_key or os.environ.get("DEEPSEEK_API_KEY", "")


def get_api_config(provider=None):
    """
    获取当前API配置
    
    Returns:
        dict: {"api_key": ..., "base_url": ..., "model_name": ..., "provider": ...}
    """
    p = provider or API_PROVIDER
    
    if p == "tianyi":
        return {
            "api_key": TIANYI_API_KEY,
            "base_url": TIANYI_API_BASE,
            "model_name": TIANYI_MODEL_NAME,
            "provider": "tianyi"
        }
    else:
        return {
            "api_key": DEEPSEEK_API_KEY,
            "base_url": DEEPSEEK_API_BASE,
            "model_name": DEEPSEEK_MODEL_NAME,
            "provider": "deepseek"
        }


# 确保目录存在
for d in [HISTORY_DIR, STATS_DIR]:
    os.makedirs(d, exist_ok=True)
