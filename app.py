"""BOM智能提取助手 — Streamlit Web App.

机械设计制造领域提效工具。上传BOM表格图片/PDF/Excel，
AI自动识别提取零件号、名称、材料、规格、数量等信息，
一键导出ERP格式Excel。

Usage:
    streamlit run app.py
"""

import datetime
import io
import os
import time

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from PIL import Image

from src import BOMAgent, generate_bom_excel, generate_erp_template, generate_comparison_report, read_excel_bom, validate_bom, get_validation_summary, FeishuBot, PartsKnowledgeBase, search_similar_parts, get_search_report

load_dotenv()

# ── Page config ──
st.set_page_config(
    page_title="BOM智能提取助手 | XPeng",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state init ──
for key, default in {
    "agent": None,
    "bom_items": [],
    "raw_result": None,
    "extraction_done": False,
    "excel_bytes": None,
    "erp_bytes": None,
    "total_saved_minutes": 0.0,
    "item_count_history": 0,
    "processing_time": 0.0,
    "agent_error": None,
    "validation_result": None,
    "feishu_url": "",
    "feishu_secret": "",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


def _get_config(key: str, default: str = "") -> str:
    try:
        return st.secrets.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


def init_agent():
    if st.session_state.agent is not None:
        return
    api_key = _get_config("DASHSCOPE_API_KEY")
    if not api_key:
        st.session_state.agent_error = "未配置 DASHSCOPE_API_KEY。请将 API Key 写入 .env 文件。"
        return
    try:
        st.session_state.agent = BOMAgent(
            api_key=api_key,
            base_url=_get_config("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        )
        st.session_state.agent_error = None
    except Exception as e:
        st.session_state.agent_error = f"AI 服务初始化失败：{e}"


init_agent()

# ── Sidebar ──
with st.sidebar:
    st.title("🔧 BOM智能提取助手")
    st.caption("Powered by Qwen AI · v1.0")
    st.caption("机械设计制造 · 提质增效")

    if st.session_state.agent is not None:
        st.success("🟢 AI 服务就绪")
    elif st.session_state.agent_error:
        st.error(f"🔴 {st.session_state.agent_error}")

    st.divider()

    # ── ERP Export Config ──
    with st.expander("⚙️ 导出配置", expanded=False):
        st.session_state.project_name = st.text_input("项目/产品名称", value="", placeholder="如：变速箱总成")
        st.session_state.designer = st.text_input("设计者", value="", placeholder="如：张三")
        st.session_state.bom_version = st.text_input("版本号", value="V1.0")

    st.divider()

    # ── Feishu config ──
    with st.expander("📨 飞书推送（可选）", expanded=False):
        st.caption("BOM提取完成后自动推送通知到飞书群")
        feishu_url = st.text_input(
            "飞书 Webhook URL",
            type="password",
            value=_get_config("FEISHU_WEBHOOK_URL", st.session_state.feishu_url),
            placeholder="https://open.feishu.cn/...",
        )
        feishu_secret = st.text_input(
            "Webhook 签名密钥",
            type="password",
            value=_get_config("FEISHU_WEBHOOK_SECRET", st.session_state.feishu_secret),
        )
        st.session_state.feishu_url = feishu_url
        st.session_state.feishu_secret = feishu_secret

    st.divider()

    # ── Stats ──
    if st.session_state.total_saved_minutes > 0:
        saved_h = st.session_state.total_saved_minutes / 60
        st.metric("⏱️ 累计节省时间", f"{st.session_state.total_saved_minutes:.0f} 分钟")
        st.metric("📄 已提取零件", f"{st.session_state.item_count_history} 项")
        st.metric("💰 估算年省", f"¥{saved_h * 12 * 150:,.0f}")

    # ── Demo file download ──
    st.divider()
    with st.expander("📦 下载示例BOM", expanded=False):
        st.caption("无BOM文件？下载示例文件测试：")
        if st.button("📥 生成示例BOM Excel", use_container_width=True):
            demo_items = [
                {"item_no": 1, "part_no": "XT-01-001", "part_name": "底座", "material": "HT200",
                 "spec": "200×150×30", "qty": 1.0, "unit": "件", "weight": 2.5, "total_weight": 2.5,
                 "source": "自制件", "remark": ""},
                {"item_no": 2, "part_no": "XT-01-002", "part_name": "上盖", "material": "45#",
                 "spec": "200×150×15", "qty": 1.0, "unit": "件", "weight": 1.2, "total_weight": 1.2,
                 "source": "自制件", "remark": "调质HRC28-32"},
                {"item_no": 3, "part_no": "XT-01-003", "part_name": "输入轴", "material": "40Cr",
                 "spec": "φ45×280", "qty": 1.0, "unit": "件", "weight": 3.5, "total_weight": 3.5,
                 "source": "自制件", "remark": "调质+高频"},
                {"item_no": 4, "part_no": "XT-01-004", "part_name": "齿轮", "material": "20CrMnTi",
                 "spec": "m=3 z=32", "qty": 2.0, "unit": "件", "weight": 0.8, "total_weight": 1.6,
                 "source": "自制件", "remark": "渗碳淬火HRC58-62"},
                {"item_no": 5, "part_no": "XT-01-005", "part_name": "轴承端盖", "material": "Q235A",
                 "spec": "φ90×12", "qty": 2.0, "unit": "件", "weight": 0.3, "total_weight": 0.6,
                 "source": "自制件", "remark": ""},
                {"item_no": 6, "part_no": "XT-01-006", "part_name": "输入油封", "material": "丁腈橡胶",
                 "spec": "TC45×62×8", "qty": 1.0, "unit": "件", "weight": 0.05, "total_weight": 0.05,
                 "source": "外购件", "remark": "NOK品牌"},
                {"item_no": 7, "part_no": "GB/T 70.1-2008", "part_name": "内六角圆柱头螺钉",
                 "material": "8.8级", "spec": "M8×25", "qty": 8.0, "unit": "件", "weight": 0.01,
                 "total_weight": 0.08, "source": "标准件", "remark": ""},
                {"item_no": 8, "part_no": "GB/T 93-1987", "part_name": "弹簧垫圈", "material": "65Mn",
                 "spec": "M8", "qty": 8.0, "unit": "件", "weight": 0.002, "total_weight": 0.016,
                 "source": "标准件", "remark": ""},
                {"item_no": 9, "part_no": "XT-01-007", "part_name": "密封垫片", "material": "石棉橡胶",
                 "spec": "200×150×1.5", "qty": 2.0, "unit": "件", "weight": 0.02, "total_weight": 0.04,
                 "source": "外购件", "remark": ""},
                {"item_no": 10, "part_no": "GB/T 5783-2012", "part_name": "六角头螺栓",
                 "material": "35CrMo", "spec": "M10×40", "qty": 4.0, "unit": "件",
                 "weight": 0.04, "total_weight": 0.16, "source": "标准件", "remark": "镀锌"},
            ]
            demo_xlsx = generate_bom_excel(demo_items, {"project_name": "示例-减速器总成", "designer": "测试用户", "date": datetime.date.today().isoformat()})
            st.download_button(
                "⬇️ 下载示例BOM.xlsx", data=demo_xlsx, file_name="示例BOM_减速器.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

# ── Main content ──
st.title("🔧 BOM智能提取助手")
st.markdown(
    "> **上传BOM表格 → AI多Agent协作识别 → 一键导出ERP格式** &nbsp;&nbsp; "
    "| &nbsp; 图片/PDF/Excel全支持 &nbsp;|&nbsp; 物料标准化 &nbsp;|&nbsp; 效率提升90%+"
)

step_names = ["1. 上传BOM文件", "2. AI智能提取", "3. 审核编辑", "4. 导出ERP格式"]
current_step = 1
if st.session_state.extraction_done:
    current_step = 3
if st.session_state.excel_bytes:
    current_step = 4

progress_pct = min(current_step / len(step_names), 1.0)
st.progress(progress_pct, text=f"步骤 {current_step}/{len(step_names)}: {step_names[current_step - 1]}")
st.divider()

# ═══════════════════════════════════════════════════════════════
# STEP 1 & 2: Upload & Extract
# ═══════════════════════════════════════════════════════════════

col_upload, col_preview = st.columns([1, 1])

with col_upload:
    st.subheader("📤 上传BOM文件")

    input_type = st.radio(
        "输入类型",
        ["📷 图片（拍照/截图）", "📄 PDF文件", "📊 Excel文件"],
        horizontal=True,
    )

    if "图片" in input_type:
        uploaded_files = st.file_uploader(
            "上传BOM表格图片",
            type=["jpg", "jpeg", "png", "bmp", "webp"],
            accept_multiple_files=True,
            help="拍摄BOM表照片或上传截图，AI自动识别。支持多张同时上传。",
        )
    elif "PDF" in input_type:
        uploaded_files = st.file_uploader(
            "上传BOM PDF文件",
            type=["pdf"],
            accept_multiple_files=True,
            help="上传含BOM表格的PDF文件（装配图、明细表等）",
        )
    else:
        uploaded_files = st.file_uploader(
            "上传BOM Excel文件",
            type=["xlsx", "xls"],
            accept_multiple_files=True,
            help="上传Excel格式BOM，AI自动识别列对应关系并标准化",
        )

    if uploaded_files:
        st.caption(f"已选择 {len(uploaded_files)} 个文件")

        agent_ready = st.session_state.agent is not None
        if not agent_ready and "Excel" in input_type:
            # Excel can work without Agent!
            agent_ready = True

        if st.button("🔍 AI 智能提取", type="primary", use_container_width=True, disabled=not agent_ready):
            all_items = []
            total_time = 0.0
            warnings = []

            progress_bar = st.progress(0)
            status_text = st.empty()

            try:
                for i, file in enumerate(uploaded_files):
                    status_text.text(f"({i+1}/{len(uploaded_files)}) 正在处理：{file.name} ...")
                    img_bytes = file.read()
                    ext = file.name.rsplit(".", 1)[-1].lower()
                    t_start = time.time()

                    if ext in ("xlsx", "xls"):
                        result = read_excel_bom(img_bytes, file.name)
                    elif ext == "pdf":
                        result = st.session_state.agent.extract_from_pdf_page(img_bytes)
                    else:
                        result = st.session_state.agent.extract_from_image(img_bytes, file.name)

                    elapsed = time.time() - t_start
                    total_time += elapsed
                    all_items.extend(result.items)
                    warnings.extend(result.warnings)

                    # Renumber and stream partial results to UI
                    for j, item in enumerate(all_items, 1):
                        item.item_no = j

                    st.session_state.bom_items = list(all_items)
                    st.session_state.extraction_done = True
                    st.session_state.processing_time = total_time

                    progress_bar.progress((i + 1) / len(uploaded_files))
                    status_text.text(
                        f"({i+1}/{len(uploaded_files)}) {file.name} ✅ — "
                        f"{len(result.items)}项 · {elapsed:.1f}s"
                    )

                st.session_state.item_count_history += len(all_items)

                est_manual = len(all_items) * 0.5
                ai_time = total_time / 60
                saved = est_manual - ai_time
                st.session_state.total_saved_minutes += max(saved, 0)

                status_text.text(
                    f"✅ 提取完成！共 {len(all_items)} 项零件，"
                    f"AI用时 {total_time:.1f} 秒，"
                    f"对比手动录入预计节省 {max(saved, 0):.0f} 分钟"
                )
                time.sleep(1.5)
                st.rerun()

            except Exception as e:
                st.error(f"提取失败：{e}")
                st.info("💡 请确认API Key已正确配置，或尝试上传更清晰的图片")

        if not agent_ready and "Excel" not in input_type:
            st.warning("AI服务未就绪。请在 .env 文件中配置 DASHSCOPE_API_KEY。")

with col_preview:
    st.subheader("📋 提取结果预览")

    if st.session_state.extraction_done and st.session_state.bom_items:
        items = st.session_state.bom_items
        df = pd.DataFrame([it.to_dict() for it in items[:20]])

        column_map = {
            "item_no": "序号", "part_no": "图号", "part_name": "名称",
            "material": "材料", "spec": "规格", "qty": "数量",
            "unit": "单位", "source": "来源",
        }
        display_df = df[[c for c in column_map if c in df.columns]].rename(columns=column_map)
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        if len(items) > 20:
            st.caption(f"…以及更多 {len(items) - 20} 项，请切换到【审核编辑】标签页查看全部")

        cols = st.columns(4)
        cols[0].metric("📄 零件项数", len(items))
        total_qty = sum(it.qty for it in items)
        cols[1].metric("📦 总数量", f"{total_qty:.0f}")
        total_w = sum(it.total_weight for it in items if it.total_weight > 0)
        cols[2].metric("⚖️ 总重量(kg)", f"{total_w:.1f}")
        cols[3].metric("⏱️ AI耗时", f"{st.session_state.processing_time:.1f}s")

        est_manual = len(items) * 0.5
        st.info(
            f"⏱️ **效率对比**：手动录入约 **{est_manual:.0f} 分钟** → AI提取 **{st.session_state.processing_time:.0f} 秒**，"
            f"提升 **{((est_manual - st.session_state.processing_time/60) / est_manual * 100):.0f}%**"
        )

    elif not st.session_state.extraction_done:
        st.info("👆 上传BOM文件并点击「AI智能提取」开始")
        with st.expander("📖 支持的文件类型说明"):
            st.markdown("""
            | 类型 | 说明 | 典型场景 |
            |------|------|----------|
            | 📷 图片 | JPG/PNG/BMP | 拍摄纸质BOM、图纸明细表截图 |
            | 📄 PDF | PDF文档 | 装配图P2明细表、工艺BOM |
            | 📊 Excel | .xlsx/.xls | 已有Excel BOM但需标准化整理 |

            **支持的BOM列**：序号、图号/零件号、名称、材料、规格、数量、单位、备注、单重、总重、来源（自制/外购/标准）
            """)

st.divider()

# ═══════════════════════════════════════════════════════════════
# STEP 3: Review & Edit
# ═══════════════════════════════════════════════════════════════

if st.session_state.extraction_done and st.session_state.bom_items:
    st.subheader("✏️ 审核与编辑")

    tab_review, tab_validate, tab_search, tab_stats = st.tabs(["📝 编辑BOM数据", "🔍 数据校验", "🔄 相似件检索", "📊 统计分析"])

    with tab_review:
        items = st.session_state.bom_items
        if items:
            records = [it.to_dict() for it in items]
            edited_df = st.data_editor(
                pd.DataFrame(records),
                column_config={
                    "item_no": st.column_config.NumberColumn("序号", width="small"),
                    "part_no": st.column_config.TextColumn("图号/零件号", width="medium"),
                    "part_name": st.column_config.TextColumn("零件名称", width="medium", required=True),
                    "material": st.column_config.TextColumn("材料", width="small"),
                    "spec": st.column_config.TextColumn("规格", width="medium"),
                    "qty": st.column_config.NumberColumn("数量", min_value=0.0, format="%.2f", width="small"),
                    "unit": st.column_config.SelectboxColumn("单位", options=["件", "kg", "m", "套", "副", "个", "根", "块"], width="small"),
                    "weight": st.column_config.NumberColumn("单重(kg)", format="%.3f", width="small"),
                    "total_weight": st.column_config.NumberColumn("总重(kg)", format="%.3f", width="small"),
                    "source": st.column_config.SelectboxColumn("来源", options=["自制件", "外购件", "标准件", "外协件", "焊接件", "铸造件", ""], width="small"),
                    "remark": st.column_config.TextColumn("备注", width="large"),
                },
                num_rows="dynamic",
                use_container_width=True,
                height=500,
                key="bom_editor",
            )

            # Sync back
            from src.agent import BOMItem
            new_items = []
            for i, (_, row) in enumerate(edited_df.iterrows()):
                # Skip empty rows
                part_name = row.get("part_name", "")
                part_no = row.get("part_no", "")
                if (pd.isna(part_name) or str(part_name).strip() == "") and (pd.isna(part_no) or str(part_no).strip() == ""):
                    continue
                new_items.append(BOMItem(
                    item_no=i + 1,
                    part_no=str(part_no) if not pd.isna(part_no) else "",
                    part_name=str(part_name) if not pd.isna(part_name) else "",
                    material=str(row.get("material", "")) if not pd.isna(row.get("material", "")) else "",
                    spec=str(row.get("spec", "")) if not pd.isna(row.get("spec", "")) else "",
                    qty=float(row.get("qty", 1.0)) if not pd.isna(row.get("qty", 1.0)) else 1.0,
                    unit=str(row.get("unit", "件")) if not pd.isna(row.get("unit", "件")) else "件",
                    weight=float(row.get("weight", 0.0)) if not pd.isna(row.get("weight", 0.0)) else 0.0,
                    total_weight=float(row.get("total_weight", 0.0)) if not pd.isna(row.get("total_weight", 0.0)) else 0.0,
                    source=str(row.get("source", "")) if not pd.isna(row.get("source", "")) else "",
                    remark=str(row.get("remark", "")) if not pd.isna(row.get("remark", "")) else "",
                ))
            st.session_state.bom_items = new_items

    with tab_validate:
        items = st.session_state.bom_items
        if items:
            if st.button("🔍 运行数据校验", type="primary", use_container_width=True):
                vr = validate_bom(items)
                st.session_state.validation_result = vr

            vr = st.session_state.validation_result
            if vr:
                # Status banner
                if vr.status == "通过":
                    st.success(f"✅ 数据校验通过！质量评分：{vr.score:.0f}/100")
                elif vr.status == "有警告":
                    st.warning(f"⚠️ 发现 {vr.warning_count} 个警告，质量评分：{vr.score:.0f}/100")
                else:
                    st.error(f"❌ 发现 {vr.error_count} 个错误 + {vr.warning_count} 个警告，质量评分：{vr.score:.0f}/100")

                # Metrics
                cols = st.columns(4)
                cols[0].metric("质量评分", f"{vr.score:.0f}/100")
                cols[1].metric("❌ 错误", vr.error_count)
                cols[2].metric("⚠️ 警告", vr.warning_count)
                cols[3].metric("ℹ️ 提示", len(vr.issues) - vr.error_count - vr.warning_count)

                # Issue list
                if vr.issues:
                    st.markdown("---")
                    for issue in vr.issues:
                        icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(issue.level, "•")
                        st.markdown(f"{icon} {issue.message}")
                        if issue.suggestion:
                            st.caption(f"  💡 {issue.suggestion}")
            else:
                st.info("点击上方按钮运行自动校验。校验内容：字段完整性、重量一致性、材料牌号、零件号重复、数量有效性。")
        else:
            st.info("请先提取BOM数据")

    with tab_search:
        items = st.session_state.bom_items
        if items:
            st.markdown("**知识库检索**：从历史BOM数据中查找相似/可复用零件，减少重复设计")

            kb = PartsKnowledgeBase()
            st.caption(f"知识库已收录 {kb.count()} 个历史零件")

            col_btn, col_add = st.columns([1, 1])
            with col_btn:
                if st.button("🔄 检索相似件", type="primary", use_container_width=True):
                    with st.spinner("正在检索..."):
                        summary = search_similar_parts(items, kb)
                        st.session_state.search_summary = summary
                        st.session_state.search_report = get_search_report(summary)

            with col_add:
                if st.button("📥 当前BOM加入知识库", use_container_width=True):
                    project = st.session_state.get("project_name", "")
                    kb.add_parts(items, project=project)
                    st.success(f"已将 {len(items)} 个零件加入知识库（总计 {kb.count()} 个）")

            report = st.session_state.get("search_report")
            if report:
                st.markdown("---")
                cols = st.columns(4)
                cols[0].metric("检索零件数", report["total_queried"])
                cols[1].metric("找到相似件", report["matches_found"])
                cols[2].metric("可复用候选", report["reuse_candidates"])
                cols[3].metric("新零件", report["new_parts_count"])

                if report["matches"]:
                    st.markdown("---")
                    st.subheader("相似件匹配结果")
                    for m in report["matches"]:
                        reuse_icon = "🟢" if m["can_reuse"] else "🟡"
                        with st.expander(
                            f"{reuse_icon} {m['query_name']} → {m['matched_name']} "
                            f"(相似度 {m['score']:.0%})",
                            expanded=m["can_reuse"],
                        ):
                            cols = st.columns(2)
                            cols[0].markdown(f"**当前零件**：{m['query_name']} `{m['query_part_no']}`")
                            cols[1].markdown(f"**历史零件**：{m['matched_name']} `{m['matched_part_no']}`")
                            st.caption(f"匹配原因：{m['match_reason']}")
                            if m["can_reuse"]:
                                st.success(f"可复用：{m['reuse_note']}")
                            else:
                                st.info("需确认规格后决定是否复用")

                if report["new_parts"]:
                    st.markdown("---")
                    st.subheader("新零件（知识库中无匹配）")
                    new_df = pd.DataFrame(report["new_parts"])
                    new_df.columns = ["图号", "名称", "材料"]
                    st.dataframe(new_df, use_container_width=True, hide_index=True)
                    st.caption("这些零件在历史数据中未找到匹配，可能是全新设计。点击上方「当前BOM加入知识库」可将其收录。")
        else:
            st.info("请先提取BOM数据")

    with tab_stats:
        if items:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("零件总数", len(items))
            col2.metric("自制件", sum(1 for it in items if "自制" in it.source))
            col3.metric("外购件", sum(1 for it in items if "外购" in it.source))
            col4.metric("标准件", sum(1 for it in items if "标准" in it.source))

            sources = {}
            for it in items:
                s = it.source or "未分类"
                sources[s] = sources.get(s, 0) + 1
            if sources:
                st.bar_chart(pd.DataFrame({"数量": sources.values()}, index=list(sources.keys())))

            materials = {}
            for it in items:
                if it.material:
                    materials[it.material] = materials.get(it.material, 0) + 1
            if materials:
                with st.expander(f"🏷️ 材料分布（{len(materials)} 种）"):
                    for mat, count in sorted(materials.items(), key=lambda x: -x[1]):
                        st.text(f"  {mat}: {count} 项")

st.divider()

# ═══════════════════════════════════════════════════════════════
# STEP 4: Export
# ═══════════════════════════════════════════════════════════════

if st.session_state.extraction_done and st.session_state.bom_items:
    st.subheader("📥 导出数据")

    col_export, col_time = st.columns([1, 1])

    with col_export:
        items = st.session_state.bom_items
        records = [it.to_dict() for it in items]

        metadata = {
            "project_name": st.session_state.get("project_name", ""),
            "designer": st.session_state.get("designer", ""),
            "date": datetime.date.today().isoformat(),
            "version": st.session_state.get("bom_version", "V1.0"),
        }

        excel_data = generate_bom_excel(records, metadata)
        st.session_state.excel_bytes = excel_data

        erp_data = generate_erp_template(records)
        st.session_state.erp_bytes = erp_data

        today = datetime.date.today().isoformat()
        proj = metadata["project_name"] or "BOM清单"

        st.download_button(
            label=f"📥 下载BOM清单 ({proj}_{today}).xlsx",
            data=excel_data,
            file_name=f"BOM清单_{proj}_{today}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        st.download_button(
            label=f"📤 下载ERP导入模板 ({today}).xlsx",
            data=erp_data,
            file_name=f"ERP导入模板_{today}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        # Copy to clipboard as table
        df = pd.DataFrame(records)
        st.caption(f"共 {len(items)} 项，可直接粘贴到飞书表格/Excel")

        # Feishu push
        st.divider()
        st.subheader("📨 推送飞书通知")
        if st.button("🚀 发送到飞书", use_container_width=True, disabled=not st.session_state.feishu_url):
            vr = st.session_state.validation_result
            status = vr.status if vr else "未校验"
            score = vr.score if vr else 0
            error_count = vr.error_count if vr else 0
            warning_count = vr.warning_count if vr else 0
            item_count = len(items)
            manual_est = item_count * 0.5
            ai_time = st.session_state.processing_time / 60
            saved = max(manual_est - ai_time, 0)

            bot = FeishuBot(webhook_url=st.session_state.feishu_url, secret=st.session_state.feishu_secret)
            success = bot.send_bom_notification(
                project_name=proj,
                item_count=item_count,
                validation_status=status,
                validation_score=score,
                time_saved_minutes=saved * 60,
                error_count=error_count,
                warning_count=warning_count,
            )
            if success:
                st.success("✅ 已推送飞书通知！")
                st.balloons()
            else:
                st.error("推送失败，请检查飞书 Webhook 配置")
        if not st.session_state.feishu_url:
            st.caption("请在左侧边栏配置飞书 Webhook URL")

    with col_time:
        st.subheader("⏱️ 效率分析")

        item_count = len(items)
        manual_est = item_count * 0.5
        ai_time = st.session_state.processing_time / 60
        saved = manual_est - ai_time
        saved_pct = (saved / manual_est * 100) if manual_est > 0 else 0

        cols = st.columns(3)
        cols[0].metric("手动录入", f"{manual_est:.0f} 分钟", delta=None)
        cols[1].metric("AI提取", f"{ai_time:.1f} 分钟", delta=f"-{saved:.0f} 分钟")
        cols[2].metric("效率提升", f"{saved_pct:.0f}%")

        st.divider()

        monthly_saved = saved * 20
        yearly_saved = monthly_saved * 12
        yearly_cost = yearly_saved * 150

        col_m, col_y = st.columns(2)
        col_m.metric("月省时间", f"{monthly_saved:.0f} 小时", delta=f"×20次月")
        col_y.metric("年省时间", f"{yearly_saved:.0f} 小时", delta=f"×12月")

        st.divider()
        st.metric("💎 年节省人工成本", f"¥{yearly_cost:,.0f}", delta="按150元/时计")
        st.caption(f"100人团队年省约 ¥{yearly_cost * 100:,.0f}")

        # Generate comparison report
        comp_bytes = generate_comparison_report(manual_est, ai_time, item_count)
        st.download_button(
            "📊 下载效率对比报告",
            data=comp_bytes,
            file_name=f"效率对比报告_{today}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

elif not st.session_state.extraction_done:
    st.info("👆 上传BOM文件后，此处可导出Excel和ERP模板")

st.divider()
st.caption(
    "🤖 BOM智能提取助手 v1.0 | Powered by Qwen AI + 多Agent协作 | "
    "专为机械设计制造领域打造 | "
    "Made for XPeng 效能跃升·AI开挂 赛题三"
)
