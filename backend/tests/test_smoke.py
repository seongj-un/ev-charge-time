from fastapi.testclient import TestClient

from evcharge.main import create_app


def test_app_starts_and_health_responds():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200


def test_service_key_normalizes_encoding_and_decoding_forms():
    """공공데이터포털이 주는 두 형태의 "일반 인증키"가 같은 값이 되어야 한다.

    포털은 같은 키를 Encoding(%2B…)과 Decoding(+…)으로 나눠 보여준다. httpx가
    쿼리 파라미터를 다시 퍼센트 인코딩하므로 Encoding 키를 그대로 실으면
    %2B → %252B 가 되어 인증이 실패한다. 어느 쪽을 넣어도 되게 해두지 않으면
    "키를 넣었는데 인증이 안 된다"는 상황이 반복된다.
    """
    from evcharge.settings import Settings

    encoding_form = Settings(charger_api_key="abc%2Bdef%2Fghi%3D").charger_api_key
    decoding_form = Settings(charger_api_key="abc+def/ghi=").charger_api_key
    with_noise = Settings(charger_api_key='  "abc+def/ghi="  ').charger_api_key

    assert encoding_form == decoding_form == with_noise == "abc+def/ghi="


def test_missing_service_key_is_empty_not_an_error():
    """키가 없어도 기동은 막지 않는다 — 나머지 기능은 그대로 돌아야 한다."""
    from evcharge.settings import Settings

    assert Settings(charger_api_key="").charger_api_key == ""
