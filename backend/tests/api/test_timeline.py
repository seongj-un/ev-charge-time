def test_spring_fall_saturday_has_a_discount_window(client):
    response = client.get("/api/timeline", params={"day": "2026-10-17"})

    assert response.status_code == 200
    body = response.json()
    assert body["day"] == "2026-10-17"
    assert body["mode"] == "self_low"
    assert body["season"] == "spring_fall"
    assert body["is_holiday"] is False
    assert len(body["hours"]) == 24
    assert [h["hour"] for h in body["hours"] if h["discounted"]] == [11, 12, 13]


def test_sunday_is_light_all_day(client):
    body = client.get("/api/timeline", params={"day": "2026-10-18"}).json()

    assert all(hour["band"] == "light" for hour in body["hours"])


def test_holiday_is_flagged(client):
    body = client.get("/api/timeline", params={"day": "2026-10-09"}).json()

    assert body["is_holiday"] is True


def test_day_is_required(client):
    assert client.get("/api/timeline").status_code == 422


def test_public_fast_needs_a_base_price(client):
    response = client.get(
        "/api/timeline", params={"day": "2026-10-17", "mode": "public_fast"}
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_public_fast_with_a_base_price(client):
    body = client.get(
        "/api/timeline",
        params={"day": "2026-10-17", "mode": "public_fast", "public_base_price": 350.0},
    ).json()

    assert body["hours"][12]["price_per_kwh"] == 301.4


def test_non_finite_base_price_is_422(client):
    response = client.get(
        "/api/timeline",
        params={"day": "2026-10-17", "mode": "public_fast", "public_base_price": "inf"},
    )
    assert response.status_code == 422
