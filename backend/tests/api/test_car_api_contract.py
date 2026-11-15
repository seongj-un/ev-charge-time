"""차량 앱 API 계약 스냅숏 (BE-12).

`/api/car/*`와 `/api/chargers*`의 OpenAPI에서 경로, 쿼리, 요청·응답 필드(타입, 필수 여부,
Literal 값, 범위·길이·개수 제약, 기본값)를 펴서 `snapshots/car_api_contract.json`과 비교한다.
앱(Kotlin)은 이 모양에 맞춰 만들어지므로, 바뀌면 이 테스트가 실패해 의도한 변경인지 확인하게 한다.

의도한 변경이면 스냅숏을 다시 만든다(그리고 PR 본문과 docs/car-api.md에 적는다):

    UPDATE_CAR_API_SNAPSHOT=1 uv run pytest tests/api/test_car_api_contract.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from evcharge.main import create_app

SNAPSHOT = Path(__file__).parent / "snapshots" / "car_api_contract.json"
PREFIXES = ("/api/car/", "/api/chargers")


def contract() -> dict[str, Any]:
    spec = create_app().openapi()
    components = spec.get("components", {}).get("schemas", {})
    result: dict[str, Any] = {}
    for path, operations in sorted(spec["paths"].items()):
        if not path.startswith(PREFIXES):
            continue
        for method, operation in sorted(operations.items()):
            entry: dict[str, Any] = {}
            params = {
                f"{param['in']}:{param['name']}": _leaf(
                    _resolve(param.get("schema", {}), components),
                    components,
                    required=param.get("required", False),
                )
                for param in operation.get("parameters", [])
            }
            if params:
                entry["parameters"] = params
            body = operation.get("requestBody", {}).get("content", {}).get("application/json")
            if body:
                fields: dict[str, str] = {}
                _flatten(body["schema"], "", fields, components, required=True)
                entry["request"] = fields
            responses: dict[str, Any] = {}
            for status, response in sorted(operation.get("responses", {}).items()):
                schema = response.get("content", {}).get("application/json", {}).get("schema")
                if status.startswith("2") and schema:
                    fields = {}
                    _flatten(schema, "", fields, components, required=True)
                    responses[status] = fields
                else:
                    responses[status] = "error"
            entry["responses"] = responses
            result[f"{method.upper()} {path}"] = entry
    return result


def _resolve(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        schema = components[schema["$ref"].rsplit("/", 1)[-1]]
    return schema


def _variants(schema: dict[str, Any]) -> list[dict[str, Any]] | None:
    return schema.get("anyOf") or schema.get("oneOf")


def _flatten(
    schema: dict[str, Any],
    prefix: str,
    out: dict[str, str],
    components: dict[str, Any],
    *,
    required: bool,
    nullable: bool = False,
    depth: int = 0,
) -> None:
    assert depth < 12, f"너무 깊은 스키마: {prefix}"
    schema = _resolve(schema, components)
    variants = _variants(schema)
    if variants:
        real = [_resolve(v, components) for v in variants if v.get("type") != "null"]
        nullable = nullable or len(real) < len(variants)
        if len(real) == 1 and "default" in schema and "default" not in real[0]:
            real = [{**real[0], "default": schema["default"]}]
        if len(real) == 1:
            _flatten(
                real[0],
                prefix,
                out,
                components,
                required=required,
                nullable=nullable,
                depth=depth + 1,
            )
            return
        if all(v.get("type") == "object" or "properties" in v for v in real):
            # 동작(actions)처럼 종류가 여럿인 객체: 종류마다 펼친다.
            out[prefix or "."] = _mark("oneOf", required, nullable)
            for variant in real:
                tag = _tag(variant)
                _flatten(
                    variant, f"{prefix}<{tag}>", out, components, required=True, depth=depth + 1
                )
            return
        out[prefix or "."] = _mark(
            " | ".join(_leaf(v, components, required=True) for v in real), required, nullable
        )
        return
    if schema.get("type") == "object" or "properties" in schema:
        if prefix:
            out[prefix] = _mark("object", required, nullable)
        needed = set(schema.get("required", []))
        for name, child in schema.get("properties", {}).items():
            key = f"{prefix}.{name}" if prefix else name
            _flatten(child, key, out, components, required=name in needed, depth=depth + 1)
        return
    if schema.get("type") == "array":
        out[prefix or "."] = _mark("array" + _limits(schema), required, nullable)
        _flatten(
            schema.get("items", {}), f"{prefix}[]", out, components, required=True, depth=depth + 1
        )
        return
    out[prefix or "."] = _mark(_leaf(schema, components, required=True), required, nullable)


def _tag(variant: dict[str, Any]) -> str:
    kind = variant.get("properties", {}).get("type", {})
    if "const" in kind:
        return str(kind["const"])
    if kind.get("enum"):
        return str(kind["enum"][0])
    return variant.get("title", "object")


def _leaf(schema: dict[str, Any], components: dict[str, Any], *, required: bool) -> str:
    schema = _resolve(schema, components)
    variants = _variants(schema)
    if variants:
        real = [_resolve(v, components) for v in variants if v.get("type") != "null"]
        text = " | ".join(_leaf(v, components, required=True) for v in real)
        return _mark(text, required, len(real) < len(variants))
    text = schema.get("type", "any")
    if schema.get("format"):
        text += f"({schema['format']})"
    if "const" in schema:
        text += f"={json.dumps(schema['const'], ensure_ascii=False)}"
    if "enum" in schema:
        text += "∈" + json.dumps(schema["enum"], ensure_ascii=False)
    return _mark(text + _limits(schema), required, False)


# 앱이 맞춰야 하는 범위·길이·개수 제약과 기본값. 바뀌면 같은 값을 보내도 422가 나거나(좁아짐)
# 생략했을 때 뜻이 달라진다(기본값).
LIMIT_KEYS = (
    "minimum",
    "exclusiveMinimum",
    "maximum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
    "default",
)


def _limits(schema: dict[str, Any]) -> str:
    parts = [
        f"{key}={json.dumps(schema[key], ensure_ascii=False)}"
        for key in LIMIT_KEYS
        if key in schema
    ]
    return f" [{', '.join(parts)}]" if parts else ""


def _mark(text: str, required: bool, nullable: bool) -> str:
    return text + ("" if required else " (optional)") + (" | null" if nullable else "")


def _diff(old: dict[str, Any], new: dict[str, Any], prefix: str = "") -> list[str]:
    lines = []
    for key in sorted(set(old) | set(new)):
        where = f"{prefix}{key}"
        if key not in new:
            lines.append(f"- 사라짐: {where}")
        elif key not in old:
            lines.append(f"+ 생김: {where}")
        elif isinstance(old[key], dict) and isinstance(new[key], dict):
            lines += _diff(old[key], new[key], f"{where} / ")
        elif old[key] != new[key]:
            lines.append(f"~ 바뀜: {where}: {old[key]!r} → {new[key]!r}")
    return lines


def test_car_api_contract_matches_the_snapshot():
    current = contract()
    if os.environ.get("UPDATE_CAR_API_SNAPSHOT") == "1":
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(
            json.dumps(current, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    saved = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    changes = _diff(saved, current)
    assert not changes, (
        "차량 앱 API 계약이 스냅숏과 다릅니다. 의도한 변경이면 "
        "UPDATE_CAR_API_SNAPSHOT=1로 다시 만들고 PR과 docs/car-api.md에 적으세요.\n"
        + "\n".join(changes)
    )


def test_snapshot_covers_every_car_and_charger_path():
    paths = {key.split(" ", 1)[1] for key in contract()}
    assert "/api/car/voice" in paths
    assert "/api/chargers" in paths
    assert "/api/chargers/freshness" in paths
    assert all(path.startswith(PREFIXES) for path in paths)


def test_the_diff_names_what_changed():
    old = {"POST /api/car/plan": {"request": {"soc_now": "number", "gone": "string"}}}
    new = {"POST /api/car/plan": {"request": {"soc_now": "integer", "added": "string"}}}

    assert _diff(old, new) == [
        "+ 생김: POST /api/car/plan / request / added",
        "- 사라짐: POST /api/car/plan / request / gone",
        "~ 바뀜: POST /api/car/plan / request / soc_now: 'number' → 'integer'",
    ]


def test_limits_and_defaults_are_part_of_the_contract():
    contract_now = contract()
    voice = contract_now["POST /api/car/voice"]["request"]
    assert "maxItems=6" in voice["history"]
    plan = contract_now["POST /api/car/plan"]["request"]
    assert plan["soc_now"] == "number [minimum=0.0, exclusiveMaximum=100.0]"
    assert "default=80" in plan["soc_target"]
