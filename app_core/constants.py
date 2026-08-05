# app_core/constants.py
from enum import Enum, unique

class Currency:
    """既知の通貨コード定数。"""
    CNY = "CNY"
    JPY = "JPY"
    KNOWN = {"CNY", "JPY"}
    BASE = "CNY"


def to_cny(amount: float, currency: str, rates_map: dict) -> float:
    """
    任意通貨の金額を CNY (人民元) に折算。
    """
    if not currency or currency == Currency.CNY:
        return amount
    rate = rates_map.get(currency, 0.0)
    return amount * rate


@unique
class BalanceCategory(str, Enum):
    """貸借対照表カテゴリ"""
    ASSET = "asset"         # 資産
    LIABILITY = "liability" # 負債
    EQUITY = "equity"       # 資本・純資産


class FinanceCategory:
    """財務取引カテゴリ"""
    SALES_INCOME = "销售收入"
    SALES_REFUND = "销售退款"
    COST_GOODS = "商品成本"
    EXCHANGE = "货币兑换"
    DEBT_IN = "借入资金"
    DEBT_ASSET = "债务-资产形成"
    DEBT_REPAY = "债务偿还"
    DEBT_OFFSET = "债务-资产核销"
    ASSET_ADJUST = "资产价值修正"
    
    SYSTEM_GENERATED = {
        DEBT_ASSET, DEBT_OFFSET, ASSET_ADJUST
    }


class StockLogReason:
    """在庫変動理由"""
    OUT_STOCK = "出库"
    IN_INSPECT = "入库验收"
    INSPECT_COMPLETED = "验收完成入库"
    OTHER_IN = "其他入库"
    TRANSFER = "库存移动"
    
    IN_STOCK = "入库"
    PRE_IN = "预入库"
    PRE_IN_REDUCE = "计划入库减少"
    PRE_IN_COMPLETE = "预入库完成"
    EXTRA_PROD = "额外生产入库"
    WAIT_PROD = "排单待产"
    EXTRA_PROD_WAIT = "额外生产待产"
    RETURN_IN = "退货入库"
    UNDO_SHIP = "发货撤销"


class OrderStatus:
    """販売注文ステータス"""
    PENDING = "待发货"
    SHIPPED = "已发货"
    COMPLETED = "订单完成"
    AFTER_SALES = "售后中"
    PRESALE_PENDING_DEPOSIT = "待完成定金"
    PRESALE_PENDING_FINAL = "待付尾款"


class AssetPrefix:
    """自動生成資産プレフィックス"""
    CASH = "流动资金"
    WIP_OFFSET = "在制资产冲销-"
    PRE_STOCK = "预入库大货资产-"
    STOCK = "大货资产-"
    PENDING_SETTLE = "待结算"


PRODUCT_COST_CATEGORIES = [
    "大货材料费", 
    "大货加工费", 
    "物流邮费", 
    "包装费", 
    "设计开发费", 
    "检品发货等人工费", 
    "宣发费", 
    "售后成本",
    "其他成本"
]

PLATFORM_CODES = {
    "weidian": "微店",
    "booth": "Booth",
    "offline_cn": "国内线下",
    "offline_jp": "日本线下",
    "instagram": "Instagram",
    "other": "其他(CNY)",
    "other_jpy": "其他(JPY)"
}

PLATFORM_CURRENCY_MAP = {
    "weidian": Currency.CNY,
    "offline_cn": Currency.CNY,
    "other": Currency.CNY,
    
    "booth": Currency.JPY,
    "offline_jp": Currency.JPY,
    "instagram": Currency.JPY,
    "other_jpy": Currency.JPY
}
