import streamlit as st
import pandas as pd
import io
import zipfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import (
    Product, ProductColor, InventoryLog,
    FinanceRecord, CostItem,
    FixedAsset, FixedAssetLog,
    ConsumableItem, ConsumableLog, 
    CompanyBalanceItem, PreShippingItem, 
    SystemSetting, ProductPrice,
    SalesOrder, SalesOrderItem, OrderRefund 
)
from database import Base
from views.product_view import show_product_page
from views.cost_view import show_cost_page
from views.inventory_view import show_inventory_page
from views.finance_view import show_finance_page
from views.balance_view import show_balance_page
from views.asset_view import show_asset_page
from views.consumable_view import show_other_asset_page
from views.sales_view import show_sales_page
from views.sales_order_view import show_sales_order_page
from streamlit_option_menu import option_menu
import os

# === 1. 页面配置 (必须放在第一行) ===
st.set_page_config(page_title="Yurara综合管理系统", layout="wide")

# ==========================================
# === 登录认证 ===
# ==========================================

def check_login():
    if st.session_state.get("authenticated", False):
        return True

    st.header("🔒 Yurara Studio 系统登录")
    
    with st.form("login_form"):
        user_input = st.text_input("用户名")
        pwd_input = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录", type="primary")
        
        if submitted:
            try:
                all_creds = st.secrets["credentials"]
                found = False
                
                for key, cred_config in all_creds.items():
                    if "username" in cred_config and "password" in cred_config:
                        if user_input == cred_config["username"] and pwd_input == cred_config["password"]:
                            st.session_state.authenticated = True
                            st.session_state.current_user_name = cred_config["username"] 
                            st.success(f"欢迎回来，{user_input}！")
                            st.rerun()
                            found = True
                            break
                
                if not found:
                    st.error("用户名或密码错误")
            
            except KeyError:
                st.error("Secrets 配置错误：找不到 [credentials] 节点")
            except Exception as e:
                st.error(f"登录发生未知错误: {e}")
                
    return False

if not check_login():
    st.stop()

# ==========================================
# === 2. 数据库连接与测试环境隔离 ===
# ==========================================

# 初始化测试模式状态
if "test_mode" not in st.session_state:
    st.session_state.test_mode = False

@st.cache_resource
def get_real_engine():
    """获取真实数据库连接 (Supabase)"""
    try:
        # 1. 优先尝试从环境变量读取 (Zeabur 云端环境)
        db_url = os.getenv("DATABASE_URL")
        
        # 2. 如果环境变量没有，再尝试从本地 secrets.toml 读取 (本地测试环境)
        if not db_url:
            db_url = st.secrets["database"]["DATABASE_URL"]
            
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return create_engine(db_url, pool_pre_ping=True)
    except Exception as e:
        st.error(f"真实数据库连接初始化失败: {e}")
        return None

@st.cache_resource
def get_test_engine():
    """获取测试数据库连接 (本地 SQLite)"""
    # check_same_thread=False 是 Streamlit 多线程访问 SQLite 所必需的
    return create_engine("sqlite:///yurara_test_env.db", pool_pre_ping=True, connect_args={"check_same_thread": False})

# 根据当前是否处于测试模式选择不同的数据库引擎
engine = get_test_engine() if st.session_state.test_mode else get_real_engine()

if not engine:
    st.stop()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# === 全局表映射，用于备份和测试环境克隆 ===
TABLES_MAP = [
    ("products.csv", "products", Product),
    ("product_colors.csv", "product_colors", ProductColor),
    ("product_prices.csv", "product_prices", ProductPrice),
    ("finance_records.csv", "finance_records", FinanceRecord),
    ("cost_items.csv", "cost_items", CostItem),
    ("inventory_logs.csv", "inventory_logs", InventoryLog),
    ("fixed_assets.csv", "fixed_assets_detail", FixedAsset),
    ("fixed_asset_logs.csv", "fixed_asset_logs", FixedAssetLog),
    ("consumables.csv", "consumable_items", ConsumableItem),
    ("consumable_logs.csv", "consumable_logs", ConsumableLog),
    ("company_balance.csv", "company_balance_items", CompanyBalanceItem),
    ("pre_shipping_items.csv", "pre_shipping_items", PreShippingItem),
    ("sales_orders.csv", "sales_orders", SalesOrder),
    ("sales_order_items.csv", "sales_order_items", SalesOrderItem),
    ("order_refunds.csv", "order_refunds", OrderRefund),
]

