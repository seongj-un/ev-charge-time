# 차량 앱 연동 가이드 (와트잇, Pleos Connect)

차량 앱(Kotlin, Pleos SDK)을 만드는 사람이 한 번에 볼 문서다. 각 API의 필드와 규칙 전체는
[`car-api.md`](car-api.md)에 있다. 이 문서는 "언제 무엇을 부르고, SDK의 어떤 값을 어디에 넣고,
응답으로 무엇을 하는지"만 다룬다.

원칙

- **계산은 서버가, 실행은 차가.** 앱은 충전을 켜거나 끄지 않는다(`setEvChargeSwitch`,
  `setEvChargePercentLimit`을 쓰지 않는다. 둘 다 제어 권한이 필요하다). 서버가 준 예약 시각과
  목표 %를 운전자가 차 설정에 넣도록 안내한다.
- **주행 중에는 화면 대신 말(TTS).** 응답의 `speech`는 그대로 읽으면 되는 문장이다. 숫자는 전부
  서버 계산값이니 앱이 숫자를 다시 만들거나 반올림하지 않는다.
- **게스트로 쓴다.** 로그인 없이 기기 토큰 하나로 개인 기록(절감, 출발 시각)을 묶는다.
- 계약 보호: `/api/car/*`와 `/api/chargers*`의 필드 목록은
  `backend/tests/api/snapshots/car_api_contract.json`에 스냅숏으로 있다. 서버가 필드를 바꾸면
  테스트가 실패하므로, 앱은 이 파일을 기준으로 맞추면 된다.

SDK 이름은 Pleos SDK 소스(Vehicle, NaviHelper, navidata, FusedLocation)에서 확인한 것만 적었다.
Pleos SDK에서 `@hide`이면서 `@Deprecated`인 API(배터리 용량, 기어)는 Deprecated 메시지가 가리키는
Android Automotive 표준 Car API(`CarPropertyManager`)로 읽는다(2절 아래 "표준 Car API로 읽는 값").

## 1. 언제 무엇을 부르나

| 시점 | 부를 API | 토큰 | 앱이 할 일 |
| --- | --- | --- | --- |
| 앱을 처음 실행할 때 한 번 | `POST /api/car/devices` | | `device_token`을 안전하게 저장(4절) |
| 시동 ON(앱 시작) | `POST /api/car/briefing` | 선택 | `speech`를 TTS로 읽는다. `actions`의 예약 값은 정차 중에 보여 준다 |
| 귀가 중, 집 도착 전 | `POST /api/car/voice` `trigger: "arrival_briefing"`, `text` 없음 | 필수 | 서버 문장(첫 질문)을 읽고 `ask`면 바로 마이크를 연다. Claude를 부르지 않는다 |
| 운전자가 말했을 때 | `POST /api/car/voice` `text` + `history` | 필수 | `speech`를 읽고 `actions`를 처리(3절) |
| 주차해 충전기를 꽂았을 때(충전 중) | `POST /api/car/leak-check` | 선택 | `leaking`이면 `speech`를 읽는다. 집은 `place: "home"`, 공공 충전기는 `"public"`과 결제 방식 |
| 장거리 주행, 경로가 있을 때 | `POST /api/car/chargers/along-route` | | 잔량이 모자라면 `speech`를 읽고 `add_waypoint`/`ask`를 처리 |
| 주변 빈 충전기 | `GET /api/chargers?available_only=true` | | 결과가 비고 `X-Status-Note` 헤더가 있으면 그 문장을 읽는다(`decodeURIComponent`) |
| "몇 %까지 채우나" | `POST /api/car/charge-target` | | `soc_target`을 차 설정이나 `car/plan`의 `soc_target`으로. 주행 중에는 `soc_now`를 보내지 않는다 |
| 출발(기어 P 해제) | `POST /api/car/departures` | 필수 | 실제 출발 시각을 보낸다. 오프라인이면 쌓아 두었다가 나중에 보내도 된다(90일 안) |
| 다음 시동 ON, 밤사이 충전된 것을 확인했을 때 | `POST /api/car/savings/{saving_id}/confirm` | 필수 | 같은 밤 충전은 `saving_id` 하나만 확정(아래) |
| 절약 리포트 화면 | `GET /api/car/savings/summary?month=YYYY-MM` | 필수 | `speech`, `month_won`, `year_won`. `note`(서버 계산값이라는 안내)도 함께 보여 준다 |
| 설정 > 출발 기록 지우기 | `DELETE /api/car/departures` | 필수 | 이 기기의 출발 기록 전부 삭제 |

