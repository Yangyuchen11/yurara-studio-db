from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

# --- A. 产品、颜色与成本 ---
class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    total_quantity = Column(Integer, default=0)
    
    # 销售相关
    target_platform = Column(String)
    price_weidian = Column(Float, default=0.0)      # 微店
    price_booth = Column(Float, default=0.0)        # Booth
    price_offline_jp = Column(Float, default=0.0)   # 日本线下
    price_offline_cn = Column(Float, default=0.0)   # 中国线下
    price_instagram = Column(Float, default=0.0)    # ins日本
    price_other_jpy = Column(Float, default=0.0)    # 其他（日本)
    price_other = Column(Float, default=0.0)        # 其他 (中国)
    
    # 关联
    costs = relationship("CostItem", back_populates="product")
    colors = relationship("ProductColor", back_populates="product", cascade="all, delete-orphan")

class ProductColor(Base):
    __tablename__ = "product_colors"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    color_name = Column(String)
    quantity = Column(Integer)
    
    product = relationship("Product", back_populates="colors")

class CostItem(Base):
    __tablename__ = "cost_items"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    item_name = Column(String)
    actual_cost = Column(Float)   # 实付总价
    supplier = Column(String)
    category = Column(String)
    unit_price = Column(Float, default=0.0) # 单价 (预算/参考)
    quantity = Column(Integer, default=1)   # 数量
    remarks = Column(String, default="")    # 备注
    unit = Column(String, default="") # 单位 (如: 米/个)

    finance_record_id = Column(Integer, ForeignKey("finance_records.id"), nullable=True)
    product = relationship("Product", back_populates="costs")

# --- B. 库存变动日志 ---
class InventoryLog(Base):
    __tablename__ = "inventory_logs"
    id = Column(Integer, primary_key=True, index=True)
    product_name = Column(String) 
    variant = Column(String)      
    change_amount = Column(Integer) 
    reason = Column(String)       
    date = Column(Date, default=datetime.now)

# --- C. 财务记录 ---
class FinanceRecord(Base):
    __tablename__ = "finance_records"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date)
    amount = Column(Float)    
    currency = Column(String, default="CNY") 
    category = Column(String) 
    description = Column(String)

# class FixedAsset(Base):
#     __tablename__ = "fixed_assets"
#     id = Column(Integer, primary_key=True, index=True)
#     name = Column(String)
#     purchase_price = Column(Float)
#     purchase_date = Column(Date)
#     description = Column(String)

# --- D. 公司账面/资产负债 ---
class CompanyBalanceItem(Base):
    __tablename__ = "company_balance_items"
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String) # 分类：asset(资产), liability(债务), equity(资本)
    name = Column(String)     # 项目名：如“现金(CNY账户)”
    amount = Column(Float)    # 金额
    currency = Column(String, default="CNY") # 币种：CNY 或 JPY

# --- E. 固定资产管理 ---
class FixedAsset(Base):
    __tablename__ = "fixed_assets_detail" # 表名
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)           # 项目名称
    unit_price = Column(Float)      # 单价
    quantity = Column(Integer)      # 制作数量/购入数量
    remaining_qty = Column(Integer) # 剩余数量
    shop_name = Column(String)      # 店名
    remarks = Column(String)        # 备注
    purchase_date = Column(Date, default=datetime.now)
    currency = Column(String, default="CNY") # 默认为人民币资产

    finance_record_id = Column(Integer, ForeignKey("finance_records.id"), nullable=True)

# --- F. 耗材/消耗品管理 ---
class ConsumableItem(Base):
    __tablename__ = "consumable_items"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)           # 项目名称 (如: 飞机盒)
    category = Column(String)       # 分类 (如: 包装/赠品/办公)
    unit_price = Column(Float)      # 单价 (通过 总价/数量 计算得出)
    initial_quantity = Column(Integer) # 初始购入数量
    remaining_qty = Column(Integer)    # 剩余数量 (动态变动)
    shop_name = Column(String)      # 供应商
    remarks = Column(String)        # 备注
    purchase_date = Column(Date, default=datetime.now)

    finance_record_id = Column(Integer, ForeignKey("finance_records.id"), nullable=True)

# --- G. 固定资产核销记录 ---
class FixedAssetLog(Base):
    __tablename__ = "fixed_asset_logs"
    id = Column(Integer, primary_key=True, index=True)
    asset_name = Column(String)      # 资产名称
    decrease_qty = Column(Integer)   # 核销/减少数量
    reason = Column(String)          # 核销原因 (损坏/丢失/报废)
    date = Column(Date, default=datetime.now)