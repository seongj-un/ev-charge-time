# 차량 앱 API (`/api/car/*`)

현대자동차그룹 차량용 앱 개발 공모전(Pleos Connect, Android Automotive)용 차량 앱이
부르는 API. 차량 앱은 로그인 없이(게스트) 쓴다. 계산 엔드포인트(`car/plan`, `car/leak-check`)는
기기 토큰 없이 부르면 DB를 쓰지 않는다. 절감 기록(아래 "절감 리포트" 절)과 음성 대화
(`car/voice`)는 기기 토큰이 필요하다.
주변 충전소는 기존 `GET /api/chargers`를 그대로 쓴다 (맨 아래 절).

핵심 원칙

- **계산은 서버가, 실행은 차가.** 서버와 앱은 충전을 직접 켜고 끄지 않는다. 시동이
  꺼지면 서드파티 앱은 동작할 수 없으므로, 서버가 가장 싼 시작·종료 시각을 계산해
  주면 운전자가 그 값을 차량 기본 예약 충전에 넣는다.
- **숫자는 전부 서버 계산값이다.** 금액, 시각, 잔량은 계산 결과나 요청 값에서 그대로
  온다. TTS 문장도 서버 템플릿으로 만든다.
- 시각은 응답에서 항상 KST(`+09:00`)다. 요청에서 오프셋이 없는 시각은 KST로 읽는다
  (`/api/recommend`와 같은 규칙).
- 요청 시각의 연도는 보낸 그대로와 KST로 옮긴 뒤 모두 1970~9998년이어야 한다. 밖이면 그
  필드에 422(`"시각은 1970년부터 9998년 사이여야 합니다."`). `/api/recommend`도 같다.
- 설정 파일(요금, 공휴일, 공공 충전 단가)이 없거나 깨졌으면 500이고, 본문은 출처별 일반
  문구다(`"요금 설정을 읽지 못했습니다."`, `"공휴일 설정을 읽지 못했습니다."`,
  `"공공 충전 단가 설정을 읽지 못했습니다."`). 파일 경로는 서버 로그에만 남는다.
- 숫자 자리에 JSON `NaN`, `Infinity`, `-Infinity`가 오면 모든 엔드포인트가 422다. 오류 본문의
  `input`에는 그 값이 문자열(`"NaN"`, `"Infinity"`, `"-Infinity"`)로 담긴다. 나머지 422 본문은
  FastAPI 기본 모양 그대로다.

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
| `saving_id` | string \| null | 기기 토큰과 함께 왔고 `savings_won > 0`이라 대기 절감 기록을 만들었을 때만. 아래 "절감 리포트" 절 |

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

## `POST /api/car/leak-check` "돈이 새고 있어요" 알림

차가 충전 중일 때 앱이 부른다. 지금 충전 방식으로 새는 돈을 계산해, 기준 이상이면 할 일을
알려 주는 문장을 돌려준다. 서버는 충전을 켜거나 끄지 않는다.

돈이 새는 원인은 두 가지다.

- `place="home"` (집·회사 완속): **시간대**. 지금 바로 충전했을 때와 출발 전 가장 싼 구간의
  차이. 계산과 시각 검사는 `POST /api/car/plan`과 같다 (꽂는 시각 = 서버 현재 시각).
- `place="public"` (공공 충전기): **결제 방식**. 로밍가·비회원가와 회원가의 차이.
  한국소비자원 2025-12-17 발표 20개 사업자 평균 단가(`backend/config/public_charging_prices.yaml`)로
  추정한다. 시간대 계산은 하지 않는다 (공공 급속 기준단가 미확인).

### 요청 (JSON)

| 필드 | 타입 | 필수 | 기본 | 규칙 |
| --- | --- | --- | --- | --- |
| `place` | string | | `home` | `home`, `public` |
| `soc_now` | number | 예 | | 0 이상 100 미만 (%) |
| `battery_capacity_wh` | number | 예 | | 1,000 이상 1,000,000 이하 (Wh) |
| `soc_target` | number | | 80 | 0 초과 100 이하 (%) |
| `charger_kw` | number | | 7.0 | 0 초과 1000 이하 (kW). home에서만 쓴다 |
| `depart_at` | datetime | | 다음 오전 8시 | home에서만 쓴다. 없으면 지금 다음에 처음 오는 오전 8시(KST)로 가정하고 `assumptions`에 적는다. 기기 토큰이 있고 평소 출발 시각 제안이 `high`이면 오전 8시 대신 그 시각을 가정한다(아래 "출발 시각 학습"). 받은 `depart_at`은 토큰이 있으면 `stated` 출발 기록으로 남는다. 가정한 시각은 늦추지 않는다(아래 `speech` 참고). 있으면 car/plan과 같은 검사(현재 시각 이후, 72시간 이내) |
| `mode` | string | | `self_low` | home에서만 쓴다 |
| `payment` | string | public이면 예 | | `member`, `roaming`, `nonmember` |
| `charger_speed` | string | public이면 예 | | `slow`, `fast` |

home에서는 `payment`·`charger_speed`를, public에서는 `depart_at`·`mode`·`charger_kw`를 보지 않는다.

### 응답 200

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `leaking` | bool | `leak_won > 0`이고 `leak_won >= CAR_LEAK_MIN_WON`(기본 500)이면 true |
| `leak_won` | int | 새는 금액(원, 반올림). home은 car/plan의 `savings_won`, public은 `energy_kwh × (unit_price_now - unit_price_member)` |
| `cause` | string \| null | `time`(home) 또는 `payment`(public). `leaking=false`면 null |
| `energy_kwh` | number | 채울 전력량. 충전이 필요 없으면 0 |
| `plan` | ChargePlanOut \| null | home이고 `leaking=true`일 때만. car/plan의 `plan`과 같음 |
| `reservation` | Reservation \| null | home이고 `leaking=true`일 때만. car/plan의 `reservation`과 같음 (24시간 이상이면 null) |
| `unit_price_now` | number \| null | public일 때만. 지금 결제 방식의 사업자 평균 단가(원/kWh) |
| `unit_price_member` | number \| null | public일 때만. 회원가 사업자 평균 단가(원/kWh) |
| `speech` | string | TTS가 그대로 읽을 문장 |
| `assumptions` | string[] | 계산 전제. public은 "사업자 평균 기준 추정"을 늘 포함하고, 급속이면 원문 대조 전이라는 줄이 붙는다 |
| `saving_id` | string \| null | 기기 토큰과 함께 왔고 `leaking=true`라 대기 절감 기록을 만들었을 때만. 아래 "절감 리포트" 절 |

`speech`:

