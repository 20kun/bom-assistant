"""BOM extraction agent — multi-LLM pipeline for intelligent BOM parsing."""

import base64
import io
import json
import logging
import re
import time
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable

import pandas as pd
from openai import OpenAI
from PIL import Image

from .preprocess import preprocess_image

logger = logging.getLogger(__name__)

# ── Retry decorator ──


def retry_on_error(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff: float = 2.0,
) -> Callable:
    """Exponential backoff retry on API errors."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_error = None
            delay = base_delay
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries:
                        wait = min(delay * (backoff ** attempt), max_delay)
                        logger.warning(f"API call failed (attempt {attempt+1}/{max_retries+1}): {e}. Retrying in {wait:.1f}s...")
                        time.sleep(wait)
            raise last_error  # type: ignore[misc]
        return wrapper
    return decorator


BOM_COLUMNS = [
    "item_no",      # 序号
    "part_no",      # 图号/零件号
    "part_name",    # 名称
    "material",     # 材料
    "spec",         # 规格
    "qty",          # 数量
    "unit",         # 单位
    "remark",       # 备注
    "weight",       # 单重
    "total_weight", # 总重
    "source",       # 来源（自制/外购/标准件）
]

MATERIAL_NORMALIZE = {
    "45钢": "45#", "45号钢": "45#", "45#钢": "45#", "C45": "45#",
    "q235": "Q235A", "q235a": "Q235A", "Q235": "Q235A",
    "6061": "6061-T6", "6061铝": "6061-T6", "6061铝合金": "6061-T6",
    "304": "06Cr19Ni10", "304不锈钢": "06Cr19Ni10", "sus304": "06Cr19Ni10",
    "ht200": "HT200", "HT20-40": "HT200",
    "45": "45#",
    "40cr": "40Cr", "40铬": "40Cr",
    "20crmnti": "20CrMnTi",
    "gcr15": "GCr15",
    "cr12": "Cr12",
    "cr12mov": "Cr12MoV",
    "h13": "4Cr5MoSiV1",
    "p20": "3Cr2Mo",
    "718h": "3Cr2NiMo",
}

SOURCE_NORMALIZE = {
    "自制": "自制件", "加工": "自制件", "机加工": "自制件",
    "外购": "外购件", "采购": "外购件", "购买": "外购件",
    "标准": "标准件", "标准件": "标准件", "国标": "标准件",
    "外协": "外协件", "外加工": "外协件",
    "焊接": "焊接件", "焊": "焊接件",
    "铸件": "铸造件", "铸造": "铸造件",
}


@dataclass
class BOMItem:
    """Single BOM line item."""
    item_no: int = 0
    part_no: str = ""
    part_name: str = ""
    material: str = ""
    spec: str = ""
    qty: float = 1.0
    unit: str = "件"
    remark: str = ""
    weight: float = 0.0
    total_weight: float = 0.0
    source: str = ""

    def to_dict(self) -> dict:
        return {
            "item_no": self.item_no,
            "part_no": self.part_no,
            "part_name": self.part_name,
            "material": self.material,
            "spec": self.spec,
            "qty": self.qty,
            "unit": self.unit,
            "remark": self.remark,
            "weight": self.weight,
            "total_weight": self.total_weight,
            "source": self.source,
        }


@dataclass
class BOMExtractionResult:
    """Full BOM extraction result."""
    items: list[BOMItem] = field(default_factory=list)
    raw_text: str = ""
    table_headers: list[str] = field(default_factory=list)
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def total_qty(self) -> int:
        return len(self.items)

    def to_records(self) -> list[dict]:
        return [item.to_dict() for item in self.items]


# ── Vision Prompt (image-based BOM) ──

VISION_BOM_PROMPT = """你是机械制造业的BOM（物料清单）专家。请仔细分析这张图纸/图片中的BOM表、物料清单或零件明细表。

