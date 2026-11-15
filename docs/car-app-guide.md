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
- 계약 보호: `/api/car/*`와 `/api/chargers*`의 필드 목록(타입, 필수 여부, Literal 값, 범위·길이·개수
  제약, 기본값)은 `backend/tests/api/snapshots/car_api_contract.json`에 스냅숏으로 있다. 서버가 이것을
  바꾸면 테스트가 실패하므로, 앱은 이 파일을 기준으로 맞추면 된다. 스냅숏이 지키지 못하는 것은 4절 끝.

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
| 집 출발(그날 첫 P 해제) | `POST /api/car/departures` | 필수 | **하루(KST 날짜)의 첫 P 해제만** 보낸다(아래 "출발 기록 규칙"). 오프라인이면 쌓아 두었다가 나중에 보내도 된다(90일 안). 단 서버는 **기록한 날(서버 시각, KST) 기준 하루 10건**까지 받고 11번째부터 429(`Retry-After`)라, 밀린 기록은 하루 10건씩 나눠 보낸다 |
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
  확정은 이 잔량 비교로만 한다. `getEvChargeSwitchState`로 확정하지 않는다(2절: 충전 스위치 설정값일
  수 있어 예약 충전을 기다리는 동안에도 true일 수 있다).
  만든 지 72시간이 지난 기록은 확정할 수 없다(410).

출발 기록 규칙

- 서버가 받는 출발은 **집에서 나선 시각** 하나다. 서버는 같은 날 종류(평일, 주말·공휴일)의 28일
  기록 전부로 중앙값을 내므로, 회사·마트에서 다시 출발한 시각까지 보내면 평소 출발이 그쪽으로
  끌려간다. 평일 10일 동안 07:30·12:10·18:30을 모두 보내면 평소 출발이 12:10(신뢰도 low)이 되고,
  귀가 질문이 "내일 낮 12시 10분쯤 출발하세요?"가 된다(`test_reporting_every_park_release_loses_the_usual_time`).
- 앱은 마지막으로 보낸 날짜를 저장해 두고, **그날 이미 보냈으면 보내지 않는다.** 보내기에 실패하면
  (오프라인, 5xx) 그날 첫 출발로 쌓아 두었다가 4절 "재시도 규칙"대로 다시 보낸다.
