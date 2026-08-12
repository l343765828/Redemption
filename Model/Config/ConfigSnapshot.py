from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


class SnapshotManifestSource(Protocol):
    period_num: int | str | None
    calc_month: int | None
    source: str
    source_version: str
    loaded_at: str
    raw_row_count: int
    raw_rows_checksum: str
    requirements_version: str
    canonical_values: tuple[tuple[str, str, str], ...]
    canonical_checksum: str
    snapshot_id: str


@dataclass(frozen=True, slots=True)
class ConfigSnapshotManifest:
    """配置快照的可序列化审计模型；不包含密钥或外部连接信息。"""

    period_num: int | str | None
    calc_month: int | None
    source: str
    source_version: str
    loaded_at: str
    raw_row_count: int
    raw_rows_checksum: str
    requirements_version: str
    canonical_values: tuple[tuple[str, str, str], ...]
    canonical_checksum: str
    snapshot_id: str

    @classmethod
    def from_snapshot(cls, snapshot: SnapshotManifestSource) -> "ConfigSnapshotManifest":
        return cls(
            period_num=snapshot.period_num,
            calc_month=snapshot.calc_month,
            source=snapshot.source,
            source_version=snapshot.source_version,
            loaded_at=snapshot.loaded_at,
            raw_row_count=snapshot.raw_row_count,
            raw_rows_checksum=snapshot.raw_rows_checksum,
            requirements_version=snapshot.requirements_version,
            canonical_values=tuple(snapshot.canonical_values),
            canonical_checksum=snapshot.canonical_checksum,
            snapshot_id=snapshot.snapshot_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "period_num": self.period_num,
            "calc_month": self.calc_month,
            "source": self.source,
            "source_version": self.source_version,
            "loaded_at": self.loaded_at,
            "raw_row_count": self.raw_row_count,
            "raw_rows_checksum": self.raw_rows_checksum,
            "requirements_version": self.requirements_version,
            "canonical_values": [list(value) for value in self.canonical_values],
            "canonical_checksum": self.canonical_checksum,
            "snapshot_id": self.snapshot_id,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ConfigSnapshotManifest":
        return cls(
            period_num=value.get("period_num"),
            calc_month=value.get("calc_month"),
            source=str(value["source"]),
            source_version=str(value["source_version"]),
            loaded_at=str(value["loaded_at"]),
            raw_row_count=int(value["raw_row_count"]),
            raw_rows_checksum=str(value["raw_rows_checksum"]),
            requirements_version=str(value["requirements_version"]),
            canonical_values=tuple(tuple(item) for item in value["canonical_values"]),
            canonical_checksum=str(value["canonical_checksum"]),
            snapshot_id=str(value["snapshot_id"]),
        )
