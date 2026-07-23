"""운동기록·인바디 결정론적 계산. LLM에 넘기기 전에 사실 관계(볼륨, 세션 빈도,
과거 중량 범위, 인바디 변화량)를 코드로 확정해, 모델이 수치를 추측하지 않게 한다."""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel

from app.common.models import InBodyRecord, WorkoutDiary

# 운동일지 분석에 사용할 기간(주). 이보다 오래된 기록은 분석에서 제외한다.
RECENT_WEEKS = 4
# 종목별 "과거 중량 범위"를 제공하려면 최소 이만큼의 세트 기록이 있어야 한다.
# 계획서에 정확한 기준이 없어 임의로 정한 값 — 실사용 후 조정 가능.
MIN_HISTORY_SETS_FOR_WEIGHT_RANGE = 3
# 금액·중량 등 Decimal 반올림 자리수(소수점 2자리).
TWO_PLACES = Decimal("0.01")


class WeightRange(BaseModel):
    """특정 운동 종목에서 실제로 사용한 중량의 최소~최대값.
    WorkoutAnalyzer가 이력이 충분한 종목에만 만들어준다(부족하면 필드 자체가 None)."""

    min_weight: Decimal
    max_weight: Decimal


class WorkoutAnalysisResult(BaseModel):
    """WorkoutAnalyzer.analyze() 최종 출력. 루틴 프롬프트에 "사실"로 그대로 박힌다."""

    total_volume: Decimal  # 최근 4주 총 훈련량(무게 x 횟수 합), 맨몸운동 제외
    part_session_counts: dict[str, int]  # 부위(예: CHEST) -> 최근 4주 세션 횟수
    exercise_weight_ranges: dict[str, WeightRange | None]  # 종목명 -> 중량 범위(이력 부족 시 None)


class InBodyTrend(BaseModel):
    """analyze_inbody_trend()의 출력. 최초 기록 대비 최신 기록의 변화량."""

    weight_change: Decimal | None  # 최신 체중 - 최초 체중. 기록 2건 미만이면 None
    body_fat_change: Decimal | None  # 최신 체지방률 - 최초 체지방률. 둘 중 하나라도 없으면 None
    records_used: int  # 변화량 계산에 사용된(정렬 후 처음/끝) 기록 수, 참고용 메타데이터


