import streamlit as st
import pandas as pd
import io
import zipfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# === 1. 页面配置 (必须放在第一行) ===
st.set_page_config(page_title="Yurara综合管理系统", layout="wide")

# ==========================================
# === 【修改 1】: 登录认证 (只做身份验证) ===
# ==========================================

def check_login():
    """
    功能：验证 secrets.toml [credentials] 中的账号密码
    """
    if st.session_state.get("authenticated", False):
        return True

    st.header("🔒 Yurara Studio 系统登录")
    
    with st.form("login_form"):
        user_input = st.text_input("用户名")
        pwd_input = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录", type="primary")
        
        if submitted:
            try:
                # 获取所有凭证配置
                all_creds = st.secrets["credentials"]
                found = False
                
                # 遍历字典查找匹配的用户
                for key, cred_config in all_creds.items():
                    # 防御性编程：确保字段存在
                    if "username" in cred_config and "password" in cred_config:
                        if user_input == cred_config["username"] and pwd_input == cred_config["password"]:
                            st.session_state.authenticated = True
                            # 只需要存当前是谁登录了，不需要存数据库配置了
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
# === 【修改 2】: 统一使用 Master URL 连接数据库 ===
# ==========================================

@st.cache_resource
def get_engine():
    """
    不管是谁登录，统一使用 secrets.toml [database] 中的 URL 连接
    """
    try:
        # 1. 读取主连接字符串
        db_url = st.secrets["database"]["DATABASE_URL"]
        
        # 2. 修正 SQLAlchemy 协议头 (如果原链接是 postgres:// 则改为 postgresql+psycopg2://)
        # 这样可以确保使用 psycopg2 驱动，避免一些兼容性问题
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif db_url.startswith("postgresql://"):
             # 确保显式指定驱动
            db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

        # 3. 创建引擎
        # pool_pre_ping=True: 自动处理连接断开重连
        engine = create_engine(db_url, pool_pre_ping=True)
        return engine

    except Exception as e:
        st.error(f"数据库连接初始化失败: {e}")
        return None

# 获取数据库引擎 (不再需要传入用户信息)
engine = get_engine()

# 如果连接失败则停止
if not engine:
    st.stop()

# 创建 Session 工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# === 3. 业务逻辑 (基本保持不变) ===
# ==========================================
from database import Base 
# 引入模型
from models import (
    Product, ProductColor, InventoryLog, 
    FinanceRecord, CostItem, 
    FixedAsset, FixedAssetLog, 
    ConsumableItem, CompanyBalanceItem
)
# 引入视图
from views.product_view import show_product_page
from views.cost_view import show_cost_page
from views.inventory_view import show_inventory_page
from views.finance_view import show_finance_page
from views.balance_view import show_balance_page
from views.asset_view import show_fixed_asset_page
from views.consumable_view import show_consumable_page
from streamlit_option_menu import option_menu

# 初始化表结构
Base.metadata.create_all(bind=engine)

# 获取会话
db = next(get_db())

# --- 侧边栏 ---
with st.sidebar:
    # 显示当前登录的前端用户
    current_user = st.session_state.get("current_user_name", "Unknown")
    st.caption(f"当前账号: {current_user}")
    
    if st.button("退出登录"):
        st.session_state.authenticated = False
        st.rerun()

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

    # === 汇率 ===
    st.divider()
    st.markdown("### 💱 全局汇率设置")
    if "global_rate_input" not in st.session_state:
        st.session_state.global_rate_input = 4.8
    rate_input = st.number_input(
        "汇率 (100 JPY 兑 CNY)", 
        value=st.session_state.global_rate_input, 
        step=0.1, format="%.2f"
    )
    st.session_state.global_rate_input = rate_input
    exchange_rate = rate_input / 100.0

    # === 备份/恢复 (代码复用之前写好的逻辑) ===
    st.divider()
    with st.expander("💾 数据备份与恢复"):
        # ... (此处保持你原来的备份恢复代码不变) ...
        # 注意：这里也是直接使用 engine 和 db，无需修改
        
        # 定义映射
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
        
        # 下载逻辑
        zip_buffer = io.BytesIO()
        try:
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                for file_name, table_name, model_cls in tables_map:
                    try:
                        df = pd.read_sql(db.query(model_cls).statement, db.bind)
                        csv_bytes = df.to_csv(index=False).encode('utf-8-sig')
                        zf.writestr(file_name, csv_bytes)
                    except Exception as e:
                        pass # 忽略空表错误
            st.download_button("⬇️ 下载全量备份 (ZIP)", data=zip_buffer.getvalue(), file_name="yurara_backup.zip", mime="application/zip")
        except Exception as e:
            st.error(f"导出错误: {e}")

        st.divider()
        # 上传逻辑
        uploaded_file = st.file_uploader("上传备份 ZIP", type="zip")
        if uploaded_file and st.button("🔴 确认导入"):
            try:
                with zipfile.ZipFile(uploaded_file) as zf:
                    for file_name, table_name, model_cls in tables_map:
                        if file_name in zf.namelist():
                            with zf.open(file_name) as f:
                                df = pd.read_csv(f, encoding='utf-8-sig')
                                if not df.empty:
                                    df.to_sql(table_name, engine, if_exists='append', index=False)
                                    st.toast(f"已导入 {table_name}")
                st.success("恢复完成")
                st.rerun()
            except Exception as e:
                st.error(f"导入错误: {e}")

# 路由分发 (保持不变)
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