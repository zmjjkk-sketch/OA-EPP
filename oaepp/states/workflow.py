"""F-T-007 Issue关闭必填PR编号 — WorkflowState

提供 Issue-PR 关联规则的状态管理：
- require_pr_on_close: 是否要求关闭 Issue 时关联 PR（默认开启）
- require_merged_pr: 是否要求 PR 已合并才能关闭 Issue
- course_rules: 各课程的独立规则配置
- issue_pr_associations: Issue-PR 关联记录
- warnings: 未关联 PR 直接关闭的警告记录
- pr_validation_result: PR 验证结果
"""

import datetime
import json
from typing import Any, Dict, List, Optional

try:
    import reflex as rx
except Exception:
    rx = None


if rx is not None:
    class WorkflowState(rx.State):
        """Issue-PR 关联规则状态管理"""

        # ── 核心状态变量 ──
        require_pr_on_close: bool = True
        require_merged_pr: bool = False
        course_rules: Dict[str, Dict[str, Any]] = {}
        issue_pr_associations: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []
        pr_validation_result: Dict[str, Any] = {}

        # ── UI 状态变量 ──
        pr_number_input: str = ""
        show_pr_modal: bool = False
        current_issue: Optional[Dict[str, Any]] = None
        selected_course_id: str = ""
        course_id_input: str = ""
        editing_course_id: str = ""
        show_unmerged_confirm: bool = False
        pending_close_data: Optional[Dict[str, Any]] = None
        toast_message: str = ""
        toast_type: str = "info"

        _github_token: Optional[str] = None

        # ── 规则配置 ──

        def toggle_pr_required(self, value: bool):
            self.require_pr_on_close = value

        def toggle_merged_required(self, value: bool):
            self.require_merged_pr = value

        def set_global_rule(self, require_pr_on_close: bool, require_merged_pr: bool):
            self.require_pr_on_close = require_pr_on_close
            self.require_merged_pr = require_merged_pr

        def set_course_rule(self, course_id: str, require_pr_on_close: bool, require_merged_pr: bool):
            self.course_rules[course_id] = {
                "course_id": course_id,
                "require_pr_on_close": require_pr_on_close,
                "require_merged_pr": require_merged_pr,
                "updated_at": datetime.datetime.now().isoformat(),
            }

        def get_course_rule(self, course_id: str) -> Dict[str, Any]:
            if course_id in self.course_rules:
                return self.course_rules[course_id]
            return {
                "course_id": course_id,
                "require_pr_on_close": self.require_pr_on_close,
                "require_merged_pr": self.require_merged_pr,
            }

        def remove_course_rule(self, course_id: str):
            self.course_rules.pop(course_id, None)

        def update_course_id_input(self, value: str):
            self.course_id_input = value

        def update_editing_course_id(self, value: str):
            self.editing_course_id = value

        def add_course_rule_ui(self):
            cid = self.course_id_input.strip()
            if cid:
                self.set_course_rule(cid, True, False)
                self.course_id_input = ""
                self.toast_message = f"课程 {cid} 规则已添加"
                self.toast_type = "success"

        def edit_course_rule_ui(self, course_id: str):
            self.editing_course_id = course_id

        def save_edited_course_rule(self, course_id: str, require_pr: bool, require_merged: bool):
            self.set_course_rule(course_id, require_pr, require_merged)
            self.editing_course_id = ""

        # ── PR 验证 ──

        async def validate_pr_number(self, pr_number: int, owner: str = "roboticsystem", repo: str = "OA-EPP") -> Dict[str, Any]:
            self.pr_validation_result = await self._validate_pr_via_api(owner, repo, pr_number)
            return self.pr_validation_result

        async def _validate_pr_via_api(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
            try:
                import os
                import httpx

                api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
                headers = {}
                if self._github_token or os.environ.get("GITHUB_TOKEN"):
                    token = self._github_token or os.environ.get("GITHUB_TOKEN")
                    headers["Authorization"] = f"token {token}"

                async with httpx.AsyncClient() as client:
                    response = await client.get(api_url, headers=headers, timeout=10)

                if response.status_code == 404:
                    return {
                        "valid": False,
                        "exists": False,
                        "message": f"PR #{pr_number} 不存在",
                    }
                if response.status_code != 200:
                    return {
                        "valid": False,
                        "exists": False,
                        "message": f"GitHub API 请求失败: {response.status_code}",
                    }

                data = response.json()
                is_merged = data.get("merged", False) or (data.get("merged_at") is not None)

                return {
                    "valid": True,
                    "exists": True,
                    "number": data.get("number", 0),
                    "title": data.get("title", ""),
                    "state": data.get("state", ""),
                    "is_merged": is_merged,
                    "merged_at": data.get("merged_at"),
                    "user_login": data.get("user", {}).get("login", ""),
                    "url": data.get("html_url", ""),
                    "message": f"PR #{pr_number} 验证成功",
                }
            except Exception as e:
                return {
                    "valid": False,
                    "exists": False,
                    "message": f"验证失败: {str(e)}",
                }

        def update_pr_input(self, value: str):
            self.pr_number_input = value
            self.pr_validation_result = {}
            if value.isdigit():
                import asyncio
                asyncio.create_task(self._validate_pr_via_api("roboticsystem", "OA-EPP", int(value)))

        def open_pr_modal(self, issue: Dict[str, Any]):
            self.current_issue = issue
            self.pr_number_input = ""
            self.pr_validation_result = {}
            self.show_pr_modal = True

        def close_pr_modal(self):
            self.show_pr_modal = False
            self.current_issue = None
            self.pr_number_input = ""
            self.pr_validation_result = {}
            self.show_unmerged_confirm = False
            self.pending_close_data = None

        def confirm_close_issue(self):
            if not self.current_issue or not self.pr_number_input.isdigit():
                self.toast_message = "请输入有效的 PR 编号"
                self.toast_type = "error"
                return
            import asyncio
            asyncio.create_task(self._do_close_issue())

        async def _do_close_issue(self):
            issue = self.current_issue or {}
            pr_num = int(self.pr_number_input)
            course_id = self.selected_course_id or "default"
            closed_by = "teacher"

            rule = self.get_course_rule(course_id)
            validation = await self._validate_pr_via_api("roboticsystem", "OA-EPP", pr_num)

            if not validation.get("valid"):
                self.pr_validation_result = validation
                return

            if rule.get("require_merged_pr", False) and not validation.get("is_merged"):
                self.pending_close_data = {
                    "issue": issue,
                    "pr_number": pr_num,
                    "pr_info": validation,
                    "course_id": course_id,
                }
                self.show_unmerged_confirm = True
                return

            await self._record_association(issue.get("number", 0), pr_num, validation, course_id, closed_by)
            self.show_pr_modal = False
            self.current_issue = None
            self.pr_number_input = ""
            self.pr_validation_result = {}
            self.toast_message = f"Issue #{issue.get('number')} 已关闭，关联 PR #{pr_num}"
            self.toast_type = "success"

        def confirm_unmerged_close(self):
            if not self.pending_close_data:
                return
            data = self.pending_close_data
            import asyncio
            asyncio.create_task(self._do_unmerged_close(data))
            self.show_unmerged_confirm = False
            self.pending_close_data = None

        async def _do_unmerged_close(self, data: Dict[str, Any]):
            issue = data["issue"]
            pr_num = data["pr_number"]
            pr_info = data["pr_info"]
            course_id = data["course_id"]
            closed_by = "teacher"

            await self._record_association(issue.get("number", 0), pr_num, pr_info, course_id, closed_by)
            self.show_pr_modal = False
            self.current_issue = None
            self.pr_number_input = ""
            self.pr_validation_result = {}
            self.toast_message = f"Issue #{issue.get('number')} 已关闭（未合并 PR #{pr_num}）"
            self.toast_type = "warning"

        def cancel_unmerged_close(self):
            self.show_unmerged_confirm = False
            self.pending_close_data = None

        # ── Webhook ──

        async def handle_github_webhook(self, event_data: Dict[str, Any]):
            try:
                if event_data.get("action") != "closed":
                    return
                issue = event_data.get("issue", {})
                if not issue:
                    return
                issue_number = issue.get("number")
                issue_title = issue.get("title", "")
                closed_by = issue.get("closed_by", {}).get("login", "")
                closed_at = issue.get("closed_at")
                if not issue_number:
                    return

                has_pr_link = False
                body = issue.get("body", "")
                if body and ("#" in body or "pull/" in body):
                    has_pr_link = True
                for comment in event_data.get("comments", []):
                    if "#" in comment.get("body", ""):
                        has_pr_link = True
                if not has_pr_link:
                    await self._generate_warning(issue_number, issue_title, closed_by, closed_at)
            except Exception:
                pass

        def get_webhook_payload(self) -> Dict[str, Any]:
            return {"url": "/api/webhook/issue-close", "description": "监听 Issue 关闭事件"}

        # ── 记录管理 ──

        async def _record_association(self, issue_number: int, pr_number: int, pr_info: Dict[str, Any], course_id: str, closed_by: str):
            association = {
                "id": len(self.issue_pr_associations) + 1,
                "course_id": course_id,
                "issue_number": issue_number,
                "pr_number": pr_number,
                "pr_title": pr_info.get("title", ""),
                "pr_state": pr_info.get("state", ""),
                "pr_is_merged": pr_info.get("is_merged", False),
                "pr_merged_at": pr_info.get("merged_at"),
                "pr_url": pr_info.get("url", ""),
                "closed_by": closed_by,
                "closed_at": datetime.datetime.now().isoformat(),
            }
            self.issue_pr_associations.append(association)

        async def _generate_warning(self, issue_number: int, issue_title: str, closed_by: str, closed_at: Optional[str]):
            warning = {
                "id": len(self.warnings) + 1,
                "issue_number": issue_number,
                "issue_title": issue_title,
                "closed_by": closed_by,
                "closed_at": closed_at or datetime.datetime.now().isoformat(),
                "warning_type": "no_pr_associated",
                "warning_message": f"Issue #{issue_number} 被直接关闭，未关联 PR",
                "resolved": False,
                "resolved_at": None,
                "created_at": datetime.datetime.now().isoformat(),
            }
            self.warnings.append(warning)

        def resolve_warning(self, warning_id: int):
            for warning in self.warnings:
                if warning.get("id") == warning_id:
                    warning["resolved"] = True
                    warning["resolved_at"] = datetime.datetime.now().isoformat()
                    break

        # ── Toast ──

        def clear_toast(self):
            self.toast_message = ""
            self.toast_type = "info"

else:
    WorkflowState = None
