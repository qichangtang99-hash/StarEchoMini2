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
API_PROVIDER = "deepseek"

# ---- 天翼AI开放平台（星辰自研模型） ----
TIANYI_API_BASE = "https://ai.ctaigw.cn/v1/"
TIANYI_MODEL_NAME = "xingchen-pro"

# ---- DeepSeek ----
DEEPSEEK_API_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL_NAME = "deepseek-v4-flash"


def _read_secret(key_name: str) -> str:
    """从 Streamlit Secrets 读取值，读不到返回空字符串（不抛异常）"""
    try:
        import streamlit as st
        return st.secrets[key_name]
    except Exception:
        return ""


def get_api_config(provider=None):
    """
    获取当前API配置（延迟读取Secrets，确保Streamlit已初始化）
    
    Returns:
        dict: {"api_key": ..., "base_url": ..., "model_name": ..., "provider": ...}
    """
    p = provider or API_PROVIDER

    if p == "tianyi":
        api_key = _read_secret("TIANYI_API_KEY") or os.environ.get("TIANYI_API_KEY", "")
        return {
            "api_key": api_key,
            "base_url": TIANYI_API_BASE,
            "model_name": TIANYI_MODEL_NAME,
            "provider": "tianyi"
        }
    else:
        api_key = _read_secret("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")
        return {
            "api_key": api_key,
            "base_url": DEEPSEEK_API_BASE,
            "model_name": DEEPSEEK_MODEL_NAME,
            "provider": "deepseek"
        }


# ============================================================
# GitHub 外部持久化存储配置
# ============================================================
GITHUB_REPO = "qichangtang99-hash/StarEcho"
GITHUB_BRANCH = "data"   # 独立分支，不影响代码部署


def get_github_token():
    """从 Streamlit Secrets 读取 GitHub Token"""
    return _read_secret("GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN", "")


def get_github_repo():
    """获取 GitHub 仓库名"""
    return _read_secret("GITHUB_REPO") or os.environ.get("GITHUB_REPO", GITHUB_REPO)


def get_github_branch():
    """获取 GitHub 存储分支名"""
    return _read_secret("GITHUB_BRANCH") or os.environ.get("GITHUB_BRANCH", GITHUB_BRANCH)


# 确保目录存在
for d in [HISTORY_DIR, STATS_DIR, KNOWLEDGE_BASE_DIR]:
    os.makedirs(d, exist_ok=True)
