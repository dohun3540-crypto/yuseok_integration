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


---

## Final 2026-11-02 selective QA hardening — all-team integration candidate

**Write repository:** `dohun3540-crypto/yuseok_integration` only. **Parent/source of this final candidate:** PR #1 HEAD `427138a52d99585d9b6847b78fc6e14c6bb5e288` (baseline 739 pytest PASS, 0 failed, 0 skipped, Ruff PASS, PDF inventory 60/60 PASS; workflow run [41451016385](https://github.com/dohun3540-crypto/yuseok_integration/actions/runs/41451016385)). This historical CI MUST NOT be called the new commit's CI.

**Source read-only comparisons:**
- Copy [PR #17](https://github.com/dohun3540-crypto/leadtime-guardian-agent.copy/pull/17) @ `fcc2afb2be315e261fa35b9ab17ee1a1134f578c`: already-integrated member 3 tool paths retained, no bulk merge; original QA data/Gold labels remain unapproved. Its team 3 docs/migration and duplicate workflows are not copied: `yuseok_integration` already has a single integrated CI and handoff structure.
- Copy [PR #18](https://github.com/dohun3540-crypto/leadtime-guardian-agent.copy/pull/18) @ `34f023f594e6bfeea60cb7ee88fce9b7f3140121`: precisely import `src/leadtime_guardian/qa/experiment_compare.py` and `tests/test_qa_experiment_identity_hardening.py` (the only PR #18 source/test change; other PR #18 files are historical reports). Original PR #18 module SHA `0c0bbf2c38456019d891625e7486e379e1f96ecf`; synthetic tests SHA `220f0a43f3e6638b90cf6721b1abb7f1e4d31ccb`.
- Upstream original PR #12 @ `e9b9992b593a42d427ff1bbadeb9a9866ca593bd` and PR #13 @ `a925103077173b37d1cefcd6a9576ae644dc2040` remain read-only. All six original Safety V6 operational Git Blob SHAs match the baseline integration. Existing `src/leadtime_guardian/qa/audit.py`, `input_delivery.py`, `qa/inventory.py` have stronger local type/finite-number protections than the unmodified copy PR #17 version; preserve their implementation.

### Selected behavior added from PR #18

1. Fail on duplicate source `file_id` within a B0 or E1 run, rather than merely checking distinct filenames.
2. Fail on reused operational Extract/MergeDocuments/NormalizeDocuments `step_run_id`; on optional Stage metadata present but contradicting its operational `job_id`, `config_id` or `config_version`. Do **not** require absent optional metadata.
3. Permit IndependentQA evidence to use its own legitimately separate Studio QA Job (no false operational-stage binding errors).
4. Compare C013 or any **same established case ID** locally, while still blocking mismatched B0/E1 cases, unauthenticated comparisons and any claim of measured improvement.
5. Preserve nine synthetic-only PR #18 tests; these do not establish authenticated Studio evidence or human Gold accuracy.

No Safety V6 core/Agent API/Adapter modules, original PDF/data cases, native Studio configs, Gold candidates, test names, regression thresholds or already verified QA guards were altered by this selective import. No Studio operations, provider calls, secret handling or new human approval.

### Data/SHA and case review — scope and limits

- Existing Git tree: 68 `data/cases/` files remained Git Blob identical to copy PR #17. This includes the original C001 PDFs and C002-C020 archive/manifests; no extraction/regeneration.
- Previous exact baseline CI 60/60 PDFs machine SHA/page/structure PASS, 0 duplicate hashes, 0 FAIL, 0 BLOCKED. All 20 synthetic cases are included in the archive/manifest inventory; mechanical inspection ≠ PDF visual verification or gold accuracy.
- C001 archived Studio V4 replay only: local 0→60 shortage, extra 60 EA, KRW 60,500; **not** new authenticated V6 run.
- C013 PO1/PO999 must remain distinct and apply fail-closed; C017 Korean/ISO date source normalization remains dependent on actual Extract/Normalize native output; C008 R1 40 / R2 60 partial receipts and R2-only change tested synthetically.
- C001 `qa/gold_candidates/SYN-C001/candidate.v1.json`: `AI_CANDIDATE`, `human_reviewed=false`, `team_approved=false`, `eligible_for_official_metrics=false`, `gold_frozen=false`. No latest human-approved XLSX source bytes are present on this branch.
- Schema: preserve Strict JSON float exponent overflow, finite number checks, negative quantities/amounts, case/document uniqueness and signed-zero/recursive-type protections. Team 2 live provenance and PDF File/Job/Step receipts remain unavailable; neither local hash equality nor stored V4 archive authenticates new Studio jobs.
- Studio configuration STATIC ONLY: 68 suspected nullable/type-instruction conflicts across the four extraction schemas, classified in `STUDIO_CONFIG_CHANGE_REQUEST.md`; this is a static path count, NOT 68 reproduced live errors. Studio operator must confirm against actual saved configuration and stage outputs.

### Regression/CI protocol for new final commit

The source integration baseline must remain **739 passed / 0 skipped** on Linux CI. PR #18 introduces nine synthetic-only tests, so the expected full collection is **748** if no overlapping test paths were removed. Confirm *actual* count in the new exact-HEAD CI; do not assert success from this document alone.

- `python -m pip install -r requirements-validation.txt`
- `python -m ruff check .`
- `python -m pytest -q`
- `python scripts/qa_archive_check.py --root .`
- `python scripts/qa_gate_check.py --root .`
- `python -m qa.inventory --root . --out <NEW_OUTPUT_PATH>` (new path required, never overwrite originals)
- `python -m qa.integration --case-id C001 --job-id <ACTUAL_JOB_ID> --github-sha <EXACT_CODE_SHA> ...` for a read-only integration check with source evidence. CLI exit 2 / status BLOCKED is expected if no live/Gold evidence is provided, not integration success.

The existing `.github/workflows/ci.yml` performs full Python pytest + Ruff + immutable C001 replay + conservative Local Gate + 60-PDF inventory on PR commits. The current document deliberately does not claim to contain its own latest Git commit SHA; verify the final PR HEAD at [GitHub Actions](https://github.com/dohun3540-crypto/yuseok_integration/actions), and record that proof in the PR description. Do not loop commit-on-self-SHA.

### Release and owner handoff

| Gate | Current source-backed conclusion |
| --- | --- |
| SOURCE_INTEGRATION_COMPLETE | PASS (three members' selected source in one repo) |
| CODE_GATE | PASS at 739 baseline; final new SHA requires its own CI |
| CONTRACT_GATE | LOCAL_ONLY; stage and typed envelope checks present, authenticated real pipeline NOT VERIFIED |
| DATA_INTEGRITY_GATE | 60/60 machine PASS at baseline; final new SHA requires rerun; human PDF truth NOT VERIFIED |
| PROVENANCE_GATE | NOT_VERIFIED for new live Studio B0/E1 ↔ Python ↔ QA |
| GOLD_GATE | PENDING; human-reviewed XLSX and team-approved Gold absent |
| STUDIO_E2E_GATE | NOT_VERIFIED; old C001 split jobs cannot substitute a single integrated case |
| B0_E1_COMPARISON_GATE | NOT_MEASURED without B0-C001/E1-C001 and B0-C013/E1-C013 raw paired inputs |
| OVERALL_RELEASE_GATE | BLOCKED until source-authenticated live evidence and approved labels |

**Next responsibility:** 구도훈—retrieve original B0/E1 Stage/Native/QA receipts, verify operational↔QA provenance and run comparison; 윤현준—run real Safety V6 on *identical* Native bytes, provide Python result plus provenance sidecar; 김민주—supply latest XLSX bytes, independently PDF-ground each reviewed field, confirm separate human approval and only then quantify evaluation. If Studio cannot produce one 3-PDF case job, record the actual platform limit and approved alternative; never concatenate three jobs to imply success.

**Final Code Freeze** is conditional on the *new* exact-HEAD complete CI, final PR state and reverified source Sha. **Overall Release remains BLOCKED** even when code freeze is PASS.

## 2026-11-02 Code Freeze decision (separate from product Release)

The **actual checked-out code-and-docs SHA** `93138e0d29c267a91164797442057d3ccc6b9ba5` was verified by [Integrated Python QA run #41462111826](https://github.com/dohun3540-crypto/yuseok_integration/actions/runs/41462111826): completed / SUCCESS, **748 pytest passed, 0 failed, 0 skipped**, Ruff PASS, C001 archived integrity/local gate PASS_LOCAL, and PDF inventory **60/60 machine PASS**. These 748 include the baseline 739 and PR #18's 9 synthetic identity-hardening tests, not independent sums of QA subsets.

**CODE_FREEZE_CONFIRMED = PASS (code only)**, subject to checking the exact later documentation-only PR HEAD against its own GitHub CI. **STUDIO_E2E / live provenance / human Gold / B0-vs-E1 metrics remain unverified; OVERALL_RELEASE = BLOCKED.** The source Git tree never altered Team 2's six operating blobs, original `data/cases/` blobs, original QA safety enforcement, or Studio. Do not claim real improvement or publish approved Gold.

Final CI and final branch HEAD are documented in the Draft PR description, not recursively embedded into these files. No further SHA-only documentation commit is required.


## 2026-11-02 — P0/P1 defect reproduction and minimal repair (supersedes prior 6/6 SHA status)

**Actual failing GitHub Action:** [CI #41464204131](https://github.com/dohun3540-crypto/yuseok_integration/actions/runs/41464204131), from test-only commit `d6a43083b61bb89b798b80951e3bc5a25b23842a`, **757 passed / 8 failed**. Baseline before new boundary tests was **748 passed**. Breakdown: 4 unhashable `audit_provenance` inputs, 1 unhashable Studio Batch provenance, 3 nonzero JSON underflow values wrongly accepted by the common parser. Five new C001 consistency tests already passed in red CI. This failure was intentional reproduction, NOT current code-freeze proof.

- P0: `src/leadtime_guardian/qa/audit.py` now checks `isinstance(kind, str)` before frozenset membership. Malformed arrays/objects/false/null are rejected via established `UNKNOWN_PROVENANCE` instead of TypeError.
- P0: `src/leadtime_guardian/qa/studio_batch.py` now type-checks `provenance_level`, retaining `UNVERIFIED_BATCH_OBSERVATION_SOURCE`, `qa_status=FAIL`, `release_or_merge_authorized=false`.
- P1: `src/leadtime_guardian/strict_json.py` adds a parse-float boundary that rejects overflow and **nonzero numeric underflow to zero** (including large negative exponents) while preserving real zero/negative signed zero, finite values, duplicate-key and UTF-8 checks. This is a **necessary verified exception** to original Team 2 V6 identity: core Git Blob match is now **5/6**, not 6/6. The other five core modules remain byte-identical to original Team 2 PR #12.
- P1: `qa/inventory.py` (independent Team 3 JSON loader) receives the same nonzero-underflow safety guard, and 5 new parametrized numeric inventory tests. No PDF/source asset is rewritten.
- C001: 5 read-only candidate/manifest/DRAFT/evidence-matrix tests from copy PR #19 verify 3 original source hashes, 40 evidence matrix rows and **AI_CANDIDATE not human-reviewed**, PO/notice 100 EA vs quote capacity 60 EA, 1000.00/500 KRW string monetary values. These verify **internal record consistency only**, not PDF semantic/human Gold truth.

New exact-head Python/Ruff/Archive/Local Gate/60-PDF inventory CI **must** be inspected after this patch; no results invented here. Release remains `BLOCKED`: no authenticated new B0/E1 Studio Native/QA/Python execution or human-approved Gold, no measured accuracy/improvement. Preserve all existing 748 tests and source data. Record final CI SHA and links in Draft PR #2 body, not recursively in source files.


### Exact fixed-source CI and final invalid-type coverage

[Fix verification run #41464582467](https://github.com/dohun3540-crypto/yuseok_integration/actions/runs/41464582467) on SHA `d43e497861adbd2c2c930e818e936cac551dded6` completed **SUCCESS**: **770 passed, 0 failed, 0 skipped**, Ruff PASS, C001 archived/local gate PASS_LOCAL, and 60/60 PDF machine inventory PASS. This validates all 8 previously reproduced failures plus existing 748 and five new inventory-underflow cases. These totals overlap; 770 is the full test collection, not an additive QA count.

A final small test-only extension covers explicit `None`, numeric `0`, boolean `False`, nested invalid Studio provenance objects, negative signed zero and nested nonzero underflow. Source behavior is unchanged by that extension. **Check its exact final HEAD CI in Draft PR #2** before treating current Code Freeze as authoritative; no repeated SHA-only documentation commits are needed. Team 2 core Blob SHA now **5/6 identical** vs original PR #12; `strict_json.py` differs intentionally due to the verified accuracy/security fix. No source PDFs, candidate Gold approval state, Studio workflows or other operational engines were changed.
