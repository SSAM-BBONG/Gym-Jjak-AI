from app.core.exceptions import AppError


def no_candidates_found() -> AppError:
    return AppError(404, "PT_RECOMMENDATION_NO_CANDIDATES", "조건에 맞는 트레이너를 찾지 못했습니다.")


def onboarding_not_found() -> AppError:
    return AppError(404, "PT_RECOMMENDATION_ONBOARDING_NOT_FOUND", "온보딩 정보가 없어 추천을 진행할 수 없습니다.")


def spring_data_unavailable() -> AppError:
    return AppError(502, "PT_RECOMMENDATION_SPRING_UNAVAILABLE", "회원·트레이너 정보를 조회하지 못했습니다.", True)


def invalid_recommendation_result() -> AppError:
    return AppError(502, "PT_RECOMMENDATION_INVALID_RESULT", "AI 추천 결과가 올바르지 않습니다.")
