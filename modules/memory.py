# -*- coding: utf-8 -*-
"""
响星 mini2.0 - 记忆模块
历史策划归档、使用统计、暗礁库管理
mini2.0变化：去掉剪辑建议字段、暗礁库支持侧边栏直接打开管理
"""

import json
import os
import re
from datetime import datetime
import config


def _sync_push(local_path, github_path=None):
    """将本地文件推送到GitHub（静默降级：失败不影响本地操作）"""
    try:
        from modules.storage import sync_push_file, sync_delete_file
        sync_push_file(local_path, github_path)
    except Exception:
        pass  # 同步失败不影响本地操作


def _sync_delete(github_path):
    """从GitHub删除文件（静默降级）"""
    try:
        from modules.storage import sync_delete_file
        sync_delete_file(github_path)
    except Exception:
        pass


def _sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    illegal = r'[<>:"/\\|?*]'
    return re.sub(illegal, '_', name).strip()


# ============================================================
# 历史策划归档
# ============================================================

def save_planning(user_input, inspiration, prompts, mode="未知", steps=None):
    """
    保存一次完整策划到历史归档，同时更新索引
    mini2.0: 去掉storyboard和edit_advice字段
    
    user_input: dict（包含 theme, ai_play, target_gender, target_age, prompt_template 等键）
    """
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d %H:%M:%S")
    safe_theme = _sanitize_filename(user_input.get("theme", "未命名"))
    # 文件名用微秒精度避免同秒冲突
    _ts = now.strftime("%Y-%m-%d_%H%M%S") + f"_{now.microsecond:06d}"
    filename = f"{_ts}_{safe_theme}.json"
    filepath = os.path.join(config.HISTORY_DIR, filename)

    record = {
        "日期": date_str,
        "主题": user_input.get("theme", ""),
        "AI玩法": user_input.get("ai_play", ""),
        "目标人群": f"{user_input.get('target_gender', '')}，{user_input.get('target_age', '')}",
        "提示词模版": user_input.get("prompt_template", ""),
        "模式": mode,
        "灵感": inspiration,
        "提示词": prompts,
        "steps": steps or []
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    # 推送记录文件到GitHub
    _sync_push(filepath, f"history/{filename}")

    # 更新索引
    record_id = _ts
    _theme = user_input.get("theme", "")
    _ai_play = user_input.get("ai_play", "")
    input_summary = f"{_theme} | {_ai_play[:20]}..." if len(_ai_play) > 20 else f"{_theme} | {_ai_play}"
    output_summary = (inspiration[:40] + "...") if len(inspiration) > 40 else inspiration

    add_to_index(
        record_id=record_id,
        name=f"{_theme}_{now.strftime('%m%d')}",
        filename=filename,
        date=date_str,
        theme=_theme,
        mode=mode,
        input_summary=input_summary,
        output_summary=output_summary
    )


# ============================================================
# 使用统计
# ============================================================

def update_dimension_usage(used_dimensions: list):
    """更新维度使用频次统计"""
    filepath = os.path.join(config.STATS_DIR, "dimension_usage.json")

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            stats = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        stats = {}

    for dim in used_dimensions:
        stats[dim] = stats.get(dim, 0) + 1

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    _sync_push(filepath, "stats/dimension_usage.json")


def update_template_usage(template_name: str):
    """更新模版使用频次统计"""
    filepath = os.path.join(config.STATS_DIR, "template_usage.json")

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            stats = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        stats = {}

    stats[template_name] = stats.get(template_name, 0) + 1

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    _sync_push(filepath, "stats/template_usage.json")


# ============================================================
# 暗礁库管理（侧边栏可直接操作）
# ============================================================

def load_pitfall_rules() -> dict:
    """加载暗礁库完整数据"""
    pitfall_path = os.path.join(config.KNOWLEDGE_BASE_DIR, "pitfall_rules.json")
    try:
        with open(pitfall_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # 文件不存在或损坏，返回默认结构
        return {"规则列表": [], "天翼智铃避坑规则": {}, "彩铃风格边界": {}}


def save_pitfall_rules(data: dict):
    """保存暗礁库完整数据"""
    pitfall_path = os.path.join(config.KNOWLEDGE_BASE_DIR, "pitfall_rules.json")
    with open(pitfall_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _sync_push(pitfall_path, "knowledge_base/pitfall_rules.json")


def get_pitfall_rules_list() -> list:
    """获取暗礁规则列表"""
    data = load_pitfall_rules()
    return data.get("规则列表", [])


def get_ringtone_boundary() -> dict:
    """获取彩铃风格边界"""
    data = load_pitfall_rules()
    return data.get("彩铃风格边界", {})


def get_tianyi_avoidance_rules() -> dict:
    """获取天翼智铃避坑规则"""
    data = load_pitfall_rules()
    return data.get("天翼智铃避坑规则", {})


def add_pitfall(theme: str, feedback: str, category: str, member: str):
    """添加一条暗礁规则"""
    pitfall_data = load_pitfall_rules()

    # 中文分词：按标点符号拆分
    _punct = re.compile(r'[，。、；！？\s,;!?]+')
    keywords = [k.strip() for k in _punct.split(feedback) if k.strip()]
    if not keywords:
        keywords = [feedback]

    new_rule = {
        "主题": theme,
        "审核反馈": feedback,
        "归类": category,
        "来源成员": member,
        "日期": datetime.now().strftime("%Y-%m-%d"),
        "关键词": keywords
    }

    # 用 setdefault 防止 KeyError（JSON 中可能缺少该字段）
    pitfall_data.setdefault("规则列表", []).append(new_rule)
    save_pitfall_rules(pitfall_data)


def delete_pitfall(index: int):
    """删除一条暗礁规则（按索引）"""
    pitfall_data = load_pitfall_rules()
    rules = pitfall_data.get("规则列表", [])
    if 0 <= index < len(rules):
        rules.pop(index)
        pitfall_data["规则列表"] = rules
        save_pitfall_rules(pitfall_data)


# ============================================================
# 历史记录索引管理
# ============================================================

HISTORY_INDEX_PATH = os.path.join(config.HISTORY_DIR, "index.json")


def index_exists():
    return os.path.exists(HISTORY_INDEX_PATH)


def load_history_index():
    try:
        with open(HISTORY_INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_history_index(index):
    with open(HISTORY_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    _sync_push(HISTORY_INDEX_PATH, "history/index.json")


def add_to_index(record_id, name, filename, date, theme, mode, input_summary, output_summary):
    """添加一条记录到索引"""
    index = load_history_index()
    index.append({
        "id": record_id,
        "name": name,
        "filename": filename,
        "date": date,
        "theme": theme,
        "mode": mode,
        "input_summary": input_summary,
        "output_summary": output_summary
    })
    save_history_index(index)


def rename_in_index(record_id, new_name):
    """重命名一条记录"""
    index = load_history_index()
    for entry in index:
        if entry["id"] == record_id:
            entry["name"] = new_name
            break
    save_history_index(index)


def delete_record(record_id):
    """删除一条记录（索引+文件）"""
    index = load_history_index()
    filename = None
    for entry in index:
        if entry["id"] == record_id:
            filename = entry.get("filename")
            break
    if filename:
        filepath = os.path.join(config.HISTORY_DIR, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
        _sync_delete(f"history/{filename}")
    index = [e for e in index if e["id"] != record_id]
    save_history_index(index)


def load_record_file(record_id):
    """加载一条完整记录"""
    index = load_history_index()
    entry = next((e for e in index if e["id"] == record_id), None)
    if not entry:
        return None
    filepath = os.path.join(config.HISTORY_DIR, entry["filename"])
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_record_content(record_id, record_data):
    """保存记录内容修改"""
    index = load_history_index()
    entry = next((e for e in index if e["id"] == record_id), None)
    if not entry:
        return False
    filepath = os.path.join(config.HISTORY_DIR, entry["filename"])
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record_data, f, ensure_ascii=False, indent=2)
    _sync_push(filepath, f"history/{entry['filename']}")
    return True


def update_index_after_edit(record_id, record_data):
    """编辑记录后更新索引中的摘要"""
    index = load_history_index()
    for entry in index:
        if entry["id"] == record_id:
            theme = record_data.get("主题", "")
            ai_play = record_data.get("AI玩法", "")
            entry["input_summary"] = f"{theme} | {ai_play[:20]}..." if len(ai_play) > 20 else f"{theme} | {ai_play}"
            inspiration = record_data.get("灵感", "")
            entry["output_summary"] = (inspiration[:40] + "...") if len(inspiration) > 40 else inspiration
            entry["theme"] = theme
            break
    save_history_index(index)


def rebuild_index():
    """从history目录中的JSON文件重建索引"""
    index = []
    for fname in sorted(os.listdir(config.HISTORY_DIR)):
        if not fname.endswith(".json") or fname == "index.json":
            continue
        filepath = os.path.join(config.HISTORY_DIR, fname)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                record = json.load(f)
            parts = fname.replace(".json", "").split("_", 2)
            record_id = f"{parts[0]}_{parts[1]}" if len(parts) >= 2 else fname
            theme = record.get("主题", "未知")
            ai_play = record.get("AI玩法", "")
            input_summary = f"{theme} | {ai_play[:20]}..." if len(ai_play) > 20 else f"{theme} | {ai_play}"
            inspiration = record.get("灵感", "")
            output_summary = (inspiration[:40] + "...") if len(inspiration) > 40 else inspiration
            date = record.get("日期", "")
            name = f"{theme}_{date[5:10].replace('-', '')}" if date else fname
            mode = record.get("模式", "未知")
            index.append({
                "id": record_id,
                "name": name,
                "filename": fname,
                "date": date,
                "theme": theme,
                "mode": mode,
                "input_summary": input_summary,
                "output_summary": output_summary
            })
        except (json.JSONDecodeError, KeyError):
            continue
    save_history_index(index)
    return len(index)
