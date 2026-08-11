# -*- coding: utf-8 -*-
"""
响星 mini2.0 - 外部持久化存储模块
GitHub仓库存储：解决Streamlit Cloud重启数据丢失问题

策略：
- 启动时从GitHub拉取数据到本地（sync_pull_all）
- 写入时同时写本地和GitHub（sync_push_file）
- 读取走本地（快速，无API消耗）
- GitHub存储使用独立分支 `data`，不影响代码部署
- 同步失败不影响本地操作（静默降级）
"""

import os
import logging
import threading

logger = logging.getLogger("starecho.storage")

# PyGithub 可选依赖
_GITHUB_AVAILABLE = False
try:
    from github import Github, GithubException
    _GITHUB_AVAILABLE = True
except ImportError:
    pass


# ============================================================
# GitHub 同步管理器
# ============================================================

class GitHubSyncManager:
    """GitHub数据同步管理器，负责本地 <-> GitHub数据同步"""

    def __init__(self, token, repo_name, branch="data"):
        self._token = token
        self._repo_name = repo_name
        self._branch = branch
        self._repo = None
        self._sha_cache = {}       # path -> sha（减少API调用）
        self._lock = threading.Lock()
        self._branch_ensured = False

    def _get_repo(self):
        """延迟初始化GitHub连接"""
        if self._repo is None:
            gh = Github(self._token)
            self._repo = gh.get_repo(self._repo_name)
        return self._repo

    def _ensure_branch(self):
        """确保data分支存在，不存在则从默认分支创建"""
        if self._branch_ensured:
            return

        repo = self._get_repo()
        try:
            repo.get_branch(self._branch)
        except GithubException as e:
            if e.status == 404:
                try:
                    default_branch = repo.get_branch(repo.default_branch)
                    repo.create_git_ref(
                        ref=f"refs/heads/{self._branch}",
                        sha=default_branch.commit.sha
                    )
                    logger.info(f"Created branch '{self._branch}'")
                except Exception as ex:
                    logger.error(f"Failed to create branch: {ex}")
                    raise
            else:
                raise

        self._branch_ensured = True

    # ---- 拉取（GitHub -> 本地） ----

    def pull_file(self, github_path, local_path):
        """从GitHub拉取单个文件到本地"""
        try:
            repo = self._get_repo()
            self._ensure_branch()
            content = repo.get_contents(github_path, ref=self._branch)

            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(content.decoded_content)

            self._sha_cache[github_path] = content.sha
            logger.info(f"Pulled: {github_path} -> {local_path}")
            return True

        except GithubException as e:
            if e.status == 404:
                logger.debug(f"File not on GitHub: {github_path}")
                return False
            logger.error(f"Pull failed [{github_path}]: {e}")
            return False
        except Exception as e:
            logger.error(f"Pull error [{github_path}]: {e}")
            return False

    def pull_directory(self, github_dir, local_dir):
        """从GitHub拉取整个目录"""
        try:
            repo = self._get_repo()
            self._ensure_branch()
            contents = repo.get_contents(github_dir, ref=self._branch)

            if isinstance(contents, list):
                for item in contents:
                    if item.type == 'file':
                        local_path = os.path.join(local_dir, item.name)
                        self.pull_file(item.path, local_path)
                    elif item.type == 'dir':
                        sub_local = os.path.join(local_dir, item.name)
                        self.pull_directory(item.path, sub_local)
            return True
        except GithubException as e:
            if e.status == 404:
                logger.debug(f"Directory not on GitHub: {github_dir}")
                return False
            logger.error(f"Pull directory failed [{github_dir}]: {e}")
            return False
        except Exception as e:
            logger.error(f"Pull directory error [{github_dir}]: {e}")
            return False

    # ---- 推送（本地 -> GitHub） ----

    def push_file(self, local_path, github_path, commit_message=None):
        """将本地文件推送到GitHub"""
        try:
            repo = self._get_repo()
            self._ensure_branch()

            with open(local_path, "r", encoding="utf-8") as f:
                content_str = f.read()

            # 获取当前文件SHA（更新需要）
            sha = self._sha_cache.get(github_path)
            if not sha:
                try:
                    file_content = repo.get_contents(github_path, ref=self._branch)
                    sha = file_content.sha
                except GithubException as e:
                    if e.status != 404:
                        raise
                    sha = None

            msg = commit_message or f"Update {github_path}"

            if sha:
                result = repo.update_file(
                    github_path, msg, content_str, sha,
                    branch=self._branch
                )
                self._sha_cache[github_path] = result['commit'].sha
            else:
                result = repo.create_file(
                    github_path, msg, content_str,
                    branch=self._branch
                )
                self._sha_cache[github_path] = result['commit'].sha

            logger.info(f"Pushed: {local_path} -> {github_path}")
            return True

        except Exception as e:
            logger.error(f"Push failed [{github_path}]: {e}")
            return False

    # ---- 删除 ----

    def delete_file(self, github_path, commit_message=None):
        """从GitHub删除文件"""
        try:
            repo = self._get_repo()
            self._ensure_branch()

            sha = self._sha_cache.get(github_path)
            if not sha:
                try:
                    file_content = repo.get_contents(github_path, ref=self._branch)
                    sha = file_content.sha
                except GithubException:
                    return True  # 已不存在

            repo.delete_file(
                github_path,
                commit_message or f"Delete {github_path}",
                sha,
                branch=self._branch
            )
            self._sha_cache.pop(github_path, None)
            logger.info(f"Deleted from GitHub: {github_path}")
            return True

        except Exception as e:
            logger.error(f"Delete failed [{github_path}]: {e}")
            return False


