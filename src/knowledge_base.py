"""Historical parts knowledge base — stores and retrieves previously seen BOM items."""

import json
import os
from dataclasses import dataclass, field
from typing import Any

from .agent import BOMItem, MATERIAL_NORMALIZE, SOURCE_NORMALIZE


DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "parts_db.json")


@dataclass
class PartRecord:
    """A historical part record in the knowledge base."""
    part_no: str = ""
    part_name: str = ""
    material: str = ""
    spec: str = ""
    source: str = ""
    weight: float = 0.0
    unit: str = "件"
    remark: str = ""
    project: str = ""
    usage_count: int = 1
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "part_no": self.part_no,
            "part_name": self.part_name,
            "material": self.material,
            "spec": self.spec,
            "source": self.source,
            "weight": self.weight,
            "unit": self.unit,
            "remark": self.remark,
            "project": self.project,
            "usage_count": self.usage_count,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PartRecord":
        return cls(
            part_no=d.get("part_no", ""),
            part_name=d.get("part_name", ""),
            material=d.get("material", ""),
            spec=d.get("spec", ""),
            source=d.get("source", ""),
            weight=d.get("weight", 0.0),
            unit=d.get("unit", "件"),
            remark=d.get("remark", ""),
            project=d.get("project", ""),
            usage_count=d.get("usage_count", 1),
            tags=d.get("tags", []),
        )

    @classmethod
    def from_bom_item(cls, item: BOMItem, project: str = "") -> "PartRecord":
        return cls(
            part_no=item.part_no,
            part_name=item.part_name,
            material=item.material,
            spec=item.spec,
            source=item.source,
            weight=item.weight,
            unit=item.unit,
            remark=item.remark,
            project=project,
        )


class PartsKnowledgeBase:
    """Simple JSON-backed knowledge base for historical parts."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.parts: list[PartRecord] = []
        self._load()

    def _load(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.parts = [PartRecord.from_dict(d) for d in data]
            except (json.JSONDecodeError, IOError):
                self.parts = []

    def save(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump([p.to_dict() for p in self.parts], f, ensure_ascii=False, indent=2)

    def add_parts(self, items: list[BOMItem], project: str = ""):
        """Add BOM items to the knowledge base. Deduplicates by part_no."""
        existing = {p.part_no: i for i, p in enumerate(self.parts)}
        for item in items:
            if not item.part_no and not item.part_name:
                continue
            key = item.part_no.strip()
            if key and key in existing:
                self.parts[existing[key]].usage_count += 1
            else:
                rec = PartRecord.from_bom_item(item, project)
                self.parts.append(rec)
                if key:
                    existing[key] = len(self.parts) - 1
        self.save()

    def search_by_name(self, name: str, top_k: int = 5) -> list[tuple[PartRecord, float]]:
        """Search parts by name similarity (simple substring + edit distance)."""
        if not name:
            return []
        name_lower = name.lower()
        scored = []
        for p in self.parts:
            pname = p.part_name.lower()
            if name_lower == pname:
                scored.append((p, 1.0))
            elif name_lower in pname or pname in name_lower:
                scored.append((p, 0.8))
            else:
                # Character overlap ratio
                common = set(name_lower) & set(pname)
                total = set(name_lower) | set(pname)
                if total:
                    ratio = len(common) / len(total)
                    if ratio > 0.4:
                        scored.append((p, ratio))
        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]

    def search_by_material_and_spec(self, material: str = "", spec: str = "", top_k: int = 5) -> list[tuple[PartRecord, float]]:
        """Search parts by material and spec similarity."""
        if not material and not spec:
            return []
        mat_lower = material.lower().strip()
        spec_lower = spec.lower().strip()
        scored = []
        for p in self.parts:
            score = 0.0
            pmat = p.material.lower().strip()
            pspec = p.spec.lower().strip()
            if mat_lower and pmat:
                if mat_lower == pmat:
                    score += 0.5
                elif mat_lower in pmat or pmat in mat_lower:
                    score += 0.3
            if spec_lower and pspec:
                if spec_lower == pspec:
                    score += 0.5
                elif spec_lower in pspec or pspec in spec_lower:
                    score += 0.3
                else:
                    # Extract numeric values and compare
                    import re
                    nums_q = set(re.findall(r"[\d.]+", spec_lower))
                    nums_p = set(re.findall(r"[\d.]+", pspec))
                    if nums_q & nums_p:
                        score += 0.2
            if score > 0.2:
                scored.append((p, min(score, 1.0)))
        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]

    def get_all(self) -> list[PartRecord]:
        return list(self.parts)

    def count(self) -> int:
        return len(self.parts)

    def clear(self):
        self.parts = []
        self.save()
