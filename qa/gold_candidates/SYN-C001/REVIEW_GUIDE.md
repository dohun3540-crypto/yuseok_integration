# C001 원문 기반 후보 검수 안내

## 상태
AI_CANDIDATE. human_reviewed=false, team_approved=false. 공식 성능 지표에 사용 금지.
본 후보는 다운로드한 원본 PDF에서 제공된 파싱 본문/표를 AI가 대조했다. PDF 페이지 이미지를 사람이 직접 검수한 기록은 없다. DRAFT를 먼저 열람했으므로 맹검 독립 작성이라고 하지 않는다.

## 원본
Git 기준: 8558bdc2ee0f82d0e7c02c0adff7d1c0155564df.
경로: data/cases/SYN-C001/ 아래의 purchase_order, delivery_notice, quotation PDF.
각 파일의 실제 다운로드 SHA-256은 candidate.v1.json sources에 기록했다. 원본/DRAFT는 덮어쓰지 않았다.

## 검수표 사용
PDF_EVIDENCE_MATRIX.csv는 문서별 필드 후보와 제공된 원문 문자열/위치를 기록한다. filename으로 candidate.v1.json sources의 SHA-256과 연결한다. 모든 페이지는 원본 PDF의 로컬 1쪽이다.
40개 필드 행 중 문서 분류 3개는 제목 기반 판단이며 null 8개는 적용 제외/미기재 후보다. 이 40행을 독립된 원문 사실 40개 또는 공식 정확도 분모로 자동 계산하면 안 된다. 견적 supplier/product/capacity는 여러 출력 경로에 같은 원문이 사용된다.
AI_COMPARE_MATCH는 저장소에서 읽은 DRAFT와 AI가 값을 대조했다는 뜻이다. 사람 승인이나 기계 diff 통과가 아니다.

사람은 원본 PDF를 직접 열고 각 행의 원문과 후보를 확인한 후 reviewer, reviewed_at, decision, approval_state를 기록한다. decision은 ACCEPT/CORRECT/AMBIGUOUS/MISSING/NOT_IN_SOURCE 중 하나. 승인 전 PENDING을 유지한다. 수정 시 이전 후보를 보존하고 새 버전과 이유를 남긴다. 검수자와 시간을 AI가 지어내지 않는다. 위험 필드는 팀원1 또는 별도 검수자의 추가 확인을 기록한다.

## 중요한 해석
- 발주·변경 대상 A/R1/100 EA는 수량이 추가된 것이 아니다.
- 통보서 원문: Only the delivery date changes; the quantity remains unchanged. / 수량 변경 없이 납기만 변경합니다.
- 견적 60 EA는 대체 공급 가능 수량으로 발주 100 EA와 차이 자체가 충돌은 아니다.
- 견적 운송비 원문은 500 KRW (once per quote). 견적당 한 번 조건을 유지한다.
- 견적 원문: Replacement offer only. No purchase has been placed. / 대체 구매 검토용 견적이며 발주가 아닙니다.
- 재고·고객 주문은 별도 trusted JSON 입력이다. PDF 필드 후보에 기대 재고·부족량·총비용을 섞지 않는다.
- 빈 Evidence는 실제 예측에서 평가할 사항이다. 이 후보의 근거를 Studio가 생성한 Evidence라고 표시하지 않는다.

## 보류된 일
사람의 원문 시각 검수/승인, 후보 JSON/CSV 자동 검증, 후보 해시 계산 및 동결, trusted_base_case 독립 계산 대조, 실제 Studio 예측과 공식 평가 모두 NOT_RUN.
기대 정상 업무 status와 block reason은 아직 확정하지 않았다. 필드 후보가 DRAFT와 같다는 사실만으로 정상 승인하지 않는다.

## 다음 작업
1. JSON/CSV 구조·필드 수·원본 SHA 연결 자동 검사 추가.
2. 실제 사람이 C001 PDF 3개와 40개 필드 행 검수.
3. 승인된 범위만 새 Gold 버전으로 동결하고 해시 기록.
4. 동일 원본의 실제 예측과 별도 비교. C013/C017/C008 원문 후보 작업은 병렬 진행 가능.
