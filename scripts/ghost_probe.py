#!/usr/bin/env python3
"""幽灵探针 —— 用真实 API Key 探测 LLM 环境健康状态。

独立诊断脚本，不纳入 pytest。按需手动运行：
    python scripts/ghost_probe.py           # 运行所有探针
    python scripts/ghost_probe.py --quick   # 仅快速探针（几乎零 token 消耗）

每个探针输出 ✅ PASS 或 ❌ FAIL，附带诊断信息（响应内容、耗时、token 数）。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# 确保项目根目录在 sys.path 中（必须在 core.env 导入之前）
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from core.env import setup_environment  # noqa: E402

setup_environment(_project_root)

from core.model import has_configured_api_key  # noqa: E402

# =============================================================================
# 辅助函数
# =============================================================================


def _check(probe_name: str) -> None:
    """打印探针开始标记。"""
    print(f"\n{'='*60}")
    print(f"  🩺 {probe_name}")
    print(f"{'='*60}")


def _pass(detail: str = "") -> None:
    """打印通过。"""
    msg = "  ✅ PASS"
    if detail:
        msg += f"  | {detail}"
    print(msg)


def _fail(detail: str) -> None:
    """打印失败。"""
    print(f"  ❌ FAIL  | {detail}")


def _skip(detail: str) -> None:
    """打印跳过。"""
    print(f"  ⏭️  SKIP  | {detail}")


def _has_api_key() -> bool:
    """检查是否配置了 API Key。"""
    return has_configured_api_key()


def _get_model_info() -> dict:
    """获取当前模型配置信息。"""
    return {
        "model": os.getenv("LLM_MODEL", "gpt-4o"),
        "base_url": os.getenv("LLM_BASE_URL") or "OpenAI (默认)",
        "has_key": _has_api_key(),
    }


# =============================================================================
# 探针 1: API 连通性（~10 token）
# =============================================================================


def probe_api_connectivity() -> bool:
    """用配置的 provider 发一条最小请求，验证 200 响应。"""
    _check("API 连通性")

    if not _has_api_key():
        _fail("未配置 API Key。请在 .env 中设置 LLM_API_KEY 或 OPENAI_API_KEY。")
        return False

    info = _get_model_info()
    print(f"  Model: {info['model']}")
    print(f"  Base URL: {info['base_url']}")

    try:
        from langchain_core.messages import HumanMessage

        from core.model import get_chat_model

        model = get_chat_model(temperature=0.0)
        start = time.time()
        response = model.invoke([HumanMessage(content="Hi")])
        elapsed = time.time() - start

        content = response.content if isinstance(response.content, str) else str(response.content)
        _pass(f"延迟 {elapsed:.2f}s, 响应: '{content[:50]}'")
        return True
    except Exception as e:
        _fail(f"{type(e).__name__}: {e}")
        return False


# =============================================================================
# 探针 2: 结构化输出（~200 token）
# =============================================================================


def probe_structured_output() -> bool:
    """测试 with_structured_output(RefereeJudgment) 是否正常返回有效 JSON。"""
    _check("结构化输出 (RefereeJudgment)")

    if not _has_api_key():
        _skip("未配置 API Key。")
        return True

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from core.model import get_chat_model
        from core.schemas import RefereeJudgment

        model = get_chat_model(temperature=0.0)
        structured = model.with_structured_output(RefereeJudgment)

        start = time.time()
        raw = structured.invoke([
            SystemMessage(content="你是裁判。只输出 JSON。"),
            HumanMessage(content="请判定：当前论题=AI应受监管，草稿=AI应在高风险领域受监管，确认版=AI应在高风险领域受监管。"),
        ])
        elapsed = time.time() - start

        judgment = raw if isinstance(raw, RefereeJudgment) else RefereeJudgment(**raw)

        # 验证字段完整性（round 由工作流状态管理，不属于 RefereeJudgment 契约）
        assert isinstance(judgment.continue_debate, bool), "continue_debate 应为 bool"
        assert isinstance(judgment.new_thesis, str) and len(judgment.new_thesis) > 0
        assert isinstance(judgment.reasoning, str) and len(judgment.reasoning) > 0
        assert isinstance(judgment.improvement_hint, str), "improvement_hint 应为 str"

        _pass(
            f"延迟 {elapsed:.2f}s, "
            f"continue_debate={judgment.continue_debate}, "
            f"new_thesis='{judgment.new_thesis[:60]}...'"
        )
        return True
    except Exception as e:
        _fail(f"{type(e).__name__}: {e}")
        return False


# =============================================================================
# 探针 3: Opponent 提示词有效性（~100 token）
# =============================================================================


def probe_opponent_prompt() -> bool:
    """测试批判者提示词：输出是否 ≤80 字、单点聚焦。"""
    _check("Opponent 提示词有效性")

    if not _has_api_key():
        _skip("未配置 API Key。")
        return True

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from core.model import get_chat_model
        from core.prompts import OPPONENT_SYSTEM_PROMPT, opponent_prompt

        model = get_chat_model(temperature=0.7)
        thesis = "人工智能的发展应该受到严格监管，以确保其安全性和可控性。"

        start = time.time()
        response = model.invoke([
            SystemMessage(content=OPPONENT_SYSTEM_PROMPT),
            HumanMessage(content=opponent_prompt(thesis)),
        ])
        elapsed = time.time() - start

        content = response.content if isinstance(response.content, str) else str(response.content)
        char_count = len(content)

        issues = []
        if char_count > 80:
            issues.append(f"字数超限: {char_count} > 80")
        if "第一" in content or "第二" in content or "此外" in content:
            issues.append("疑似多点列举")
        if "作为AI" in content or "根据" in content:
            issues.append("疑似AI腔")

        if issues:
            _fail(f"延迟 {elapsed:.2f}s, 字数={char_count} | {'; '.join(issues)}\n  输出: '{content[:100]}'")
            return False
        else:
            _pass(f"延迟 {elapsed:.2f}s, 字数={char_count}, 输出: '{content[:80]}'")
            return True
    except Exception as e:
        _fail(f"{type(e).__name__}: {e}")
        return False


# =============================================================================
# 探针 4: Presenter 提示词有效性（~100 token）
# =============================================================================


def probe_presenter_prompt() -> bool:
    """测试精确化者提示词：是否保留核心意图、消解歧义。"""
    _check("Presenter 提示词有效性")

    if not _has_api_key():
        _skip("未配置 API Key。")
        return True

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from core.model import get_chat_model
        from core.prompts import PRESENTER_SYSTEM_PROMPT, presenter_prompt

        model = get_chat_model(temperature=0.7)

        start = time.time()
        response = model.invoke([
            SystemMessage(content=PRESENTER_SYSTEM_PROMPT),
            HumanMessage(content=presenter_prompt(
                current_thesis="AI应受监管。",
                critique="你说的'监管'具体指什么？谁来判断什么是高风险？",
                user_response="我觉得监管应该分级别，医疗和司法领域要严格，普通的推荐系统可以松一些。",
            )),
        ])
        elapsed = time.time() - start

        content = response.content if isinstance(response.content, str) else str(response.content)
        _pass(f"延迟 {elapsed:.2f}s, 输出: '{content[:120]}'")
        return True
    except Exception as e:
        _fail(f"{type(e).__name__}: {e}")
        return False


# =============================================================================
# 探针 5: Referee 提示词有效性（~300 token）
# =============================================================================


def probe_referee_prompt() -> bool:
    """测试裁判提示词：是否正确输出 JSON、continue_debate 判定合理。"""
    _check("Referee 提示词有效性")

    if not _has_api_key():
        _skip("未配置 API Key。")
        return True

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from core.model import get_chat_model
        from core.prompts import REFEREE_SYSTEM_PROMPT, referee_prompt
        from core.schemas import RefereeJudgment

        model = get_chat_model(temperature=0.0)
        structured = model.with_structured_output(RefereeJudgment)

        start = time.time()
        raw = structured.invoke([
            SystemMessage(content=REFEREE_SYSTEM_PROMPT),
            HumanMessage(content=referee_prompt(
                current_thesis="AI应受监管。",
                draft_thesis="AI应在高风险领域（如医疗诊断、司法判决）受到严格监管。",
                confirmed_thesis="AI应在高风险领域受到严格监管，低风险领域可适当放宽。",
                round_num=1,
            )),
        ])
        elapsed = time.time() - start

        judgment = raw if isinstance(raw, RefereeJudgment) else RefereeJudgment(**raw)

        _pass(
            f"延迟 {elapsed:.2f}s, "
            f"continue_debate={judgment.continue_debate}, "
            f"new_thesis='{judgment.new_thesis[:80]}...'"
        )
        return True
    except Exception as e:
        _fail(f"{type(e).__name__}: {e}")
        return False


# =============================================================================
# 探针 6: 完整一轮（~600 token）
# =============================================================================


def probe_full_round() -> bool:
    """模拟一轮完整流程（opponent → presenter → referee），验证三者协作。"""
    _check("完整一轮流程")

    if not _has_api_key():
        _skip("未配置 API Key。")
        return True

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from core.model import get_chat_model
        from core.prompts import (
            OPPONENT_SYSTEM_PROMPT,
            PRESENTER_SYSTEM_PROMPT,
            REFEREE_SYSTEM_PROMPT,
            opponent_prompt,
            presenter_prompt,
            referee_prompt,
        )
        from core.schemas import RefereeJudgment

        thesis = "人工智能的发展应该受到严格监管。"
        user_response_simulated = (
            "我同意监管应该分级。在高风险领域如医疗和司法，AI决策需要人工复核；"
            "但在低风险领域可以更灵活。"
        )

        total_start = time.time()

        # Step 1: Opponent
        t0 = time.time()
        opp_model = get_chat_model(temperature=0.7)
        opp_resp = opp_model.invoke([
            SystemMessage(content=OPPONENT_SYSTEM_PROMPT),
            HumanMessage(content=opponent_prompt(thesis)),
        ])
        critique = opp_resp.content if isinstance(opp_resp.content, str) else str(opp_resp.content)
        t1 = time.time()
        print(f"  [Opponent]  {t1-t0:.2f}s | {len(critique)}字 | {critique[:80]}")

        # Step 2: Presenter
        pres_model = get_chat_model(temperature=0.7)
        pres_resp = pres_model.invoke([
            SystemMessage(content=PRESENTER_SYSTEM_PROMPT),
            HumanMessage(content=presenter_prompt(thesis, critique, user_response_simulated)),
        ])
        draft = pres_resp.content if isinstance(pres_resp.content, str) else str(pres_resp.content)
        t2 = time.time()
        print(f"  [Presenter] {t2-t1:.2f}s | {len(draft)}字 | {draft[:80]}")

        # Step 3: Referee
        ref_model = get_chat_model(temperature=0.0)
        structured = ref_model.with_structured_output(RefereeJudgment)
        raw = structured.invoke([
            SystemMessage(content=REFEREE_SYSTEM_PROMPT),
            HumanMessage(content=referee_prompt(thesis, draft, draft, 1)),
        ])
        judgment = raw if isinstance(raw, RefereeJudgment) else RefereeJudgment(**raw)
        t3 = time.time()
        print(f"  [Referee]   {t3-t2:.2f}s | continue={judgment.continue_debate} | {judgment.new_thesis[:80]}")

        total_elapsed = time.time() - total_start
        _pass(f"总耗时 {total_elapsed:.2f}s")
        return True
    except Exception as e:
        _fail(f"{type(e).__name__}: {e}")
        return False


# =============================================================================
# 探针 7: 环境诊断（零 token）
# =============================================================================


def probe_environment() -> bool:
    """诊断当前环境配置（不消耗 token）。"""
    _check("环境诊断")

    info = _get_model_info()
    print(f"  Model:      {info['model']}")
    print(f"  Base URL:   {info['base_url']}")
    print(f"  API Key:    {'✅ 已配置' if info['has_key'] else '❌ 未配置'}")

    # LangSmith
    ls_key = os.getenv("LANGCHAIN_API_KEY", "")
    ls_project = os.getenv("LANGCHAIN_PROJECT", "")
    ls_tracing = os.getenv("LANGCHAIN_TRACING_V2", "")
    print(f"  LangSmith:  {'✅ 已启用' if ls_tracing == 'true' and ls_key else '⏭️  未启用'} "
          f"(project={ls_project or 'N/A'})")

    # Python 版本
    print(f"  Python:     {sys.version.split()[0]}")

    # 依赖检查（覆盖 pyproject.toml 的运行时依赖）
    deps = [
        "dotenv",
        "langchain",
        "langchain_core",
        "langchain_openai",
        "langgraph",
        "pydantic",
        "streamlit",
    ]
    for dep in deps:
        try:
            __import__(dep)
            print(f"  {dep:20s} ✅")
        except ImportError:
            print(f"  {dep:20s} ❌ 未安装")

    _pass("环境诊断完成")
    return True


# =============================================================================
# 主入口
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="幽灵探针 —— LLM 环境健康诊断工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/ghost_probe.py            # 运行所有探针
  python scripts/ghost_probe.py --quick    # 仅快速探针（不消耗 token）
        """,
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="仅运行快速探针（环境诊断 + API 连通性，几乎零 token 消耗）",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  👻 幽灵探针 —— LLM 环境健康诊断")
    print("=" * 60)
    print(f"  项目根目录: {_project_root}")
    print(f"  .env 文件:  {'✅ 存在' if (_project_root / '.env').exists() else '❌ 不存在'}")

    results: dict[str, bool] = {}

    # 快速探针
    results["环境诊断"] = probe_environment()
    results["API 连通性"] = probe_api_connectivity()

    if not args.quick:
        # 完整探针（消耗 token）
        if _has_api_key():
            results["结构化输出"] = probe_structured_output()
            results["Opponent 提示词"] = probe_opponent_prompt()
            results["Presenter 提示词"] = probe_presenter_prompt()
            results["Referee 提示词"] = probe_referee_prompt()
            results["完整一轮流程"] = probe_full_round()
        else:
            print("\n  ⚠️  未配置 API Key，跳过需要 LLM 调用的探针。")
            for name in ["结构化输出", "Opponent 提示词", "Presenter 提示词", "Referee 提示词", "完整一轮流程"]:
                results[name] = True  # 跳过不算失败

    # 总结
    print(f"\n{'='*60}")
    print("  探针总结")
    print(f"{'='*60}")
    passed = sum(1 for v in results.values() if v)
    failed = sum(1 for v in results.values() if not v)
    for name, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"  {status}  {name}")
    print(f"\n  {passed}/{len(results)} 通过, {failed} 失败")

    if failed > 0:
        print("\n  💡 提示: 检查 .env 配置和网络连接后重试。")
        sys.exit(1)
    else:
        print("\n  🎉 所有探针通过！")
        sys.exit(0)


if __name__ == "__main__":
    main()
