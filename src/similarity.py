"""Similar part search agent — find reusable/historical parts from knowledge base."""

from dataclasses import dataclass, field

from .agent import BOMItem
from .knowledge_base import PartsKnowledgeBase, PartRecord


@dataclass
class SimilarityMatch:
    """A matched part from the knowledge base."""
    query_item: BOMItem
    matched_part: PartRecord
    score: float
    match_reason: str
    can_reuse: bool = False
    reuse_note: str = ""


@dataclass
class SearchSummary:
    """Summary of similarity search results."""
    total_queried: int = 0
    matches_found: int = 0
    reuse_candidates: int = 0
    matches: list[SimilarityMatch] = field(default_factory=list)
    new_parts: list[BOMItem] = field(default_factory=list)


def search_similar_parts(
    items: list[BOMItem],
    kb: PartsKnowledgeBase,
    min_score: float = 0.4,
    top_k: int = 3,
) -> SearchSummary:
    """Search for similar/reusable parts for each BOM item.

    Args:
        items: Current BOM items to search for.
        kb: Knowledge base to search against.
        min_score: Minimum similarity score to consider a match.
        top_k: Number of top matches to return per item.

    Returns:
        SearchSummary with matches and new parts.
    """
    summary = SearchSummary(total_queried=len(items))

    for item in items:
        # Strategy 1: Search by part name (most reliable)
        name_matches = kb.search_by_name(item.part_name, top_k=top_k)

        # Strategy 2: Search by material + spec
        mat_spec_matches = kb.search_by_material_and_spec(
            material=item.material, spec=item.spec, top_k=top_k
        )

        # Merge and deduplicate
        seen = set()
        all_matches = []
        for part, score in name_matches + mat_spec_matches:
            key = part.part_no or part.part_name
            if key not in seen:
                seen.add(key)
                all_matches.append((part, score))

        # Sort by score
        all_matches.sort(key=lambda x: -x[1])

        best_match = None
        for part, score in all_matches[:top_k]:
            if score < min_score:
                continue
            reason = _build_match_reason(item, part, score)
            can_reuse = score >= 0.7 and part.source in ("标准件", "外购件", "自制件")
            reuse_note = ""
            if can_reuse:
                if score >= 0.95:
                    reuse_note = "完全匹配，可直接复用"
                elif score >= 0.8:
                    reuse_note = "高度相似，确认规格后可复用"
                else:
                    reuse_note = "相似件，需确认尺寸/材料"

            match = SimilarityMatch(
                query_item=item,
                matched_part=part,
                score=score,
                match_reason=reason,
                can_reuse=can_reuse,
                reuse_note=reuse_note,
            )
            summary.matches.append(match)
            if best_match is None or score > best_match.score:
                best_match = match

        if best_match and best_match.score >= min_score:
            summary.matches_found += 1
            if best_match.can_reuse:
                summary.reuse_candidates += 1
        else:
            summary.new_parts.append(item)

    return summary


def _build_match_reason(query: BOMItem, match: PartRecord, score: float) -> str:
    """Build human-readable match reason."""
    reasons = []
    if query.part_name and match.part_name:
        if query.part_name == match.part_name:
            reasons.append(f"名称完全匹配: {match.part_name}")
        elif query.part_name in match.part_name or match.part_name in query.part_name:
            reasons.append(f"名称相似: {query.part_name} ≈ {match.part_name}")
    if query.material and match.material:
        if query.material == match.material:
            reasons.append(f"材料一致: {match.material}")
    if query.spec and match.spec:
        if query.spec == match.spec:
            reasons.append(f"规格一致: {match.spec}")
        elif query.spec in match.spec or match.spec in query.spec:
            reasons.append(f"规格相似: {query.spec} ≈ {match.spec}")
    if match.part_no:
        reasons.append(f"历史图号: {match.part_no}")
    if match.project:
        reasons.append(f"来源项目: {match.project}")
    if match.usage_count > 1:
        reasons.append(f"已使用{match.usage_count}次")
    return "; ".join(reasons) if reasons else f"相似度: {score:.0%}"


def get_search_report(summary: SearchSummary) -> dict:
    """Get search summary as dict for display/export."""
    return {
        "total_queried": summary.total_queried,
        "matches_found": summary.matches_found,
        "reuse_candidates": summary.reuse_candidates,
        "new_parts_count": len(summary.new_parts),
        "matches": [
            {
                "query_name": m.query_item.part_name,
                "query_part_no": m.query_item.part_no,
                "matched_name": m.matched_part.part_name,
                "matched_part_no": m.matched_part.part_no,
                "score": round(m.score, 2),
                "can_reuse": m.can_reuse,
                "reuse_note": m.reuse_note,
                "match_reason": m.match_reason,
            }
            for m in summary.matches
            if m.score >= 0.4
        ],
        "new_parts": [
            {"part_no": it.part_no, "part_name": it.part_name, "material": it.material}
            for it in summary.new_parts
        ],
    }
