# Studio V6 정적 계약 변경 요청

담당: 구도훈. CONFIG_STATIC_ONLY. 이번 작업에서 Studio를 편집/실행하지 않았다.
원본 SHA-256 `931933760e35799f88c4272bbd0c1d1b9503ca2dea9e552ac70823b5a6a0abe9`.
kind `studio.workflow-config-draft`, export `2026-11-01T17:06:51.261Z`,
workflow `agt_SKBQWBYeuMxZuUNH4zfmd7`, config `cfg_iqQJTyc6PDK9Ym9s2bAEAm`, version 2.
V6는 이름이고 저장된 config version 2와 다르다.

V4 대비 Parse 설정과 연결선 10개는 동일하며 Normalize prompt는 1,788→6,717자다.
아래 JSON 경로는 읽기 전용 원본에서 확인했다. 실제 Studio가 nullable schema를
지원하는지, 실제 export가 운영에 적용됐는지는 별도 확인이 필요하다.

| Node / JSON path | 현행 및 충돌 조건 | 권장 수정/확인 | 예상 검증 |
|---|---|---|---|
| Extract 4개 / `workflowConfig.informationExtractConfiguration.schemas[*].json_schema.schema.properties` | string/integer/number에 null 지시가 혼재. 정적 분석 68개 지점 | Studio 지원 범위에서 명시적 nullable 타입 또는 원본 absence metadata 계약 확정. 불명확한 0/빈 문자열을 Python이 추정하지 않음 | 선택 부재·필수 부재·실제 0을 별도 실행하고 Extract raw와 Normalize 대조 |
| 같은 경로의 `items.items.properties.receipt_id`, `quantity` | 빈 문자열 지시와 상위 null 지시, integer 누락 표현 충돌 | 행별 원문·입고 ID·누락 여부 보존 | C008 R1/R2 및 수량 누락/0/false 음성 검증 |
| 같은 경로의 `quote` | Extract는 배열, Python normalized는 단일 객체/null | 0행→null, 1행→객체. 2행 이상은 기존 V6의 손실 경고·차단 유지, 모든 행 raw 보존. 첫 행 선택 금지 | 0/1/2행 견적; 2행은 계산 차단 |
| Normalize / `workflowConfig.instructConfiguration.nodes[0].prompt` | original_delivery가 원문에 없으면 null; Python은 통보서에도 신뢰 원본 납기 대조 필수 | 누락을 다른 문서에서 채우지 말고 차단 사유를 명시. 계약 완화를 원하면 별도 검토 | original_delivery 누락은 BLOCKED |
| Normalize / 같은 prompt의 부분입고 규칙 | 문서 수준 날짜 하나로 서로 다른 행별 날짜 표현 불가 | 원본 행별 날짜 보존, 단일 날짜로 손실이 생기면 null+warning 유지 | C008의 R2 날짜가 R1로 전파되지 않음 |
| Extract `evidence.items.properties.confidence`, Normalize evidence | number 선언과 미제공 null 지시 충돌. confidence 0의 출처 불명 | 실제 제공값 0은 보존, 제공 여부는 raw/metadata로 확인. 임의 null 치환 금지 | 0/null/누락과 source_page 좌표계 검증 |
| Normalize / warnings 및 evidence 규칙 | 비어 있지 않은 warnings를 Python은 차단. 정상 선택 필드 부재의 과도한 경고도 차단 가능 | Extract부터 역할별 필수/선택 구분. Python에서 경고 삭제 금지. 근거 전달 경로를 개선 | 실제 C001 정상/필수 근거 부재 케이스 각각 확인 |
| Normalize / quote 식별자·공급업체·운송비·단위·통화 | Studio의 선택적 누락 허용과 Python 필수 quote_id/supplier_id/shipping_cost 및 EA/KRW 충돌 | 값 만들지 말고 미확보는 차단으로 표시. 지원 통화/단위 정책을 명시 | shipping_cost null은 차단, 명시적 0은 유효, 비EA/비KRW는 차단 |
| Normalize / PO·날짜 비교 | 발주 100과 견적 capacity 60은 다른 사실. PO999와 PO1은 실제 연결 충돌 | 수량 의미를 구분, ID 원문 유지, 실제 충돌은 warning 보존 | C001 오경고 방지, C013 안전 차단, C017 명시적 유효 한국어 날짜만 ISO 변환 |

각 충돌 경로와 선언 타입은 `STUDIO_STATIC_SUMMARY.json`에 기록했다. 68은 정적
지시/타입 충돌 지점 수이며 실제 오류 발생 횟수나 필드 정확도가 아니다. 스크린샷·설정
지침만으로 해결 판정하지 않고, 구도훈이 제공할 원본 Native 단계별 결과로 재검증한다.
