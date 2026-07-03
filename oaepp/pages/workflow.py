"""F-T-007 Issue-PR 关联规则管理页面

验收标准：
1. 规则开关可配置（默认开启）
2. 关闭 Issue 时弹框强制填写 PR 编号并实时校验
3. 未合并 PR 关闭时弹出教师二次确认
4. Issue 详情页展示关联 PR 编号及合并状态
5. Webhook 监听绕过平台直接关闭情况并生成警告
6. 规则配置支持按课程独立设置
"""
try:
    import reflex as rx
except Exception:
    rx = None


def _html_fallback():
    return """
<div class="oaepp-workflow-page">
  <h1>工作流管理</h1>
  <div class="section">
    <h2>规则配置</h2>
    <div class="rule-item">
      <label><input type="checkbox" checked> 关闭 Issue 时必须关联 PR</label>
    </div>
    <div class="rule-item">
      <label><input type="checkbox"> 要求 PR 已合并才能关闭 Issue</label>
    </div>
  </div>
  <div class="section">
    <h2>警告记录</h2>
    <table>
      <tr><th>Issue</th><th>标题</th><th>关闭者</th><th>状态</th></tr>
      <tr><td>#123</td><td>修复登录问题</td><td>user1</td><td>待处理</td></tr>
    </table>
  </div>
</div>
"""