识别所有零件行，提取以下信息并以JSON数组返回：
- item_no: 序号（整数）
- part_no: 图号/零件号/代号
- part_name: 零件名称
- material: 材料（如45#、Q235A、HT200、6061-T6等，保留原始标注）
- spec: 规格尺寸（如φ50×120、20×20×200等）
- qty: 数量（每台件数，浮点数）
- unit: 单位（件、kg、m、套等）
- remark: 备注/补充说明
- weight: 单重（kg，如无则填0）
- total_weight: 总重（kg，如无则填0）
- source: 来源（识别表格中"来源""备注"列的关键词：自制/外购/标准件/外协/焊接件，如无标注则留空）

返回格式：{"items": [{"item_no": 1, "part_no": "...", ...}], "confidence": 0.85}

注意：
1. 如遇手写BOM，尽量识别文字
2. 如表格不完整，用已有信息填充，缺失字段留空或填默认值
3. 区分零件序号和数量，不要混淆
4. 材料标注需保持原始写法，不要猜测修改
5. 识别表格标题行，但不要将标题行作为数据行返回
"""

# ── Parse Prompt (text-based BOM) ──

BOM_PARSE_PROMPT = """你是机械制造业BOM解析专家。以下是从图片/文档中提取的文本，请将其解析为结构化的BOM数据。

## BOM文本内容：
{bom_text}

## 解析要求：
1. 识别列对应关系（序号、图号、名称、材料、规格、数量、单位、备注、单重、总重、来源）
2. 每一行零件生成一条记录
3. 材料标准化（如"45号钢"→"45#"，"304不锈钢"→"06Cr19Ni10"）
4. 来源归类（自制/外购/标准件/外协件/焊接件/铸造件）
5. 数量为浮点数（如"2件"→2.0，"1套"→1.0）

## 输出JSON：
{{"items": [{{"item_no": 1, "part_no": "XT-01-001", "part_name": "底座", "material": "HT200", "spec": "200×150×30", "qty": 1.0, "unit": "件", "remark": "", "weight": 2.5, "total_weight": 2.5, "source": "自制件"}}], "warnings": [], "confidence": 0.9}}

只返回JSON，不要任何额外解释。"""


# ── Excel BOM Parse Prompt ──

EXCEL_BOM_PROMPT = """你是机械制造业BOM解析专家。以下是从Excel文件中读取的BOM表格数据：

{excel_text}

请解析为结构化BOM JSON。识别标准BOM列：序号、图号/零件号、名称、材料、规格、数量、单位、备注、单重、总重、来源。