# 初始化表结构 (会自动建在当前绑定的引擎上)
Base.metadata.create_all(bind=engine)

# === 辅助函数：获取/保存系统设置 ===
def get_system_setting(db, key, default_value=""):
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not setting:
        setting = SystemSetting(key=key, value=str(default_value))
        db.add(setting)
        db.commit()
    return setting.value

def set_system_setting(db, key, new_value):
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting:
        setting.value = str(new_value)
    else:
        setting = SystemSetting(key=key, value=str(new_value))
        db.add(setting)
    db.commit()

# ==========================================
# === 3. 侧边栏与业务路由 ===
# ==========================================

db = next(get_db())

with st.sidebar:
    current_user = st.session_state.get("current_user_name", "Unknown")
    
    # 顶部状态栏：醒目的测试环境提示
    if st.session_state.test_mode:
        st.error("🧪 **测试环境已开启**\n\n当前操作仅写入本地沙盒库，不会影响真实数据。")
    else:
        st.caption(f"当前账号: {current_user}")
        
    if st.button("退出登录"):
        st.session_state.authenticated = False
        st.rerun()

    selected = option_menu(
        menu_title="Yurara Studio",
        menu_icon="dataset",
        options=[
            "财务流水录入",
            "公司账面概览",
            "商品管理",
            "商品成本核算",
            "销售订单管理",
            "库存管理",
            "销售额一览",
            "固定资产管理",
            "其他资产管理"
        ],
        icons=[
            "currency-yen",
            "clipboard-data",
            "bag-heart",
            "calculator",
            "cart-check",
            "arrow-left-right",
            "graph-up-arrow",
            "camera-reels",
            "box-seam"
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
    db_rate_str = get_system_setting(db, "exchange_rate", "4.8")
    rate_input = st.number_input(
        "汇率 (100 JPY 兑 CNY)", 
        value=float(db_rate_str), 
        step=0.1, 
        format="%.2f",
        key="global_rate_widget" 
    )
    if abs(rate_input - float(db_rate_str)) > 0.001:
        set_system_setting(db, "exchange_rate", rate_input)
        st.toast(f"汇率已更新: {rate_input}", icon="💾")
        st.rerun()
    exchange_rate = rate_input / 100.0

    # === 备份/恢复 ===
    st.divider()
    with st.popover("💾 数据备份与恢复", width="stretch"):
        # 下载全量备份
        zip_buffer = io.BytesIO()
        try:
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                for file_name, _, model_cls in TABLES_MAP:
                    try:
                        df_export = pd.read_sql(db.query(model_cls).statement, db.bind)
                        csv_bytes = df_export.to_csv(index=False).encode('utf-8-sig')
                        zf.writestr(file_name, csv_bytes)
                    except Exception as e:
                        pass
            st.download_button("⬇️ 下载全量备份 (ZIP)", data=zip_buffer.getvalue(), file_name="yurara_backup.zip", mime="application/zip")
        except Exception as e:
            st.error(f"导出错误: {e}")

        st.divider()
        
        # 导入备份
        uploaded_file = st.file_uploader("上传备份 ZIP", type="zip")
        if uploaded_file and st.button("🔴 确认导入"):
            try:
                with zipfile.ZipFile(uploaded_file) as zf:
                    for file_name, table_name, _ in TABLES_MAP:
                        if file_name in zf.namelist():
                            with zf.open(file_name) as f:
                                df_import = pd.read_csv(f, encoding='utf-8-sig')
                                if not df_import.empty:
                                    df_import.to_sql(table_name, engine, if_exists='append', index=False)
                                    st.toast(f"已导入 {table_name}")
                
                if "postgres" in str(engine.url):
                    from sqlalchemy import text
                    with engine.connect() as conn:
                        for _, table_name, _ in TABLES_MAP:
                            try:
                                conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), coalesce(max(id),0) + 1, false) FROM {table_name};"))
                            except Exception:
                                pass 
                        conn.commit()
                        
                st.success("恢复完成")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"导入错误: {e}")

    # === 清空所有数据 ===
    with st.popover("🔴 清空当前环境数据", width="stretch"):
        env_name = "测试环境" if st.session_state.test_mode else "真实环境"
        st.error(f"⚠️ **警告**：此操作将删除【{env_name}】的所有业务数据！")
        
        confirm_input = st.text_input("请输入确认口令", placeholder="输入 DELETE 以确认")
        
        if st.button("💣 确认清空", type="primary", disabled=(confirm_input != "DELETE"), width="stretch"):
            try:
                # 按照依赖关系顺序删除
                db.query(ProductColor).delete()
                db.query(CostItem).delete()
                db.query(FixedAsset).delete()
                db.query(ConsumableItem).delete()
                db.query(PreShippingItem).delete() 
                db.query(SalesOrderItem).delete() 
                db.query(OrderRefund).delete() 

                db.query(InventoryLog).delete()
                db.query(FixedAssetLog).delete()
                db.query(ConsumableLog).delete()   
                db.query(CompanyBalanceItem).delete()

                db.query(Product).delete()
                db.query(FinanceRecord).delete()
                db.query(SalesOrder).delete() 
                
                db.commit()
                st.session_state["toast_msg"] = ("数据已清空！表结构已保留。", "🧹")
                
                for key in list(st.session_state.keys()):
                    if key not in ['authenticated', 'current_user_name', 'global_rate_input', 'test_mode']:
                        del st.session_state[key]
                st.rerun()
            except Exception as e:
                db.rollback()
                st.error(f"清空失败: {e}")

    # ==========================================
    # === 新增：环境切换按钮 (放置在左下角) ===
    # ==========================================
    st.markdown("<br><br>", unsafe_allow_html=True) # 撑开一点间距，使其靠下
    st.divider()
    
    test_mode_toggle = st.toggle(
        "🧪 **开启测试环境**", 
        value=st.session_state.test_mode, 
        help="开启后，系统会复制当前的真实数据。你在测试环境的任何操作均不会影响线上数据。"
    )

    if test_mode_toggle != st.session_state.test_mode:
        if test_mode_toggle:
            # 切换到测试环境：执行数据复制
            with st.spinner("正在从真实环境复制数据到沙盒，请稍候..."):
                real_engine = get_real_engine()
                test_engine = get_test_engine()
                
                # 1. 清空并重建测试环境的表结构
                Base.metadata.drop_all(bind=test_engine)
                Base.metadata.create_all(bind=test_engine)
                
                # 2. 从真实库拉取数据写入测试库
                real_db = sessionmaker(bind=real_engine)()
                try:
                    for _, table_name, model_cls in TABLES_MAP:
                        try:
                            # 提取整表数据
                            df_sync = pd.read_sql(real_db.query(model_cls).statement, real_db.bind)
                            if not df_sync.empty:
                                # 写入 SQLite 测试库 (利用 pandas 自动处理 ID 映射)
                                df_sync.to_sql(table_name, test_engine, if_exists='append', index=False)
                        except Exception as e:
                            pass # 忽略某张空表的异常
                finally:
                    real_db.close()
            
            st.session_state.test_mode = True
            st.rerun()
        else:
            # 返回真实环境
            st.session_state.test_mode = False
            st.rerun()

# --- 路由分发 ---
if selected == "商品管理":
    show_product_page(db)
elif selected == "商品成本核算":
    show_cost_page(db)
elif selected == "库存管理":
    show_inventory_page(db)
elif selected == "销售订单管理":
    show_sales_order_page(db)
elif selected == "销售额一览":
    show_sales_page(db)
elif selected == "财务流水录入":
    show_finance_page(db, exchange_rate)
elif selected == "公司账面概览":
    show_balance_page(db, exchange_rate)
elif selected == "固定资产管理":
    show_asset_page(db, exchange_rate)
elif selected == "其他资产管理":
    show_other_asset_page(db, exchange_rate)