- 집 위치를 알면(예: 밤에 주차하는 곳) 그 근처(GPS 오차를 감안한 반경, 예 300 m)에서 P를 해제했을
  때만 보낸다. 집 밖에서 자고 출발한 날은 보내지 않는 편이 학습에 낫다. 모르면 "그날 첫 P 해제"만으로
  충분하다.

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
| 표준 Car API `EV_CHARGE_STATE` (아래) | `EvChargeState` | voice `context.charging` = `STATE_CHARGING`(1)일 때만 true | Pleos `EvBattery.getEvChargeSwitchState`는 소스 주석이 "current EV battery charging state"지만 구현이 `setEvChargeSwitch`와 같은 `EV_CHARGE_SWITCH` 속성을 읽는다. Android의 같은 이름 속성은 "The setting that the user wants"(설정값)라, 실제 충전 상태인지 **실차 확인 필요**. 확인 전에는 `charging`에 쓰지 않는다. 모르면 `charging`을 보내지 않는다(선택 필드). 확정 판단에는 쓰지 않는다 |
| `RouteStateInfo.remainDestinationChargingInt` (`getRouteStateInfo` → `onRouteStateInfo`) | Int, 소스에 단위 없음("battery or fuel level") | `arrival_soc` | **% 인지 확인 필요.** 아래 `estimatedSocAtDest`가 %로 명시돼 있어 그쪽을 먼저 쓴다 |
| `TripInfo.estimatedSocAtDest` (`requestTrip` → `onTripInfo`) | % | `arrival_soc` | 경로 주행 뒤 예상 잔량 |
| `DestinationInfo.remainDistance` (`getDestinationInfo` → `onDestinationInfo`) | m | `remain_distance_m` | 소스 주석이 "starting point to the waypoint"로 적혀 있다(경유지 주석과 같은 문장). 목적지까지 남은 거리인지 실제 값으로 확인 필요 |
| `DestinationInfo.remainTime` | 초 | voice `context.arrival_at` = 지금 + remainTime | 지금부터 24시간 안이어야 한다. `remainDistance`와 같은 주석이라 목적지까지인지 확인 필요 |
| `DestinationInfo.latitude`, `longitude` | 도 | `destination.lat`, `destination.lng` | |
| `CurrentLocationInfo.latitude`, `longitude` (`getCurrentLocationInfo` → `onCurrentLocationInfo`) | 도 | `origin`, voice `context.lat`/`lng`, `GET /api/chargers`의 `lat`/`lng` | 경로가 없을 때는 `FusedLocation.getLastKnownLocation` → `LocationData.latitude/longitude`(권한 `FUSED_LOCATION`, dangerous) |
| `TripInfo.summary.routePoints` (`RoutePointInfo.latitude`, `longitude`) | 도 | `route_points`(최대 50개, 순서대로) | 경유지와 목적지만 온다(경로 모양 점이 아님). `RoutePointInfo.pointType == RoutePointType.WAYPOINT`인 점만 보낸다(`RoutePointType`에는 `ORIGIN`, `DESTINATION`도 있다) |
| 표준 Car API `GEAR_SELECTION` (아래) | `VehicleGear` | `departures`의 `departed_at`(P에서 다른 기어로 바뀐 시각) | Pleos `Gear.getCurrentGearSelectionState`·`registerGearSelection`은 `@hide`·`@Deprecated`("use the Google GEAR_SELECTION property")라 쓰지 않는다 |
| STT 결과 문자열 | | voice `text`(500자 이하) | Pleos SDK 소스에는 STT/TTS API가 없다. 안드로이드 기본 음성 인식·TTS를 쓴다 |

### 표준 Car API로 읽는 값 (`CarPropertyManager`)

`Car.createCar(context)`로 연결한 뒤 `car.getCarManager(Car.PROPERTY_SERVICE) as CarPropertyManager`를
쓴다. 아래 속성은 모두 전역 속성이라 area ID는 `0`이다(공식 문서: "global area ID (0)"). 읽기 메서드는 몇 초 걸릴 수 있어 메인 스레드가
아닌 곳에서 부른다(공식 문서).

