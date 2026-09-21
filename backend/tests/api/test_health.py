def test_health_reports_unverified_tariff_items(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["unverified_tariff_items"], list)
    assert body["unverified_tariff_items"], "미확인 항목이 하나도 없을 리 없다"
    assert all(isinstance(item, str) for item in body["unverified_tariff_items"])
    assert "adders.climate_env_per_kwh" in body["unverified_tariff_items"]