확정할 `saving_id` 고르기

- `car/plan`, `car/leak-check`, `car/briefing`, 음성 `plan_charge`·`leak_check`가 아끼는 돈이 있을 때
  대기 기록을 만들고 `saving_id`를 준다(토큰이 있을 때만).
- 운전자가 실제로 넣은 예약을 낸 응답의 `saving_id` **하나만** 확정한다. 브리핑의 예약을 넣었으면
  브리핑 것, 음성으로 다시 계산한 예약을 넣었으면 그것이다. 둘 다 확정하면 같은 충전이 두 번
  더해진다.
- 확정 시점: 시동이 꺼진 동안 앱은 돌지 않으므로 예약 충전이 시작되는 순간은 볼 수 없다. 주차할 때
  잔량을 저장해 두고, 다음 시동 ON에 잔량이 그보다 올라 있으면(예약대로 충전됐다고 보고) 확정한다.
  예약 시각까지 시동이 켜져 있으면 `getEvChargeSwitchState`(충전 중 여부)로 바로 확인해도 된다.
  만든 지 72시간이 지난 기록은 확정할 수 없다(410).

브리핑과 음성 계획의 숫자가 다른 이유

- 브리핑은 운전 시작 때라 "18:00 이후 꽂는다", "지금 잔량"을 가정한다(`assumptions`에 적힌다).
- 음성 `plan_charge`는 내비 도착 예정 시각(`arrival_at`)과 도착 예상 잔량(`arrival_soc`)으로 다시
  계산한다. 그래서 예약 시각과 금액이 브리핑과 다를 수 있고, 이것이 정상이다. 앱은 마지막으로
  계산한 값(운전자가 들은 값)을 쓴다.

## 2. Pleos SDK 값 → 요청 필드

| SDK 값 | 단위(소스 주석) | 요청 필드 | 주의 |
| --- | --- | --- | --- |
| `EvBattery.getEvBatteryStateOfCharge` / `registerEvBatteryStateOfCharge` | % | `soc_now` | 권한 `pleos.car.permission.CAR_ENERGY` |
| 표준 Car API `INFO_EV_BATTERY_CAPACITY` (아래) | Wh | `battery_capacity_wh` | Pleos `EvBattery.getEvBatteryCapacity`는 `@hide`·`@Deprecated`("use the Google INFO_EV_BATTERY_CAPACITY property")라 쓰지 않는다 |
| `EvBattery.getSinceChargeEvEfficiency` / `registerSinceChargeEvEfficiency` | km/kWh | `efficiency_km_per_kwh` | 0.5~20만 받는다. 충전 직후 등 값이 이상하면 보내지 않는다(선택 필드) |
| `EvBattery.getEvChargeSwitchState` | Boolean | voice `context.charging`, 확정 시점 판단 | 소스 설명은 "current EV battery charging state" |
| `RouteStateInfo.remainDestinationChargingInt` (`getRouteStateInfo` → `onRouteStateInfo`) | Int, 소스에 단위 없음("battery or fuel level") | `arrival_soc` | **% 인지 확인 필요.** 아래 `estimatedSocAtDest`가 %로 명시돼 있어 그쪽을 먼저 쓴다 |
| `TripInfo.estimatedSocAtDest` (`requestTrip` → `onTripInfo`) | % | `arrival_soc` | 경로 주행 뒤 예상 잔량 |
| `DestinationInfo.remainDistance` (`getDestinationInfo` → `onDestinationInfo`) | m | `remain_distance_m` | 소스 주석이 "starting point to the waypoint"로 적혀 있다(경유지 주석과 같은 문장). 목적지까지 남은 거리인지 실제 값으로 확인 필요 |
| `DestinationInfo.remainTime` | 초 | voice `context.arrival_at` = 지금 + remainTime | 지금부터 24시간 안이어야 한다. `remainDistance`와 같은 주석이라 목적지까지인지 확인 필요 |
| `DestinationInfo.latitude`, `longitude` | 도 | `destination.lat`, `destination.lng` | |
| `CurrentLocationInfo.latitude`, `longitude` (`getCurrentLocationInfo` → `onCurrentLocationInfo`) | 도 | `origin`, voice `context.lat`/`lng`, `GET /api/chargers`의 `lat`/`lng` | 경로가 없을 때는 `FusedLocation.getLastKnownLocation` → `LocationData.latitude/longitude`(권한 `FUSED_LOCATION`, dangerous) |
| `TripInfo.summary.routePoints` (`RoutePointInfo.latitude`, `longitude`) | 도 | `route_points`(최대 50개, 순서대로) | 경유지와 목적지만 온다(경로 모양 점이 아님). 목적지 점은 빼고 남은 경유지만 보낸다 |
| 표준 Car API `GEAR_SELECTION` (아래) | `VehicleGear` | `departures`의 `departed_at`(P에서 다른 기어로 바뀐 시각) | Pleos `Gear.getCurrentGearSelectionState`·`registerGearSelection`은 `@hide`·`@Deprecated`("use the Google GEAR_SELECTION property")라 쓰지 않는다 |
| STT 결과 문자열 | | voice `text`(500자 이하) | Pleos SDK 소스에는 STT/TTS API가 없다. 안드로이드 기본 음성 인식·TTS를 쓴다 |

