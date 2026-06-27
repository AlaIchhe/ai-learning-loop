"""
Referee 节点 —— 论题拼合者与终局判定者。

职责：
1. 读取本轮的所有输入（current_thesis / _draft_thesis / _confirmed_thesis）。
2. 使用结构化输出调用 LLM，强制输出符合 RefereeJudgment schema 的 JSON。
3. 将本轮论题演化归档为 RoundRecord 追加到 history。
4. 判定是否继续下一轮或结束辩论。
5. 结束时生成 final_result。

契约：
- 输入：完整的 AgentState（TypedDict）
- 输出：dict，仅包含需要更新的字段
- 不修改 state 本身，不产生副作用
"""

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agents._base import extract_content, make_message
from core.model import get_chat_model
from core.prompts import (
    FINAL_SUMMARY_PROMPT,
    REFEREE_SYSTEM_PROMPT,
    final_summary_prompt,
    referee_prompt,
)
from core.schemas import RefereeJudgment, RoundRecord
from core.state import AgentState


def referee_deliberate_node(
    state: AgentState, model: ChatOpenAI | None = None
) -> dict:
    """裁判审议节点：拼合论题并判定是否继续。

    使用 with_structured_output 确保 LLM 输出严格符合 RefereeJudgment schema。
    审议后将本轮归档为 RoundRecord，并判定继续或结束。

    Args:
        state: 全局 AgentState，至少需包含 current_thesis / _draft_thesis /
               _confirmed_thesis / round / messages / history。
        model: 可注入的 LLM 实例。默认通过 get_chat_model() 读取配置。

    Returns:
        dict，包含以下键：
        - current_thesis: str          裁判拼合后的新论题（仅 continue 时）
        - messages: list[dict]         追加了 referee 消息的列表
        - history: list[RoundRecord]   追加了本轮归档的列表
        - status: "opponent_computing" | "done"
        - final_result: str            终局总结报告（仅 done 时）
    """
    if model is None:
        model = get_chat_model(temperature=0.0)

    # --- Step 1: 结构化输出，获取 RefereeJudgment ---
    structured_model = model.with_structured_output(RefereeJudgment)

    # 构建历史摘要（用于终局判定上下文）
    # 注：checkpointer 恢复时 Pydantic 模型会序列化为 dict，故需兼容两种访问方式
    history_summary = ""
    if state["history"]:
        summaries = []
        for r in state["history"]:
            rn = r.round_number if hasattr(r, "round_number") else r.get("round_number", "?")  # type: ignore[union-attr]
            tb = r.thesis_before if hasattr(r, "thesis_before") else r.get("thesis_before", "?")  # type: ignore[union-attr]
            ta = r.thesis_after if hasattr(r, "thesis_after") else r.get("thesis_after", "?")  # type: ignore[union-attr]
            cb = r.continue_debate if hasattr(r, "continue_debate") else r.get("continue_debate", "?")  # type: ignore[union-attr]
            summaries.append(f"Round {rn}: {tb} -> {ta} (continue: {cb})")
        history_summary = "\n".join(summaries)

    system_msg = SystemMessage(content=REFEREE_SYSTEM_PROMPT)
    user_msg = HumanMessage(
        content=referee_prompt(
            current_thesis=state["current_thesis"],
            draft_thesis=state["_draft_thesis"],
            confirmed_thesis=state["_confirmed_thesis"],
            round_num=state["round"],
            history_summary=history_summary,
        )
    )

    raw = structured_model.invoke([system_msg, user_msg])
    judgment = raw if isinstance(raw, RefereeJudgment) else RefereeJudgment(**raw)
    judgment.round = state["round"]

    # --- Step 2: 本轮归档 ---
    round_record = RoundRecord(
        round_number=state["round"],
        thesis_before=state["current_thesis"],
        critique=state["_critique"],
        user_response=state["_user_response"],
        draft_thesis=state["_draft_thesis"],
        confirmed_thesis=state["_confirmed_thesis"],
        thesis_after=judgment.new_thesis,
        continue_debate=judgment.continue_debate,
        referee_reasoning=judgment.reasoning,
    )

    result: dict = {
        "history": state["history"] + [round_record],
    }

    # --- Step 3: 判定路由 ---
    if judgment.continue_debate:
        # 正常轮次：静默更新论题，不产生对用户可见的消息
        result["current_thesis"] = judgment.new_thesis
        result["status"] = "opponent_computing"
        result["messages"] = state["messages"]
        # 将裁判的攻击方向指引写入轮次缓存，供下一轮 opponent 使用
        result["_improvement_hint"] = judgment.improvement_hint
    else:
        # 辩论终止：生成最终总结，作为裁判消息展示给用户
        result["status"] = "done"

        history_json = json.dumps(
            [r.model_dump() for r in result["history"]],
            ensure_ascii=False,
            default=str,
        )
        summary_system = SystemMessage(content=FINAL_SUMMARY_PROMPT)
        summary_user = HumanMessage(
            content=final_summary_prompt(
                initial_thesis=_get_initial_thesis(state),
                final_thesis=judgment.new_thesis,
                history_json=history_json,
            )
        )
        summary_response = model.invoke([summary_system, summary_user])
        final_result = extract_content(summary_response).strip()

        # 将最终总结作为裁判消息写入对话历史
        result["messages"] = state["messages"] + [
            make_message("referee", final_result, state["round"])
        ]
        result["final_result"] = final_result

    return result


def _get_initial_thesis(state: AgentState) -> str:
    """从历史记录中推断初始论题。

    第一轮的 thesis_before 即为用户最初输入的论题。
    注：checkpointer 恢复时 Pydantic 模型会序列化为 dict。
    """
    if state["history"]:
        first = state["history"][0]
        return str(
            first.thesis_before if hasattr(first, "thesis_before")
            else first.get("thesis_before", state["current_thesis"])  # type: ignore[union-attr]
        )
    return state["current_thesis"]
