from app.core.exceptions import AppError


def invalid_recommendation_result() -> AppError:
    return AppError(502, "PT_RECOMMENDATION_INVALID_RESULT", "AI 추천 결과가 올바르지 않습니다.")
