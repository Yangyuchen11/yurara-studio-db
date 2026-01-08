import streamlit as st
import pandas as pd
import io
import zipfile
from database import engine, Base, get_db
from sqlalchemy import text

# 引入所有模型以便导出 (确保 models.py 中包含这些类)
from models import (
    Product, ProductColor, InventoryLog, 
    FinanceRecord, CostItem, 
    FixedAsset, FixedAssetLog, 
    ConsumableItem, CompanyBalanceItem
)

# 引入各个页面视图
from views.product_view import show_product_page
from views.cost_view import show_cost_page
from views.inventory_view import show_inventory_page
from views.finance_view import show_finance_page
from views.balance_view import show_balance_page
from views.asset_view import show_fixed_asset_page
from views.consumable_view import show_consumable_page
from streamlit_option_menu import option_menu

# 初始化数据库表
Base.metadata.create_all(bind=engine)

# 页面配置
st.set_page_config(page_title="Yurara综合管理系统", layout="wide")

# 获取数据库会话
db = next(get_db())

# --- 侧边栏配置 ---
with st.sidebar:
    selected = option_menu(
        menu_title="Yurara Studio",
        menu_icon="dataset",
        options=[
            "公司资产一览", "财务流水录入", "商品管理", 
            "库存管理", "成本核算", "固定资产管理", "耗材管理"
        ],
        icons=[
            "clipboard-data", "currency-yen", "bag-heart", 
            "arrow-left-right", "calculator", "camera-reels", "box-seam"
        ],
        default_index=0,
        styles={
            "container": {"padding": "5px", "background-color": "#262730"},
            "icon": {"color": "#555", "font-size": "18px"}, 
            "nav-link": {"font-size": "14px", "text-align": "left", "margin": "5px", "--hover-color": "#7284aa"},
            "nav-link-selected": {"background-color": "#263c54", "color": "white", "font-weight": "normal"},
        }
    )

    # === 全局汇率设置 ===
    st.divider()
    st.markdown("### 💱 全局汇率设置")
    st.caption("基准: 100 JPY 兑 CNY")
    
    if "global_rate_input" not in st.session_state:
        st.session_state.global_rate_input = 4.8

    rate_input = st.number_input(
        "汇率", 
        value=st.session_state.global_rate_input, 
        step=0.1, 
        format="%.2f", 
        label_visibility="collapsed"
    )
    st.session_state.global_rate_input = rate_input
    exchange_rate = rate_input / 100.0
    st.info(f"当前: 1 JPY ≈ {exchange_rate:.3f} CNY")

    # ==========================================
    # === 新增：数据备份与恢复 (导入/导出) ===
    # ==========================================
    st.divider()
    with st.expander("💾 数据备份与恢复", expanded=False):
        
        # 定义表与模型的映射 (顺序很重要：先父后子)
        tables_map = [
            ("products.csv", "products", Product),
            ("finance_records.csv", "finance_records", FinanceRecord),
            ("product_colors.csv", "product_colors", ProductColor),
            ("cost_items.csv", "cost_items", CostItem),
            ("inventory_logs.csv", "inventory_logs", InventoryLog),
            ("fixed_assets.csv", "fixed_assets", FixedAsset),
            ("fixed_asset_logs.csv", "fixed_asset_logs", FixedAssetLog),
            ("consumables.csv", "consumables", ConsumableItem),
            ("company_balance.csv", "company_balance", CompanyBalanceItem),
        ]

        st.caption("📥 **导出数据**")
        # --- 导出逻辑 (修改版：支持 UTF-8-SIG) ---
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for file_name, table_name, model_cls in tables_map:
                try:
                    df = pd.read_sql(db.query(model_cls).statement, db.bind)
                    # === 关键修改：转换为带 BOM 的 UTF-8 字节流 ===
                    # 这样 Excel 打开才不会乱码
                    csv_bytes = df.to_csv(index=False).encode('utf-8-sig')
                    zf.writestr(file_name, csv_bytes)
                except Exception as e:
                    print(f"Skipping {table_name}: {e}")

        st.download_button(
            label="⬇️ 下载全量备份 (ZIP)",
            data=zip_buffer.getvalue(),
            file_name="yurara_backup.zip",
            mime="application/zip",
            use_container_width=True
        )

        st.divider()
        st.caption("📤 **导入恢复**")
        st.warning("⚠️ 警告：导入操作是【追加】模式。如需完全恢复备份，建议先清空数据库（可手动删除 .db 文件）。")
        
        # --- 导入逻辑 (修改版：指定编码) ---
        uploaded_file = st.file_uploader("上传备份 ZIP", type="zip")
        if uploaded_file is not None:
            if st.button("🔴 确认导入数据", type="primary", use_container_width=True):
                try:
                    with zipfile.ZipFile(uploaded_file) as zf:
                        for file_name, table_name, model_cls in tables_map:
                            if file_name in zf.namelist():
                                with zf.open(file_name) as f:
                                    # === 关键修改：指定 encoding='utf-8-sig' ===
                                    # 确保能正确读取带 BOM 的 CSV
                                    df = pd.read_csv(f, encoding='utf-8-sig')
                                    if not df.empty:
                                        # 注意：导入时如果包含 'id' 列，可能会与现有自增 ID 冲突。
                                        # 如果是空库导入没问题。如果是追加导入，建议去掉 ID 列或由数据库处理。
                                        # 这里为了完全恢复备份，我们保留 ID。
                                        df.to_sql(table_name, engine, if_exists='append', index=False)
                                        st.toast(f"已导入: {table_name} ({len(df)}条)", icon="✅")
                    
                    st.success("数据恢复完成！")
                    st.rerun()
                except Exception as e:
                    st.error(f"导入失败: {e}")
                    st.caption("常见原因：ID冲突（尝试导入已存在的数据）或 表结构不匹配。")

# 为了兼容路由逻辑
menu = selected

# 路由分发
if selected == "商品管理":
    show_product_page(db)

elif selected == "成本核算":
    show_cost_page(db)

elif selected == "库存管理":
    show_inventory_page(db)

elif selected == "财务流水录入":
    show_finance_page(db, exchange_rate)

elif selected == "公司资产一览":
    show_balance_page(db, exchange_rate)

elif selected == "固定资产管理":
    show_fixed_asset_page(db)

elif selected == "耗材管理":
    show_consumable_page(db)