### 표준 Car API로 읽는 값 (`CarPropertyManager`)

`Car.createCar(context)`로 연결한 뒤 `car.getCarManager(Car.PROPERTY_SERVICE) as CarPropertyManager`를
쓴다. 두 속성 모두 전역 속성이라 area ID는 `0`이다. 읽기 메서드는 몇 초 걸릴 수 있어 메인 스레드가
아닌 곳에서 부른다(공식 문서).

| 속성 (`VehiclePropertyIds`) | 타입·단위 | 변경 방식 | 권한 | 쓰는 곳 |
| --- | --- | --- | --- | --- |
| [`INFO_EV_BATTERY_CAPACITY`](https://developer.android.com/reference/android/car/VehiclePropertyIds#INFO_EV_BATTERY_CAPACITY) | Float, Wh(`VehicleUnit.WATT_HOUR`), 새 차 기준 공칭 사용 가능 용량 | STATIC(한 번 읽으면 됨) | [`android.car.permission.CAR_INFO`](https://developer.android.com/reference/android/car/Car#PERMISSION_CAR_INFO) (normal) | `getFloatProperty(INFO_EV_BATTERY_CAPACITY, 0)`를 반올림한 정수 → `battery_capacity_wh` |
| [`GEAR_SELECTION`](https://developer.android.com/reference/android/car/VehiclePropertyIds#GEAR_SELECTION) | Integer, [`VehicleGear`](https://developer.android.com/reference/android/car/VehicleGear) 값(`GEAR_PARK` = 4) | ONCHANGE | [`android.car.permission.CAR_POWERTRAIN`](https://developer.android.com/reference/android/car/Car#PERMISSION_POWERTRAIN) (normal) | [`subscribePropertyEvents`](https://developer.android.com/reference/android/car/hardware/property/CarPropertyManager)로 구독. 직전 값이 `GEAR_PARK`이고 새 값이 다른 기어면 그 시각을 `departed_at`으로 `POST /api/car/departures` |

- 단위·권한·상수 값은 위 링크의 Android 공식 문서에서 확인했다(2026-11-15).
- `INFO_EV_BATTERY_CAPACITY`는 새 차 기준 공칭 용량이다(공식 문서). 노화와 온도를 반영한 실시간
  용량은 `EV_CURRENT_BATTERY_CAPACITY`로 따로 있다. 이 가이드는 `INFO_EV_BATTERY_CAPACITY`를 쓴다.
- 공식 문서는 `registerCallback(callback, propertyId, updateRateHz)`를 deprecated로 두고
  `subscribePropertyEvents(propertyId, updateRateHz, callback)`를 권한다. 어느 Car API 버전부터
  `subscribePropertyEvents`가 있는지는 문서에서 찾지 못했다(**확인 필요**). 차에 없으면
  `registerCallback`을 쓴다. `updateRateHz`는 연속 속성에만 의미가 있어 ONCHANGE인 `GEAR_SELECTION`에는
  영향이 없다.
- 기어 이벤트는 시동이 켜진 동안만 받는다. 시동 직후 첫 값이 이미 D라면(P 해제를 놓침) 그 시각을
  보내지 않는다. 한 번 놓친 출발은 운전자가 말한 시각으로 학습이 이어진다.

내비 값 받는 법: `NaviHelper.addListener(NaviHelperEventListener)`로 리스너를 걸고 `getRouteStateInfo`,
`getDestinationInfo`, `getCurrentLocationInfo`, `requestTrip`을 부르면 같은 이름의 `on...` 콜백으로
온다(권한 `pleos.car.permission.NAVI_ROUTE`).

시각: 요청 시각은 오프셋이 있으면 그대로, 없으면 KST로 읽는다. 응답 시각은 항상 `+09:00`이다.

## 3. actions 처리

| `type` | 오는 곳 | 필드 | 앱이 할 일 |
| --- | --- | --- | --- |
| `set_reservation` | 브리핑, `car/plan`의 `reservation`, 음성 `plan_charge`·집 `leak_check` | `start_hhmm`, `end_hhmm` | 차량 기본 예약 충전 화면으로 안내하고 두 시각을 보여 준다. 앱이 예약을 직접 넣지 않는다. 주행 중이면 말로만 알리고 정차 뒤 화면을 띄운다 |
| `navigate` | 음성 `find_chargers` | `station_id`, `name`, `lat`, `lng` | 운전자가 "응"이라고 하면 `NaviHelper.requestRoute(RouteInfo(latitude, longitude, poiName, poiId, address, poiSubId))` |
| `add_waypoint` | `car/chargers/along-route`, 음성 `find_chargers_along_route` | `station_id`, `name`, `lat`, `lng` | 운전자가 "응"이라고 하면 `NaviHelper.addWaypoint(RequestWaypointInfo(latitude, longitude, poiName, waypointIndex, poiId, address, poiSubId))`. `waypointIndex`는 `WaypointIndex.FIRST` |
| `ask` | 귀가 브리핑 첫 질문, `?`로 끝난 음성 답, 바닥날 수 있는 경유지 추천 | `question` | `speech`를 다 읽은 뒤 바로 마이크를 연다. 다음 요청의 `history`에 이 턴을 `{"role": "wattit", "text": <읽은 speech>}`로 넣는다 |

- `RouteInfo`·`RequestWaypointInfo`의 `poiId`, `address`, `poiSubId`는 소스에서 null을 받지 않는
  `String`이다. 응답에는 주소가 없으므로 `poiId`에 `station_id`, `address`는 `GET /api/chargers`에서
  받은 주소나 빈 문자열, `poiSubId`는 빈 문자열을 넣는다. 실제 내비가 빈 값을 받는지 확인이 필요하다.
- 음성 `history`: 최대 6턴. `wattit` 턴은 서버가 준 `speech`를 글자 그대로 넣는다. 평소 출발 시각
  질문에 "응"이라고 답한 것을 서버가 알아보려면 직전 `wattit` 턴이 그 질문으로 끝나야 한다.
- 음성 응답의 `fallback: true`는 Claude 문장 대신 서버 문장을 읽는다는 뜻이다. 앱은 그대로 읽으면 된다.

## 4. 기기 토큰과 오류

기기 토큰

- `POST /api/car/devices`의 응답에서 한 번만 보인다. 서버는 해시만 저장하므로 다시 받을 수 없다.
- 서버 쪽 만료는 없다. Android Keystore로 감싼 저장소(예: EncryptedSharedPreferences)에 둔다.
  로그나 크래시 리포트에 남기지 않는다.
- 새로 발급하면 다른 기기로 본다. 절감 합계와 출발 기록이 새로 시작되므로, 저장한 토큰이 있는데
  401이 날 때(저장소가 지워짐 등)만 다시 발급한다. IP당 시간 한도가 있다(기본 10회/시간, 429).
- 헤더: `Authorization: Bearer <device_token>`.

오류 코드별 앱 동작

| 코드 | 언제 | 앱 동작 |
| --- | --- | --- |
| 401 | 토큰이 필요한 API에 토큰이 없거나 틀림 | 저장된 토큰을 지우고 한 번 다시 발급한 뒤 재시도. 다시 401이면 그 기능만 끈다 |
| 404 | 확정할 절감 기록이 없음(오래돼 정리됨, 다른 기기) | 그 `saving_id`를 버린다. 재시도하지 않는다 |
| 410 | 만든 지 72시간이 지난 기록을 확정 | 버린다 |
| 422 | 입력 검증 실패(범위 밖 값, NaN, 출발 시각이 이미 지남, 시간 부족 등) | 재시도하지 않는다. SDK 값을 점검한다. `car/plan`의 "시간이 부족해요"처럼 본문 `detail`이 문자열이면 그 문장을 읽어도 된다 |
| 429 | 하루·시간 한도 초과(음성, 확정, 출발 기록, 기기 발급) | `Retry-After`(초)만큼 기다린다. 음성 429는 본문 `speech`를 읽는다 |
| 501 | 서버에 키가 없음. 음성(`ANTHROPIC_API_KEY`), 주변 충전소(`CHARGER_API_KEY`) | 음성은 본문 `speech`("음성 대화는 아직 준비 중이에요.")를 읽고 음성 버튼을 숨긴다. 귀가 브리핑 첫 질문은 501이 나지 않는다 |
| 503 | 충전소 캐시를 아직 수집하지 않음 | "충전소 정보를 준비 중"으로 안내하고 잠시 뒤 다시 부른다 |
| 500 | 서버 설정 오류 | 일반 오류 문장. 주행 중이면 말하지 않는다 |

- OpenAPI(`/docs`)에는 401·429·501이 음성에만 적혀 있다. 다른 API의 오류 코드는 위 표와
  `car-api.md`의 각 절이 기준이다.
- 계산 API(`car/plan`, `car/leak-check`, `car/briefing`, `car/charge-target`)는 토큰이 틀려도 계산은
  그대로 준다(`saving_id`만 null). 이때는 다시 발급하지 않아도 된다.

## 5. 하루 흐름 예

`backend/tests/scenarios/test_car_day.py`가 아래 순서를 시계를 고정해 끝까지 돌고, 단계마다 숫자가
같은 입력의 `car/plan`과 맞는지 확인한다.

1. 화 08:00 기기 발급.
2. 화 17:50 시동 ON 브리핑(잔량 32%): 평소 출발 기록이 없어 "내일 오전 8시 출발 기준"으로 오늘 밤
   예약과 아끼는 금액을 말한다.
3. 화 18:20 귀가 중 첫 질문: "집에 도착하면 배터리가 25% 남아요. 내일 몇 시에 출발하세요?"
4. 운전자 "7시 반에 나가" → 도착 예정 18:40·도착 잔량 25%로 다시 계산한 예약(`set_reservation`)과
   `saving_id`. 07:30은 "운전자가 말한 출발 시각"으로 남는다.
5. 수 07:31 기어 P 해제 → 출발 기록(30분 안의 07:30을 실제 출발로 바꾼다).
6. 수 08:00 예약 충전이 돈 것을 확인 → 4의 `saving_id` 확정 → 이번 달 합계가 그 금액.
7. 지난주 평일 출발 4건이 더 쌓이면, 수 17:50 브리핑은 "평소 출발 07:30" 기준으로 계산하고, 18:20
   귀가 질문은 "내일도 오전 7시 30분에 출발하세요?"가 된다. "응"이라고 하면 07:30으로 계획한다.

## 6. 실제 차에서 확인할 것

- `CarPropertyManager`의 `INFO_EV_BATTERY_CAPACITY`, `GEAR_SELECTION`이 이 차에서 지원되는지
  (`getPropertyList()`에 있는지)와 차의 Car API 레벨.
- `remainDestinationChargingInt`의 단위(%인지), `DestinationInfo.remainDistance`·`remainTime`이
  목적지까지 남은 값인지.
- 밤사이 충전 확인: 주차 때 잔량과 다음 시동 때 잔량 비교로 충분한지.
- `requestRoute`·`addWaypoint`에 `address`·`poiSubId`를 빈 문자열로 넣어도 되는지.