- home, 새는 경우: "지금은 요금이 비싼 시간이라 돈이 새고 있어요. 오늘 밤 10시부터 충전하면
  약 1,994원 아낄 수 있어요. 지금 충전을 멈추고 차량 예약 충전을 밤 10시 시작, 새벽 4시 39분
  종료로 설정해 주세요." (시각 읽기는 car/plan과 같다)
  - 지금이 경부하(가장 싼 시간대)인데도 새는 경우(바로 충전하면 뒤이은 비싼 시간대까지
    이어짐, 예: 평일 07:00)는 첫 문장이 "지금 바로 충전하면 비싼 시간대까지 이어져서 돈이
    새고 있어요."다.
  - 이미 충전 중이라 예약만 걸면 지금 충전이 계속될 수 있어서, 멈추라는 말을 같은 문장에
    넣는다.
  - `depart_at` 없이 가정한 출발로 계산했으면 첫 문장 앞에 가정을 붙인다: "내일 오전 8시
    출발 기준으로, 지금은 요금이 비싼 시간이라 돈이 새고 있어요. …" (오늘 8시를 가정했으면
    "오늘 오전 8시 출발 기준으로"). 지금 요금표에서는 22~08시가 전부 경부하라, 오늘 8시
    가정으로 새는 경우는 나오지 않는다.
  - 평소 출발 시각(high)을 가정했으면: "평소처럼 내일 오전 7시 30분 출발 기준으로, …", `assumptions`에
    "출발 시각 미입력: 평소 출발 시각(5건 기준)으로 11월 20일 오전 7시 30분(KST) 출발로 가정".
- public, 새는 경우: "비회원가로 충전하고 있어서 돈이 새고 있어요. 이번 충전(약 35kWh)은
  회원가보다 약 5,344원 더 나와요. 이 충전소 사업자 회원으로 결제하면 아낄 수 있어요. 사업자
  평균 기준 추정이에요." (전력량은 10kWh 이상이면 정수, 그 밑은 소수 첫째 자리)
- 새지 않거나 기준 미만: "지금 충전해도 괜찮아요."
- 이미 목표 잔량: "이미 목표 잔량 80%에 닿아서 더 충전하지 않아도 돼요."
- home에서 지금 바로 충전해도 출발 전에 다 못 채움: "출발 전까지 목표만큼 채우려면 지금 바로
  충전해야 해요." (car/plan은 이때 422지만, 여기서는 더 싼 선택지가 없다는 뜻이라 200으로
  답한다).
- `depart_at` 없이 가정한 출발(첫 오전 8시)까지 지금 바로 충전해도 다 못 채움: "오늘 오전 8시에
  출발하신다면 지금 바로 충전을 계속해야 해요. 출발 시각을 알려 주시면 다시 계산해 드릴게요."
  평소 출발 시각을 가정했으면 "평소처럼 내일 오전 7시 30분에 출발하신다면 …"
  (`leaking=false`). 가정을 다음 날로 늦춰 다시 계산하지 않는다 — 늦춘 출발로 "지금 충전을
  멈추라"고 하면, 그날 아침 나가는 운전자가 충전이 안 된 차로 출발한다. 편의(충전 실패 막기)가
  돈보다 먼저다. 앱이나 음성 대화가 출발 시각을 물어 다시 부르면 된다.

### 오류

| 상태 | 언제 | 본문 |
| --- | --- | --- |
| 422 | 필드 범위·타입 오류, home의 `depart_at` 시각 오류 | FastAPI 검증 오류 `{"detail": [...]}`. 시각 오류의 `loc`은 `["body", "depart_at"]` |
| 422 | public인데 `payment`나 `charger_speed`가 없음 | 같은 모양. `loc`은 `["body", "payment"]` 또는 `["body", "charger_speed"]`, `msg`는 "place가 public이면 payment가 필요합니다." |
| 500 | public인데 단가 설정 파일이 잘못됨 | 서버 설정 오류. home은 이 파일을 읽지 않아 영향이 없다 |

## 절감 리포트 (기기 토큰, 대기 → 확정 → 월·년 합산)

1회 절감액만으로는 와닿지 않아서 달·해 합계를 보여 준다. 합계는 **"추천을 따랐을 때 아낀
금액"(서버 계산값)**이고 실제 청구 요금이 아니다. 응답의 `note`가 늘 이 말을 한다.

흐름

1. 앱 설치 때 `POST /api/car/devices`로 기기 토큰을 한 번 받는다. 개인정보는 받지 않는다.
2. `car/plan`·`car/leak-check`를 `Authorization: Bearer <device_token>`과 함께 부르면, 아끼는
   돈이 있을 때(`savings_won > 0` / `leaking=true`) 서버가 **대기** 기록을 만들고 응답에
   `saving_id`를 붙인다.
   - 토큰이 없으면 지금과 같은 응답이다(`saving_id: null`). DB를 열지 않는다.
   - 토큰이 틀려도 계산은 그대로 돌려주고 기록만 하지 않는다(`saving_id: null`).
   - 기록 중 DB 오류가 나도 계산은 그대로 나간다(`saving_id: null`, 서버 로그에 경고).
3. 앱이 추천을 실제로 따른 것을 보면(예약 시각에 충전 시작을 Vehicle SDK로 확인, 운전자가
   회원 결제로 바꿨다고 확인) `POST /api/car/savings/{saving_id}/confirm`으로 **확정**한다.
4. `GET /api/car/savings/summary`가 확정된 기록만 더한다.

규칙

- 대기 기록은 기기당 최근 20개만 남고, 더 오래된 대기 기록은 새 기록을 만들 때 지워진다.
  확정된 기록은 지우지 않는다.
- 기록 한 건은 최대 100,000원이다(넘으면 100,000원으로 저장). 공개 엔드포인트라 합계를
  부풀리는 입력을 막는다.
- 원인(`cause`)은 car/plan이면 `time`, car/leak-check면 응답의 `cause`(`time`·`payment`)다.
  같은 상황에 두 엔드포인트를 다 부르면 대기 기록이 두 건 생기므로, 앱은 실제로 따른 쪽
  하나만 확정한다.

### `POST /api/car/devices` 기기 토큰 발급

본문 없음. 201:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `device_id` | string | UUID |
| `device_token` | string | 이 응답에서만 보인다(`Cache-Control: no-store`). 서버는 sha256만 저장한다 |

IP마다 `CAR_DEVICE_RATE_LIMIT_WINDOW_MINUTES`(기본 60)분에 `CAR_DEVICE_RATE_LIMIT_COUNT`(기본
10)번까지다. 넘으면 429와 `Retry-After`(초). 운영에서는 Caddy 뒤라 `FORWARDED_ALLOW_IPS`로
Caddy의 `X-Forwarded-For`를 믿게 해야 실제 클라이언트 IP로 센다(`docker-compose.prod.yml`).
IP는 원문 대신 가명 처리한 키로 센다: `CAR_IP_HASH_SECRET`으로 만든 HMAC-SHA256이고, 비밀값이
비어 있으면 솔트 없는 sha256(서버가 경고 로그를 한 번 남긴다)이다. 창이 지난 카운터 행은 같은
IP가 다시 발급할 때 재사용되어 따로 정리하지 않는다.

### `POST /api/car/savings/{saving_id}/confirm` 확정