# ============================================================
# 全局实例管理（线程安全，延迟初始化）
# ============================================================

_sync_manager = None
_sync_init_lock = threading.Lock()


def _create_sync_manager():
    """从配置创建同步管理器"""
    if not _GITHUB_AVAILABLE:
        logger.info("PyGithub not installed, GitHub sync disabled")
        return None

    try:
        import config
        token = config.get_github_token()
        repo = config.get_github_repo()
        branch = config.get_github_branch()

        if not token or not repo:
            logger.info("GitHub sync not configured (missing token or repo)")
            return None

        return GitHubSyncManager(token, repo, branch)
    except Exception as e:
        logger.error(f"Failed to create sync manager: {e}")
        return None


def get_sync():
    """获取全局同步管理器（线程安全，延迟初始化）"""
    global _sync_manager
    if _sync_manager is None:
        with _sync_init_lock:
            if _sync_manager is None:
                _sync_manager = _create_sync_manager()
    return _sync_manager


# ============================================================
# 高级同步接口（供其他模块调用）
# ============================================================

def sync_pull_all():
    """启动时从GitHub拉取所有持久化数据到本地"""
    sync = get_sync()
    if not sync:
        return False

    import config

    # 确保本地目录存在
    for d in [config.HISTORY_DIR, config.STATS_DIR, config.KNOWLEDGE_BASE_DIR]:
        os.makedirs(d, exist_ok=True)

    # 同步已知固定路径文件
    fixed_files = [
        ("history/index.json",
         os.path.join(config.HISTORY_DIR, "index.json")),
        ("knowledge_base/pitfall_rules.json",
         os.path.join(config.KNOWLEDGE_BASE_DIR, "pitfall_rules.json")),
        ("knowledge_base/dimension_framework.json",
         os.path.join(config.KNOWLEDGE_BASE_DIR, "dimension_framework.json")),
        ("stats/template_usage.json",
         os.path.join(config.STATS_DIR, "template_usage.json")),
        ("stats/dimension_usage.json",
         os.path.join(config.STATS_DIR, "dimension_usage.json")),
    ]

    for github_path, local_path in fixed_files:
        sync.pull_file(github_path, local_path)

    # 同步历史记录目录（可能有多个JSON文件）
    sync.pull_directory("history", config.HISTORY_DIR)

    logger.info("GitHub sync pull all completed")
    return True


def sync_push_file(local_path, github_path=None, commit_message=None):
    """将本地文件推送到GitHub（静默降级：失败不影响本地操作）"""
    sync = get_sync()
    if not sync:
        return False

    if github_path is None:
        # 自动推断github_path（基于项目根目录的相对路径）
        try:
            import config
            github_path = os.path.relpath(local_path, config.PROJECT_ROOT).replace("\\", "/")
        except Exception:
            return False

    return sync.push_file(local_path, github_path, commit_message)


def sync_delete_file(github_path, commit_message=None):
    """从GitHub删除文件（静默降级）"""
    sync = get_sync()
    if not sync:
        return False
    return sync.delete_file(github_path, commit_message)


def is_sync_enabled():
    """检查GitHub同步是否已启用"""
    return get_sync() is not None
