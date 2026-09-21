from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from .errors import TariffConfigError, TariffNotConfiguredError

Status = Literal["verified", "derived", "unverified"]
VALID_STATUSES: frozenset[str] = frozenset({"verified", "derived", "unverified"})


@dataclass(frozen=True)
class TariffValue:
    """요금 항목 하나. 값만이 아니라 출처와 확인 상태를 함께 들고 다닌다."""

    value: Any
    source: str
    status: Status


@dataclass(frozen=True)
class Tariff:
    version: str
    items: dict[str, TariffValue]

    @classmethod
    def load(cls, path: Path) -> Tariff:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise TariffConfigError(f"요금 설정 파일이 없습니다: {path}") from exc

        if not isinstance(raw, dict):
            raise TariffConfigError(f"요금 설정 파일의 최상위가 매핑이 아닙니다: {path}")

        version = raw.get("version")
        if not isinstance(version, str):
            raise TariffConfigError("요금 설정에 문자열 'version'이 필요합니다.")

        items: dict[str, TariffValue] = {}
        _collect(raw, prefix="", items=items)
        return cls(version=version, items=items)

    def unverified_items(self) -> list[str]:
        """공식 확인이 끝나지 않은 항목의 점 경로.

        목록을 코드에 박아두지 않고 설정을 훑어 만든다. 요금표를 확인할 때
        고칠 곳이 YAML 한 군데뿐이어야 두 목록이 어긋나지 않는다.
        """
        return sorted(
            path for path, item in self.items.items() if item.status != "verified"
        )

    def get(self, path: str) -> Any:
        item = self.items.get(path)
        if item is None or item.value is None:
            raise TariffNotConfiguredError(f"요금 설정에 '{path}' 값이 없습니다.")
        return item.value

    def get_optional(self, path: str) -> Any | None:
        item = self.items.get(path)
        return None if item is None else item.value


def _collect(node: Any, prefix: str, items: dict[str, TariffValue]) -> None:
    """'status' 키를 가진 매핑을 요금 항목으로, 나머지 매핑은 컨테이너로 본다."""
    if not isinstance(node, dict):
        return

    if "status" in node:
        status = node["status"]
        if status not in VALID_STATUSES:
            raise TariffConfigError(
                f"'{prefix}'의 status가 올바르지 않습니다: {status!r} "
                f"(허용: {', '.join(sorted(VALID_STATUSES))})"
            )
        items[prefix] = TariffValue(
            value=node.get("value"),
            source=str(node.get("source", "")),
            status=status,
        )
        return

    for key, child in node.items():
        if key == "version":
            continue
        _collect(child, f"{prefix}.{key}" if prefix else str(key), items)
