# 차량 앱 API (`/api/car/*`)

현대자동차그룹 차량용 앱 개발 공모전(Pleos Connect, Android Automotive)용 차량 앱이
부르는 API. 차량 앱은 로그인 없이(게스트) 쓰고, 이 엔드포인트들은 DB를 쓰지 않는다.

핵심 원칙

- **계산은 서버가, 실행은 차가.** 서버와 앱은 충전을 직접 켜고 끄지 않는다. 시동이
  꺼지면 서드파티 앱은 동작할 수 없으므로, 서버가 가장 싼 시작·종료 시각을 계산해
  주면 운전자가 그 값을 차량 기본 예약 충전에 넣는다.
- **숫자는 전부 서버 계산값이다.** 금액, 시각, 잔량은 계산 결과나 요청 값에서 그대로
  온다. TTS 문장도 서버 템플릿으로 만든다.
- 시각은 응답에서 항상 KST(`+09:00`)다. 요청에서 오프셋이 없는 시각은 KST로 읽는다
  (`/api/recommend`와 같은 규칙).

## `POST /api/car/plan` 차량 충전 계획

차량이 아는 값(잔량, 배터리 용량)과 도착·출발 시각으로 가장 싼 충전 구간을 계산하고,
차량 예약 충전에 넣을 값과 TTS로 읽을 문장을 함께 돌려준다. 계산은
`/api/recommend`와 같다 (`recommend_service.compute_recommendation`).

### 요청 (JSON)

| 필드 | 타입 | 필수 | 기본 | 규칙 |
| --- | --- | --- | --- | --- |
| `soc_now` | number | 예 | | 0 이상 100 미만 (%). 현재 잔량 또는 내비가 준 도착 시 예상 잔량 |
| `battery_capacity_wh` | number | 예 | | 1,000 이상 1,000,000 이하 (Wh). Pleos Vehicle SDK `getEvBatteryCapacity` 값 그대로. 서버가 kWh로 바꾼다 |
| `soc_target` | number | | 80 | 0 초과 100 이하 (%) |
| `charger_kw` | number | | 7.0 | 0 초과 1000 이하 (kW) |
| `plug_in_at` | datetime | | 서버 현재 시각 | 충전기를 꽂을 수 있는 시각 = 도착 예정 시각. 이미 지났으면 서버 현재 시각으로 당긴다 |
| `depart_at` | datetime | 예 | | 다음 출발 시각 = 충전 완료 필요 시각. 서버 현재 시각과 `plug_in_at`보다 뒤, `plug_in_at`(당긴 뒤의 값)부터 72시간 이내 |
| `mode` | string | | `self_low` | `self_low`, `self_high`, `public_fast` (`/api/recommend`와 같음) |

숫자 필드는 `NaN`, `Infinity`를 받지 않는다. 모르는 필드는 무시한다.

### 응답 200

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `needs_charging` | bool | `soc_target <= soc_now`이면 `false` |
| `plan` | ChargePlanOut \| null | 가장 싼 구간 (`/api/recommend`의 `best`와 같음). `needs_charging=false`면 null |
| `baseline_now` | ChargePlanOut \| null | `plug_in_at`부터 바로 충전했을 때. `needs_charging=false`면 null |
| `savings_won` | int \| null | `baseline_now.cost_won - plan.cost_won` (0 이상). `needs_charging=false`면 null |
| `reservation` | Reservation \| null | 차량 예약 충전에 넣을 값. 아래 참고 |
| `speech` | string | TTS가 그대로 읽을 한국어 문장 |
| `assumptions` | string[] | 계산 전제. `needs_charging=false`면 빈 배열 |
| `unverified_tariff_items` | string[] | 아직 공식 근거를 못 찾은 요금 항목 (`/health`와 같음) |

ChargePlanOut: `start`, `end`(KST datetime), `energy_kwh`, `cost_won`, `discounted_kwh`.

Reservation:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `start_at` | datetime | 예약 시작 (KST, 분 단위) |
| `end_at` | datetime | 예약 종료 (KST, 분 단위). 자정을 넘으면 다음 날 |
| `start_hhmm` | string | `"22:00"`처럼 24시간 `HH:MM` |
| `end_hhmm` | string | `"01:00"`처럼 24시간 `HH:MM` |

분 단위로 맞추는 규칙 (`domain/reservation.py`):

- 시작은 `plan.start`를 분 단위로 내린다. 내린 값이 `plug_in_at`보다 앞서면 대신 올린다.
  `plug_in_at`을 생략해 서버 현재 시각(초 포함)이 쓰일 때 이 경우가 생긴다.
- 종료는 `plan.end`를 분 단위로 올린다. 시작을 올렸으면 그 시작에서 필요한 충전 시간을
  다 채운 시각을 올린다. 그래서 예약 구간은 계산된 충전 시간보다 짧지 않다.
