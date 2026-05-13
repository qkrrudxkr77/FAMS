#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Workthrough SSO 테스트 토큰 생성기 (로컬 개발 전용)

사용법:
  python gen_test_token.py <email> [empNo]
  python gen_test_token.py qkrrudxkr77@bodyfriend.co.kr 12345

생성된 토큰 사용:
  http://localhost:9090/api/token/login?token=<생성된토큰>
"""

import sys
import jwt
from datetime import datetime, timedelta

WORKTHROUGH_SECRET = 'WorkthrouthSSOToken^%@#&A3812_129273023_12978130A'
WORKTHROUGH_ALGORITHM = 'HS256'


def generate_token(email, empNo=None):
    """Workthrough 테스트 토큰 생성"""
    now = datetime.utcnow()
    exp = now + timedelta(days=365)  # 1년 유효

    payload = {
        'email': email,
        'empNo': empNo or '',
        'iat': now,
        'exp': exp
    }

    token = jwt.encode(
        payload,
        WORKTHROUGH_SECRET,
        algorithm=WORKTHROUGH_ALGORITHM
    )

    return token


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("사용법: python gen_test_token.py <email> [empNo]")
        print("예시:   python gen_test_token.py qkrrudxkr77@bodyfriend.co.kr 12345")
        sys.exit(1)

    email = sys.argv[1]
    empNo = sys.argv[2] if len(sys.argv) > 2 else None

    token = generate_token(email, empNo)

    print("\n=== 생성된 테스트 토큰 (1년 유효) ===")
    print("이메일: " + email)
    print("사번: " + (empNo or "(없음)"))
    print("\n아래 URL을 브라우저에서 열어주세요:")
    print("http://localhost:9090/api/token/login?token=" + token)
    print()