`Authorization: Bearer <device_token>` 필수. 200:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `saving_id` | string | |
| `cause` | string | `time`, `payment` |
| `savings_won` | int | 서버 계산값(원) |
| `energy_kwh` | number | |
| `source` | string | `plan`, `leak_check` |
| `created_at` | datetime | 대기 기록을 만든 시각 |
| `confirmed_at` | datetime | 처음 확정한 시각. 다시 불러도 바뀌지 않는다(멱등) |

확정 남용 막기(토큰 하나로 "계산 → 확정"을 되풀이해 합계와 DB 행을 늘리지 못하게):

- 기록을 만든 뒤 `CAR_SAVINGS_CONFIRM_WINDOW_HOURS`(기본 72, car/plan 계산 구간 상한과 같음)
  시간이 지나면 410. 기한은 DB 시계로 잰다.
- 기기당 KST 하루 `CAR_SAVINGS_DAILY_CONFIRM_MAX`(기본 3)건까지. 넘으면 429와 다음 날 0시(KST)까지의
  `Retry-After`(초). 기기 행을 잡고 세므로 병렬 요청으로도 넘을 수 없다.
- 이미 확정된 기록을 다시 부르면 기한·한도와 상관없이 200이고 한도를 쓰지 않는다.

### `GET /api/car/savings/summary?month=YYYY-MM` 합산

`Authorization: Bearer <device_token>` 필수. `month`를 빼면 서버 현재 시각의 KST 달. 200:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `month` | string | `YYYY-MM` |
| `month_won`, `month_count` | int | 그 달(KST)에 **확정된** 기록의 합계·건수 |
| `year` | int | `month`의 해 |
| `year_won`, `year_count` | int | 그해(KST)에 확정된 기록의 합계·건수 |
| `total_won` | int | 이 기기의 확정 기록 전체 합계 |
| `by_cause` | object | `{time_won, payment_won}`. 전체 기간(`total_won`)을 원인별로 나눈 값 |
| `speech` | string | 시동을 켤 때 읽을 한 줄 |
| `note` | string | "추천을 따랐을 때 아낀 금액(서버 계산값)이며 실제 청구 요금과 다를 수 있습니다." |

달·해는 확정 시각(`confirmed_at`)을 KST로 본다. `/api/me/plans/summary`와 같은 달 경계 함수
(`api/months.py`)를 쓴다.

`speech`:

- 그 달 기록이 있음: "이번 달 와트잇으로 약 8,400원, 올해 약 52,000원 아꼈어요." 다른 달이면
  "11월 …", 다른 해면 "2026년 12월 와트잇으로 약 …원, 2026년 한 해 약 …원 아꼈어요."
- 그 달 기록은 없고 전에 있음: "2월에는 아낀 기록이 없어요. 지금까지 와트잇으로 약 9,600원 아꼈어요."
- 기록이 하나도 없음: "아직 아낀 기록이 없어요. 와트잇 추천대로 충전하면 여기에 쌓여요."

### 오류

| 상태 | 언제 | 본문 |
| --- | --- | --- |
| 401 | confirm·summary에 토큰이 없거나 틀림 | `{"detail": "..."}`, `WWW-Authenticate: Bearer` |
| 404 | confirm할 기록이 없음(다른 기기의 기록, 20개 상한으로 지워진 대기 기록, UUID가 아닌 id 포함) | `{"detail": "절감 기록을 찾을 수 없습니다."}` |
| 410 | 만든 지 72시간이 지난 기록을 확정 | `{"detail": "이 기록은 확정할 수 있는 기간(72시간)이 지났습니다."}` |
| 422 | `month` 형식 오류(연도는 1~9998) | `{"detail": "month는 YYYY-MM 형식이어야 합니다."}` |
| 429 | confirm 하루 한도 초과 | `{"detail": "오늘 확정할 수 있는 횟수(3건)를 다 썼습니다. 내일 다시 확정해 주세요."}`, `Retry-After` |
| 429 | 기기 발급 IP 한도 초과 | `{"detail": "..."}`, `Retry-After` |

## `POST /api/car/voice` 음성 대화 (Claude)

운전자 말(Pleos STT가 바꾼 글자)을 받아 Claude가 이해하고 도구를 골라 부르고, TTS로 읽을
답(`speech`)과 앱이 보여 줄 동작(`actions`)을 돌려준다. 금액·시각·잔량 같은 숫자는 도구가
낸 서버 계산값만 쓴다.

순서: 기기 토큰(401) → 귀가길 브리핑 첫 질문(200, 키·한도 없이) → 키(501) → 하루 한도(429)
→ Claude. 요청 본문 검증(422)은 이 모든 것보다 먼저다.

### 요청 (JSON), `Authorization: Bearer <device_token>` 필수

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `text` | string | `trigger`가 없으면 필수 | 운전자 말. 1~500자, 공백만이면 422 |
| `trigger` | string \| null | | `"arrival_briefing"`(귀가길 브리핑) |
| `history` | array | | 최근 6턴까지 `{role: "driver"\|"wattit", text: 1~500자}`. 오래된 것부터 |
| `context` | object | 필수 | 앱이 Pleos SDK로 읽은 차량 상태 (아래) |

`context`:

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `soc_now` | number | 필수 | 지금 잔량 %, 0~100 |
| `battery_capacity_wh` | number | 필수 | 배터리 용량 Wh, 1,000~1,000,000 |
| `lat`, `lng` | number | | 현재 위치. 둘 다 보내거나 둘 다 빼야 한다. 없으면 `find_chargers`가 "위치 없음" |
| `arrival_soc` | number | | NaviHelper 목적지 도착 예상 잔량 %. 있으면 충전 계획은 이 값에서 시작한다 |
| `arrival_at` | datetime | | NaviHelper 목적지 도착 예정 시각(오프셋 없으면 KST). 충전 계획의 꽂는 시각으로 쓴다. 지금부터 24시간을 넘으면 422, 이미 지났으면 지금으로 본다 |
| `destination` | `{lat, lng}` | | 내비 목적지. `find_chargers_along_route` 도구가 쓴다(없으면 그 도구는 오류 결과) |
| `remain_distance_m` | number | | 내비 남은 거리 m. 있으면 경로 위 충전소별 잔량을 추정한다 |
| `route_points` | `{lat, lng}[]` | | 내비 경유지(남은 것, 순서대로), 최대 50개. 없으면 현재 위치에서 목적지까지 직선 근사 |
| `efficiency_km_per_kwh` | number | | Vehicle SDK 충전 후 평균 전비(km/kWh), 0 초과 20 이하. 도착 예상 잔량이나 남은 거리가 없을 때 경로 위 충전소 잔량 추정에 쓴다 |
| `charger_kw` | number | | 충전기 출력, 기본 7.0 |
| `charging` | bool | | 지금 충전 중인지 (Claude에게 상황으로만 알린다) |
| `place` | string | | `"home"`·`"public"`. `leak_check`가 쓴다(없으면 home) |