- 단, 종료는 `depart_at`(분 단위 내림)을 넘지 않는다. 출발까지 시간이 충전 시간과 거의
  같고 시작을 올린 경우에만 이 상한이 걸리고, 그때 예약 구간은 충전 시간보다 2분 미만
  짧을 수 있다.
- 맞춘 구간이 24시간 이상이거나 비면(충전이 1분 남짓) 차량 예약 한 번으로 넣을 수 없어
  `reservation`이 null이다. `plan`은 그대로 나간다.

`speech` 규칙:

- 시각은 예약 값(분 단위)을 "오늘 밤 10시부터 내일 새벽 1시까지"처럼 읽는다. 때는
  새벽(0~5시), 오전(6~11시), 낮(12시), 오후(13~17시), 저녁(18~20시), 밤(21~23시)이고,
  00:00은 전날 "밤 12시"로, 00:01~00:59는 때 없이 "0시 29분"처럼 읽는다. 날은 서버 현재 시각 기준 오늘·내일·모레, 그 뒤는
  "10월 10일"이다. 끝 시각은 시작과 같은 날이면 날을, 때까지 같으면 때도 뺀다.
- `savings_won > 0`이면 "…보다 약 4,100원 아낍니다."를, 0이면 "바로 충전해도 요금 차이가
  없습니다."를 넣는다. 비교 대상은 `plug_in_at`이 미래면 "도착하자마자 충전하는 것",
  아니면 "지금 바로 충전하는 것"이다.
- `reservation`이 있으면 "(도착하면) 차량 예약 충전을 밤 10시 시작, 새벽 1시 종료로 설정해
  주세요."로 끝난다. 24시간 이상이라 null이면 예약 한 번으로는 설정할 수 없다고 말한다.
- 맞춘 구간이 비면 문장 전체가 "충전할 양이 아주 적어 차량 예약 충전으로 설정할 수
  없습니다. 출발 전에 바로 충전해 주세요."다.
- `needs_charging=false`면 "잔량 85%가 목표 80% 이상이라 충전하지 않아도 됩니다."
  (잔량은 소수 첫째 자리까지)
- 마크다운, 이모지는 넣지 않는다.

예시 요청과 응답 (서버 현재 시각 2026-10-07 17:00 KST):

```json
{"soc_now": 30, "battery_capacity_wh": 70000, "soc_target": 60,
 "plug_in_at": "2026-10-07T18:00", "depart_at": "2026-10-08T08:00"}
```

```json
{
  "needs_charging": true,
  "plan": {"start": "2026-10-07T22:00:00+09:00", "end": "2026-10-08T01:00:00+09:00",
           "energy_kwh": 21.0, "cost_won": 2352, "discounted_kwh": 0.0},
  "baseline_now": {"start": "2026-10-07T18:00:00+09:00", "end": "2026-10-07T21:00:00+09:00",
                   "energy_kwh": 21.0, "cost_won": 2747, "discounted_kwh": 0.0},
  "savings_won": 395,
  "reservation": {"start_at": "2026-10-07T22:00:00+09:00", "end_at": "2026-10-08T01:00:00+09:00",
                  "start_hhmm": "22:00", "end_hhmm": "01:00"},
  "speech": "오늘 밤 10시부터 내일 새벽 1시까지 충전하면 가장 쌉니다. 도착하자마자 충전하는 것보다 약 395원 아낍니다. 도착하면 차량 예약 충전을 밤 10시 시작, 새벽 1시 종료로 설정해 주세요.",
  "assumptions": ["충전 출력 일정", "연속 충전", "기본요금 제외, kWh당 요금만 계산"],
  "unverified_tariff_items": ["public_fast.base_price_per_kwh", "weekend_discount_sunset"]
}
```

### 오류

오류 모양은 `/api/recommend`와 같다.

| 상태 | 언제 | 본문 |
| --- | --- | --- |
| 422 | 필드 범위·타입 오류, `depart_at`이 서버 현재 시각이나 `plug_in_at` 이전, 두 시각 사이가 72시간 초과 | FastAPI 검증 오류 `{"detail": [{"type", "loc", "msg", "input"}]}`. 시각 오류의 `loc`은 `["body", "depart_at"]` |
| 422 | 시간이 모자람 (충전 시간 > 가능한 시간) | `{"detail": "시간이 부족해요. …"}` (문자열) |
| 422 | `mode=public_fast`인데 요금 설정에 공공 급속 기준단가가 없음 | `{"detail": "…"}` (문자열). 이 엔드포인트는 `public_base_price`를 받지 않는다 |

시각 검사는 충전이 필요 없는 요청(`soc_target <= soc_now`)에도 한다.

72시간 상한은 `/api/recommend`(14일)보다 짧다. 계산량이 구간 길이의 제곱으로 늘어
로그인 없이 부를 수 있는 이 엔드포인트에서 14일 구간은 요청 하나에 약 3초가 걸리기
때문이다. 도착부터 다음 출발까지는 주말을 넘겨도 72시간 안에 든다.
