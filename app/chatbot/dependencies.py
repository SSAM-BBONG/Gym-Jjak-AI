"""챗봇/루틴 도메인 조립부. app/core/dependencies.py는 어떤 도메인도 import하지 않는
단방향 규칙을 지키고, 챗봇 쪽 서비스 조립은 이 파일이 전담한다
(.docs/MODULE_OWNERSHIP.md §5). Settings -> GeminiAdapter/Embeddings -> Chroma/Retriever
-> UserDataClient/ConversationProvider -> RoutineService -> ChatbotGraph -> ChatbotService
순서로 팩토리를 구성한다. 각 팩토리는 lru_cache로 프로세스당 1회만 생성한다."""

from functools import lru_cache

from app.chatbot.graph import build_chatbot_graph
from app.chatbot.nodes import ChatbotDeps
from app.chatbot.service import ChatbotService
from app.common.conversation import ConversationProvider, InMemoryConversationProvider
from app.common.dev_user_data import LocalDevUserDataClient
from app.common.user_data_client import InMemoryUserDataClient, UserDataClient
from app.core.settings import get_settings
from app.llm.gemini_adapter import GeminiAdapter
from app.llm.port import LLMPort
from app.rag.embeddings import GeminiEmbeddings
from app.rag.retriever import ChromaRetriever, RetrieverPort
from app.rag.vector_store import create_chroma_client, get_or_create_collection
from app.routine.analyzer import WorkoutAnalyzer
from app.routine.service import RoutineService


@lru_cache
def get_chatbot_llm_client() -> LLMPort:
    return GeminiAdapter(temperature=get_settings().chatbot_llm_temperature)


@lru_cache
def get_routine_llm_client() -> LLMPort:
    return GeminiAdapter(temperature=get_settings().routine_llm_temperature)


@lru_cache
def get_user_data_client() -> UserDataClient:
    """Spring 연동 전까지 사용하는 임시 구현체. Deferred Integration Plan에서 HTTP로 교체.

    app_env=local일 때만 Swagger 등으로 바로 확인 가능한 샘플 데이터(LocalDevUserDataClient)를
    쓰고, 그 외 환경(test/production)에서는 항상 안전한 빈 값만 반환하는
    InMemoryUserDataClient를 쓴다 — 샘플 데이터가 실수로 운영에 노출되지 않게 하기 위함이다."""
    if get_settings().app_env == "local":
        return LocalDevUserDataClient()
    return InMemoryUserDataClient()


@lru_cache
def get_conversation_provider() -> ConversationProvider:
    return InMemoryConversationProvider()


@lru_cache
def get_retriever() -> RetrieverPort:
    settings = get_settings()
    client = create_chroma_client(settings)
    collection = get_or_create_collection(client)
    return ChromaRetriever(collection, GeminiEmbeddings())


@lru_cache
def get_routine_service() -> RoutineService:
    llm: LLMPort = get_routine_llm_client()
    return RoutineService(
        user_data=get_user_data_client(),
        analyzer=WorkoutAnalyzer(),
        retriever=get_retriever(),
        llm=llm,
    )


@lru_cache
def get_chatbot_deps() -> ChatbotDeps:
    return ChatbotDeps(
        llm=get_chatbot_llm_client(),
        retriever=get_retriever(),
        user_data=get_user_data_client(),
        routine_service=get_routine_service(),
        conversation_provider=get_conversation_provider(),
    )


@lru_cache
def get_chatbot_graph():
    return build_chatbot_graph()


@lru_cache
def get_chatbot_service() -> ChatbotService:
    return ChatbotService(graph=get_chatbot_graph(), deps=get_chatbot_deps())