### 응답 200

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `speech` | string | TTS로 읽을 답. 2문장 이하·80자 안팎을 Claude에 요청하고, 200자를 넘으면 서버 문장으로 바꾼다 |
| `actions` | array | 앱이 실행·표시할 것. 종류마다 많아야 하나, 아래 순서 보장 없음 |
| `fallback` | bool | Claude의 문장을 버리고 서버 문장으로 대신했으면 true |
| `saving_id` | string \| null | `plan_charge`·`leak_check`가 대기 절감 기록을 만들었으면 (BE-5와 같은 기록, 같은 확정 API) |

`actions` 종류:

- `{"type": "set_reservation", "start_hhmm", "end_hhmm"}`: 차량 기본 예약 충전에 넣을 값.
  `plan_charge`나 집 충전 `leak_check`가 예약 값을 냈을 때. 앱은 충전을 켜고 끄지 않고, 운전자가
  넣도록 보여 준다.
- `{"type": "navigate", "station_id", "name", "lat", "lng"}`: `find_chargers`가 찾은 가장 가까운
  충전소.
- `{"type": "add_waypoint", "station_id", "name", "lat", "lng"}`: `find_chargers_along_route`가 고른
  경유지 추천(아래 "경로 위 충전소 찾기"와 같은 규칙). 추천 충전소까지 가기 전에 바닥날 수 있으면
  대신 `ask` "더 가까운 충전소를 찾아볼까요?"를 준다.
- `{"type": "ask", "question"}`: 와트잇이 질문으로 끝냈다. 앱은 읽은 뒤 바로 마이크를 연다.
  귀가길 브리핑 첫 질문과, Claude의 답이 `?`로 끝날 때(마지막 문장).

### 귀가길 브리핑

`trigger: "arrival_briefing"`이고 `text`가 없으면 서버 문장으로 첫 질문을 한다. Claude를 부르지
않으므로 키가 없어도 200이고 하루 한도도 쓰지 않는다.

- `arrival_soc`가 있으면: "집에 도착하면 배터리가 32% 남아요. 내일 몇 시에 출발하세요?"
- 없으면: "지금 배터리가 32%예요. 내일 몇 시에 출발하세요?"
- `actions`: `[{"type": "ask", "question": "내일 몇 시에 출발하세요?"}]`
- 이 기기의 평소 출발 시각 제안이 있으면 질문이 바뀐다(아래 "출발 시각 학습", 다음 아침 기준):
  `high` "내일도 오전 7시 30분에 출발하세요?", `low` "내일 오전 7시 30분쯤 출발하세요?".
  `ask` 동작의 질문도 같다.

평소 출발 시각 제안이 있으면 시스템 컨텍스트에 `usual_departure: 내일 07:30 (confidence high,
기록 5건)`을 넣고, 운전자가 "응", "맞아"처럼 받아들이면 그 시각으로 `plan_charge`를 부르라고
알린다. 이 시각은 숫자 검증의 시각 근거에 들어간다("평소처럼 7시 반"은 통과, 다른 시각은
여전히 서버 문장으로 바뀐다). `plan_charge`가 받은 출발 시각은 `stated` 출발 기록으로 남는다.

다음 턴에서 앱은 운전자 답을 `text`로, 위 질문을 `history: [{"role": "wattit", ...}]`로 보내고
`trigger`는 그대로 두어도 된다(Claude에게 "귀가 중, 출발 시각을 물었다"는 상황을 알린다).
Claude는 `plan_charge(depart_time)`를 불러 예약 시각을 돌려준다.

### 도구 (모두 읽기 전용, 서버 함수를 직접 부른다)

Claude가 넣는 값은 운전자의 의도뿐이고, 차량 값(잔량, 용량, 출력, 위치, 장소)은 서버가
`context`에서 채운다. Claude가 다른 값을 넣어도 무시한다. 입력이 틀리면 Claude에게 오류
결과를 돌려준다.

| 도구 | Claude 입력 | 서버가 하는 일 |
| --- | --- | --- |
| `plan_charge` | `depart_time` "HH:MM"(필수), `soc_target` 1~100(기본 80) | `car/plan` 계산. 꽂는 시각은 `arrival_at`(없으면 지금), 출발은 꽂은 뒤 처음 오는 그 시각, 시작 잔량은 `arrival_soc` 또는 `soc_now`. 절감액은 도착하자마자 충전하는 경우와 비교한다. 충전 요금(`cost_won`)은 Claude에 넘기지 않는다 |
| `find_chargers` | `available_only`(기본 true), `min_kw`, `radius_m` 500~20,000(기본 3,000) | `GET /api/chargers`와 같은 검색, 가까운 순 최대 3곳. 충전소 이름은 줄바꿈을 펴고 40자로 잘라 넘긴다(공공 API에서 온 글). `navigate` 동작에는 원래 이름 |
| `leak_check` | `payment`, `charger_speed`, `depart_time` | `car/leak-check` 계산. 장소는 `context.place` |
| `find_chargers_along_route` | `min_kw`(기본 50), `corridor_m` 500~10,000(기본 3,000) | `POST /api/car/chargers/along-route`와 같은 함수. 출발은 `context`의 위치, 목적지·경로 지점·잔량·남은 거리·전비·배터리 용량도 `context`에서. 결과에 `reserve_soc`(15)와 `min_kw`를 함께 준다 |
| `savings_summary` | `month` "YYYY-MM"(기본 이번 달) | 이 기기의 절약 리포트 |

### 숫자 검증과 서버 문장

Claude 답의 숫자를 **단위별로** 근거와 비교한다. 하나라도 근거가 없으면 그 답을 버리고
**마지막 도구의 서버 문장**을 읽는다(`fallback: true`). 도구를 안 썼으면 "정확한 숫자를 확인하지
못했어요. 충전 계획이나 주변 충전기를 다시 물어봐 주세요."

| 표현 | 근거 |
| --- | --- |
| "N원", "N천 원", "N만 원" | 절감·새는 금액 필드(`savings_won`, `leak_won`, 리포트의 `*_won`)와 서버 문장의 "N원". 충전 요금은 넘기지 않는다 |
| "N%", "N퍼센트" | 잔량 값(`soc_now`, `arrival_soc`, 도구의 `soc_start`·`soc_target`)과 서버 문장의 "N%" |
| "밤 10시", "새벽 3시 19분", "7시 반", "22:00" | 예약 시작·종료, 출발, 도착 시각. 12시간제와 "오전·오후·새벽·아침·낮·저녁·밤"을 해석한다 |
| "A부터 B까지" (한국어 시각이나 HH:MM) | 예약 구간이 있으면 A가 시작, B가 종료여야 한다(뒤바뀌면 실패) |
| "N킬로미터", "N킬로", "N km", "N미터", "N m" | 거리 필드(도구 결과의 `*_m`, `*_km`: `distance_m`, `offset_m`, `route_m`, `radius_m`, `distance_km` 등, `context.remain_distance_m`)와 서버 문장의 거리. 10m, 0.1km, 1km 단위로 반올림한 모양도 허용한다. 꺾은선 위치 `along_m`은 도로 거리와 달라 근거가 아니다. "km/kWh", "km/h"는 거리로 보지 않는다 |
| "N킬로와트", "N kW" | 출력 필드(도구 결과의 `*_kw`: `max_kw`, `min_kw` 등, `context.charger_kw`)와 서버 문장의 출력. "킬로와트"·"킬로와트시"는 거리 "킬로"로 읽지 않는다. "킬로와트시"·"kWh"는 그 밖의 숫자로 본다 |
| 그 밖의 숫자 | 도구 결과·`context`에 나온 숫자. 날짜 문자열의 숫자("2026-11-17"의 2026, 11, 17)와 식별자(`station_id` 등 `*_id`)의 숫자는 넣지 않는다 |