class WorkoutAnalyzer:
    """운동일지를 코드로 집계해 LLM에게 "사실"만 넘기는 결정론적 계산기.

    루틴 추천 LLM이 운동량이나 과거 중량을 상상해서 답하지 않도록, 이 클래스가
    먼저 확정적인 숫자(volume, 세션 빈도, 중량 범위)를 계산해두고 프롬프트에
    데이터로 박아 넣는다(app/routine/prompts.py의 _format_analysis 참고).

    analyze() 한 번 호출이 계산 전체를 담당하며, 내부적으로 3단계로 나뉜다.
    1) 최근 4주로 기간을 자른다.
    2) 부위별 세션 횟수와 총 볼륨을 동시에 누적한다.
    3) 종목별로 과거 중량 이력이 충분한지 판단해 범위를 만들거나 비워둔다.
    """

    def analyze(
        self,
        diaries: list[WorkoutDiary],
        *,
        today: date | None = None,
    ) -> WorkoutAnalysisResult:
        """운동일지 목록을 받아 WorkoutAnalysisResult(볼륨/세션빈도/중량범위)를 계산한다.

        Args:
            diaries: 기간 제한 없이 넘어온 전체 운동일지. 이 메서드 안에서 직접 4주로 자른다.
            today: 기준일. 테스트에서 날짜를 고정하기 위한 것이고, 실전에서는 생략하면
                오늘 날짜를 쓴다.

        규칙(계획서 Task 7 기준):
        - 최근 4주(RECENT_WEEKS) 이내 기록만 사용한다. 그보다 오래된 기록은 완전히 무시.
        - 같은 (날짜, 부위) 조합은 여러 종목을 했더라도 "1세션"으로만 센다.
          예: 같은 날 벤치프레스+푸시업을 모두 했어도 CHEST 세션은 1회.
        - 볼륨(총 훈련량)은 중량이 0보다 큰 세트만 (무게 x 횟수)로 더한다.
          맨몸운동(중량 0, 예: 플랭크)은 세션 횟수에는 들어가지만 볼륨에는 안 들어간다.
        - 종목별 "과거 중량 범위"는 세트 수가 MIN_HISTORY_SETS_FOR_WEIGHT_RANGE(3) 이상
          쌓였을 때만 만든다. 이력이 부족하면 None을 반환해, 프롬프트가 무게를 추측하지
          않고 RPE/RIR 같은 체감 강도로 안내하도록 신호를 준다.
        """
        # 1단계: 기준일에서 4주를 뺀 시점(cutoff)보다 오래된 일지는 버린다.
        reference_date = today or date.today()
        cutoff = reference_date - timedelta(weeks=RECENT_WEEKS)
        recent = [d for d in diaries if d.diary_date >= cutoff]

        total_volume = Decimal("0")
        sessions: set[tuple[date, str]] = set()  # (날짜, 부위) 조합 = 세션 1회. set이라 자동 중복 제거.
        exercise_weights: dict[str, list[Decimal]] = {}  # 종목명 -> 그동안 사용한 중량(0 제외) 목록

        # 2단계: 일지를 한 번 순회하면서 세션 집합과 볼륨, 종목별 중량 이력을 동시에 채운다.
        for diary in recent:
            sessions.add((diary.diary_date, diary.part))
            weights = exercise_weights.setdefault(diary.exercise, [])
            for workout_set in diary.sets:
                if workout_set.weight > 0:  # 맨몸운동(중량 0)은 볼륨/중량이력에서 제외
                    total_volume += workout_set.weight * workout_set.reps
                    weights.append(workout_set.weight)

        # sessions 집합에서 부위(part)별로 몇 번 등장했는지 세면 "부위별 세션 횟수"가 된다.
        part_session_counts: dict[str, int] = {}
        for _, part in sessions:
            part_session_counts[part] = part_session_counts.get(part, 0) + 1

        # 3단계: 종목별로 중량 기록이 충분히 쌓였을 때만 min~max 범위를 만든다.
        # 부족하면 None -> 프롬프트가 "추측 금지, RPE/RIR로 안내"라는 문구로 대체한다.
        exercise_weight_ranges: dict[str, WeightRange | None] = {}
        for exercise, weights in exercise_weights.items():
            if len(weights) >= MIN_HISTORY_SETS_FOR_WEIGHT_RANGE:
                exercise_weight_ranges[exercise] = WeightRange(
                    min_weight=min(weights), max_weight=max(weights)
                )
            else:
                exercise_weight_ranges[exercise] = None

        return WorkoutAnalysisResult(
            # 소수점 계산 누적 오차를 없애기 위해 마지막에 한 번만 소수점 2자리로 반올림한다.
            total_volume=total_volume.quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
            part_session_counts=part_session_counts,
            exercise_weight_ranges=exercise_weight_ranges,
        )


def analyze_inbody_trend(records: list[InBodyRecord]) -> InBodyTrend:
    """인바디 기록 목록에서 "최초 대비 최신이 얼마나 변했는지"만 계산하는 결정론적 함수.

    UserDataClient.get_recent_inbody()가 이미 최근 6개월·최대 6건으로 필터링해서
    넘겨주므로, 여기서는 그 안에서 가장 오래된 것과 가장 최신 것만 비교한다
    (중간 기록들은 추세선을 만들지 않고 양 끝만 본다 — 단순하고 결정론적인 설계).

    records가 2건 미만이면 비교할 대상이 없으므로 None을 반환하고, 절대 임의의
    변화량을 추측해서 채우지 않는다.
    """
    if len(records) < 2:
        return InBodyTrend(weight_change=None, body_fat_change=None, records_used=len(records))

    # 입력 순서를 신뢰하지 않고 측정일 기준으로 다시 정렬해 가장 오래된/최신 기록을 찾는다.
    ordered = sorted(records, key=lambda r: r.measured_at)
    earliest, latest = ordered[0], ordered[-1]

    # 체지방률은 선택 필드라 둘 다 값이 있을 때만 변화량을 계산한다.
    body_fat_change = None
    if earliest.body_fat_percentage is not None and latest.body_fat_percentage is not None:
        body_fat_change = latest.body_fat_percentage - earliest.body_fat_percentage

    return InBodyTrend(
        weight_change=latest.weight - earliest.weight,
        body_fat_change=body_fat_change,
        records_used=len(records),
    )
