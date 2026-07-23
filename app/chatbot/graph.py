"""LangGraph 조립과 조건부 라우팅.

flowchart:
    START -> access_guard
    access_guard --(오류)--> END
    access_guard --(통과)--> intent_router
    intent_router --routine--> routine_node
    intent_router --personal--> agent_node
    intent_router --service_policy--> rag_node
    intent_router --reject--> reject_node
    agent_node --tool_calls--> tool_node --> agent_node
    agent_node --answer/오류--> format_node
    rag_node/routine_node --> format_node
    reject_node --> persist_node
    format_node --> persist_node --> END

의존성(llm/retriever/user_data/routine_service/conversation_provider, tool_registry)은
그래프 자체에 묶지 않고 매 실행마다 config["configurable"]로 주입한다."""

from langgraph.graph import END, StateGraph

from app.chatbot.nodes import (
    access_guard,
    agent_node,
    format_node,
    intent_router,
    persist_node,
    rag_node,
    reject_node,
    routine_node,
    tool_node,
)
from app.chatbot.state import ChatState


def _after_access_guard(state: ChatState) -> str:
    return "blocked" if state.get("error_code") else "continue"


def _route_by_intent(state: ChatState) -> str:
    return state.get("route") or "reject"


def _after_agent(state: ChatState) -> str:
    if state.get("error_code"):
        return "error"
    return "tools" if state.get("pending_tool_calls") else "done"


def build_chatbot_graph():
    """컴파일된 그래프를 반환한다. 도메인 종류가 여러 개라 매 요청 재컴파일할 필요는
    없고, 앱 시작 시 한 번만 만들어 재사용하면 된다(의존성은 config로 매번 갈아 끼운다)."""
    graph = StateGraph(ChatState)

    graph.add_node("access_guard", access_guard)
    graph.add_node("intent_router", intent_router)
    graph.add_node("agent_node", agent_node)
    graph.add_node("tool_node", tool_node)
    graph.add_node("rag_node", rag_node)
    graph.add_node("routine_node", routine_node)
    graph.add_node("reject_node", reject_node)
    graph.add_node("format_node", format_node)
    graph.add_node("persist_node", persist_node)

    graph.set_entry_point("access_guard")

    graph.add_conditional_edges(
        "access_guard", _after_access_guard, {"blocked": END, "continue": "intent_router"}
    )
    graph.add_conditional_edges(
        "intent_router",
        _route_by_intent,
        {
            "routine": "routine_node",
            "personal": "agent_node",
            "service_policy": "rag_node",
            "reject": "reject_node",
        },
    )
    graph.add_conditional_edges(
        "agent_node", _after_agent, {"tools": "tool_node", "done": "format_node", "error": "format_node"}
    )
    graph.add_edge("tool_node", "agent_node")
    graph.add_edge("rag_node", "format_node")
    graph.add_edge("routine_node", "format_node")
    graph.add_edge("reject_node", "persist_node")
    graph.add_edge("format_node", "persist_node")
    graph.add_edge("persist_node", END)

    return graph.compile()
