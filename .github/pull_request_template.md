## 📌 PR 요약 (Summary)
- (예) City 하위의 Village 데이터를 조회하는 REST API 구현 및 Service 계층 비즈니스 로직 추가
- 

## 💡 어떤 기능인가요?
- (예: LMS 수강 신청 시 좌석 예약 처리를 위한 백엔드 API 구현)
-
## ✨ 변경 사항 (Changes)
- `VillageController` 및 `GET /api/v1/cities/{cityId}/villages` 추가
- `VillageService` 내역 조회 로직 구현
- **DB 스키마 변경:** `village` 테이블에 새로운 컬럼 추가 여부 (없음)

## 📝 작업 상세 내용
- [ ] 기능 구현
- [ ] 버그 수정
- [ ] 리팩토링
- [ ] 테스트 완료

## 📋 테스트 내용 (Testing)
- [x] JUnit 단위 테스트 (Controller, Service) 통과 확인
- [x] Postman을 통한 로컬 환경 API 엔드포인트 응답 테스트 완료

# 🚨 리뷰어 참고 사항 (Reviewer Notes)
## 💬 리뷰어에게 할 말
- 동시성 처리 부분에서 락(Lock)을 걸었는데, 성능상 문제가 없을지 중점적으로 봐주시면 감사하겠습니다!

## ✅ 체크 리스트
- [ ] 로컬 환경에서 빌드가 정상적으로 성공했나요?
- [ ] 코딩 컨벤션(네이밍, 들여쓰기 등)을 준수했나요?
- [ ] 불필요한 파일이나 콘솔 로그(System.out.println 등)가 포함되지 않았나요?

## 📎 관련 이슈 (Related Issues)
### { Closes #이슈번호 } 형식으로 PR을 작성하면, 이 코드가 메인 브랜치에 병합될 때해당 번호의 이슈가 자동으로 닫히게(Close) 됩니다.
- Closes #
