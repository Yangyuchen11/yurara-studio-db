# services/sales_service.py
import pandas as pd
from sqlalchemy import or_
from models import InventoryLog

class SalesService:
    """
    负责销售数据的获取、清洗与聚合逻辑
    """

    @staticmethod
    def get_raw_sales_logs(db):
        """
        获取所有与销售相关的库存日志
        包含：正常销售(is_sold=True) 和 撤销记录(reason="发货撤销")
        """
        return db.query(InventoryLog).filter(
            or_(
                InventoryLog.is_sold == True, 
                InventoryLog.reason == "发货撤销"
            )
        ).order_by(InventoryLog.id.asc()).all()

    @staticmethod
    def process_sales_data(all_logs):
        """
        核心逻辑：将数据库日志对象转换为标准化的销售明细 DataFrame
        处理逻辑包括：
        1. 销售：负数库存转正数销量
        2. 退货：正数库存转负数销量
        3. 撤销：根据历史记录回溯价格和平台，计算冲销金额
        """
        if not all_logs:
            return pd.DataFrame()

        raw_data_list = []
        # 价格记忆器 (Key: Product_Variant, Value: InfoDict)
        last_sold_info = {}

        for log in all_logs:
            p_key = f"{log.product_name}_{log.variant}"
            
            # 提取基础信息
            item = {
                "id": log.id,
                "date": log.date,
                "product": log.product_name,
                "variant": log.variant,
                "platform": log.platform or "其他/未知", # 默认填充
                "currency": log.currency or "CNY",
                "qty": 0,
                "amount": 0.0,
                "type": "unknown"
            }

            # --- A. 销售 (Sale) ---
            if log.is_sold and log.change_amount < 0:
                item["qty"] = -log.change_amount # 负转正
                item["amount"] = log.sale_amount or 0
                item["type"] = "sale"
                
                # 记忆该款式的成交信息，供撤销时回溯
                last_sold_info[p_key] = {
                    "unit_price": (item["amount"] / item["qty"]) if item["qty"] else 0,
                    "currency": item["currency"],
                    "platform": item["platform"]
                }

            # --- B. 退货 (Return) ---
            elif log.is_sold and log.change_amount > 0:
                item["qty"] = -log.change_amount # 正转负
                item["amount"] = log.sale_amount or 0 # 也是负数
                item["type"] = "return"

            # --- C. 撤销 (Undo) ---
            elif log.reason == "发货撤销":
                # 尝试回溯平台信息 (如果日志里没记)
                if item["platform"] == "其他/未知":
                    mem = last_sold_info.get(p_key)
                    if mem: item["platform"] = mem["platform"]
                
                deduct_qty = log.change_amount
                item["qty"] = -deduct_qty # 变成负数，抵消销量
                item["type"] = "undo"
                
                # 计算回滚金额
                if log.sale_amount and log.sale_amount != 0:
                    item["amount"] = -abs(log.sale_amount)
                    item["currency"] = log.currency
                else:
                    # 智能估算
                    mem = last_sold_info.get(p_key)
                    if mem:
                        item["amount"] = -(mem["unit_price"] * deduct_qty)
                        item["currency"] = mem["currency"]
                    else:
                        item["amount"] = 0

            raw_data_list.append(item)

        return pd.DataFrame(raw_data_list)

    @staticmethod
    def get_product_leaderboard(df):
        """
        生成产品销售榜单数据
        """
        if df.empty:
            return pd.DataFrame()
            
        # 按产品聚合
        df_prod_summary = df.groupby('product').agg({
            'amount': lambda x: x[df['currency'] == 'CNY'].sum(), # 简便起见，榜单仅按CNY排序
            'qty': 'sum'
        }).reset_index().rename(columns={'amount': 'CNY总额', 'qty': '净销量'})
        
        return df_prod_summary.sort_values(by='CNY总额', ascending=False)