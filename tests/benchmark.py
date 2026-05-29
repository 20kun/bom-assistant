"""BOM extraction benchmark — measures accuracy, speed, and generates ROI data.

Run: python tests/benchmark.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import read_excel_bom, BOMItem
from src.validator import validate_bom
from src.exporter import generate_bom_excel, generate_erp_template, generate_comparison_report

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)


# ── Expected results for accuracy measurement ──

EXPECTED = {
    "标准BOM_变速箱总成.xlsx": {
        "item_count": 25,
        "materials": {"HT250", "40Cr", "45#", "20CrMnTi", "Q235A", "丁腈橡胶", "GCr15", "35CrMo", "8.8级", "65Mn", "石棉橡胶"},
        "sources": {"铸造件", "自制件", "外购件", "标准件"},
        "has_weights": True,
    },
    "合并单元格BOM_底座组件.xlsx": {
        "item_count": 13,
        "materials": {"HT200", "Q235A", "45#", "8.8级", "40Cr", "20CrMnTi", "GCr15", "丁腈橡胶", "65Mn", "铝", "尼龙66"},
        "sources": {"铸造件", "自制件", "外购件", "标准件"},
        "has_weights": False,
    },
    "非标准列名BOM_液压系统.xlsx": {
        "item_count": 10,
        "materials": {"Q235A", "20#", "45#"},
        "sources": {"自制件", "外购件"},
        "has_weights": False,
    },
    "大型BOM_装配体50项.xlsx": {
        "item_count": 55,
        "materials": set(),  # random, can't predict
        "sources": set(),
        "has_weights": False,
    },
}


def run_benchmark():
    """Run benchmark on all fixture files."""
    print("=" * 60)
    print("BOM智能提取助手 — 基准测试")
    print("=" * 60)
    print()

    all_results = []
    total_items = 0
    total_time = 0
    total_correct = 0
    total_expected = 0

    fixtures = sorted(os.listdir(FIXTURES_DIR))
    xlsx_files = [f for f in fixtures if f.endswith(".xlsx")]

    if not xlsx_files:
        print("No fixture files found. Run generate_test_data.py first.")
        return

    for filename in xlsx_files:
        filepath = os.path.join(FIXTURES_DIR, filename)
        print(f"--- {filename} ---")

        # Read file
        with open(filepath, "rb") as f:
            file_bytes = f.read()

        t_start = time.time()
        result = read_excel_bom(file_bytes, filename)
        elapsed = time.time() - t_start

        items = result.items
        warnings = result.warnings

        # Accuracy check
        expected = EXPECTED.get(filename, {})
        exp_count = expected.get("item_count", len(items))

        count_match = len(items) == exp_count
        material_accuracy = 0
        source_accuracy = 0

        if expected.get("materials"):
            found_materials = {it.material for it in items if it.material}
            if found_materials:
                overlap = len(found_materials & expected["materials"])
                material_accuracy = overlap / len(expected["materials"]) * 100

        if expected.get("sources"):
            found_sources = {it.source for it in items if it.source}
            if found_sources:
                overlap = len(found_sources & expected["sources"])
                source_accuracy = overlap / len(expected["sources"]) * 100

        # Validate extracted data
        vr = validate_bom(items)

        print(f"  Items: {len(items)}/{exp_count} {'OK' if count_match else 'MISMATCH'}")
        print(f"  Time: {elapsed:.3f}s")
        print(f"  Warnings: {len(warnings)}")
        print(f"  Validation: {vr.status} (score={vr.score:.0f})")
        if expected.get("materials"):
            print(f"  Material accuracy: {material_accuracy:.0f}%")
        if expected.get("sources"):
            print(f"  Source accuracy: {source_accuracy:.0f}%")

        # Export test
        records = [it.to_dict() for it in items]
        t_export = time.time()
        xlsx_out = generate_bom_excel(records, {"project_name": filename})
        erp_out = generate_erp_template(records)
        export_time = time.time() - t_export
        print(f"  Export: BOM={len(xlsx_out)}B, ERP={len(erp_out)}B ({export_time:.3f}s)")

        total_items += len(items)
        total_time += elapsed
        total_correct += (1 if count_match else 0)
        total_expected += 1

        all_results.append({
            "file": filename,
            "items_extracted": len(items),
            "items_expected": exp_count,
            "count_match": count_match,
            "extraction_time_s": round(elapsed, 3),
            "validation_score": vr.score,
            "validation_errors": vr.error_count,
            "validation_warnings": vr.warning_count,
            "material_accuracy_pct": round(material_accuracy, 1),
            "source_accuracy_pct": round(source_accuracy, 1),
            "export_time_s": round(export_time, 3),
            "warnings": warnings,
        })
        print()

    # ── Summary ──
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    print(f"  测试文件数: {len(xlsx_files)}")
    print(f"  总零件数: {total_items}")
    print(f"  数量匹配率: {total_correct}/{total_expected} ({total_correct/total_expected*100:.0f}%)")
    print(f"  总提取耗时: {total_time:.3f}s")
    print(f"  平均每项: {total_time/total_items*1000:.1f}ms")

    # Manual time estimate: 0.5 min per item
    manual_time_min = total_items * 0.5
    ai_time_min = total_time / 60
    saved = manual_time_min - ai_time_min
    print(f"\n  手动录入预估: {manual_time_min:.0f} 分钟")
    print(f"  AI提取实际: {ai_time_min:.2f} 分钟")
    print(f"  节省时间: {saved:.0f} 分钟 ({saved/manual_time_min*100:.0f}%)")

    # Generate comparison report
    comp = generate_comparison_report(manual_time_min, ai_time_min, total_items)
    comp_path = os.path.join(RESULTS_DIR, "效率对比报告.xlsx")
    with open(comp_path, "wb") as f:
        f.write(comp)
    print(f"\n  效率对比报告已保存: {comp_path}")

    # Save JSON results
    json_path = os.path.join(RESULTS_DIR, "benchmark_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "total_files": len(xlsx_files),
                "total_items": total_items,
                "count_match_rate": round(total_correct / total_expected * 100, 1),
                "total_extraction_time_s": round(total_time, 3),
                "avg_time_per_item_ms": round(total_time / total_items * 1000, 1),
                "manual_estimate_min": round(manual_time_min, 1),
                "ai_actual_min": round(ai_time_min, 3),
                "time_saved_min": round(saved, 1),
                "time_saved_pct": round(saved / manual_time_min * 100, 1),
            },
            "details": all_results,
        }, f, ensure_ascii=False, indent=2)
    print(f"  详细结果已保存: {json_path}")

    return all_results


if __name__ == "__main__":
    run_benchmark()