- 운전자 말(이번 `text`와 `history`의 `driver` 턴)의 숫자는 같은 규칙으로 근거에 더한다. `wattit`
  턴은 클라이언트가 보낸 값이라 근거로 쓰지 않는다.
- 소수는 사람이 말하는 모양을 허용한다(32.46 → "32", "32.5").
- 한글로 쓴 수("천 원"의 앞 숫자 없이 "천 원", "여덟 시")는 검사하지 못한다. 시스템 프롬프트로
  아라비아 숫자를 쓰게 한다.

### 실패해도 200

운전 중 화면에 오류를 띄우지 않는다. 아래는 모두 200 + `fallback: true`이고, 그때까지 실행한
도구의 `actions`·`saving_id`는 그대로 준다. `speech`는 마지막 도구의 서버 문장, 도구를 안
썼으면 "지금은 대답하기 어려워요. 잠시 후 다시 말씀해 주세요."

- Claude 오류(4xx/5xx, 연결 실패)·시간 초과: 대화 한 번 전체가 8초(호출마다 남은 시간을 넘김,
  재시도 없음)
- 잘린 답(`max_tokens` 300)·거절
- Claude 호출이 3번 모두 도구를 부르고 끝남(루프 상한). 한 응답의 도구는 4개까지 실행하고
  넘는 것은 오류 결과를 준다.
- 답이 비었거나 200자를 넘음

### 하루 한도 (KST 0시 기준)

Claude를 부르는 요청만 센다. 기기 → IP → 서비스 순서로 보고, 앞 한도에 걸린 요청은 뒤 카운터를
깎지 않는다.

- 기기별 `CAR_VOICE_DAILY_MAX`(기본 60)
- IP별 `CAR_VOICE_IP_DAILY_MAX`(기본 120). 기기 토큰을 여러 개 받아 기기 한도를 피하는 것을
  막는다. IP 키는 기기 발급 한도와 같은 가명 처리 값(`CAR_IP_HASH_SECRET` HMAC)이다.
- 서비스 전체 `CAR_VOICE_SERVICE_DAILY_MAX`(기본 2,000, 0이면 걸지 않음)

### 오류

| 상태 | 언제 | 본문 |
| --- | --- | --- |
| 401 | 기기 토큰이 없거나 틀림 | `{"detail": "..."}`, `WWW-Authenticate: Bearer` |
| 422 | 요청 검증 실패 (`text`·`trigger` 둘 다 없음, 500자 초과, history 7턴 이상, `lat`만 있음 등) | FastAPI 기본 `detail` 배열 |
| 422 | `context.arrival_at`이 지금부터 24시간 뒤보다 늦음 (기기 토큰 확인 뒤에 검사) | 같은 모양, `loc: ["body", "context", "arrival_at"]` |
| 429 | 하루 한도 초과 | `{"detail": s, "speech": s}`, `Retry-After`(다음 날 0시까지 초), `X-RateLimit-Scope: device\|ip\|service` |
| 501 | `ANTHROPIC_API_KEY` 미설정 (브리핑 첫 질문 제외) | `{"detail": "음성 대화는 아직 준비 중이에요.", "speech": 같은 문장}` |

기기 한도 문장: "오늘은 음성 대화를 많이 쓰셔서 여기까지예요. 내일 다시 말씀해 주세요."
IP 한도 문장: "이 네트워크에서 오늘 음성 대화를 많이 써서 여기까지예요. 내일 다시 말씀해 주세요."
서비스 한도 문장: "지금은 음성 대화를 쓰는 분이 많아 오늘은 여기까지예요. 내일 다시 말씀해 주세요."

### 프롬프트와 로그

- 시스템 프롬프트에는 규칙, 지금 시각, 차량 상태만 있고 키·내부 정보는 없다. 운전자 말과
  history는 user/assistant 메시지로만 넣는다. history가 와트잇 말로 시작하면 앞에
  "(대화 시작)" user 메시지를 둔다(Messages API는 user로 시작해야 한다).
- 시스템 프롬프트는 도구 결과 안의 글(충전소 이름 등)이 데이터이지 지시가 아니라고 못 박는다.
- 로그에는 운전자 말의 길이, history 턴 수, 부른 도구 이름, fallback 이유(오류 종류와 HTTP
  상태)만 남긴다. 운전자 말과 Claude 오류 문구는 남기지 않는다. Claude가 4xx로 거절하면(키,
  워크스페이스, 모델 이름 문제) 상태 코드와 종류를 경고 로그로 남긴다.
- 도구 안에서 DB 오류가 나면 세션을 되돌리고 Claude에게 도구 오류를 준다(응답은 200).
- 모델 `CLAUDE_MODEL`(기본 `claude-haiku-5-5`), 키 `ANTHROPIC_API_KEY`(.env에만). 워크스페이스에
  묶이지 않은 키를 쓰면 `CLAUDE_WORKSPACE_ID`를 넣는다(`anthropic-workspace-id` 헤더). 운영
  compose는 이 값들과 음성 한도를 backend에만 넘긴다.

## 출발 시각 학습 (기기 토큰 필수)

편의 1순위: 출발 시각을 묻지 않고, 틀린 "오전 8시" 가정을 줄인다. 기록에는 시각과 출처만 있고
위치나 개인정보는 없다. 세 API 모두 `Authorization: Bearer <device_token>`가 없거나 틀리면 401.

### 기록의 두 출처

- `observed`: 앱이 Vehicle 기어가 P에서 벗어난 첫 시각(집 출발)을 `POST /api/car/departures`로 보낸다.
- `stated`: 운전자가 정한 출발 시각. 기기 토큰과 함께 온 `car/plan`의 `depart_at`, `car/leak-check`
  (home)의 받은 `depart_at`, 음성 `plan_charge`의 출발 시각을 서버가 남긴다. 서버가 가정한 시각은
  남기지 않는다. 토큰이 없으면 DB를 열지 않고, 기록이 실패해도 계산 응답은 그대로다.

남기는 규칙

