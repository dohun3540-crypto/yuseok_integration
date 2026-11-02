"""설치 대상 src와 분리된 팀원3 QA 도구의 로컬 시험 경로."""

import sys
from pathlib import Path

# pytest 콘솔 실행도 python -m pytest와 동일한 저장소 루트를 찾게 한다.
# 운영 패키지·CI 설정은 변경하지 않는다.
REPOSITORY_ROOT = str(Path(__file__).resolve().parents[2])
if REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, REPOSITORY_ROOT)
