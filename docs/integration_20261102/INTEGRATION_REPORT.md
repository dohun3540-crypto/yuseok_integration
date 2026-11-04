# LeadTime Guardian GitHub 통합 검수

2026-11-02 KST. 작업 브랜치: `codex/leadtime-integration-20261102`.
통합 기준 및 Draft PR 대상: `feat/qa-pr13-pr14-final-selective-freeze-20261101`
(`ece3a7dcc254b5c7a14c72792750170346419eb8`). README-only main은 변경하지 않는다.
이 보고서는 이전 날짜의 완료 보고보다 **이번 통합 변경**에 우선한다.

## 1차 계약 확정

| 구성 | 확인한 소스 | 통합 결정 |
|---|---|---|
| 구도훈 QA 기준 | ece3a7d, 통합 저장소에 존재 | Wrapper, case_id, 중복 문서, provenance, stage, Cross-Agent 유지 |
| QA 병렬 수정 | d244d6a, 통합 저장소에 존재 | 재귀 타입 비교와 35개 테스트 선택 이식. 순환/과도한 깊이와 signed zero 차이 차단 유지 |
| 윤현준 V6 | 원본 PR #12 e9b9992, open/unmerged | engine, studio_adapter, studio_integration, strict_json, provenance, agents_api 6개 blob 모두 기준과 동일. 중복 이식하지 않음 |
| 김민주 데이터 도구 | 원본 PR #13 a925103, open/unmerged | qa 도구·템플릿·미승인 C001 후보·tests/qa 이식. 개발 검증 SHA 90e2faa와 구분 |
| QA copy 원본 PR #15/#16 | 연결 도구에서 404 | 원본 PR 상태/현재 HEAD는 NOT_VERIFIED. 통합 저장소에 복제된 지정 SHA 사용 |

상세 blob 및 ZIP SHA-256은 `SOURCE_SHA_MANIFEST.json` 참조. ZIP 9개 항목 중
인계서·프롬프트·체크섬 3개는 두 ZIP 간 동일하다. DOCX 안의 실행 프롬프트도
TXT와 중복이므로 별도의 추가 지시로 계산하지 않았다.

## 실제 연결과 변경 내역

`python -m qa.integration`이 원본 bytes를 읽어 V6의 `documents_from_export`와
기존 `audit_combined_bytes`를 호출한다. 이 경로는 Python 엔진, 독립 portfolio QA,
원본 QA 입력/보고서가 제공될 때의 Cross-Agent 검증을 수행한다. 이어서 팀원 3
`inventory.collect`, `review_records.inspect_records`, `xlsx_snapshot.snapshot`과
미승인 후보의 필드별 비교를 연결한다. 파일을 고치거나 승인 상태를 만들지 않는다.

루트 `qa`는 저장소 전용 검수 도구이고 `leadtime_guardian.qa`는 설치되는 독립 QA
패키지이다. 같은 모듈명을 덮어쓰지 않는다. `requirements-validation.txt` 하나로
양쪽 의존성을 설치하고, 전체 pytest가 `tests/qa`까지 수집한다.

| 충돌/문제 | 처리 |
|---|---|
| 병렬 QA 브랜치를 통째로 적용하면 기존 severity/null-version 개선 삭제 | input_delivery 비교 함수와 새 타입 테스트만 선택. 기존 Studio QA adapter 유지 |
| QA/인벤토리 JSON에서 `1e999`, `-1e999`가 무한대로 파싱됨 | 수정 전 4개 실패 재현. QA는 V6 strict parser 재사용, 인벤토리는 finite float 검증 추가 |
| Windows autocrlf가 보관 원본 해시 변경 | data/configs/후보에 -text 속성. Git blob bytes 복원, 기존 data/configs 내용은 전부 동일함을 확인 |
| 기존 CI 두 개가 전체 테스트/Ruff 중복 실행 | 단일 Integrated Python QA workflow로 통합. 팀원 3 전용 브랜치 조건을 복사하지 않고 같은 전체 검사에 포함 |
| Windows symlink 권한 부재 | 해당 테스트에 권한 확인 fixture. WinError 1314만 skip, Linux에서는 계속 실행 |

엔진의 경고 차단, 신뢰 수량·날짜 대조, EA/KRW 정책은 완화하지 않았다. 실제 0을
null로 바꾸지 않고, PO999를 PO1로 치환하지 않으며, 다른 Receipt의 날짜를 전파하지 않는다.

## 2차 코드 통합 검증

로컬 Python 3.12.10 / Windows. 세부 버전은 `dependencies-local.txt`, 명령·종료코드는
`VALIDATION_LOCAL.json`, 전체 출력은 `pytest-local.txt`에 보존했다.

