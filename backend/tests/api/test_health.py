def test_health_reports_unverified_tariff_items(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["unverified_tariff_items"], list)
    assert body["unverified_tariff_items"], "미확인 항목이 하나도 없을 리 없다"
    assert all(isinstance(item, str) for item in body["unverified_tariff_items"])
    # 공공 급속 단가는 충전사업자가 정하므로 한전 요금표로는 확인되지 않는다
    assert "public_fast.base_price_per_kwh" in body["unverified_tariff_items"]