workflow_page = None
if rx is not None:
    try:
        from oaepp.states.workflow import WorkflowState
    except ImportError:
        try:
            from states.workflow import WorkflowState
        except ImportError:
            WorkflowState = None

    def _toast_area():
        return rx.cond(
            WorkflowState.toast_message != "",
            rx.box(
                rx.hstack(
                    rx.text(WorkflowState.toast_message, size="2"),
                    rx.button("×", on_click=WorkflowState.clear_toast, variant="ghost", size="sm"),
                    justify="space-between",
                    align="center",
                    width="100%",
                ),
                padding="12px 16px",
                border_radius="8px",
                background=rx.cond(
                    WorkflowState.toast_type == "error", "#fef2f2",
                    rx.cond(WorkflowState.toast_type == "warning", "#fffbeb",
                        rx.cond(WorkflowState.toast_type == "success", "#f0fdf4", "#eff6ff")
                    ),
                ),
                border=rx.cond(
                    WorkflowState.toast_type == "error", "1px solid #fecaca",
                    rx.cond(WorkflowState.toast_type == "warning", "1px solid #fef3c7",
                        rx.cond(WorkflowState.toast_type == "success", "1px solid #bbf7d0", "1px solid #bfdbfe")
                    ),
                ),
                width="100%",
                margin_bottom="12px",
            ),
        )

    def _rule_config_section():
        return rx.box(
            rx.vstack(
                rx.heading("规则配置", size="5"),
                rx.text("全局规则适用于所有课程，可单独为课程配置独立规则", color="gray", size="2"),

                rx.hstack(
                    rx.checkbox(
                        default_checked=True,
                        on_change=WorkflowState.toggle_pr_required,
                    ),
                    rx.text("关闭 Issue 时必须关联 PR", weight="medium"),
                    spacing="3",
                    align="center",
                ),
                rx.hstack(
                    rx.checkbox(
                        default_checked=False,
                        on_change=WorkflowState.toggle_merged_required,
                    ),
                    rx.text("要求 PR 已合并才能关闭 Issue", weight="medium"),
                    spacing="3",
                    align="center",
                ),
                rx.box(
                    rx.text("当前状态：", weight="bold"),
                    rx.text(f"强制关联 PR: {'开启' if WorkflowState.require_pr_on_close else '关闭'}"),
                    rx.text(f"要求合并: {'开启' if WorkflowState.require_merged_pr else '关闭'}"),
                    padding="12px",
                    background="#f8fafc",
                    border_radius="8px",
                    width="100%",
                ),

                rx.divider(),
                rx.heading("课程独立规则", size="4"),
                rx.text("添加课程 ID 来配置独立规则", color="gray", size="2"),

                rx.hstack(
                    rx.input(
                        placeholder="输入课程 ID",
                        value=WorkflowState.course_id_input,
                        on_change=WorkflowState.update_course_id_input,
                    ),
                    rx.button("添加", on_click=WorkflowState.add_course_rule_ui, size="sm"),
                    spacing="3",
                    align="end",
                ),

                rx.cond(
                    len(WorkflowState.course_rules) > 0,
                    rx.vstack(
                        rx.foreach(
                            WorkflowState.course_rules,
                            lambda item: _course_rule_card(item),
                        ),
                        spacing="3",
                        width="100%",
                    ),
                    rx.text("暂无课程独立规则，将使用全局规则", color="gray", size="1"),
                ),

                spacing="4",
                width="100%",
            ),
            padding="24px",
            border_radius="12px",
            box_shadow="0 4px 12px rgba(0,0,0,0.05)",
            background="white",
            width="100%",
        )

    def _course_rule_card(item):
        return rx.box(
            rx.hstack(
                rx.vstack(
                    rx.text(f"课程: {item.course_id}", weight="bold"),
                    rx.text(f"强制关联 PR: {'开启' if item.require_pr_on_close else '关闭'}"),
                    rx.text(f"要求合并: {'开启' if item.require_merged_pr else '关闭'}"),
                    spacing="1",
                ),
                rx.button("删除", on_click=WorkflowState.remove_course_rule(item.course_id), size="sm", variant="outline", color_scheme="red"),
                justify="space-between",
                align="start",
                width="100%",
            ),
            padding="12px",
            border="1px solid #e2e8f0",
            border_radius="8px",
            width="100%",
        )

    def _pr_validation_modal():
        return rx.cond(
            WorkflowState.show_pr_modal,
            rx.box(
                rx.box(
                    rx.vstack(
                        rx.hstack(
                            rx.heading("关联 PR 编号", size="4"),
                            rx.button("×", on_click=WorkflowState.close_pr_modal, variant="ghost", size="sm"),
                            justify="space-between",
                            align="center",
                            width="100%",
                        ),
                        rx.text("请输入与此 Issue 关联的 PR 编号", color="gray", size="2"),
                        rx.input(
                            placeholder="输入 PR 编号",
                            value=WorkflowState.pr_number_input,
                            on_change=WorkflowState.update_pr_input,
                        ),

                        rx.cond(
                            WorkflowState.pr_validation_result != {},
                            rx.box(
                                rx.cond(
                                    WorkflowState.pr_validation_result.valid,
                                    rx.vstack(
                                        rx.hstack(
                                            rx.text("✓", color="green"),
                                            rx.text(WorkflowState.pr_validation_result.message, color="green"),
                                            spacing="2",
                                        ),
                                        rx.text(f"标题: {WorkflowState.pr_validation_result.title}", size="1"),
                                        rx.text(f"状态: {WorkflowState.pr_validation_result.state}", size="1"),
                                        rx.text(f"合并状态: {'已合并' if WorkflowState.pr_validation_result.is_merged else '未合并'}", size="1"),
                                        spacing="1",
                                    ),
                                    rx.hstack(
                                        rx.text("✗", color="red"),
                                        rx.text(WorkflowState.pr_validation_result.message, color="red"),
                                        spacing="2",
                                    ),
                                ),
                                padding="12px",
                                border_radius="8px",
                                background=rx.cond(
                                    WorkflowState.pr_validation_result.valid, "#f0fdf4", "#fef2f2"
                                ),
                                width="100%",
                            ),
                        ),

                        rx.hstack(
                            rx.button("取消", on_click=WorkflowState.close_pr_modal, variant="outline"),
                            rx.button(
                                "确认关闭 Issue",
                                on_click=WorkflowState.confirm_close_issue,
                                color_scheme="red",
                            ),
                            justify="end",
                            spacing="3",
                            width="100%",
                        ),
                        spacing="4",
                        width="100%",
                    ),
                    padding="24px",
                    background="white",
                    border_radius="12px",
                    box_shadow="0 10px 40px rgba(0,0,0,0.2)",
                    max_width="480px",
                    width="90%",
                ),
                position="fixed",
                top="0",
                left="0",
                width="100vw",
                height="100vh",
                background="rgba(0,0,0,0.4)",
                display="flex",
                align_items="center",
                justify_content="center",
                z_index="1000",
            ),
        )

    def _unmerged_confirm_modal():
        return rx.cond(
            WorkflowState.show_unmerged_confirm,
            rx.box(
                rx.box(
                    rx.vstack(
                        rx.heading("确认关闭", size="4"),
                        rx.text("该 PR 尚未合并，确定要关闭此 Issue 吗？", color="orange", weight="medium"),
                        rx.text("关闭未合并 PR 的 Issue 可能导致工作流不完整", color="gray", size="2"),
                        rx.hstack(
                            rx.button("取消", on_click=WorkflowState.cancel_unmerged_close, variant="outline"),
                            rx.button("确认关闭", on_click=WorkflowState.confirm_unmerged_close, color_scheme="red"),
                            justify="end",
                            spacing="3",
                            width="100%",
                        ),
                        spacing="4",
                        width="100%",
                    ),
                    padding="24px",
                    background="white",
                    border_radius="12px",
                    box_shadow="0 10px 40px rgba(0,0,0,0.2)",
                    max_width="400px",
                    width="90%",
                ),
                position="fixed",
                top="0",
                left="0",
                width="100vw",
                height="100vh",
                background="rgba(0,0,0,0.4)",
                display="flex",
                align_items="center",
                justify_content="center",
                z_index="1001",
            ),
        )

    def _warning_records_section():
        return rx.box(
            rx.vstack(
                rx.hstack(
                    rx.heading("警告记录", size="5"),
                    rx.button("刷新", on_click=WorkflowState.load_warnings, size="sm"),
                    justify="space-between",
                    align="center",
                    width="100%",
                ),
                rx.text("Webhook 检测到绕过平台直接关闭 Issue 的记录", color="gray", size="2"),

                rx.cond(
                    len(WorkflowState.warnings) > 0,
                    rx.vstack(
                        rx.foreach(
                            WorkflowState.warnings,
                            lambda w: rx.box(
                                rx.hstack(
                                    rx.vstack(
                                        rx.hstack(
                                            rx.text(f"Issue #{w.issue_number}", weight="bold"),
                                            rx.cond(
                                                w.resolved,
                                                rx.box(rx.text("已处理", size="1"), padding="2px 8px", border_radius="4px", background="#dcfce7", color="green"),
                                                rx.box(rx.text("待处理", size="1"), padding="2px 8px", border_radius="4px", background="#fef3c7", color="orange"),
                                            ),
                                            spacing="3",
                                            align="center",
                                        ),
                                        rx.text(w.issue_title, size="2", color="gray"),
                                        rx.text(f"关闭者: {w.closed_by}  |  {w.warning_message}", size="1", color="gray"),
                                        spacing="1",
                                    ),
                                    rx.cond(
                                        ~w.resolved,
                                        rx.button("标记处理", on_click=WorkflowState.resolve_warning(w.id), size="sm", variant="outline"),
                                    ),
                                    justify="space-between",
                                    align="start",
                                    width="100%",
                                ),
                                padding="12px",
                                border_radius="8px",
                                background=rx.cond(w.resolved, "#f8fafc", "#fffbeb"),
                                border=rx.cond(w.resolved, "1px solid #e2e8f0", "1px solid #fef3c7"),
                                width="100%",
                            ),
                        ),
                        spacing="3",
                        width="100%",
                    ),
                    rx.box(
                        rx.text("暂无警告记录，Webhook 正在监听中", color="gray"),
                        padding="24px",
                        text_align="center",
                    ),
                ),

                spacing="4",
                width="100%",
            ),
            padding="24px",
            border_radius="12px",
            box_shadow="0 4px 12px rgba(0,0,0,0.05)",
            background="white",
            width="100%",
        )

    def _associations_section():
        return rx.box(
            rx.vstack(
                rx.hstack(
                    rx.heading("Issue-PR 关联记录", size="5"),
                    rx.button("刷新", on_click=WorkflowState.load_associations, size="sm"),
                    justify="space-between",
                    align="center",
                    width="100%",
                ),

                rx.cond(
                    len(WorkflowState.issue_pr_associations) > 0,
                    rx.vstack(
                        rx.foreach(
                            WorkflowState.issue_pr_associations,
                            lambda a: rx.box(
                                rx.vstack(
                                    rx.hstack(
                                        rx.text(f"Issue #{a.issue_number}", weight="bold"),
                                        rx.box(
                                            rx.text(f"PR #{a.pr_number}", size="1"),
                                            padding="2px 8px",
                                            border_radius="4px",
                                            background="#dbeafe",
                                        ),
                                        rx.cond(
                                            a.pr_is_merged,
                                            rx.box(rx.text("已合并", size="1"), padding="2px 8px", border_radius="4px", background="#dcfce7", color="green"),
                                            rx.box(rx.text("未合并", size="1"), padding="2px 8px", border_radius="4px", background="#fef3c7", color="orange"),
                                        ),
                                        spacing="3",
                                        align="center",
                                    ),
                                    rx.text(f"PR 标题: {a.pr_title}", size="2", color="gray"),
                                    rx.hstack(
                                        rx.text(f"关闭者: {a.closed_by}", size="1", color="gray"),
                                        rx.text(f"课程: {a.course_id}", size="1", color="gray"),
                                        spacing="4",
                                    ),
                                    spacing="1",
                                ),
                                padding="12px",
                                border="1px solid #e2e8f0",
                                border_radius="8px",
                                width="100%",
                            ),
                        ),
                        spacing="3",
                        width="100%",
                    ),
                    rx.box(
                        rx.text("暂无关联记录", color="gray"),
                        padding="24px",
                        text_align="center",
                    ),
                ),

                spacing="4",
                width="100%",
            ),
            padding="24px",
            border_radius="12px",
            box_shadow="0 4px 12px rgba(0,0,0,0.05)",
            background="white",
            width="100%",
        )

    def _webhook_info_section():
        return rx.box(
            rx.vstack(
                rx.heading("Webhook 配置", size="5"),
                rx.text("监听 GitHub Issue 关闭事件，检测绕过平台直接关闭的情况", color="gray", size="2"),
                rx.box(
                    rx.vstack(
                        rx.text("Webhook URL:", weight="bold"),
                        rx.text("/api/webhook/issue-close", font_family="monospace", background="#f1f5f9", padding="8px 12px", border_radius="4px"),
                        rx.text("触发事件: Issues (closed)", size="2", color="gray"),
                        spacing="2",
                    ),
                    padding="12px",
                    background="#f8fafc",
                    border_radius="8px",
                    width="100%",
                ),
                spacing="4",
                width="100%",
            ),
            padding="24px",
            border_radius="12px",
            box_shadow="0 4px 12px rgba(0,0,0,0.05)",
            background="white",
            width="100%",
        )

    def _demo_issue_section():
        return rx.box(
            rx.vstack(
                rx.heading("模拟 Issue 关闭", size="5"),
                rx.text("在下方输入 Issue 编号和课程 ID 来模拟关闭流程", color="gray", size="2"),
                rx.hstack(
                    rx.input(placeholder="Issue 编号", value=WorkflowState.pr_number_input, on_change=WorkflowState.update_pr_input),
                    rx.input(placeholder="课程 ID (可选)", value=WorkflowState.course_id_input, on_change=WorkflowState.update_course_id_input),
                    rx.button(
                        "开始关闭",
                        on_click=WorkflowState.open_pr_modal({"number": 0, "title": "示例 Issue"}),
                        color_scheme="red",
                    ),
                    spacing="3",
                    width="100%",
                    flex_wrap="wrap",
                ),
                spacing="4",
                width="100%",
            ),
            padding="24px",
            border_radius="12px",
            box_shadow="0 4px 12px rgba(0,0,0,0.05)",
            background="white",
            width="100%",
        )

    @rx.page(route="/workflow", title="工作流管理")
    def workflow_page():
        return rx.container(
            rx.vstack(
                rx.heading("工作流管理", size="6"),
                rx.text("Issue-PR 关联规则配置与监控", color="gray"),
                _toast_area(),
                _rule_config_section(),
                _demo_issue_section(),
                _associations_section(),
                _warning_records_section(),
                _webhook_info_section(),
                _pr_validation_modal(),
                _unmerged_confirm_modal(),
                spacing="6",
                width="100%",
                padding="24px",
            ),
            min_height="100vh",
            background="#f8fafc",
            max_width="960px",
            width="100%",
        )


def render():
    return _html_fallback()