| 검사 | 결과 |
|---|---|
| 전체 pytest | 734 passed, 5 skipped, 0 failed; exit 0 |
| Ruff 전체 | PASS; exit 0 |
| 원본 PDF 인벤토리 | 60 PASS, 0 FAIL, 0 BLOCKED; exit 0 |
| C001 archived integrity / replay gate | 로컬 PASS; release BLOCKED |
| 새 연결 CLI | 실제 archived C001 + AI 후보 연결 확인; exit 2는 미확보 외부 Gate BLOCKED 의미 |
| 새 JSON overflow red/green | 수정 전 4 failed → 수정 후 타입 회귀와 합쳐 56 passed |
| 로컬 SDK HTTP mock | 13 passed; 127.0.0.1만 사용, 실제 Studio 호출 없음 |
| GitHub Ubuntu / Python 3.11 CI | **739 passed, 0 skipped**, 전체 Ruff/Archive/인벤토리 성공; [run 41450548344](https://github.com/dohun3540-crypto/yuseok_integration/actions/runs/41450548344) |

처음 기본 임시 경로의 권한 오류와 Windows CRLF·locale·symlink 및 로컬 HTTP 제한을
별도로 기록했다. 작업 내부 임시 경로, UTF-8 실행 모드, 원본 바이트 보존 설정으로
재검증했다. Windows에서 skip한 5개도 GitHub Ubuntu CI에서 모두 통과했다.
구현 커밋 `21bff34a254a7d24295357ac745f418de03366be`의 CI URL과 SHA는
`CI_RESULT.json`에 기록한다. 이후 보고서 보강 커밋의 검사도 PR Checks에서 확인한다.

## 3차 Native 검증과 케이스 Gate

| 케이스 | 이번 로컬 증거 | V6 실제 Native 검증 |
|---|---|---|
| C001 | 기존 2026-10-30 V4 원본 replay: 부족량 0→60, 추가 60, 견적 비용 60,500 KRW; 독립 QA PASS_LOCAL | V6 새 실행 원본 미수신: BLOCKED |
| C013 | 합성 DRAFT의 PO1/PO999 보존, 계산값 null·추천 없음, 독립 QA가 안전 차단 확인 | V6 실제 PO 충돌 차단: BLOCKED |
| C017 | 합성 ISO 날짜 정상 처리; 한국어 문자열을 Python에 직접 넣으면 차단 | 한국어 원문→Extract→Normalize 실측: NOT_VERIFIED |
| C008 | R1 40/R2 60 분리, R2만 변경, 부족 40/견적 비용 40,500 KRW; 모호한 입력 차단 회귀 | 실제 부분입고 Native: NOT_VERIFIED |

`tests/test_qa_combined_v6_contract.py`와 기존 V6·adapter·stage·Cross-Agent·B0/E1
테스트는 전체 suite에 포함된다. 합성 B0/E1 비교는 기능 검증이며 개선률이 아니다.
이번 첨부는 V6 설정, 인계서, 보고서뿐이다. 최신 C001/C013 Native, QA Input/Report,
실행 메타데이터, 최신 검수 XLSX, 승인 Gold는 없었다. 과거 V4 실행은 새 V6 실행으로
표기하지 않는다. 후보와 로컬 예측의 일치는 공식 추출 정확도가 아니다.

## 최종 상태와 후속 입력

| 상태 | 판정 |
|---|---|
| GITHUB_CODE_INTEGRATION | PASS_LOCAL / GitHub CI SUCCESS; CI_RESULT.json 참조 |
| STUDIO_CONFIG_BY_GU_DOHUN | CONFIG_STATIC_ONLY, 68개 null 지시/타입 충돌 지점 발견 |
| STUDIO_NATIVE_E2E | BLOCKED |
| HUMAN_GOLD | BLOCKED / NEEDS_REVIEW |
| OVERALL_RELEASE | BLOCKED |

Studio 변경 요청은 `STUDIO_CONFIG_CHANGE_REQUEST.md`, 실제 원본 수신 명세는
`NATIVE_AND_GOLD_REQUEST.md`에 있다. 승인 Gold가 없으므로 정확도/개선률은
NOT_MEASURED, LIVE_VERIFIED는 부여하지 않는다.

## 공개 저장소 검토

새로 추가한 것은 코드·합성 테스트·빈 검수 템플릿·AI_CANDIDATE 상태의 합성 C001
후보와 기술 보고다. 최신 개인 검수 기록, 업로드된 DOCX/PDF/V6 설정 원본, 토큰을
추가하지 않았다. 기존 공개 브랜치의 PDF/Native/설정은 바꾸지 않았다. 새 후보의
reviewer/reviewed_at은 비어 있고, 사람 검수나 승인으로 승격하지 않았다.
main, 원본 저장소, 기존 PR은 수정·병합·삭제하지 않았다. Studio 접속·수정·실행은 0회다.