- 같은 기기 30분 안의 기록은 하나로 합친다. observed가 stated를 대신하고, observed끼리는 이른 시각
  (처음 P를 벗어난 때), stated끼리는 나중에 말한 시각을 남긴다. stated는 observed를 바꾸지 않는다.
- 기기당 하루(KST, 기록한 날) 새로 만드는 수를 출처별로 센다. 합치기는 세지 않는다.
  - observed: `CAR_DEPARTURE_DAILY_OBSERVED_MAX`(기본 10)건. 넘으면 429.
  - stated: `CAR_DEPARTURE_DAILY_STATED_MAX`(기본 5)건. 넘으면 조용히 남기지 않는다.
  - 따로 세므로 말한 시각이 다 차도 실제 출발은 남는다. 기기당 최대 약 90일 × 15건.
- 출발 시각이 90일 지난 기록은 기록할 때마다(모든 기기) 지운다.

### `POST /api/car/departures`

요청 `{"departed_at": "2026-11-19T07:31:00+09:00", "source": "observed"}` (`source`는 생략 가능,
`observed`만 받는다. 오프셋이 없으면 KST).

| 상태 | 언제 | 본문 |
| --- | --- | --- |
| 201 | 새 기록 | `{departure_id, departed_at, source, merged: false}` |
| 200 | 30분 안의 기록과 합침 | 같은 모양, `merged: true`, 남은 기록의 시각과 출처 |
| 401 | 기기 토큰 없음·틀림 | `{"detail": ...}`, `WWW-Authenticate: Bearer` |
| 422 | `departed_at`이 지금+5분보다 늦음("departed_at은 지금보다 늦을 수 없습니다."), 90일보다 오래됨("departed_at은 90일 안이어야 합니다."), 연도 범위 밖, `source`가 `observed`가 아님 | FastAPI 기본 `detail` 배열, `loc: ["body", "departed_at"]` |
| 429 | 오늘 observed 상한(기본 10건)을 다 씀 | `{"detail": "오늘 남길 수 있는 출발 기록(10건)을 다 썼습니다. 내일 다시 보내 주세요."}`, `Retry-After`(다음 날 0시까지 초) |

### `DELETE /api/car/departures`

이 기기의 기록(observed, stated)을 전부 지운다. `200 {"deleted": N}`. 다른 기기의 기록은 그대로다.

### `GET /api/car/departures/suggest?date=YYYY-MM-DD`

`date`를 생략하면 내일(KST). 형식이 틀리면 422 "date는 YYYY-MM-DD 형식이어야 합니다.", 그 해의 공휴일
정보가 없으면 422(공휴일 안내 문구).

규칙

1. `date` 전 28일(`date - 28일 0시` ~ `date 0시`, KST) 기록 중 같은 날 종류만 쓴다. 날 종류는
   `weekday`(월~금)와 `weekend_holiday`(토·일·공휴일, 공휴일은 요금 계산과 같은 설정)다. 공휴일
   정보가 없는 해의 기록은 요일로만 가른다.
2. observed가 3건 이상이면 observed만, 아니면 observed와 stated를 함께 쓴다.
3. 3건 미만이면 제안하지 않는다.
4. 하루 분(0~1439)의 중앙값을 10분 단위로 반올림한다(5분은 올림, 짝수 개면 가운데 둘의 평균).
5. 5건 이상이고 중앙값 절대편차가 20분 이하이면 `high`, 아니면 `low`.

6. 반올림한 중앙값이 22:00 이후면 제안하지 않는다(`suggested_depart_at`·`confidence` null, 기록
   부족과 같은 문장). 23:56 출발이 반올림으로 다음 날 00:00이 되어 `date`와 날짜가 어긋나는 일을
   막는다.

한계: 자정을 넘나드는 출발(23:50과 00:10)은 하루 분으로 보면 멀리 떨어져 중앙값이 틀린다. 아침
출발을 위한 기능이라 다루지 않고, 중앙값이 22:00 이후로 나오면 위 6번으로 제안하지 않는다.

응답 200

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `date` | date | 제안한 날 |
| `suggested_depart_at` | datetime \| null | KST. 3건 미만이면 null |
| `confidence` | `"high"` \| `"low"` \| null | |
| `basis_count` | int | 제안에 쓴 기록 수(제안이 없으면 같은 날 종류의 기록 수) |
| `day_type` | `"weekday"` \| `"weekend_holiday"` | |
| `speech` | string | high "내일도 오전 7시 30분에 출발하세요?", low "내일 오전 7시 30분쯤 출발하세요?", 없음 "내일 몇 시에 출발하세요?" (오늘이면 "오늘", 그 밖의 날은 "11월 21일") |

### 다음 출발 (leak-check, 음성)

`car/leak-check`(home, `depart_at` 없음)와 음성 대화는 다음 출발의 제안을 쓴다. 오늘 제안이 아직
오지 않았으면 오늘, 아니면 기본 가정(지금 다음에 처음 오는 오전 8시)의 날의 제안이다. 그 날보다
뒤로는 넘어가지 않는다: 일요일 06:00에 주말 기록이 없으면 월요일 평일 제안이 있어도 쓰지 않고
오늘 오전 8시를 가정한다(가정한 출발이 하루 늦어지면 "지금 충전을 멈추라"는 말이 나올 수 있다).
제안을 계산할 수 없으면(기록 부족, 공휴일 정보 없음, DB 오류) 지금처럼 동작한다(오전 8시 가정,
기존 질문).

- leak-check는 `high`일 때만 오전 8시 대신 쓴다. 가정이라는 점과 PR #15 규칙(가정한 출발까지 못
  채우면 멈추라 하지 않음)은 같다.
- 음성은 `high`와 `low` 모두 쓴다(질문과 `usual_departure`).

## `POST /api/car/chargers/along-route` 경로 위 충전소 찾기 ("충전 실패 피하기")

장거리 이동 중 도착 예상 잔량이 모자라면, 경로 근처에서 지금 비어 있는 급속 충전기를 경로
순서대로 골라 경유지로 넣게 한다. 로그인·기기 토큰 없이 쓰는 공개 계산 API다(`GET /api/chargers`와
같음). 외부 API를 부르지 않고 충전소 캐시만 읽는다.

**경로는 근사다.** Pleos NaviHelper는 경로 전체 선형(polyline)을 주지 않는다. 그래서 서버는
`origin → route_points → destination`을 이은 꺾은선을 경로로 본다. 도로를 따라간 거리가 아니다.
NaviHelper의 경로 위 지점(`RoutePointInfo`)이나 경유지 좌표를 `route_points`로 보내면 근사가
도로에 가까워진다.

**`route_points`는 남은 지점만 보내면 된다.** 지나온 지점이 섞여 있어도 서버가 버린다.

1. `route_points + [destination]` 꺾은선에서 현재 위치와 가장 가까운 선분을 찾고(100m 안으로
   비슷하면 앞쪽 선분), 그 선분의 시작점까지를 지나온 것으로 보고 버린다. 현재 위치가 첫 경로
   지점보다 앞(아직 닿기 전)이면 그대로 둔다.
