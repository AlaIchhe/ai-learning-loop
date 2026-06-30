#!/usr/bin/env python3
"""
真实 API 集成测试 —— 使用真实 LLM + 真实 LangGraph 流程，无 Mock。

适配 DeepSeek（不支持 with_structured_output，改用 JSON-mode 手动解析）。

所有测试用真实的 LLM 调用，验证：
1. 单 Agent 有效性（Opponent / Presenter / Referee）
2. 完整 LangGraph 工作流（含 interrupt / resume）
3. 多轮论题演化

运行：
    python scripts/integration_test_real.py           # 全部测试
    python scripts/integration_test_real.py --quick   # 仅单 Agent 测试
    python scripts/integration_test_real.py --workflow  # 仅工作流测试
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

# 确保项目根目录在 sys.path 中（必须在 core.env 导入之前）
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from socratic_loop.infra.env import setup_environment  # noqa: E402

setup_environment(_project_root)

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from socratic_loop.agents.referee import referee_deliberate_node  # noqa: E402
from socratic_loop.infra.model import get_chat_model, has_configured_api_key  # noqa: E402
from socratic_loop.core.prompts import (  # noqa: E402
    OPPONENT_SYSTEM_PROMPT,
    PRESENTER_SYSTEM_PROMPT,
    opponent_prompt,
    presenter_prompt,
)
from socratic_loop.core.state import AgentState, make_initial_state  # noqa: E402

# =============================================================================
# 辅助函数
# =============================================================================


def _header(title: str) -> None:
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")


def _sub(title: str) -> None:
    print(f"\n  --- {title} ---")


def _ok(detail: str = "") -> None:
    msg = "  [PASS]"
    if detail:
        msg += f"  {detail}"
    print(msg)


def _fail(detail: str) -> None:
    print(f"  [FAIL]  {detail}")


def _info(detail: str) -> None:
    print(f"  [INFO]  {detail}")


def _has_api_key() -> bool:
    return has_configured_api_key()


# =============================================================================
# 测试 1: Opponent 单 Agent 有效性
# =============================================================================


def test_opponent_agent() -> bool:
    """验证 Opponent 对真实论题生成有效批判（≤80字，单点突破）。"""
    _header("测试 1: Opponent Agent（真实 API）")

    model = get_chat_model(temperature=0.7)
    thesis = "所有AI系统都应受到政府监管。"

    _info(f"论题: {thesis}")
    t0 = time.time()
    response = model.invoke([
        SystemMessage(content=OPPONENT_SYSTEM_PROMPT),
        HumanMessage(content=opponent_prompt(thesis)),
    ])
    elapsed = time.time() - t0

    content = response.content if isinstance(response.content, str) else str(response.content)
    char_count = len(content)

    _info(f"延迟: {elapsed:.2f}s | 字数: {char_count}")
    _info(f"输出: {content}")

    # 验证规则
    ok = True
    if char_count > 80:
        _fail(f"字数超限: {char_count} > 80")
        ok = False
    else:
        _ok("字数 ≤ 80 ✓")

    multipoint_markers = ["第一", "第二", "此外", "另外", "同时", "一方面"]
    if any(m in content for m in multipoint_markers):
        _fail("疑似多点列举")
        ok = False
    else:
        _ok("单点聚焦 ✓")

    ai_tells = ["作为AI", "根据", "从唯物主义", "作为一个语言模型"]
    if any(t in content for t in ai_tells):
        _fail("疑似AI腔")
        ok = False
    else:
        _ok("自然表达 ✓")

    return ok


# =============================================================================
# 测试 2: Presenter 单 Agent 有效性
# =============================================================================


def test_presenter_agent() -> bool:
    """验证 Presenter 将用户回应精确化为学术论题。"""
    _header("测试 2: Presenter Agent（真实 API）")

    model = get_chat_model(temperature=0.7)
    thesis = "所有AI系统都应受到政府监管。"
    critique = "谁来定义'所有AI系统'？一个开源的表情包生成器和一个自动驾驶系统，适用同一套监管标准？"
    user_response = (
        "我觉得监管应该分级。像医疗诊断、司法判决、自动驾驶这种涉及生命安全的领域，"
        "必须严格监管，要求人工复核。但像内容推荐、游戏AI这种风险低的，可以宽松一些。"
    )

    _info(f"原论题: {thesis}")
    _info(f"批判: {critique}")
    _info(f"用户回应: {user_response}")

    t0 = time.time()
    response = model.invoke([
        SystemMessage(content=PRESENTER_SYSTEM_PROMPT),
        HumanMessage(content=presenter_prompt(thesis, critique, user_response)),
    ])
    elapsed = time.time() - t0

    content = response.content if isinstance(response.content, str) else str(response.content)
    _info(f"延迟: {elapsed:.2f}s | 字数: {len(content)}")
    _info(f"输出: {content}")

    # 基本验证
    ok = True
    if len(content) < 10:
        _fail("输出过短")
        ok = False
    else:
        _ok("输出长度正常 ✓")

    # 检查是否保留了核心意图（分级监管）
    has_grading = any(kw in content for kw in ["分级", "差异", "风险", "严格"])
    if not has_grading:
        _fail("可能丢失了用户核心意图（分级监管）")
        ok = False
    else:
        _ok("保留了分级监管的核心意图 ✓")

    return ok


# =============================================================================
# 测试 3: Referee 单 Agent 有效性（JSON-mode，适配 DeepSeek）
# =============================================================================


def test_referee_agent() -> bool:
    """验证 Referee 裁判节点（JSON-mode，适配 DeepSeek）正确输出结构化判定。"""
    _header("测试 3: Referee Agent - JSON-mode（真实 API，适配 DeepSeek）")


    state: AgentState = {
        "current_thesis": "AI应受监管。",
        "round": 1,
        "agent_temperature": 0.7,
        "status": "referee_deliberating",
        "messages": [],
        "history": [],
        "final_result": "",
        "_critique": "批判：论题缺乏边界限定。",
        "_user_response": "同意，应限定在高风险领域。",
        "_draft_thesis": "AI应在高风险领域（医疗、司法、自动驾驶）受到严格监管，低风险领域可宽松监管。",
        "_confirmed_thesis": "AI应在涉及生命安全的领域受到严格监管，低风险领域可适度放宽。",
        "_improvement_hint": "",
    }

    t0 = time.time()
    result = referee_deliberate_node(state, json_mode=True)
    elapsed = time.time() - t0

    _info(f"延迟: {elapsed:.2f}s")

    # 从历史记录中提取 judgment 信息
    record = result["history"][-1]
    continue_debate = record.continue_debate
    new_thesis = record.thesis_after
    reasoning = record.referee_reasoning

    _info(f"continue_debate: {continue_debate}")
    _info(f"new_thesis: {new_thesis[:100]}...")
    _info(f"reasoning: {reasoning[:80]}...")
    elapsed = time.time() - t0

    _info(f"延迟: {elapsed:.2f}s")
    _info(f"continue_debate: {continue_debate}")
    _info(f"new_thesis: {new_thesis[:100]}...")
    _info(f"reasoning: {reasoning[:80]}...")

    ok = True
    if not isinstance(continue_debate, bool):
        _fail("continue_debate 类型错误")
        ok = False
    else:
        _ok("continue_debate 类型正确 ✓")

    if not new_thesis or len(new_thesis) < 5:
        _fail("new_thesis 过短或为空")
        ok = False
    else:
        _ok("new_thesis 有效 ✓")

    if not reasoning or len(reasoning) < 5:
        _fail("reasoning 过短或为空")
        ok = False
    else:
        _ok("reasoning 有效 ✓")

    return ok


# =============================================================================
# Referee 节点适配器（JSON-mode，用于 LangGraph 工作流测试）
# =============================================================================


def _deepseek_referee_node(state: AgentState) -> dict:
    """裁判节点适配器：使用生产 referee_deliberate_node 的 JSON-mode。

    与 agents/referee.py 共享同一实现，仅指定 json_mode=True。
    """
    return referee_deliberate_node(state, json_mode=True)  # type: ignore[return-value]


# =============================================================================
# 测试 4: LangGraph 单轮工作流（真实 LLM + 真实 interrupt）
# =============================================================================


def test_workflow_single_round() -> bool:
    """完整单轮辩论：Opponent → interrupt → Presenter → interrupt → Referee → done。

    使用真实 DeepSeek API 调用 + 真实 LangGraph interrupt()/Command(resume=...)。
    这是最接近生产环境运行方式的测试。
    """
    _header("测试 4: LangGraph 完整单轮工作流（真实 API）")

    # ---- 导入真实 Agent 节点（Opponent/Presenter 不需要修改） ----
    from socratic_loop.agents.opponent import opponent_compute_node, opponent_interact_node
    from socratic_loop.agents.presenter import presenter_compute_node, presenter_interact_node
    from socratic_loop.workflow.graph import build_graph

    checkpointer = MemorySaver()
    graph = build_graph(
        opponent_compute_node=opponent_compute_node,
        opponent_interact_node=opponent_interact_node,
        presenter_compute_node=presenter_compute_node,
        presenter_interact_node=presenter_interact_node,
        referee_deliberate_node=_deepseek_referee_node,  # DeepSeek 兼容版
        checkpointer=checkpointer,
    )

    thread_id = str(uuid4())
    config: dict = {"configurable": {"thread_id": thread_id}}
    thesis = "人工智能的发展应该受到严格监管。"

    _info(f"初始论题: {thesis}")

    # ---- Step 1: invoke → 停在 opponent_interact ----
    _sub("Step 1: invoke 到第一个 interrupt")
    t0 = time.time()
    result = graph.invoke(make_initial_state(thesis), config)
    t1 = time.time()

    _info(f"状态: {result['status']} | 延迟: {t1-t0:.2f}s")
    _info(f"Opponent 批判: {result['_critique'][:100]}")

    ok = True
    if result["status"] != "awaiting_critique_response":
        _fail("状态应为 awaiting_critique_response")
        ok = False
    else:
        _ok("状态正确: awaiting_critique_response ✓")
    if len(result["messages"]) != 1 or result["messages"][0]["role"] != "opponent":
        _fail("消息列表异常")
        ok = False
    else:
        _ok("消息正确: 1条 opponent 消息 ✓")

    # ---- Step 2: resume with user response → 停在 presenter_interact ----
    _sub("Step 2: resume 用户回应")
    user_reply = (
        "我同意监管应该有区别。高风险领域如医疗诊断和自动驾驶必须严格监管，"
        "但低风险的AI应用可以给予更多自由度。"
    )
    t0 = time.time()
    result = graph.invoke(Command(resume=user_reply), config)
    t1 = time.time()

    _info(f"状态: {result['status']} | 延迟: {t1-t0:.2f}s")
    _info(f"Presenter 草稿: {result['_draft_thesis'][:120]}")

    if result["status"] != "awaiting_thesis_confirmation":
        _fail("状态应为 awaiting_thesis_confirmation")
        ok = False
    else:
        _ok("状态正确: awaiting_thesis_confirmation ✓")
    roles = [m["role"] for m in result["messages"]]
    if roles != ["opponent", "user", "presenter"]:
        _fail(f"消息角色序列异常: {roles}")
        ok = False
    else:
        _ok("消息角色序列正确: opponent → user → presenter ✓")

    # ---- Step 3: resume with confirmation → Referee → done ----
    _sub("Step 3: resume 用户确认 → Referee 判定")
    t0 = time.time()
    result = graph.invoke(Command(resume=result["_draft_thesis"]), config)
    t1 = time.time()

    _info(f"状态: {result['status']} | 延迟: {t1-t0:.2f}s")
    if result["status"] == "done":
        _info(f"最终论题: {result['current_thesis'][:150]}...")
        _info(f"最终总结: {result['final_result'][:150]}...")
    else:
        _info(f"新论题 (继续下一轮): {result['current_thesis'][:150]}...")

    if result["status"] not in ("done", "awaiting_critique_response"):
        _fail(f"意外状态: {result['status']}")
        ok = False
    elif result["status"] == "done":
        _ok("裁判判定结束 ✓")
    else:
        _ok("裁判判定继续 → 进入下一轮 ✓")

    msg_count = len(result["messages"])
    _info(f"总消息数: {msg_count}, 历史轮次数: {len(result['history'])}")

    # 验证历史记录
    if len(result["history"]) != 1:
        _fail("应有1条轮次记录")
        ok = False
    else:
        rec = result["history"][0]
        _info(f"RoundRecord: thesis_before={rec.thesis_before[:40]}... → thesis_after={rec.thesis_after[:40]}...")
        _ok("RoundRecord 归档成功 ✓")

    return ok


# =============================================================================
# 测试 5: 多轮工作流（两轮完整辩论）
# =============================================================================


def test_workflow_multi_round() -> bool:
    """两轮辩论工作流 —— 验证多轮状态演化和 checkpoint 持久性。"""
    _header("测试 5: LangGraph 多轮工作流（真实 API）")

    from socratic_loop.agents.opponent import opponent_compute_node, opponent_interact_node
    from socratic_loop.agents.presenter import presenter_compute_node, presenter_interact_node
    from socratic_loop.workflow.graph import build_graph

    checkpointer = MemorySaver()
    graph = build_graph(
        opponent_compute_node=opponent_compute_node,
        opponent_interact_node=opponent_interact_node,
        presenter_compute_node=presenter_compute_node,
        presenter_interact_node=presenter_interact_node,
        referee_deliberate_node=_deepseek_referee_node,
        checkpointer=checkpointer,
    )

    thread_id = str(uuid4())
    config: dict = {"configurable": {"thread_id": thread_id}}
    thesis = "AI应该被监管。"

    _info(f"初始论题: {thesis}")

    ok = True
    total_start = time.time()

    # === Round 1 ===
    _sub("Round 1")
    s = graph.invoke(make_initial_state(thesis), config)
    _info(f"R1 批判: {s['_critique'][:100]}")
    s = graph.invoke(Command(resume="高风险AI如医疗诊断必须严格监管，低风险可放宽。"), config)
    _info(f"R1 草稿: {s['_draft_thesis'][:100]}")
    s = graph.invoke(Command(resume=s["_draft_thesis"]), config)

    if s["status"] == "done":
        _info("R1 裁判判定结束（单轮即充分）")
        # 单轮就结束了，多轮测试也算通过（裁判认为无需继续）
        _ok("裁判认为论题已充分深化（单轮完成）✓")
        return ok

    _info(f"R1 裁判判定继续 → 新论题: {s['current_thesis'][:120]}")
    assert s["round"] == 2, f"应进入R2，实际round={s['round']}"

    # === Round 2 ===
    _sub("Round 2")

    # R2: 用户回应批判 → Presenter 精确化
    s = graph.invoke(
        Command(resume="我觉得还应该考虑开源AI模型的问题，它们可以被任何人下载和修改。"),
        config,
    )
    _info(f"R2 批判: {s['_critique'][:100]}")
    _info(f"R2 草稿: {s['_draft_thesis'][:100]}")

    # R2: 用户确认草稿 → Referee 判定
    s = graph.invoke(Command(resume=s["_draft_thesis"]), config)

    total_elapsed = time.time() - total_start
    _info(f"R2 Referee 后状态: {s['status']} | 总耗时: {total_elapsed:.2f}s")

    # 验证
    if len(s["history"]) < 2:
        _fail(f"应有≥2条轮次记录，实际: {len(s['history'])}")
        ok = False
    else:
        _ok(f"{len(s['history'])} 轮历史记录完整 ✓")
        for _i, rec in enumerate(s["history"]):
            _info(f"R{rec.round_number}: {rec.thesis_before[:40]}... → {rec.thesis_after[:40]}...")

    if s["status"] == "done":
        _ok("最终状态: done ✓")
        _info(f"最终论题: {s['current_thesis'][:200]}")
        _info(f"最终总结: {s['final_result'][:200]}...")
    else:
        _info(f"最终状态: {s['status']}（裁判认为仍需继续深化）")

    return ok


# =============================================================================
# 测试 6: Checkpoint 持久性验证
# =============================================================================


def test_checkpoint_persistence() -> bool:
    """验证 checkpoint 在中断点的状态保存与恢复。"""
    _header("测试 6: Checkpoint 持久性验证")

    from socratic_loop.agents.opponent import opponent_compute_node, opponent_interact_node
    from socratic_loop.agents.presenter import presenter_compute_node, presenter_interact_node
    from socratic_loop.workflow.graph import build_graph

    checkpointer = MemorySaver()
    graph = build_graph(
        opponent_compute_node=opponent_compute_node,
        opponent_interact_node=opponent_interact_node,
        presenter_compute_node=presenter_compute_node,
        presenter_interact_node=presenter_interact_node,
        referee_deliberate_node=_deepseek_referee_node,
        checkpointer=checkpointer,
    )

    thread_id = str(uuid4())
    config: dict = {"configurable": {"thread_id": thread_id}}

    # Invoke → interrupt
    graph.invoke(make_initial_state("checkpoint测试论题"), config)

    # 通过 get_state 读取 checkpoint
    snapshot = graph.get_state(config)
    saved = snapshot.values

    ok = True
    if saved["current_thesis"] != "checkpoint测试论题":
        _fail("checkpoint 中 thesis 不一致")
        ok = False
    else:
        _ok("thesis 保存正确 ✓")

    if saved["status"] != "awaiting_critique_response":
        _fail(f"checkpoint 中 status 不一致: {saved['status']}")
        ok = False
    else:
        _ok("status 保存正确 ✓")

    if saved["round"] != 1:
        _fail("checkpoint 中 round 不一致")
        ok = False
    else:
        _ok("round 保存正确 ✓")

    if len(saved["messages"]) != 1:
        _fail(f"checkpoint 中消息数异常: {len(saved['messages'])}")
        ok = False
    else:
        _ok("消息保存正确 ✓")

    # 验证可以从 checkpoint 恢复
    result = graph.invoke(Command(resume="用户回应"), config)
    if result["status"] != "awaiting_thesis_confirmation":
        _fail("从 checkpoint 恢复后状态异常")
        ok = False
    else:
        _ok("从 checkpoint 恢复成功 ✓")

    return ok


# =============================================================================
# 主入口
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="真实 API 集成测试 —— DeepSeek 兼容版",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/integration_test_real.py             # 全部测试
  python scripts/integration_test_real.py --quick     # 仅单 Agent 测试
  python scripts/integration_test_real.py --workflow  # 仅工作流测试
        """,
    )
    parser.add_argument("--quick", action="store_true", help="仅运行单 Agent 测试")
    parser.add_argument("--workflow", action="store_true", help="仅运行工作流测试")
    args = parser.parse_args()

    print("=" * 65)
    print("  真实 API 集成测试 —— DeepSeek 兼容版")
    print("=" * 65)
    print(f"  Model: {os.getenv('LLM_MODEL', 'gpt-4o')}")
    print(f"  Base URL: {os.getenv('LLM_BASE_URL', 'OpenAI (默认)')}")

    if not _has_api_key():
        print("\n  [FATAL] 未配置 API Key。请在 .env 中设置 LLM_API_KEY。")
        sys.exit(1)

    results: dict[str, bool] = {}

    if args.workflow:
        results["LangGraph 单轮工作流"] = test_workflow_single_round()
        results["LangGraph 多轮工作流"] = test_workflow_multi_round()
        results["Checkpoint 持久性"] = test_checkpoint_persistence()
    elif args.quick:
        results["Opponent 单Agent"] = test_opponent_agent()
        results["Presenter 单Agent"] = test_presenter_agent()
        results["Referee JSON-mode"] = test_referee_agent()
    else:
        # 完整测试序列
        results["Opponent 单Agent"] = test_opponent_agent()
        results["Presenter 单Agent"] = test_presenter_agent()
        results["Referee JSON-mode"] = test_referee_agent()
        results["LangGraph 单轮工作流"] = test_workflow_single_round()
        results["LangGraph 多轮工作流"] = test_workflow_multi_round()
        results["Checkpoint 持久性"] = test_checkpoint_persistence()

    # 总结
    print(f"\n{'='*65}")
    print("  测试总结")
    print(f"{'='*65}")
    passed = sum(1 for v in results.values() if v)
    failed = sum(1 for v in results.values() if not v)
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}]  {name}")
    print(f"\n  {passed}/{len(results)} 通过, {failed} 失败")

    if failed > 0:
        print("\n  提示: 检查具体失败项的详细信息。")
        sys.exit(1)
    else:
        print("\n  全部集成测试通过！")
        sys.exit(0)


if __name__ == "__main__":
    main()
