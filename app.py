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
    ConsumableItem, ConsumableLog,  # 确保包含耗材日志
    CompanyBalanceItem, PreShippingItem, # 【新增】预出库表
    SystemSetting,
)

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

# === 辅助函数：获取/保存系统设置 ===
def get_system_setting(db, key, default_value=""):
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not setting:
        # 如果不存在，初始化一个默认值
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
from views.asset_view import show_asset_page
from views.consumable_view import show_other_asset_page
from views.sales_view import show_sales_page
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
            "财务流水录入",
            "公司账面概览",  
            "商品管理", 
            "商品成本核算", 
            "销售额一览",
            "库存管理", 
            "固定资产管理", 
            "其他资产管理"
        ],
        icons=[
            "currency-yen", 
            "clipboard-data", 
            "bag-heart", 
            "calculator", 
            "graph-up-arrow",
            "arrow-left-right", 
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

    # === 新的数据库持久化汇率代码 ===
    st.divider()
    st.markdown("### 💱 全局汇率设置")
    
    # 1. 从数据库读取当前存储的汇率 (默认 4.8)
    # 注意：db 是你在主程序上方定义的数据库会话
    db_rate_str = get_system_setting(db, "exchange_rate", "4.8")
    
    # 2. 显示输入框
    rate_input = st.number_input(
        "汇率 (100 JPY 兑 CNY)", 
        value=float(db_rate_str), 
        step=0.1, 
        format="%.2f",
        key="global_rate_widget" # 给个key防止重绘丢失焦点
    )
    
    # 3. 如果用户修改了数值，保存回数据库
    # 浮点数比较需要容错，或者简单的比较字符串
    if abs(rate_input - float(db_rate_str)) > 0.001:
        set_system_setting(db, "exchange_rate", rate_input)
        st.toast(f"汇率已更新并永久保存: {rate_input}", icon="💾")
        # 稍微延迟一下或者直接 rerun 刷新整个页面的计算
        st.rerun()

    # 4. 设置全局变量供后续页面使用
    exchange_rate = rate_input / 100.0

# === 备份/恢复 ===
    st.divider()
    with st.popover("💾 数据备份与恢复", use_container_width=True):
        # 定义映射: (CSV文件名, 数据库表名, SQLAlchemy模型类)
        # 【修改点】加入了 pre_shipping_items 和 consumable_logs
        tables_map = [
            ("products.csv", "products", Product),
            ("product_colors.csv", "product_colors", ProductColor),
            ("finance_records.csv", "finance_records", FinanceRecord),
            ("cost_items.csv", "cost_items", CostItem),
            ("inventory_logs.csv", "inventory_logs", InventoryLog),
            ("fixed_assets.csv", "fixed_assets_detail", FixedAsset),
            ("fixed_asset_logs.csv", "fixed_asset_logs", FixedAssetLog),
            ("consumables.csv", "consumable_items", ConsumableItem),
            ("consumable_logs.csv", "consumable_logs", ConsumableLog),
            ("company_balance.csv", "company_balance_items", CompanyBalanceItem),
            ("pre_shipping_items.csv", "pre_shipping_items", PreShippingItem), 
        ]
        
        # 下载逻辑
        zip_buffer = io.BytesIO()
        try:
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                for file_name, _, model_cls in tables_map:
                    try:
                        df = pd.read_sql(db.query(model_cls).statement, db.bind)
                        csv_bytes = df.to_csv(index=False).encode('utf-8-sig')
                        zf.writestr(file_name, csv_bytes)
                    except Exception as e:
                        pass # 忽略空表
            st.download_button("⬇️ 下载全量备份 (ZIP)", data=zip_buffer.getvalue(), file_name="yurara_backup.zip", mime="application/zip")
        except Exception as e:
            st.error(f"导出错误: {e}")

        st.divider()
        
        # 上传逻辑
        uploaded_file = st.file_uploader("上传备份 ZIP", type="zip")
        if uploaded_file and st.button("🔴 确认导入"):
            try:
                with zipfile.ZipFile(uploaded_file) as zf:
                    for file_name, table_name, _ in tables_map:
                        if file_name in zf.namelist():
                            with zf.open(file_name) as f:
                                df = pd.read_csv(f, encoding='utf-8-sig')
                                if not df.empty:
                                    df.to_sql(table_name, engine, if_exists='append', index=False)
                                    st.toast(f"已导入 {table_name}")
                
                # Postgres 序列重置逻辑 (防止ID冲突)
                if "postgres" in str(engine.url):
                    from sqlalchemy import text
                    with engine.connect() as conn:
                        for _, table_name, _ in tables_map:
                            try:
                                conn.execute(text(f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), coalesce(max(id),0) + 1, false) FROM {table_name};"))
                            except Exception:
                                pass 
                        conn.commit()
                        
                st.success("恢复完成")
                st.rerun()
            except Exception as e:
                st.error(f"导入错误: {e}")

    # ==========================================
    # === 清空所有数据 ===
    # ==========================================

    with st.popover("🔴 清空所有数据 (保留表结构)", use_container_width=True):
        st.error("⚠️ **严重警告**：此操作将删除所有业务数据！但会保留数据库表结构。")
        st.markdown("请务必先点击上方的 **⬇️ 下载全量备份** 以防万一。")
        
        confirm_input = st.text_input("请输入确认口令", placeholder="输入 DELETE 以确认")
        
        if st.button("💣 确认清空", type="primary", disabled=(confirm_input != "DELETE"), use_container_width=True):
            try:
                # 按照依赖关系顺序删除 (先删子表，再删主表)
                
                # 1. 删除关联表/子表
                db.query(ProductColor).delete()
                db.query(CostItem).delete()        
                db.query(FixedAsset).delete()      
                db.query(ConsumableItem).delete()
                db.query(PreShippingItem).delete() # 【新增】
                
                # 2. 删除日志表/独立表
                db.query(InventoryLog).delete()
                db.query(FixedAssetLog).delete()
                db.query(ConsumableLog).delete()   # 【新增】
                db.query(CompanyBalanceItem).delete()
                
                # 3. 删除主表 (父表)
                db.query(Product).delete()
                db.query(FinanceRecord).delete()
                
                db.commit()
                
                st.session_state["toast_msg"] = ("数据已清空！表结构已保留。", "🧹")
                
                # 清除缓存状态
                for key in list(st.session_state.keys()):
                    if key not in ['authenticated', 'current_user_name', 'global_rate_input']:
                        del st.session_state[key]
                
                st.rerun()
                
            except Exception as e:
                db.rollback()
                st.error(f"清空失败: {e}")

# 路由分发 (保持不变)
if selected == "商品管理":
    show_product_page(db)
elif selected == "商品成本核算":
    show_cost_page(db)
elif selected == "库存管理":
    show_inventory_page(db) # 只显示库存
elif selected == "销售额一览":
    show_sales_page(db)     # 新增页面
elif selected == "财务流水录入":
    show_finance_page(db, exchange_rate)
elif selected == "公司账面概览":
    show_balance_page(db, exchange_rate)
elif selected == "固定资产管理":
    show_asset_page(db, exchange_rate)
elif selected == "其他资产管理":
    show_other_asset_page(db, exchange_rate)