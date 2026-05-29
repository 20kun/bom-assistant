"""BOM validation agent — auto-check data consistency, material standards, duplicates."""

from dataclasses import dataclass, field

from .agent import BOMItem, BOMExtractionResult


# ── Standard material database (subset) ──

STANDARD_MATERIALS = {
    "45#", "Q235A", "Q235B", "Q345B", "Q345D",
    "HT150", "HT200", "HT250", "HT300",
    "QT400-18", "QT450-10", "QT500-7", "QT600-3",
    "40Cr", "45Cr", "20CrMnTi", "20CrMo", "35CrMo", "42CrMo",
    "GCr15", "GCr9",
    "Cr12", "Cr12MoV", "CrWMn", "9SiCr",
    "4Cr5MoSiV1", "3Cr2Mo", "3Cr2NiMo",
    "65Mn", "60Si2Mn", "50CrVA",
    "06Cr19Ni10", "06Cr18Ni11Ti", "022Cr17Ni12Mo2",
    "1Cr13", "2Cr13", "3Cr13", "4Cr13",
    "6061-T6", "6063-T5", "7075-T6", "5052-H32",
    "T2", "H62", "HPb59-1",
    "8.8级", "10.9级", "12.9级",
    "丁腈橡胶", "氟橡胶", "硅橡胶", "聚氨酯",
    "石棉橡胶", "PTFE", "尼龙66", "POM",
}

MATERIAL_CATEGORIES = {
    "碳钢": ["45#", "Q235A", "Q235B", "Q345B", "Q345D"],
    "铸铁": ["HT150", "HT200", "HT250", "HT300", "QT400-18", "QT450-10", "QT500-7", "QT600-3"],
    "合金钢": ["40Cr", "45Cr", "20CrMnTi", "20CrMo", "35CrMo", "42CrMo"],
    "不锈钢": ["06Cr19Ni10", "06Cr18Ni11Ti", "022Cr17Ni12Mo2", "1Cr13", "2Cr13", "3Cr13", "4Cr13"],
    "铝合金": ["6061-T6", "6063-T5", "7075-T6", "5052-H32"],
    "铜合金": ["T2", "H62", "HPb59-1"],
}


@dataclass
class ValidationIssue:
    """Single validation issue."""
    level: str  # "error", "warning", "info"
    item_no: int
    field: str
    message: str
    suggestion: str = ""


@dataclass
class ValidationResult:
    """Full validation result."""
    issues: list[ValidationIssue] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    score: float = 100.0  # 0-100 data quality score

    @property
    def status(self) -> str:
        if self.error_count > 0:
            return "有错误"
        if self.warning_count > 0:
            return "有警告"
        return "通过"


def validate_bom(items: list[BOMItem]) -> ValidationResult:
    """Run all validation checks on BOM items."""
    result = ValidationResult()
    _check_empty_fields(items, result)
    _check_weight_consistency(items, result)
    _check_material_standards(items, result)
    _check_duplicates(items, result)
    _check_qty_validity(items, result)
    _check_part_no_format(items, result)

    result.error_count = sum(1 for i in result.issues if i.level == "error")
    result.warning_count = sum(1 for i in result.issues if i.level == "warning")

    # Score: start at 100, -5 per warning, -10 per error
    result.score = max(0, 100 - result.error_count * 10 - result.warning_count * 5)
    return result


def _check_empty_fields(items: list[BOMItem], result: ValidationResult):
    """Check for missing critical fields."""
    for item in items:
        if not item.part_name or item.part_name.strip() == "":
            result.issues.append(ValidationIssue(
                level="error", item_no=item.item_no, field="part_name",
                message=f"第{item.item_no}项: 零件名称为空",
                suggestion="请补充零件名称",
            ))
        if not item.part_no or item.part_no.strip() == "":
            result.issues.append(ValidationIssue(
                level="warning", item_no=item.item_no, field="part_no",
                message=f"第{item.item_no}项: 图号/零件号为空",
                suggestion="建议补充图号以便追溯",
            ))
        if not item.material or item.material.strip() == "":
            result.issues.append(ValidationIssue(
                level="warning", item_no=item.item_no, field="material",
                message=f"第{item.item_no}项({item.part_name}): 材料为空",
                suggestion="建议标注材料牌号",
            ))


