from app.core.exceptions import AppError


def unsupported_image_type() -> AppError:
    return AppError(400, "DIET_UNSUPPORTED_IMAGE_TYPE", "지원하지 않는 이미지 형식입니다.")


def image_too_large() -> AppError:
    return AppError(413, "DIET_IMAGE_TOO_LARGE", "이미지 크기 제한을 초과했습니다.")


def image_download_failed() -> AppError:
    return AppError(502, "DIET_IMAGE_DOWNLOAD_FAILED", "식단 이미지를 불러오지 못했습니다.", True)


def unsafe_image_url() -> AppError:
    return AppError(400, "DIET_INVALID_IMAGE_URL", "허용되지 않는 이미지 URL입니다.")


def food_not_detected() -> AppError:
    return AppError(422, "DIET_FOOD_NOT_DETECTED", "사진에서 분석할 음식을 확인하지 못했습니다.")


def invalid_analysis_result() -> AppError:
    return AppError(502, "DIET_INVALID_ANALYSIS_RESULT", "AI 식단 분석 결과가 올바르지 않습니다.")


def llm_timeout() -> AppError:
    return AppError(504, "LLM_TIMEOUT", "AI 분석 응답 시간이 초과되었습니다.", True)


def llm_error() -> AppError:
    return AppError(502, "LLM_NETWORK_ERROR", "AI 식단 분석에 실패했습니다.", True)