2. 바로 앞에 남긴 점과 50m 안인 점은 합친다(GPS 위치와 내비 지점의 어긋남). 목적지가 마지막
   경로 지점과 붙어 있으면 목적지를 남긴다.

`route_m`, 도로 비율, "뒤에 있는 충전소" 판정은 이렇게 정리한 남은 경로로 계산한다. 한계: 나중에
현재 위치 옆(100m 안)을 다시 지나는 경로는 좌표만으로 "지금 출발"과 "돌아오는 중"을 구분할 수
없어 돌아오는 중으로 본다.

### 요청 (JSON)

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `origin` | `{lat, lng}` | 필수 | 현재 위치. 위도 -85~85, 경도 -180~180 |
| `destination` | `{lat, lng}` | 필수 | 목적지 |
| `route_points` | `{lat, lng}[]` | | 경로 위 지점을 순서대로, 최대 50개 |
| `soc_now` | number | 필수 | 지금 잔량 %, 0~100 |
| `arrival_soc` | number | | 내비 도착 예상 잔량 % |
| `remain_distance_m` | number | | 내비 남은 거리 m (0 초과, 3,000km 이하) |
| `min_kw` | number | | 최소 출력 kW, 기본 50 |
| `corridor_m` | int | | 경로에서 벗어나도 되는 거리, 기본 3,000, 500~10,000 |
| `reserve_soc` | number | | 이 잔량 아래로 떨어지면 못 간다고 본다, 기본 15 |
| `efficiency_km_per_kwh` | number | | Vehicle SDK 충전 후 평균 전비(`getSinceChargeEvEfficiency`), 0 초과 20 이하 |
| `battery_capacity_wh` | number | | 배터리 용량 Wh, 1,000~1,000,000. 전비 추정에 쓴다 |

경로 길이(꺾은선)는 1,000km 이하이고, 이웃한 두 점의 경도 차가 180도를 넘으면(날짜변경선)
422다. 이웃한 두 점 사이 거리에는 상한이 없다. NaviHelper가 주는 경로 지점(`TripSummary.routePoints`)은
경유지와 목적지뿐이라, 경유지 없는 장거리가 이 기능의 기본 장면이다. 계산량은 점 합치기, 10km
조각 사각형, 후보 3,000행 상한으로 묶는다(아래 "계산").

**장거리 직선 근사의 한계.** 경유지 사이가 100km를 넘는 구간이 있으면 실제 도로가 직선에서 크게
벗어날 수 있어, 도로 옆 휴게소가 corridor 밖이라 빠질 수 있다. 이때 `assumptions`에 "경유지 사이가
먼 구간은 실제 도로가 직선에서 크게 벗어날 수 있어, 도로 옆 휴게소가 검색 범위 밖일 수 있어요."를
넣는다. corridor를 넓히면(최대 10km) 덜 빠진다.

### 계산

1. 선분을 10km 조각으로 나눠 조각마다 corridor만큼 넓힌 사각형으로 캐시에서 후보를 고른다
   (인덱스를 타는 범위 비교의 OR). 행은 경로 순서(처음 걸리는 조각 순)로 최대 3,000개만 읽는다.
   넘으면 앞쪽 구간만 보고 `coverage_note`에 "경로 근처 충전소가 많아 앞쪽 구간의 충전소만
   살펴봤어요."를 붙인다.
2. 각 충전소를 꺾은선에 투영해 `offset_m`(경로까지 최단 거리)과 `along_m`(출발부터 투영 지점까지
   꺾은선 거리)을 잰다. 선분마다 중간 위도에서 평면으로 펴서 투영하고, 길이는 하버사인이다.
   충전소가 선분의 corridor 사각형 밖이면 그 선분은 계산하지 않는다.
3. corridor 밖, 현재 위치보다 뒤(정리된 첫 선분의 시작점 뒤)에 있는 충전소는 뺀다. 목적지를
   조금 지난 충전소는 목적지까지의 거리로 offset을 잰다.
4. 지금 충전대기(상태 2)이면서 출력이 `min_kw` 이상인 충전기가 한 대 이상 있는 충전소만
   남긴다. **같은 충전기 한 대가 두 조건을 다 맞아야 한다**(`GET /api/chargers`와 같은 판정 코드).
5. `along_m` 순으로 최대 5곳.

### 잔량 추정

충전소까지의 거리 `distance_m` = `along_m` × 도로 비율 + `offset_m`. 도로 비율은
`remain_distance_m` / `route_m`이고, `remain_distance_m`가 없으면 도로 계수 1.25다(`assumptions`에
"내비 남은 거리가 없어 도로 거리를 직선거리의 1.25배(도로 계수)로 잡았어요."). 꺾은선은 도로보다
짧아서 늘린다(내비 값이 있으면 목적지에서 추정이 `arrival_soc`와 같아진다). 문장의 거리도 이
값이다.

소모율은 아래 순서로 정하고, 둘 다 안 되면 추정하지 않는다(`est_soc`, `reachable` null).

1. **내비**: `arrival_soc`와 `remain_distance_m`가 있으면 (`soc_now` − `arrival_soc`) /
   `remain_distance_m` (%/m). 도착 잔량이 더 높으면 0. 이번 경로의 고도·속도를 반영하므로 먼저 쓴다.
2. **전비**: 없으면 `efficiency_km_per_kwh`와 `battery_capacity_wh`로 100 / (전비 × 용량 Wh) %/m
   (1m에 1 / (전비 × 1000) kWh).

- `est_soc` = `soc_now` − 소모율 × `distance_m` (소수 첫째 자리, 0 아래는 0)
- `runs_out` = 0으로 자르기 전 추정 잔량 ≤ 0 (가는 동안 쓰는 양이 지금 잔량 이상). 이 충전소까지
  가기 전에 배터리가 바닥날 수 있다. 추정하지 않았으면 null
- 도착 잔량: `arrival_soc`가 있으면 그 값. 없고 전비로 추정했으면 `soc_now` − 소모율 ×
  (`route_m` × 도로 비율)로 추정해 `need_charge`에 쓰고, 문장 앞에 "전비로 추정하면"을 붙인다.
- `reachable` = `est_soc` ≥ `reserve_soc`