def _check_weight_consistency(items: list[BOMItem], result: ValidationResult):
    """Check total_weight = weight × qty."""
    for item in items:
        if item.weight > 0 and item.qty > 0 and item.total_weight > 0:
            expected = round(item.weight * item.qty, 3)
            actual = round(item.total_weight, 3)
            diff = abs(expected - actual)
            if diff > 0.01 and diff / max(expected, 0.001) > 0.01:
                result.issues.append(ValidationIssue(
                    level="error", item_no=item.item_no, field="total_weight",
                    message=f"第{item.item_no}项({item.part_name}): "
                            f"总重({actual}kg) ≠ 单重({item.weight}kg) × 数量({item.qty}) = {expected}kg",
                    suggestion=f"应为 {expected}kg，差值 {diff:.3f}kg",
                ))


def _check_material_standards(items: list[BOMItem], result: ValidationResult):
    """Check if materials are in standard database."""
    for item in items:
        if not item.material or item.material.strip() == "":
            continue
        mat = item.material.strip()
        if mat not in STANDARD_MATERIALS:
            # Check if it's a partial match or alias
            matched = False
            for std in STANDARD_MATERIALS:
                if std.lower() == mat.lower():
                    matched = True
                    break
            if not matched:
                result.issues.append(ValidationIssue(
                    level="warning", item_no=item.item_no, field="material",
                    message=f"第{item.item_no}项({item.part_name}): 材料 '{mat}' 不在标准牌号库中",
                    suggestion="请确认材料牌号是否正确，或补充到标准库",
                ))


def _check_duplicates(items: list[BOMItem], result: ValidationResult):
    """Check for duplicate part numbers."""
    seen = {}
    for item in items:
        if not item.part_no or item.part_no.strip() == "":
            continue
        pn = item.part_no.strip()
        if pn in seen:
            result.issues.append(ValidationIssue(
                level="error", item_no=item.item_no, field="part_no",
                message=f"第{item.item_no}项: 图号 '{pn}' 与第{seen[pn]}项重复",
                suggestion="检查是否为同一零件重复录入，或需加后缀区分版本",
            ))
        else:
            seen[pn] = item.item_no


def _check_qty_validity(items: list[BOMItem], result: ValidationResult):
    """Check quantity is positive."""
    for item in items:
        if item.qty <= 0:
            result.issues.append(ValidationIssue(
                level="error", item_no=item.item_no, field="qty",
                message=f"第{item.item_no}项({item.part_name}): 数量为 {item.qty}，应大于0",
                suggestion="请修正数量",
            ))
        if item.qty != int(item.qty) and item.unit == "件":
            result.issues.append(ValidationIssue(
                level="info", item_no=item.item_no, field="qty",
                message=f"第{item.item_no}项({item.part_name}): 数量 {item.qty} 不是整数，但单位为'件'",
                suggestion="确认数量是否正确",
            ))


def _check_part_no_format(items: list[BOMItem], result: ValidationResult):
    """Check part number format consistency."""
    formats = {"dash": 0, "dot": 0, "slash": 0, "plain": 0}
    for item in items:
        pn = item.part_no.strip()
        if not pn or pn.startswith("GB"):
            continue
        if "-" in pn:
            formats["dash"] += 1
        elif "." in pn:
            formats["dot"] += 1
        elif "/" in pn:
            formats["slash"] += 1
        else:
            formats["plain"] += 1

    dominant = max(formats, key=formats.get)
    if dominant == "plain":
        return

    inconsistent = []
    for item in items:
        pn = item.part_no.strip()
        if not pn or pn.startswith("GB"):
            continue
        if dominant == "dash" and "-" not in pn:
            inconsistent.append(item)
        elif dominant == "dot" and "." not in pn:
            inconsistent.append(item)
        elif dominant == "slash" and "/" not in pn:
            inconsistent.append(item)

    for item in inconsistent[:5]:  # Limit to first 5
        result.issues.append(ValidationIssue(
            level="info", item_no=item.item_no, field="part_no",
            message=f"第{item.item_no}项: 图号 '{item.part_no}' 格式与其他项不一致",
            suggestion=f"多数图号使用 {'-' if dominant == 'dash' else '.' if dominant == 'dot' else '/'} 分隔",
        ))


def get_validation_summary(result: ValidationResult) -> dict:
    """Get validation summary for display/export."""
    return {
        "status": result.status,
        "score": result.score,
        "error_count": result.error_count,
        "warning_count": result.warning_count,
        "issues": [
            {
                "level": i.level,
                "item_no": i.item_no,
                "field": i.field,
                "message": i.message,
                "suggestion": i.suggestion,
            }
            for i in result.issues
        ],
    }
