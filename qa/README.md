# 팀원 3 원본 검사·Gold 검수 기반

2026-11-02 통합 안내: 아래는 팀원 3 소스 브랜치의 인계 설명입니다. 당시의 NOT_RUN과
미연결 상태는 현재 통합 검증 결과가 아닙니다. 최신 결과·출처·제한은
[통합 보고서](../docs/integration_20261102/INTEGRATION_REPORT.md)를 참고하세요.
독립 inventory/CSV/XLSX 도구는 아래 명령을 계속 지원하며, 전체 연결 경로는
`requirements-validation.txt` 설치 후 `python -m qa.integration`으로 실행합니다.

이 디렉터리는 팀원 1 독립 QA, 팀원 2 운영 코드와 별개다. 원본 PDF와 DRAFT를 수정하지 않는다.

## 이번 구현 범위
- C001~C020의 manifest 20개와 문서 3종 구성을 확인한다.
- C001은 개별 PDF, C002~C020은 개별 원본 또는 압축 내부 원본을 읽는다.
- 아카이브는 디스크에 해제하지 않는다. manifest 허용 경로의 일반 PDF만 읽으며 링크, 경로 이탈, 중복, 비PDF, 크기 초과는 거절한다.
- SHA-256과 선언된 페이지 수를 대조하고 pypdf로 페이지별 기계 텍스트를 보관한다.
- 이 텍스트는 시각적 원문 검수나 승인된 Gold가 아니다. OCR을 실행하지 않는다.
- 실제 파일을 읽을 수 없으면 BLOCKED, 불일치면 FAIL. 중복 해시는 별도 검토 대상으로 기록한다.

## 실행
저장소 루트에서 별도 가상환경을 사용한다.

```bash
python -m pip install -r qa/requirements.txt
python -m pytest tests/qa -q
python -m ruff check qa tests/qa
python -m qa.inventory --root . --out /tmp/leadtime-member3-review-001
```

출력 경로는 매번 새 경로여야 한다. 예시 경로는 Linux 기준이며 다른 환경에서는 새 임시 경로를 지정한다. 운영 data 아래 출력은 금지한다. 출력: DATA_INVENTORY.csv, SOURCE_TEXT_MACHINE.jsonl, INVENTORY_REPORT.json. 예외로 중단되면 완료 보고서가 없으며 명령의 비정상 종료를 검사 실패로 기록한다. 저장 중 실패한 출력 폴더도 완료 산출물로 취급하지 않는다.

## 상태 해석
- manifest_match는 파일 SHA 일치 여부다. 페이지 수 오류는 별도 status/reason으로 표시한다.
- manifest_studio_executed는 오래된 manifest의 주장일 뿐이다. 실제 Studio 이력 검증값은 studio_executed=null로 남긴다.
- human_reviewed=null은 승인 기록 미확보를 뜻한다. 기계 텍스트의 human_reviewed=false는 그 새 산출물에 사람 승인이 없다는 뜻이다.
- label_status=DRAFT는 이 도구가 승인 Gold를 생성하지 않는다는 뜻이다. 기존 별도 승인 여부를 추정하지 않는다.
- source_text_available=false는 텍스트 추출 결과가 비었다는 뜻이며 원문에 내용이 없다는 뜻이 아니다. 스캔 여부나 언어·난이도는 자동 추정하지 않는다.
- PASS는 검사된 파일의 기계 검사 범위만 의미한다. 정확도, 업무 차단, 사람 검수, 최종 출시 PASS가 아니다.

## 사람 검수
HUMAN_REVIEW_LOG.csv의 빈 템플릿을 복사해 사용한다. 원본 페이지, 표/행/셀, 정확한 원문, 기대값 JSON, DRAFT와의 차이를 먼저 기록한다. 실제 사람 판단만 ACCEPT/CORRECT/AMBIGUOUS/MISSING/NOT_IN_SOURCE로 기록한다. reviewer/reviewed_at은 AI가 생성하지 않는다. 단일 검수 REVIEWED_BY_MEMBER3와 별도 TEAM_APPROVED를 구분한다. 정답 고정 후 실제 예측과 비교한다. 식별자의 선행 0을 보존한다. 실제 0과 null/미기재를 구분한다.

## 다음 범위
1. 검사 실행 로그와 실제 60 PDF의 결과 확보.
2. C001, C013, C017, C008부터 원문 기반 필드 후보 작성 및 사람 검수.
3. 최신 PR #12와 QA 사본 PR #2 계약 검토. 운영 코드 가져오기/변경 없음.
4. 승인 Gold 기반 평가 비교기와 분모/분자 자체 테스트 구현.
5. 팀원 2 실제 예측 수신 후에만 해당 설정의 정량 성능 측정.

현재 이 커밋은 검사 도구의 초안이다. pytest/Ruff/실데이터 검사 실행 로그는 아직 없으며 모두 NOT_RUN이다.
