"""Seed the knowledge base with demo historical parts data."""

import json
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parts_db.json")

DEMO_PARTS = [
    # Standard parts (high reuse)
    {"part_no": "GB/T 5783-2012", "part_name": "六角头螺栓", "material": "8.8级", "spec": "M8×25", "source": "标准件", "weight": 0.01, "unit": "件", "remark": "镀锌", "project": "通用", "usage_count": 156, "tags": ["标准件", "螺栓"]},
    {"part_no": "GB/T 5783-2012", "part_name": "六角头螺栓", "material": "8.8级", "spec": "M10×30", "source": "标准件", "weight": 0.025, "unit": "件", "remark": "镀锌", "project": "通用", "usage_count": 98, "tags": ["标准件", "螺栓"]},
    {"part_no": "GB/T 5783-2012", "part_name": "六角头螺栓", "material": "8.8级", "spec": "M12×40", "source": "标准件", "weight": 0.04, "unit": "件", "remark": "镀锌", "project": "通用", "usage_count": 87, "tags": ["标准件", "螺栓"]},
    {"part_no": "GB/T 70.1-2008", "part_name": "内六角圆柱头螺钉", "material": "8.8级", "spec": "M6×20", "source": "标准件", "weight": 0.005, "unit": "件", "remark": "", "project": "通用", "usage_count": 120, "tags": ["标准件", "螺钉"]},
    {"part_no": "GB/T 70.1-2008", "part_name": "内六角圆柱头螺钉", "material": "8.8级", "spec": "M8×25", "source": "标准件", "weight": 0.01, "unit": "件", "remark": "", "project": "通用", "usage_count": 95, "tags": ["标准件", "螺钉"]},
    {"part_no": "GB/T 93-1987", "part_name": "弹簧垫圈", "material": "65Mn", "spec": "M8", "source": "标准件", "weight": 0.003, "unit": "件", "remark": "", "project": "通用", "usage_count": 200, "tags": ["标准件", "垫圈"]},
    {"part_no": "GB/T 97.1-2002", "part_name": "平垫圈", "material": "Q235A", "spec": "M8", "source": "标准件", "weight": 0.005, "unit": "件", "remark": "", "project": "通用", "usage_count": 200, "tags": ["标准件", "垫圈"]},
    {"part_no": "GB/T 6170-2000", "part_name": "六角螺母", "material": "8级", "spec": "M8", "source": "标准件", "weight": 0.008, "unit": "件", "remark": "镀锌", "project": "通用", "usage_count": 180, "tags": ["标准件", "螺母"]},
    {"part_no": "GB/T 5783-2012", "part_name": "六角头螺栓", "material": "35CrMo", "spec": "M10×40", "source": "标准件", "weight": 0.04, "unit": "件", "remark": "镀锌", "project": "通用", "usage_count": 45, "tags": ["标准件", "螺栓", "高强度"]},

    # Bearings
    {"part_no": "6311", "part_name": "深沟球轴承", "material": "GCr15", "spec": "6311", "source": "外购件", "weight": 0.85, "unit": "套", "remark": "SKF", "project": "变速箱A", "usage_count": 12, "tags": ["轴承", "SKF"]},
    {"part_no": "6313", "part_name": "深沟球轴承", "material": "GCr15", "spec": "6313", "source": "外购件", "weight": 1.2, "unit": "套", "remark": "SKF", "project": "变速箱A", "usage_count": 8, "tags": ["轴承", "SKF"]},
    {"part_no": "6309", "part_name": "深沟球轴承", "material": "GCr15", "spec": "6309", "source": "外购件", "weight": 0.55, "unit": "套", "remark": "SKF", "project": "变速箱A", "usage_count": 20, "tags": ["轴承", "SKF"]},
    {"part_no": "6208", "part_name": "深沟球轴承", "material": "GCr15", "spec": "6208", "source": "外购件", "weight": 0.35, "unit": "套", "remark": "NSK", "project": "传动装置B", "usage_count": 15, "tags": ["轴承", "NSK"]},
    {"part_no": "NJ2310", "part_name": "圆柱滚子轴承", "material": "GCr15", "spec": "NJ2310", "source": "外购件", "weight": 0.95, "unit": "套", "remark": "FAG", "project": "减速器C", "usage_count": 6, "tags": ["轴承", "FAG", "滚子"]},

    # Seals
    {"part_no": "TC55×78×10", "part_name": "骨架油封", "material": "丁腈橡胶", "spec": "TC55×78×10", "source": "外购件", "weight": 0.03, "unit": "件", "remark": "NOK", "project": "变速箱A", "usage_count": 10, "tags": ["油封", "NOK"]},
    {"part_no": "TC65×90×12", "part_name": "骨架油封", "material": "丁腈橡胶", "spec": "TC65×90×12", "source": "外购件", "weight": 0.04, "unit": "件", "remark": "NOK", "project": "变速箱A", "usage_count": 8, "tags": ["油封", "NOK"]},
    {"part_no": "TC45×62×8", "part_name": "骨架油封", "material": "丁腈橡胶", "spec": "TC45×62×8", "source": "外购件", "weight": 0.02, "unit": "件", "remark": "NOK", "project": "传动装置B", "usage_count": 12, "tags": ["油封", "NOK"]},
    {"part_no": "O-Ring-50", "part_name": "O型密封圈", "material": "丁腈橡胶", "spec": "φ50×3.5", "source": "外购件", "weight": 0.005, "unit": "件", "remark": "", "project": "通用", "usage_count": 50, "tags": ["密封", "O型圈"]},

    # Gears
    {"part_no": "BSJ-01-006", "part_name": "一级主动齿轮", "material": "20CrMnTi", "spec": "m=3 z=28", "source": "自制件", "weight": 1.5, "unit": "件", "remark": "渗碳淬火HRC58-62", "project": "变速箱A", "usage_count": 4, "tags": ["齿轮", "渗碳"]},
    {"part_no": "BSJ-01-007", "part_name": "一级从动齿轮", "material": "20CrMnTi", "spec": "m=3 z=56", "source": "自制件", "weight": 4.2, "unit": "件", "remark": "渗碳淬火HRC58-62", "project": "变速箱A", "usage_count": 4, "tags": ["齿轮", "渗碳"]},
    {"part_no": "CQ-01-001", "part_name": "主动锥齿轮", "material": "20CrMnTi", "spec": "m=5 z=18", "source": "自制件", "weight": 2.8, "unit": "件", "remark": "渗碳淬火", "project": "减速器C", "usage_count": 3, "tags": ["齿轮", "锥齿轮", "渗碳"]},
    {"part_no": "CQ-01-002", "part_name": "从动锥齿轮", "material": "20CrMnTi", "spec": "m=5 z=45", "source": "自制件", "weight": 6.5, "unit": "件", "remark": "渗碳淬火", "project": "减速器C", "usage_count": 3, "tags": ["齿轮", "锥齿轮", "渗碳"]},

    # Shafts
    {"part_no": "BSJ-01-003", "part_name": "输入轴", "material": "40Cr", "spec": "φ55×320", "source": "自制件", "weight": 5.8, "unit": "件", "remark": "调质HRC28-32", "project": "变速箱A", "usage_count": 4, "tags": ["轴", "调质"]},
    {"part_no": "BSJ-01-004", "part_name": "输出轴", "material": "40Cr", "spec": "φ65×380", "source": "自制件", "weight": 8.2, "unit": "件", "remark": "调质HRC28-32", "project": "变速箱A", "usage_count": 4, "tags": ["轴", "调质"]},
    {"part_no": "BSJ-01-005", "part_name": "中间轴", "material": "45#", "spec": "φ45×260", "source": "自制件", "weight": 3.2, "unit": "件", "remark": "", "project": "变速箱A", "usage_count": 4, "tags": ["轴"]},
    {"part_no": "CD-01-010", "part_name": "传动轴", "material": "45#", "spec": "φ40×500", "source": "自制件", "weight": 4.9, "unit": "件", "remark": "调质", "project": "传动装置B", "usage_count": 6, "tags": ["轴", "调质"]},

    # Housings
    {"part_no": "BSJ-01-001", "part_name": "箱体", "material": "HT250", "spec": "400×300×200", "source": "铸造件", "weight": 45.0, "unit": "件", "remark": "时效处理", "project": "变速箱A", "usage_count": 4, "tags": ["箱体", "铸铁", "时效"]},
    {"part_no": "BSJ-01-002", "part_name": "箱盖", "material": "HT250", "spec": "400×300×25", "source": "铸造件", "weight": 8.5, "unit": "件", "remark": "", "project": "变速箱A", "usage_count": 4, "tags": ["箱盖", "铸铁"]},
    {"part_no": "CQ-01-020", "part_name": "减速器壳体", "material": "HT200", "spec": "350×250×180", "source": "铸造件", "weight": 32.0, "unit": "件", "remark": "时效处理", "project": "减速器C", "usage_count": 3, "tags": ["壳体", "铸铁"]},

    # End covers
    {"part_no": "BSJ-01-010", "part_name": "输入轴承端盖", "material": "Q235A", "spec": "φ120×15", "source": "自制件", "weight": 0.8, "unit": "件", "remark": "", "project": "变速箱A", "usage_count": 4, "tags": ["端盖"]},
    {"part_no": "BSJ-01-011", "part_name": "输出轴承端盖", "material": "Q235A", "spec": "φ140×15", "source": "自制件", "weight": 1.0, "unit": "件", "remark": "", "project": "变速箱A", "usage_count": 4, "tags": ["端盖"]},

    # Hydraulic components
    {"part_no": "HOB-63/35-200", "part_name": "液压缸", "material": "", "spec": "HOB-63/35-200", "source": "外购件", "weight": 0, "unit": "台", "remark": "力士乐", "project": "液压系统D", "usage_count": 5, "tags": ["液压缸", "力士乐"]},
    {"part_no": "4WE6E6X/EG24N9K4", "part_name": "电磁换向阀", "material": "", "spec": "4WE6E6X/EG24N9K4", "source": "外购件", "weight": 0, "unit": "台", "remark": "力士乐", "project": "液压系统D", "usage_count": 5, "tags": ["阀", "力士乐"]},
    {"part_no": "PV2R2-26-F-RAA-4222", "part_name": "叶片泵", "material": "", "spec": "PV2R2-26-F-RAA-4222", "source": "外购件", "weight": 0, "unit": "台", "remark": "不二越", "project": "液压系统D", "usage_count": 3, "tags": ["泵", "不二越"]},

    # Common materials with typical uses
    {"part_no": "", "part_name": "底座", "material": "HT200", "spec": "", "source": "铸造件", "weight": 0, "unit": "件", "remark": "常用底座材料", "project": "通用", "usage_count": 25, "tags": ["底座", "铸铁"]},
    {"part_no": "", "part_name": "垫片", "material": "石棉橡胶", "spec": "", "source": "外购件", "weight": 0, "unit": "件", "remark": "密封垫片", "project": "通用", "usage_count": 30, "tags": ["垫片", "密封"]},
    {"part_no": "", "part_name": "键", "material": "45#", "spec": "", "source": "标准件", "weight": 0, "unit": "件", "remark": "普通平键", "project": "通用", "usage_count": 40, "tags": ["键", "标准件"]},
]


def seed():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(DEMO_PARTS, f, ensure_ascii=False, indent=2)
    print(f"Seeded {len(DEMO_PARTS)} parts to {DB_PATH}")


if __name__ == "__main__":
    seed()
