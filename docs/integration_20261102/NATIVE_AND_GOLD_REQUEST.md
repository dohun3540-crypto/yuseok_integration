# 실제 Native와 Gold 인수 명세

현재 최신 V6 Native와 승인 Gold는 BLOCKED다. 사용자가 Studio에서 확보하는 자료를
읽기 전용으로 검사한다. 아래는 요청 명세이며 실행·업로드 지시나 자동 승인 절차가 아니다.

케이스별 C001/C013 우선, 이후 C017/C008에 다음 파일을 제공한다.

- 수정하지 않은 final Native JSON과 Extract 각 분기, Merge, Normalize raw 출력.
- Independent QA 실제 Input 및 원본 Report/Native. 모델이 입력을 받았다고 주장한 문장은 원본 Input을 대체하지 않는다.
- Agent/Config ID와 버전, Job/Step ID, 실행 시각·완료 상태, 과거/신규 실행 구분.
- 원본 PDF별 파일명, 문서 ID, File ID, SHA-256, 업로드 순서 및 원본 Upload Receipt.
- 입력 PDF 원본 또는 같은 바이트를 검증할 비공개 로컬 경로. source_page의 로컬/병합 페이지 대응표.
- 사용한 trusted_base_case 원본과 코드 SHA. C013의 PO999를 PO1로 바꾸거나 Receipt 날짜를 보정하지 않는다.

실제 Stage/Provenance 검증은 기존 `scripts/qa_combined_e2e_check.py`의
`--stage-intake-manifest`, `--team2-provenance`, `--qa-pdf-receipt`,
`--operational-pdf-receipt`, `--pdf-root` 옵션을 사용한다.
`--execution-kind NEW_LIVE_STUDIO`는 필요한 단계별 원본이 없으면 Python 전에 차단된다.
새 루트 QA 통합 진입점은 보수적인 로컬 replay이며 LIVE_VERIFIED를 부여하지 않는다.

김민주에게 필요한 자료는 최신 사람이 수정한 `PDF_EVIDENCE_MATRIX.xlsx` 원본,
선택 시트명, 수정 전 후보/CSV 기준 버전·해시, 필드별 reviewer·시각·decision·approval_state,
실제 PDF 대조 기록, 최종 팀 승인/Gold 버전·해시다. 수식·병합 셀·모호한 승인 기록은
보정하지 않고 검토 대상으로 남긴다. CSV 구조 PASS도 신원 인증이나 팀 승인이 아니다.

## 로컬 재현

저장소 루트에서 실행한다. `requirements-validation.txt`는 운영과 데이터 검수 의존성을
함께 설치한다. Windows에서는 UTF-8 모드(`PYTHONUTF8=1`)와 쓰기 가능한 임시 경로를 사용한다.

```sh
python -m pip install -r requirements-validation.txt
python -m ruff check .
python -m pytest -q
python scripts/qa_archive_check.py --root .
python scripts/qa_gate_check.py --root .
python -m qa.inventory --root . --out /new/private/inventory-directory
python -m qa.xlsx_snapshot --input /private/review.xlsx --sheet Sheet1 --out /new/private/snapshot.json
python -m qa.review_records --review /private/review.csv --baseline qa/gold_candidates/SYN-C001/PDF_EVIDENCE_MATRIX.csv --out /new/private/review-check.json
```

Native·계산·독립 QA와 데이터 도구를 연결하는 오프라인 진입점:

```sh
python -m qa.integration --native /private/native.json --trusted-base /private/base.json --case-id C001 --job-id job_ACTUAL --github-sha ACTUAL_CODE_SHA --candidate qa/gold_candidates/SYN-C001/candidate.v1.json
```

QA 원본 쌍이 있으면 `--qa-native`, `--qa-report`, `--qa-agent-id`, `--qa-config-id`,
`--qa-config-version`을 추가한다. CSV 검수는 `--review`와 `--baseline`을 함께,
XLSX는 `--xlsx`와 필요 시 `--sheet`를 추가한다. 파일 누락은 오류, Native 미제공은
BLOCKED로 기록한다. exit 1은 잘못된 입력/검증 실패, exit 2는 미승인/미검증 Gate다.

`qa.integration`의 candidate diff는 필드 누락과 null, 정수/실수/불리언, 문서/원본 해시를
구분한다. 후보는 AI_CANDIDATE 상태이며 정확도 분모·개선률·Gold 승인 산출물이 아니다.
새 통합 도구도 승인 Gold가 도착하기 전까지 `official_metrics_eligible=false`를 유지한다.
