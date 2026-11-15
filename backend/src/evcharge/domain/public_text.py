"""공공 API(충전소 정보)에서 온 글 정리 (BE-14).

충전 사업자가 등록한 이름·주소는 응답(앱 화면, 내비 라벨)과 Claude 도구 결과로 나간다.
제어 문자(Cc: NUL 등)와 서식 문자(Cf: U+202E 같은 방향 제어, U+200B 폭 없는 공백)는 글을
뒤집어 보이게 하거나 숨은 글자를 넣을 수 있어 뺀다. 한글, 이모지(So), 결합 문자(Mn)는
C 범주가 아니라 그대로 둔다.
"""

from __future__ import annotations

import unicodedata


def clean_public_text(value: object) -> str:
    """공백류(줄바꿈, 탭 포함)는 한 칸 공백으로 펴고, 나머지 C 범주 문자는 뺀다.

    공백을 먼저 공백으로 바꾸는 이유: 줄바꿈도 Cc라 그냥 빼면 "남구\\n대촌로"가
    "남구대촌로"로 붙는다. 길이 자르기는 부르는 쪽이 이 결과에 한다.
    """
    kept = []
    for char in str(value or ""):
        if char.isspace():
            kept.append(" ")
        elif not unicodedata.category(char).startswith("C"):
            kept.append(char)
    return " ".join("".join(kept).split())
