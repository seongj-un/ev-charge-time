def test_health_reports_unverified_tariff_items(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["unverified_tariff_items"], list)
    assert body["unverified_tariff_items"], "미확인 항목이 하나도 없을 리 없다"
    assert all(isinstance(item, str) for item in body["unverified_tariff_items"])
    # 공공 충전 단가는 기후에너지환경부 출력별 요금(2026-08-01)으로 확인됐다
    assert "weekend_discount_sunset" in body["unverified_tariff_items"]
    assert not [i for i in body["unverified_tariff_items"] if i.startswith("public_fast.")]