| 속성 (`VehiclePropertyIds`) | 타입·단위 | 변경 방식 | 권한 | 쓰는 곳 |
| --- | --- | --- | --- | --- |
| [`INFO_EV_BATTERY_CAPACITY`](https://developer.android.com/reference/android/car/VehiclePropertyIds#INFO_EV_BATTERY_CAPACITY) | Float, Wh(`VehicleUnit.WATT_HOUR`), 새 차 기준 공칭 사용 가능 용량 | STATIC(한 번 읽으면 됨) | [`android.car.permission.CAR_INFO`](https://developer.android.com/reference/android/car/Car#PERMISSION_CAR_INFO) (normal) | `getFloatProperty(INFO_EV_BATTERY_CAPACITY, 0)`를 반올림한 정수 → `battery_capacity_wh`. **0이면 보내지 않는다**: pre-U 클라이언트는 지원하지 않는 속성에 0을 돌려준다(공식 문서). 서버는 1,000 Wh 미만을 422로 막는다 |
| [`EV_CHARGE_STATE`](https://developer.android.com/reference/android/car/VehiclePropertyIds#EV_CHARGE_STATE) | Integer, [`EvChargeState`](https://developer.android.com/reference/android/car/hardware/property/EvChargeState) 값(`STATE_CHARGING` = 1, `STATE_FULLY_CHARGED` = 2, `STATE_NOT_CHARGING` = 3 등) | ONCHANGE | [`android.car.permission.CAR_ENERGY`](https://developer.android.com/reference/android/car/Car#PERMISSION_ENERGY) (**dangerous**, 런타임 요청 필요) | 음성 요청 때 `getIntProperty(EV_CHARGE_STATE, 0)`. `STATE_CHARGING`이면 `context.charging = true`, `STATE_NOT_CHARGING`·`STATE_FULLY_CHARGED`면 false, 그 밖(`STATE_UNKNOWN`, `STATE_ERROR`)이면 보내지 않는다 |
| [`GEAR_SELECTION`](https://developer.android.com/reference/android/car/VehiclePropertyIds#GEAR_SELECTION) | Integer, [`VehicleGear`](https://developer.android.com/reference/android/car/VehicleGear) 값(`GEAR_PARK` = 4) | ONCHANGE | [`android.car.permission.CAR_POWERTRAIN`](https://developer.android.com/reference/android/car/Car#PERMISSION_POWERTRAIN) (normal) | [`subscribePropertyEvents`](https://developer.android.com/reference/android/car/hardware/property/CarPropertyManager)로 구독. 직전 값이 `GEAR_PARK`이고 새 값이 다른 기어이며 **그날 아직 보내지 않았을 때만** 그 시각을 `departed_at`으로 `POST /api/car/departures`(1절 "출발 기록 규칙") |

- 단위·권한·상수 값은 위 링크의 Android 공식 문서에서 확인했다(2026-11-15).
- `EV_CHARGE_STATE`는 목표 충전량이 100이 아니면 목표에 닿았을 때 `STATE_FULLY_CHARGED`를 돌려준다(공식
  문서). 서버에 보낼 때는 "충전 중 아님"으로 본다.
- `INFO_EV_BATTERY_CAPACITY`는 새 차 기준 공칭 용량이다(공식 문서). 노화와 온도를 반영한 실시간
  용량은 `EV_CURRENT_BATTERY_CAPACITY`로 따로 있다. 이 가이드는 `INFO_EV_BATTERY_CAPACITY`를 쓴다.
- 공식 문서는 `registerCallback(callback, propertyId, updateRateHz)`를 deprecated로 두고
  `subscribePropertyEvents(propertyId, updateRateHz, callback)`를 권한다. 공식 문서에는 어느 버전부터
  있는지 적혀 있지 않다. AOSP 소스(`packages/services/Car`의 `CarPropertyManager.java`)를 브랜치별로 보면
  `android14-release`에는 없고 `android14-qpr3-release`, `android15-release`에 있으며
  `@FlaggedApi(Flags.FLAG_VARIABLE_UPDATE_RATE)`가 붙어 있다. 차의 Car API 버전과 이 플래그가 켜져
  있는지는 **확인 필요**. 없으면 `registerCallback`을 쓴다. `updateRateHz`는 연속 속성에만 의미가 있어 ONCHANGE인 `GEAR_SELECTION`에는
  영향이 없다.
- 기어 이벤트는 시동이 켜진 동안만 받는다. 시동 직후 첫 값이 이미 D라면(P 해제를 놓침) 그 시각을
  보내지 않는다. 한 번 놓친 출발은 운전자가 말한 시각으로 학습이 이어진다.

내비 값 받는 법

- `NaviHelper`는 인스턴스다. `val navi = NaviHelper(context)`로 만들고 `navi.initialize()`를 부른 뒤
  `navi.addListener(listener: NaviHelperEventListener)`로 리스너를 건다.
- `getRouteStateInfo()` → `onRouteStateInfo`, `getDestinationInfo()` → `onDestinationInfo`,
  `getCurrentLocationInfo()` → `onCurrentLocationInfo`, `requestTrip(TripRequest)` → `onTripInfo`로 온다.
- 읽기 권한은 `pleos.car.permission.NAVI_ROUTE`(normal)다. 경로 안내·경유지 추가(`requestRoute`,
  `addWaypoint`)는 **`pleos.car.permission.NAVI_ROUTE_SEARCH`**가 따로 필요하다(3절).

시각: 요청 시각은 오프셋이 있으면 그대로, 없으면 KST로 읽는다. 응답 시각은 항상 `+09:00`이다.

### 권한 정리

normal 권한은 설치 때 부여된다. dangerous 권한은 앱 시작 때 한꺼번에 묻지 않고, **그 권한이 필요한
기능을 운전자가 처음 쓸 때** 요청한다. 거부되면 그 기능만 끄고 나머지는 그대로 쓴다.

| 권한 | 보호 수준 | 쓰는 기능 | 필수 여부 | 거부·없을 때 |
| --- | --- | --- | --- | --- |
| `android.permission.INTERNET` | normal | 모든 서버 호출 | 필수 | |
| `pleos.car.permission.CAR_ENERGY` | normal(Pleos 소스) | 잔량(`soc_now`), 전비 | 필수 | |
| `android.car.permission.CAR_INFO` | normal | 배터리 용량(`INFO_EV_BATTERY_CAPACITY`) | 필수 | |
| `android.car.permission.CAR_POWERTRAIN` | normal | 기어(`GEAR_SELECTION`) → 출발 기록 | 선택 | 출발 기록을 보내지 않는다. 출발 시각 학습은 운전자가 말한 시각으로만 돈다 |
| `pleos.car.permission.NAVI_ROUTE` | normal(Pleos 소스) | 도착 예정 시각·잔량, 남은 거리, 경로 지점, 현재 위치 | 선택 | 경로 위 충전소(`origin`·`destination`이 필요)를 끈다. 귀가 브리핑과 음성은 `arrival_at`·`arrival_soc` 없이 보낸다(서버가 "지금 배터리가 N%예요"로 말한다) |
| `pleos.car.permission.NAVI_ROUTE_SEARCH` | normal(Pleos 소스) | `navigate`·`add_waypoint` 실행 | 선택 | 충전소 이름과 거리만 말로 알리고 내비 동작은 하지 않는다 |
| `android.permission.RECORD_AUDIO` | dangerous | 음성 인식([`SpeechRecognizer`](https://developer.android.com/reference/android/speech/SpeechRecognizer)) | 음성 기능에 필수 | 처음 음성 버튼을 누를 때 요청. 거부되면 음성 버튼을 숨긴다(브리핑 TTS는 그대로) |
| `pleos.car.permission.FUSED_LOCATION` | dangerous(Pleos 소스) | 내비 경로가 없을 때 위치(주변 빈 충전기) | 선택 | 처음 "주변 충전기"를 쓸 때 요청. 거부되면 내비 현재 위치(`NAVI_ROUTE`)만 쓰고, 그것도 없으면 그 기능을 숨긴다 |
| `android.car.permission.CAR_ENERGY` | dangerous | 실제 충전 상태(`EV_CHARGE_STATE`) → 음성 `context.charging` | 선택 | `charging`을 보내지 않는다 |

- Android `CAR_ENERGY`는 선택 필드 `charging` 하나에만 쓰인다. 첫 버전에서는 **이 권한을 빼고
  시작하기를 권한다.** 서버와 음성은 `charging` 없이 동작한다.
- 권한 이름과 보호 수준은 Pleos 소스 주석과 Android 공식 문서([`Car`](https://developer.android.com/reference/android/car/Car))에서
  가져왔다. Pleos 권한(`pleos.car.permission.*`)과 Android Car 권한(`android.car.permission.*`)은 이름이
  같아도 다른 권한이다(`CAR_ENERGY`가 그렇다).

## 3. actions 처리

| `type` | 오는 곳 | 필드 | 앱이 할 일 |
| --- | --- | --- | --- |
| `set_reservation` | 브리핑, `car/plan`의 `reservation`, 음성 `plan_charge`·집 `leak_check` | `start_hhmm`, `end_hhmm` | 차량 기본 예약 충전 화면으로 안내하고 두 시각을 보여 준다. 앱이 예약을 직접 넣지 않는다. 주행 중이면 말로만 알리고 정차 뒤 화면을 띄운다 |
| `navigate` | 음성 `find_chargers` | `station_id`, `name`, `lat`, `lng` | 운전자가 "응"이라고 하면 `navi.requestRoute(RouteInfo(latitude = lat, longitude = lng, poiName = name, poiId = station_id, address = …, poiSubId = ""))`. 이름 붙은 인자로 쓴다(생성자에서 `longitude` 뒤에 `displayLatitude`·`displayLongitude: Double? = null`이 있어 위치 인자로는 컴파일되지 않는다). 권한 `NAVI_ROUTE_SEARCH` |
| `add_waypoint` | `car/chargers/along-route`, 음성 `find_chargers_along_route` | `station_id`, `name`, `lat`, `lng` | 운전자가 "응"이라고 하면 `navi.addWaypoint(RequestWaypointInfo(latitude = lat, longitude = lng, poiName = name, waypointIndex = WaypointIndex.FIRST, poiId = station_id, address = …, poiSubId = ""))`. 권한 `NAVI_ROUTE_SEARCH` |
| `ask` | 귀가 브리핑 첫 질문, `?`로 끝난 음성 답, 바닥날 수 있는 경유지 추천 | `question` | `speech`를 다 읽은 뒤 바로 마이크를 연다. 다음 요청의 `history`에 이 턴을 `{"role": "wattit", "text": <읽은 speech>}`로 넣는다 |

- `RouteInfo`·`RequestWaypointInfo`의 `poiId`, `address`, `poiSubId`는 소스에서 null을 받지 않는
  `String`이다. 응답에는 주소가 없으므로 `poiId`에 `station_id`, `address`는 `GET /api/chargers`에서
  받은 주소나 빈 문자열, `poiSubId`는 빈 문자열을 넣는다. 실제 내비가 빈 값을 받는지 확인이 필요하다.
  이것은 임시 방법이다. **BE-13에서 `navigate`·`add_waypoint` 동작에 `address`를 추가할 예정**이며,
  그때 이 항목을 고친다.
- 음성 `history`: 최대 6턴. `wattit` 턴은 서버가 준 `speech`를 글자 그대로 넣는다. 평소 출발 시각
  질문에 "응"이라고 답한 것을 서버가 알아보려면 직전 `wattit` 턴이 그 질문으로 끝나야 한다.
- 음성 응답의 `fallback: true`는 Claude 문장 대신 서버 문장을 읽는다는 뜻이다. 앱은 그대로 읽으면 된다.

## 4. 기기 토큰과 오류

기기 토큰

- `POST /api/car/devices`의 응답에서 한 번만 보인다. 서버는 해시만 저장하므로 다시 받을 수 없다.
- 서버 쪽 만료는 없다. 로그나 크래시 리포트에 남기지 않는다(아래 "로그 규칙").
- 저장: Android Keystore에 앱 전용 AES 키(`KeyGenParameterSpec`, `AES/GCM/NoPadding`)를 만들고, 그 키로
  토큰을 직접 암호화해 IV와 함께 파일에 쓴다. `EncryptedSharedPreferences`(`androidx.security:security-crypto`)는
  쓰지 않는다. 1.1.0-alpha07부터 "Deprecated all APIs in favour of existing platform APIs and direct use of
  Android Keystore"다([AndroidX Security 릴리스 노트](https://developer.android.com/jetpack/androidx/releases/security)).
- 토큰 파일은 백업에서 뺀다. [`Context.getNoBackupFilesDir()`](https://developer.android.com/reference/android/content/Context#getNoBackupFilesDir())
  아래에 두면 자동 백업에서 빠진다. 다른 곳에 두면 `android:dataExtractionRules`(Android 12 이상)와
  `android:fullBackupContent`(11 이하) 규칙에서 그 파일을 `exclude`한다([Auto Backup](https://developer.android.com/identity/data/autobackup)).
  백업으로 다른 기기에 복원된 암호문은 Keystore 키가 없어 풀리지 않는다.
- 복호화에 실패하면(키 없음, 파일 손상) 앱을 멈추지 말고 "토큰 없음"으로 보고 파일을 지운 뒤 다시
  발급한다.
- 새로 발급하면 다른 기기로 본다. 절감 합계와 출발 기록이 새로 시작되므로, 저장한 토큰을 읽을 수
  없을 때(파일 없음, 복호화 실패)와 저장한 토큰으로 401이 날 때만 다시 발급한다. IP당 시간 한도가 있다(기본 10회/시간, 429).
- 헤더: `Authorization: Bearer <device_token>`.

로그 규칙

- 릴리스 빌드에서는 HTTP 로깅을 끈다(OkHttp `HttpLoggingInterceptor`는 `Level.NONE`). `BASIC`도 URL을
  남기므로 `GET /api/chargers?lat=…&lng=…`의 위치가 logcat에 그대로 찍힌다.
- 디버그 빌드에서도 `redactHeader("Authorization")`로 토큰을 가리고, 쓰는 OkHttp에
  `redactQueryParams`가 있으면 `redactQueryParams("lat", "lng")`로 쿼리의 위치도 가린다. 요청 본문까지 찍는 `Level.BODY`는
  쓰지 않는다(위치와 음성 문장이 본문에 있다).
- 다음 값은 어느 빌드에서든 로그(logcat)와 크래시 리포트, 분석 이벤트에 남기지 않는다.
  - 기기 토큰
  - 위치: `lat`·`lng`, `origin`, `destination`, `route_points`
  - 출발 시각: `departed_at`, 출발 제안(평일 몇 시에 집이 비는지 드러난다)
  - 음성: 운전자의 `text`, `history`, 응답 `speech`
- 오류를 남길 때는 경로(쿼리 없이), 상태 코드, 오류 종류만 남긴다.

오류 코드별 앱 동작

| 코드 | 언제 | 앱 동작 |
| --- | --- | --- |
| 401 | 토큰이 필요한 API에 토큰이 없거나 틀림 | 저장된 토큰을 지우고 한 번 다시 발급한 뒤 재시도. 다시 401이면 그 기능만 끈다 |
| 404 | 확정할 절감 기록이 없음(오래돼 정리됨, 다른 기기) | 그 `saving_id`를 버린다. 재시도하지 않는다 |
| 410 | 만든 지 72시간이 지난 기록을 확정 | 버린다 |
| 422 | 입력 검증 실패(범위 밖 값, NaN, 출발 시각이 이미 지남, 시간 부족 등) | 재시도하지 않는다. SDK 값을 점검한다. `car/plan`의 "시간이 부족해요"처럼 본문 `detail`이 문자열이면 그 문장을 읽어도 된다 |
| 429 | 하루·시간 한도 초과(음성, 확정, 출발 기록, 기기 발급) | `Retry-After`(초)만큼 기다린다. 음성 429는 본문 `speech`를 읽는다 |
| 501 | 서버에 키가 없음. 음성(`ANTHROPIC_API_KEY`), 주변 충전소(`CHARGER_API_KEY`) | 음성은 본문 `speech`("음성 대화는 아직 준비 중이에요.")를 읽고 음성 버튼을 숨긴다. 귀가 브리핑 첫 질문은 501이 나지 않는다 |
| 503 | 충전소 캐시를 아직 수집하지 않음 | "충전소 정보를 준비 중"으로 안내하고, 아래 재시도 규칙대로 다시 부른다 |
| 500 등 5xx | 서버 오류 | 일반 오류 문장. 주행 중이면 말하지 않는다. 다시 보낼 기록(출발, 확정)은 아래 재시도 규칙대로 |
| 연결 실패·시간 초과 | 오프라인 | 다시 보낼 기록은 큐에 두고 아래 재시도 규칙대로 |

재시도 규칙 (5xx, 503, 연결 실패, 오프라인 큐)

- 서버는 작은 단일 워커다. 장애 뒤 모든 차가 같은 간격으로 다시 보내면 복구가 늦어지므로, 지수
  백오프에 무작위 지연(jitter)을 더한다: 첫 대기 30초, 실패할 때마다 두 배, 최대 30분. 실제 대기는
  `random(0, 그 값)`(full jitter)으로 고른다. 성공하면 처음(30초)으로 돌아간다.
- 앱이 실행 중이고 화면이 열린 동안만 재시도한다. 백그라운드 작업(WorkManager 등)으로 시동이 꺼진 뒤까지
  다시 보내지 않는다. 남은 큐는 다음 시동 때 이어서 보낸다.
- 429는 이 규칙이 아니라 `Retry-After`를 따른다. 401·404·410·422는 다시 보내지 않는다(표).
- 사용자가 직접 누른 요청(음성, 주변 충전기)은 자동으로 다시 보내지 않고 오류 문장만 보여 준다.

- 스냅숏 테스트가 지키지 못하는 것: 오류 본문(음성 429·501의 `speech`, 422의 `detail` 문장),
  헤더(`X-Status-Note`, `Retry-After`), 음성 밖 API의 오류 코드(OpenAPI(`/docs`)에는 401·429·501이
  음성에만 적혀 있다). 이것들은 위 표와 `car-api.md`의 각 절이 기준이다.
- 하루 시나리오 테스트(`backend/tests/scenarios/test_car_day.py`)는 한 기기의 하루를 한 가지 순서로만
  돈다. 단계마다 예약·금액이 같은 입력의 `car/plan`과 같은지, 운전자가 말한 시각이 "말한 출발"로
  몇 건 남는지는 보지만, 오류 경로(401·429)와 오프라인 일괄 전송은 각 API 테스트가 맡는다.
- 계산 API(`car/plan`, `car/leak-check`, `car/briefing`)는 토큰이 틀려도 계산은 그대로 준다
  (`saving_id`만 null). 이때는 다시 발급하지 않아도 된다. `car/charge-target`은 토큰을 받지 않고
  `saving_id`도 없다.

## 5. 하루 흐름 예

`backend/tests/scenarios/test_car_day.py`가 아래 순서를 시계를 고정해 끝까지 돌고, 단계마다 숫자가
같은 입력의 `car/plan`과 맞는지 확인한다.

1. 화 08:00 기기 발급.
2. 화 17:50 시동 ON 브리핑(잔량 32%): 평소 출발 기록이 없어 "내일 오전 8시 출발 기준"으로 오늘 밤
   예약과 아끼는 금액을 말한다.
3. 화 18:20 귀가 중 첫 질문: "집에 도착하면 배터리가 25% 남아요. 내일 몇 시에 출발하세요?"
4. 운전자 "7시 반에 나가" → 도착 예정 18:40·도착 잔량 25%로 다시 계산한 예약(`set_reservation`)과
   `saving_id`. 07:30은 "운전자가 말한 출발 시각"으로 남는다.
5. 수 07:25 다음 시동 ON: 잔량이 주차 때(25%)보다 올라 있으므로 4의 `saving_id` 확정 → 이번 달 합계가
   그 금액.
6. 수 07:31 그날 첫 P 해제 → 출발 기록(30분 안의 "말한 07:30"을 실제 출발로 바꾼다). 12:10 회사에서
   다시 P를 해제해도 그날 이미 보냈으므로 보내지 않는다.
7. 지난주 평일 출발 4건이 더 쌓이면, 수 17:50 브리핑은 "평소 출발 07:30" 기준으로 계산하고, 18:20
   귀가 질문은 "내일도 오전 7시 30분에 출발하세요?"가 된다. "응"이라고 하면 07:30으로 계획한다.

## 6. 실제 차에서 확인할 것

- `CarPropertyManager`의 `INFO_EV_BATTERY_CAPACITY`, `GEAR_SELECTION`이 이 차에서 지원되는지
  (`getPropertyList()`에 있는지)와 차의 Car API 레벨.
- `remainDestinationChargingInt`의 단위(%인지), `DestinationInfo.remainDistance`·`remainTime`이
  목적지까지 남은 값인지.
- 밤사이 충전 확인: 주차 때 잔량과 다음 시동 때 잔량 비교로 충분한지.
- Pleos `getEvChargeSwitchState`가 충전 스위치 설정값인지 실제 충전 상태인지(`PleosPropertyIds.EV_CHARGE_SWITCH`의
  값이 소스에 없어 Android `EV_CHARGE_SWITCH`와 같은지 확인하지 못했다). 그리고 `EV_CHARGE_STATE`가 이
  차에서 지원되는지.
- `requestRoute`·`addWaypoint`에 `address`·`poiSubId`를 빈 문자열로 넣어도 되는지(`address`는 BE-13에서
  동작에 추가 예정, `poiSubId`는 남는다).