### 응답 200

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `need_charge` | bool \| null | 도착 잔량 < `reserve_soc`. 도착 잔량은 `arrival_soc`, 없으면 전비로 추정한 값. 둘 다 없으면 null |
| `chargers` | array | `{station_id, name, lat, lng, along_m, offset_m, distance_m, available_count, max_kw, est_soc, reachable, runs_out}`. `distance_m`은 위 "잔량 추정"의 도로 기준 거리, `name`은 공공 API 이름을 줄바꿈을 펴고 40자로 자른 것, `available_count`는 지금 충전대기이면서 `min_kw` 이상인 충전기 수, `max_kw`는 그 충전소 충전기 중 최고 출력 |
| `speech` | string | TTS 문장 |
| `actions` | array | 추천이 있고 `need_charge`가 false가 아니면 `[{"type": "add_waypoint", station_id, name, lat, lng}]`. 추천 충전소가 `runs_out`이면 경유지 대신 `[{"type": "ask", "question": "더 가까운 충전소를 찾아볼까요?"}]`. 충전이 필요 없다고 말할 때는 빈 배열 |
| `assumptions` | string[] | 직선 근사, 상태는 최근 수집 기준, (100km 넘는 구간이 있으면) 장거리 직선 근사 한계, (추정했으면) 내비 또는 전비 기준 거리 비례 추정 |
| `coverage_note` | string \| null | 경로 근처에 충전소가 하나도 없으면 "이 구간은 충전소 정보가 없을 수 있어요(수집 지역 밖).", 있지만 조건에 맞는 곳이 없으면 "경로 근처 충전소 N곳 중 지금 비어 있는 50kW 이상 충전기가 없어요.", 후보 행 상한에 걸리면 뒤에 "경로 근처 충전소가 많아 앞쪽 구간의 충전소만 살펴봤어요." |
| `route_m` | int | 정리된 남은 꺾은선 길이 m |

추천(동작과 문장): 목록(경로 순서)은 그대로 두고, `reachable`이 false가 아닌 첫 충전소 → 없으면
`runs_out`이 아닌 첫 충전소 → 없으면 첫 충전소.

`speech` (`min_kw` 50 이상이면 "급속충전기", 아니면 "충전기"; 거리는 `distance_m`. `offset_m`이
500m 이상이면 "약 N킬로미터 앞, 경로에서 약 M킬로미터 벗어난 ○○"):

- 충전 필요: "이대로면 도착할 때 배터리가 8%예요. 약 42.3킬로미터 앞 ○○휴게소에 비어 있는
  급속충전기가 2대 있어요. 경유지로 넣을까요?" 추천이 `reachable: false`면 "가는 동안 배터리가
  12.5%까지 내려갈 수 있어요."를 질문 앞에 붙인다. 추천이 `runs_out`이면 "… 있어요. 이 충전소까지
  가기 전에 배터리가 바닥날 수 있어요. 더 가까운 충전소를 찾아볼까요?"로 끝낸다("0%까지"라고 하지
  않는다).
- 충전 불필요: "도착할 때 배터리가 35% 남아요. 충전 없이 가셔도 돼요." (`chargers`는 그대로 주고,
  `actions`는 비운다)
- 도착 잔량을 전비로 추정했으면: "전비로 추정하면 도착할 때 배터리가 42%예요. …" /
  "전비로 추정하면 도착할 때 배터리가 42% 남아요. 충전 없이 가셔도 돼요." 추정 잔량이 0 이하이면
  "전비로 추정하면 목적지에 닿기 전에 배터리가 바닥날 수 있어요. …"
- 잔량을 모름: "약 42.3킬로미터 앞 ○○휴게소에 비어 있는 급속충전기가 2대 있어요. 경유지로 넣을까요?"
- 추천 없음: "(충전 필요면 첫 문장) 경로 근처에 지금 비어 있는 급속충전기를 찾지 못했어요."

### 오류

| 상태 | 언제 | 본문 |
| --- | --- | --- |
| 422 | 범위 밖 값, `NaN`·`Infinity`, `route_points` 51개 이상, corridor 범위 밖, 1,000km 초과, 날짜변경선 | FastAPI 기본 `detail` 배열 |
| 503 | 충전소 캐시가 비어 있음(수집 전) | `{"detail": "충전소 정보를 아직 수집하지 않았습니다. 잠시 후 다시 시도해 주세요."}` |

## `GET /api/chargers` 빈 충전기만 찾기 ("충전 실패 피하기")

차량 앱은 주변 충전소에 웹과 같은 `GET /api/chargers`를 쓴다. 공공 API를 부르지 않고
수집기가 채운 공유 캐시만 읽는다. 장거리 이동 중 급속충전이 필요할 때는 아래 선택 쿼리로
최근 수집 기준으로 충전대기인 충전기가 있는 충전소만 받는다. 상태는 실시간이 아니다 —
수집 cron이 5분마다 최근 10분 변경분을 반영하므로 정상일 때도 5~10분 전 상태이고,
수집이 멈추면 더 오래된 상태일 수 있다.

| 쿼리 | 타입 | 기본 | 규칙 |
| --- | --- | --- | --- |
| `lat`, `lng` | number | 필수 | 위도 -90~90, 경도 -180~180. 조회에만 쓰고 저장하지 않는다 |
| `radius_m` | int | 2000 | 1~20000 |
| `charger_type` | string | | 공공 API `chgerType` 원문 코드. 최대 32자 |
| `available_only` | bool | false | true면 상태 코드 `2`(충전대기)인 충전기가 있는 충전소만 |
| `min_kw` | number | | 0 초과 1000 이하. NaN, Infinity는 422. 출력이 이 값 이상인 충전기가 있는 충전소만 |

- 세 조건(`charger_type`, `available_only`, `min_kw`)을 여러 개 주면 **같은 충전기 한 대가**
  모두 맞아야 한다. 예: `available_only=true&min_kw=50`은 "50kW 이상이면서 충전대기인
  충전기가 한 대 이상"인 충전소다. 빈 7kW와 충전 중인 100kW만 있는 충전소는 빠진다.
- 조건을 하나도 주지 않으면(`available_only=false`, `min_kw` 생략) 응답은 예전과 같다.
  충전기가 0대인 충전소도 그대로 나온다.
- 거르는 단위는 충전소다. 남긴 충전소의 `chargers`에는 조건에 안 맞는 충전기도 전부
  들어 있다. 상태·종류 코드는 원문 그대로다 (`2`만 "사용 가능").
- 캐시의 출력 값이 숫자가 아니면 `min_kw` 조건을 못 맞춘 것으로 본다.
- 정렬은 가까운 순서다.

예: 현재 위치 반경 10km에서 50kW 이상 빈 충전기가 있는 충전소

```
GET /api/chargers?lat=35.0175&lng=126.7905&radius_m=10000&available_only=true&min_kw=50
```

| 상태 | 언제 |
| --- | --- |
| 200 `[]` | 캐시는 있는데 조건에 맞는 충전소가 없음 |
| 422 | 쿼리 범위·타입 오류 (FastAPI 검증 오류 `{"detail": [...]}`) |
| 501 | 서버에 `CHARGER_API_KEY`가 없음 |
| 503 | 캐시를 아직 수집하지 않음 |

응답 필드는 `StationOut` 그대로다 (`station_id`, `name`, `address`, `lat`, `lng`,
`distance_m`, `operator`, `available_hours`, `is_favorite`(게스트는 null), `chargers[]`:
`charger_id`, `type`, `capacity_kw`, `status`, `status_updated_at`).
