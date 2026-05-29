"""BOM Intelligent Extraction Assistant — XPeng AI Competition Entry."""

from .agent import BOMAgent, read_excel_bom
from .exporter import generate_bom_excel, generate_erp_template, generate_comparison_report
from .validator import validate_bom, get_validation_summary, ValidationResult
from .feishu import FeishuBot
from .knowledge_base import PartsKnowledgeBase
from .similarity import search_similar_parts, get_search_report, SearchSummary
