from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

# --- A. 产品、颜色与成本 ---
class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    total_quantity = Column(Integer, default=0)

    # 可销售数量 (用于成本核算的分母，可变动)
    marketable_quantity = Column(Integer, default=0)
    # 销售相关
    target_platform = Column(String)
    
    # 【优化1】移除硬编码的价格字段 (price_weidian, price_booth 等)
    # 它们现在通过 prices 关系表来管理
    
    # 关联
    # 【优化2】在 Python 层面配置级联删除 (cascade="all, delete-orphan")
    costs = relationship("CostItem", back_populates="product", cascade="all, delete-orphan")
    colors = relationship("ProductColor", back_populates="product", cascade="all, delete-orphan")

class ProductColor(Base):
    __tablename__ = "product_colors"
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"))
    color_name = Column(String)
    quantity = Column(Integer)
    produced_quantity = Column(Integer, default=0)
    
    product = relationship("Product", back_populates="colors")
    # 【新增】颜色关联价格
    prices = relationship("ProductPrice", back_populates="color", cascade="all, delete-orphan")

class ProductPrice(Base):
    __tablename__ = "product_prices"
    id = Column(Integer, primary_key=True, index=True)
    color_id = Column(Integer, ForeignKey("product_colors.id", ondelete="CASCADE")) 
    platform = Column(String) 
    currency = Column(String) 
    price = Column(Float, default=0.0)
    
    # 【修改】反向关联指向 color
    color = relationship("ProductColor", back_populates="prices")

class CostItem(Base):
    __tablename__ = "cost_items"
    id = Column(Integer, primary_key=True, index=True)
    # 【优化3】数据库级联删除
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"))
    item_name = Column(String)
    actual_cost = Column(Float)   # 实付总价
    supplier = Column(String)
    category = Column(String)
    unit_price = Column(Float, default=0.0) # 单价 (预算/参考)
    quantity = Column(Float, default=1)   # 数量
    remarks = Column(String, default="")    # 备注
    unit = Column(String, default="") # 单位 (如: 米/个)
    order_no = Column(String, nullable=True) # 【新增】订单号 (用于售后成本)

    # 关联流水 (删除流水时自动清理关联的成本项)
    finance_record_id = Column(Integer, ForeignKey("finance_records.id", ondelete="CASCADE"), nullable=True)
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
    note = Column(String, nullable=True)
    is_sold = Column(Boolean, default=False) # 是否为售出
    sale_amount = Column(Float, default=0.0) # 销售总额
    currency = Column(String, nullable=True) # 币种
    platform = Column(String, nullable=True) # 销售平台
    is_other_out = Column(Boolean, default=False) # 是否为其他出库

# --- C. 财务记录 ---
class FinanceRecord(Base):
    __tablename__ = "finance_records"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date)
    amount = Column(Float)    
    currency = Column(String, default="CNY") 
    category = Column(String) 
    description = Column(String)

# --- D. 公司账面/资产负债 ---
class CompanyBalanceItem(Base):
    __tablename__ = "company_balance_items"
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String) # 分类：asset(资产), liability(债务), equity(资本)
    name = Column(String)     # 项目名：如“现金(CNY账户)”
    amount = Column(Float)    # 金额
    currency = Column(String, default="CNY") # 币种：CNY 或 JPY
    # 【数据库级联删除
    finance_record_id = Column(Integer, ForeignKey("finance_records.id", ondelete="CASCADE"), nullable=True)

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

    # 【优化3】数据库级联删除
    finance_record_id = Column(Integer, ForeignKey("finance_records.id", ondelete="CASCADE"), nullable=True)

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
    currency = Column(String, default="CNY")

    # 【优化3】数据库级联删除
    finance_record_id = Column(Integer, ForeignKey("finance_records.id", ondelete="CASCADE"), nullable=True)

# --- G. 固定资产核销记录 ---
class FixedAssetLog(Base):
    __tablename__ = "fixed_asset_logs"
    id = Column(Integer, primary_key=True, index=True)
    asset_name = Column(String)      # 资产名称
    decrease_qty = Column(Integer)   # 核销/减少数量
    reason = Column(String)          # 核销原因 (损坏/丢失/报废)
    date = Column(Date, default=datetime.now)

# --- H. 耗材变动日志 ---
class ConsumableLog(Base):
    __tablename__ = "consumable_logs"
    id = Column(Integer, primary_key=True, index=True)
    item_name = Column(String)       # 耗材名称
    change_qty = Column(Integer)     # 变动数量 (正数为补货，负数为消耗)
    value_cny = Column(Float)        # 变动价值 (折合CNY)
    date = Column(Date, default=datetime.now)
    note = Column(String)            # 备注

# --- I. 预出库管理表 ---
class PreShippingItem(Base):
    __tablename__ = "pre_shipping_items"
    id = Column(Integer, primary_key=True, index=True)
    product_name = Column(String)
    variant = Column(String)
    quantity = Column(Integer)
    # 预售信息
    pre_sale_amount = Column(Float) # 填写的预售额
    currency = Column(String)       # 币种
    # 关联的债务ID (用于出库时核销)
    related_debt_id = Column(Integer, nullable=True)
    created_date = Column(Date, default=datetime.now)
    note = Column(String, default="")

# --- J. 系统全局设置 ---
class SystemSetting(Base):
    __tablename__ = "system_settings"
    key = Column(String, primary_key=True, index=True) # 例如 "exchange_rate"
    value = Column(String) # 存为字符串，使用时再转换类型
    description = Column(String, nullable=True)

# --- K. 销售订单管理 ---
class SalesOrder(Base):
    __tablename__ = "sales_orders"
    id = Column(Integer, primary_key=True, index=True)
    order_no = Column(String, unique=True, index=True) # 订单号
    status = Column(String, default="待发货") # 状态: 待发货/已发货/订单完成/售后中
    total_amount = Column(Float, default=0.0) # 订单总金额
    currency = Column(String, default="CNY") # 币种
    platform = Column(String) # 销售平台

    # 时间节点
    created_date = Column(Date, default=datetime.now) # 创建日期
    shipped_date = Column(Date, nullable=True) # 发货日期
    completed_date = Column(Date, nullable=True) # 完成日期

    notes = Column(String, default="") # 备注

    # 关联
    items = relationship("SalesOrderItem", back_populates="order", cascade="all, delete-orphan")
    refunds = relationship("OrderRefund", back_populates="order", cascade="all, delete-orphan")

class SalesOrderItem(Base):
    __tablename__ = "sales_order_items"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("sales_orders.id", ondelete="CASCADE"))

    product_name = Column(String) # 商品名称
    variant = Column(String) # 款式/颜色
    quantity = Column(Integer) # 数量
    unit_price = Column(Float) # 单价
    subtotal = Column(Float) # 小计 (quantity * unit_price)

    # 关联
    order = relationship("SalesOrder", back_populates="items")

class OrderRefund(Base):
    __tablename__ = "order_refunds"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("sales_orders.id", ondelete="CASCADE"))

    refund_amount = Column(Float) # 退款金额
    refund_reason = Column(String) # 退款原因
    refund_date = Column(Date, default=datetime.now) # 退款日期

    is_returned = Column(Boolean, default=False) # 是否退货
    returned_quantity = Column(Integer, default=0) # 退货数量

    # 关联到成本项 (售后成本)
    cost_item_id = Column(Integer, ForeignKey("cost_items.id", ondelete="SET NULL"), nullable=True)

    # 关联
    order = relationship("SalesOrder", back_populates="refunds")
