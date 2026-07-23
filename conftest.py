import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-smoke",
        action="store_true",
        default=False,
        help="실제 Gemini API를 호출하는 smoke 테스트를 실행한다 (비용 발생, 기본은 스킵).",
    )
    parser.addoption(
        "--run-rag-eval",
        action="store_true",
        default=False,
        help="실제 Gemini Embedding API를 호출하는 RAG 품질 평가를 실행한다 (비용 발생, 기본은 스킵).",
    )


def pytest_collection_modifyitems(config, items):
    skip_smoke = pytest.mark.skip(reason="--run-smoke 옵션 없이는 실행하지 않음 (실제 Gemini 호출)")
    skip_rag_eval = pytest.mark.skip(
        reason="--run-rag-eval 옵션 없이는 실행하지 않음 (실제 Gemini Embedding 호출)"
    )
    for item in items:
        if "smoke" in item.keywords and not config.getoption("--run-smoke"):
            item.add_marker(skip_smoke)
        if "rag_eval" in item.keywords and not config.getoption("--run-rag-eval"):
            item.add_marker(skip_rag_eval)