返回JSON：{{"items": [...], "warnings": [], "confidence": 0.9}}"""


class BOMAgent:
    """Multi-agent BOM extraction pipeline."""

    def __init__(self, api_key: str, base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.text_model = "qwen-max"
        self.vision_model = "qwen-vl-max"

    # ── Image extraction ──

    def extract_from_image(self, image_bytes: bytes, filename: str = "bom.png",
                           preprocess: bool = True) -> BOMExtractionResult:
        """Extract BOM from image using vision model.

        Args:
            image_bytes: Raw image bytes.
            filename: Filename for MIME type detection.
            preprocess: Whether to run OCR-enhancing preprocessing (deskew, contrast, sharpen).
        """
        if preprocess:
            try:
                image_bytes = preprocess_image(image_bytes)
            except Exception as e:
                logger.warning(f"Image preprocessing failed ({e}), using original")

        b64 = base64.b64encode(image_bytes).decode("utf-8")

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
        mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "bmp": "image/bmp"}
        mime = mime_map.get(ext, "image/png")

        raw = self._call_vision(mime, b64)
        return self._parse_json_response(raw)

    @retry_on_error(max_retries=3, base_delay=1.0)
    def _call_vision(self, mime: str, b64: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.vision_model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": VISION_BOM_PROMPT},
                ],
            }],
            max_tokens=4096,
            temperature=0.1,
        )
        return resp.choices[0].message.content.strip()

    def extract_from_pdf_page(self, image_bytes: bytes, page_num: int = 1) -> BOMExtractionResult:
        """Extract BOM from a PDF page (rendered as image)."""
        return self.extract_from_image(image_bytes, f"pdf_page_{page_num}.png")

    # ── Text-based extraction (for OCR pre-processed text) ──

    def parse_from_text(self, raw_text: str) -> BOMExtractionResult:
        """Parse BOM from raw text using LLM."""
        raw = self._call_text_parse(BOM_PARSE_PROMPT.format(bom_text=raw_text[:8000]))
        return self._parse_json_response(raw)

    @retry_on_error(max_retries=3, base_delay=1.0)
    def _call_text_parse(self, prompt: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.text_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.1,
        )
        return resp.choices[0].message.content.strip()

    # ── Excel extraction ──

    def parse_from_excel_text(self, excel_text: str) -> BOMExtractionResult:
        """Parse BOM from Excel tabular text."""
        raw = self._call_text_parse(EXCEL_BOM_PROMPT.format(excel_text=excel_text[:8000]))
        return self._parse_json_response(raw)

    # ── JSON parsing helper ──

    def _parse_json_response(self, raw: str) -> BOMExtractionResult:
        """Parse LLM JSON response into BOMExtractionResult."""
        json_str = raw.strip()
        m = re.search(r"\{[\s\S]*\}", json_str)
        if m:
            json_str = m.group(0)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return BOMExtractionResult(raw_text=raw, warnings=["JSON解析失败，请检查格式"])

        items = []
        for item_data in data.get("items", []):
            bom_item = BOMItem(
                item_no=item_data.get("item_no", 0),
                part_no=item_data.get("part_no", ""),
                part_name=item_data.get("part_name", ""),
                material=self._normalize_material(item_data.get("material", "")),
                spec=item_data.get("spec", ""),
                qty=float(item_data.get("qty", 1.0)),
                unit=item_data.get("unit", "件"),
                remark=item_data.get("remark", ""),
                weight=float(item_data.get("weight", 0.0)),
                total_weight=float(item_data.get("total_weight", 0.0)),
                source=self._normalize_source(item_data.get("source", "")),
            )
            items.append(bom_item)

        return BOMExtractionResult(
            items=items,
            raw_text=data.get("raw_text", raw),
            table_headers=data.get("table_headers", []),
            confidence=float(data.get("confidence", 0.0)),
            warnings=data.get("warnings", []),
        )

    @staticmethod
    def _normalize_material(material: str) -> str:
        if not material:
            return ""
        return MATERIAL_NORMALIZE.get(material.lower().strip(), material.strip())

    @staticmethod
    def _normalize_source(source: str) -> str:
        if not source:
            return ""
        for key, val in SOURCE_NORMALIZE.items():
            if key in source:
                return val
        return source.strip()


# ── Excel BOM reader (no LLM, direct parsing) ──

def read_excel_bom(file_bytes: bytes, filename: str) -> BOMExtractionResult:
    """Read BOM directly from Excel file (.xlsx/.xls)."""
    try:
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
    except Exception as e:
        return BOMExtractionResult(warnings=[f"Excel读取失败: {e}"])

    all_items = []
    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        df = df.dropna(how="all")

        header_row = _find_bom_header(df)
        if header_row is None:
            continue

        # Use header row and everything after it
        df.columns = df.iloc[header_row]
        df = df.iloc[header_row + 1:].reset_index(drop=True)

        # Forward-fill merged cells (common in real-world BOMs: name/part_no span rows)
        cols_to_fill = ["part_no", "part_name", "material", "spec", "source",
                        "图号", "零件号", "名称", "材料", "规格", "来源",
                        "图号/零件号", "零件名称", "物料名称"]
        for col in df.columns:
            if str(col).strip() in cols_to_fill:
                df[col] = df[col].ffill()

        # Map columns
        col_map = _map_bom_columns(list(df.columns))
        for _, row in df.iterrows():
            if row.isna().all():
                continue

            # Validate: item_no must look like a real number (not summary text)
            raw_item_no = str(_col(row, col_map, "item_no")).strip()
            if raw_item_no and not raw_item_no.replace(".", "").replace("-", "").isdigit():
                continue

            bom_item = BOMItem(
                item_no=_safe_int(_col(row, col_map, "item_no")),
                part_no=str(_col(row, col_map, "part_no")),
                part_name=str(_col(row, col_map, "part_name")),
                material=str(_col(row, col_map, "material")),
                spec=str(_col(row, col_map, "spec")),
                qty=_safe_float(_col(row, col_map, "qty"), 1.0),
                unit=str(_col(row, col_map, "unit") or "件"),
                remark=str(_col(row, col_map, "remark")),
                weight=_safe_float(_col(row, col_map, "weight"), 0.0),
                total_weight=_safe_float(_col(row, col_map, "total_weight"), 0.0),
                source=str(_col(row, col_map, "source")),
            )
            # Skip summary/footer rows
            pn = str(bom_item.part_no)
            pname = str(bom_item.part_name)
            if not bom_item.part_no and not bom_item.part_name:
                continue
            # Check for aggregate keywords in any field
            summary_kw = ("共 ", "合计", "总计", "total", "sum", "小计")
            if any(kw in pn or kw in pname or kw in str(bom_item.item_no)
                   for kw in summary_kw):
                continue
            all_items.append(bom_item)

    if not all_items:
        return BOMExtractionResult(
            warnings=["未在Excel中找到BOM表格，请确认格式：第一行为列标题，包含'序号''名称''数量'等列"]
        )

    return BOMExtractionResult(items=all_items, confidence=0.95)


def _find_bom_header(df) -> int | None:
    """Find the row that looks like a BOM header. Returns positional index."""
    bom_keywords = [
        "序号", "图号", "名称", "材料", "数量", "零件", "物料", "item", "part", "material", "qty",
        "编号", "编码", "品名", "牌号", "用量", "规格", "代号", "单位", "备注",
    ]
    for pos, (_, row) in enumerate(df.iterrows()):
        row_text = " ".join(str(v) for v in row if pd.notna(v)).lower()
        matches = sum(1 for kw in bom_keywords if kw in row_text)
        if matches >= 3:
            return pos
    return None


COLUMN_ALIASES = {
    "item_no": ["序号", "项次", "item", "no", "item no", "编号"],
    "part_no": ["图号", "零件号", "代号", "part no", "物料号", "物料编码", "编码", "code"],
    "part_name": ["名称", "零件名称", "物料名称", "品名", "name", "描述", "description"],
    "material": ["材料", "材质", "material", "牌号"],
    "spec": ["规格", "尺寸", "spec", "规格型号", "型号规格"],
    "qty": ["数量", "件数", "qty", "quantity", "用量", "每台数量"],
    "unit": ["单位", "unit", "计量单位"],
    "remark": ["备注", "remark", "说明", "note", "notes"],
    "weight": ["单重", "单件重量", "重量", "weight", "净重"],
    "total_weight": ["总重", "总重量", "total weight"],
    "source": ["来源", "source", "类型", "type", "自制外购"],
}


def _map_bom_columns(columns: list) -> dict:
    """Map actual column names to standard BOM field names."""
    mapping = {}
    for i, col in enumerate(columns):
        col_str = str(col).strip().lower().replace(" ", "").replace("\n", "")
        for std_name, aliases in COLUMN_ALIASES.items():
            if std_name in mapping.values():
                continue
            for alias in aliases:
                if alias == col_str or alias in col_str:
                    mapping[i] = std_name
                    break
    return mapping


def _col(row, col_map: dict, field: str) -> Any:
    """Get value from row by field name from column mapping."""
    reverse = {v: k for k, v in col_map.items()}
    idx = reverse.get(field)
    if idx is not None and idx < len(row):
        val = row.iloc[idx]
        return "" if pd.isna(val) else val
    return ""


def _safe_int(val: Any) -> int:
    try:
        return int(float(str(val)))
    except (ValueError, TypeError):
        return 0


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(str(val))
    except (ValueError, TypeError):
        return default
