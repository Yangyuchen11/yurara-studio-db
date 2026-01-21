from enum import Enum, unique

# ==========================================
# 1. 基础枚举 (Enums) - 用于类型判断和强约束
# ==========================================

@unique
class Currency(str, Enum):
    """支持的货币类型"""
    CNY = "CNY"
    JPY = "JPY"

@unique
class BalanceCategory(str, Enum):
    """资产负债表分类"""
    ASSET = "asset"         # 资产
    LIABILITY = "liability" # 负债
    EQUITY = "equity"       # 权益/资本

# ==========================================
# 2. 业务常量 - 财务与流水相关
# ==========================================

class FinanceCategory:
    """财务流水分类 (对应 FinanceRecord.category)"""
    SALES_INCOME = "销售收入"
    SALES_REFUND = "销售退款"
    COST_GOODS = "商品成本"
    EXCHANGE = "货币兑换"
    DEBT_IN = "借入资金"
    DEBT_ASSET = "债务-资产形成"
    DEBT_REPAY = "债务偿还"
    DEBT_OFFSET = "债务-资产核销"
    ASSET_ADJUST = "资产价值修正"
    
    # 集合：用于判断是否属于系统自动生成的特殊流水
    SYSTEM_GENERATED = {
        DEBT_ASSET, DEBT_OFFSET, ASSET_ADJUST
    }

# ==========================================
# 3. 业务常量 - 库存与生产相关
# ==========================================

class StockLogReason:
    """库存变动原因 (对应 InventoryLog.reason)"""
    IN_STOCK = "入库"
    OUT_STOCK = "出库"
    PRE_IN = "预入库"
    PRE_IN_REDUCE = "计划入库减少"
    PRE_IN_COMPLETE = "预入库完成"
    EXTRA_PROD = "额外生产入库"
    RETURN_IN = "退货入库"
    UNDO_SHIP = "发货撤销"

class AssetPrefix:
    """自动生成的资产名称前缀 (用于 Logic Key 匹配)"""
    CASH = "流动资金"
    WIP_OFFSET = "在制资产冲销-"      # 对应 services/inventory_service.py
    PRE_STOCK = "预入库大货资产-"    # 对应 services/inventory_service.py
    STOCK = "大货资产-"             # 对应 services/inventory_service.py
    PENDING_SETTLE = "待结算"       # 销售出库时的临时资产

# ==========================================
# 4. 配置列表与映射 (Lists & Maps)
# ==========================================

# 成本分类 (原 InventoryService.COST_CATEGORIES)
PRODUCT_COST_CATEGORIES = [
    "大货材料费", 
    "大货加工费", 
    "物流邮费", 
    "包装费", 
    "设计开发费", 
    "检品发货等人工费", 
    "宣发费", 
    "其他成本"
]

# 销售平台代号 (原 ProductService 中的硬编码)
PLATFORM_CODES = {
    "weidian": "微店",
    "booth": "展会/Booth",
    "offline_cn": "国内线下",
    "offline_jp": "日本线下",
    "instagram": "Instagram",
    "other": "其他(CNY)",
    "other_jpy": "其他(JPY)"
}

# 平台与默认币种的映射关系 (用于自动判断币种)
PLATFORM_CURRENCY_MAP = {
    "weidian": Currency.CNY,
    "offline_cn": Currency.CNY,
    "other": Currency.CNY,
    
    "booth": Currency.JPY,
    "offline_jp": Currency.JPY,
    "instagram": Currency.JPY,
    "other_jpy": Currency.JPY
}