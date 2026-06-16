# yurara_app/state/sales_state.py
"""
销售数据透视 State 模块。
支持 V2.0 订单精准版 与 V1.0 历史兼容版 Tab 分页数据加载，
提供全局销量额汇总、商品销售热卖榜单排序、款式平台交叉透视以及 Recharts 堆叠图序列生成。
"""
import reflex as rx
import pandas as pd
from pydantic import BaseModel
from typing import Any
from ..state.app_state import AppState
from services.sales_service import SalesService
from constants import to_cny


class SalesLeaderboardRow(BaseModel):
    product_name: str = ""
    grand_total_cny: float = 0.0
    total_cny: float = 0.0
    total_jpy: float = 0.0


class SalesLogItem(BaseModel):
    id: str = ""
    date: str = ""
    type_label: str = ""  # 📤 售出, ↩️ 退货入库, etc.
    variant: str = ""
    qty: float = 0.0
    platform: str = ""
    amount: float = 0.0
    currency: str = ""


class VariantPivotRow(BaseModel):
    variant: str = ""
    qtys_by_platform: dict[str, int] = {}
    total_qty: int = 0


class PlatformSale(BaseModel):
    name: str = ""
    qty: int = 0
    pct_str: str = ""
    color: str = ""


class VariantSaleChartData(BaseModel):
    variant: str = ""
    total_qty: int = 0
    platforms: list[PlatformSale] = []


class SalesState(AppState):
    active_tab: str = "v2"  # "v2" 或 "v1"
    is_loading: bool = True
    _cached_df: Any = None
    
    # 汇总卡片数值
    total_cny: float = 0.0
    total_jpy: float = 0.0
    grand_total_cny: float = 0.0
    total_qty: float = 0.0
    
    # 列表与热卖榜
    leaderboard: list[SalesLeaderboardRow] = []
    
    # 深度分析商品选中状态
    selected_product: str = ""
    
    # 选中商品的指标卡
    p_net_qty: float = 0.0
    p_cny_equiv: float = 0.0
    p_active_platforms: int = 0
    
    # 交叉透视表表头与明细
    pivot_headers: list[str] = []
    pivot_rows: list[VariantPivotRow] = []
    pivot_platforms: list[str] = []
    
    # 堆叠直方图数据 (List of VariantSaleChartData)
    chart_data: list[VariantSaleChartData] = []
    
    # 变动日志及真分页状态
    logs: list[SalesLogItem] = []
    page: int = 1
    total_pages: int = 1
    total_rows: int = 0

    # ===================== 计算属性 =====================

    @rx.var
    def total_cny_str(self) -> str:
        return f"¥ {self.total_cny:,.2f}"

    @rx.var
    def total_jpy_str(self) -> str:
        return f"¥ {self.total_jpy:,.0f}"

    @rx.var
    def grand_total_cny_str(self) -> str:
        return f"¥ {self.grand_total_cny:,.2f}"

    @rx.var
    def total_qty_str(self) -> str:
        return f"{int(self.total_qty)} 件"

    @rx.var
    def p_net_qty_str(self) -> str:
        return f"{int(self.p_net_qty)} 件"

    @rx.var
    def p_cny_equiv_str(self) -> str:
        return f"¥ {self.p_cny_equiv:,.2f}"

    @rx.var
    def p_active_platforms_str(self) -> str:
        return f"{self.p_active_platforms} 个"

    @rx.var
    def leaderboard_is_empty(self) -> bool:
        return len(self.leaderboard) == 0

    @rx.var
    def has_selected_product(self) -> bool:
        return self.selected_product != ""

    @rx.var
    def logs_is_empty(self) -> bool:
        return len(self.logs) == 0

    @rx.var
    def product_names_list(self) -> list[str]:
        return [r.product_name for r in self.leaderboard]

    # ===================== 事件处理器 =====================

    @rx.event
    def set_tab(self, tab_name: str):
        """切换精准订单 Tab / 历史数据 Tab 并重新加载"""
        self.active_tab = tab_name
        self.selected_product = ""
        self.leaderboard = []
        self.page = 1
        self._cached_df = None  # 清除缓存以加载新 Tab 数据
        yield SalesState.load_sales_data()

    @rx.event
    def load_sales_data(self):
        """从后端服务加载全局销售指标和商品热卖榜单"""
        self.is_loading = True
        self._cached_df = None  # 全量重新加载时清除缓存
        db = self.get_db()
        try:
            # 1. 抓取 pandas DataFrame 源数据 (基于缓存机制)
            if self.active_tab == "v2":
                df = SalesService.process_sales_data_v2(db)
            else:
                raw_logs = SalesService.get_raw_sales_logs_v1(db)
                df = SalesService.process_sales_data_v1(db, raw_logs)
            
            self._cached_df = df  # 缓存抓取到的数据
                
            if df.empty:
                self.total_cny = 0.0
                self.total_jpy = 0.0
                self.grand_total_cny = 0.0
                self.total_qty = 0.0
                self.leaderboard = []
                self.selected_product = ""
                return

            # 2. 算全局销售指标
            total_cny_val = df[df['currency'] == 'CNY']['amount'].sum()
            self.total_cny = round(float(total_cny_val), 2)
            self.total_jpy = 0.0
            
            # calculate grand_total_cny by folding all rows using to_cny:
            grand_total = 0.0
            for _, r in df.iterrows():
                amt = float(r['amount'])
                curr = str(r['currency'])
                grand_total += to_cny(amt, curr, self.rates_map)
                
            self.grand_total_cny = round(grand_total, 2)
            self.total_qty = round(float(df['qty'].sum()), 2)

            # 3. 统计产品热卖排行榜
            df_prod_summary = SalesService.get_product_leaderboard(df, self.rates_map)
            leader_list = []
            for _, row in df_prod_summary.iterrows():
                leader_list.append(SalesLeaderboardRow(
                    product_name=str(row['product']),
                    grand_total_cny=round(float(row['折合CNY总额']), 2),
                    total_cny=round(float(row.get('CNY总额', 0.0)), 2),
                    total_jpy=round(float(row.get('JPY总额', 0.0)), 2)
                ))
            self.leaderboard = leader_list

            # 4. 默认选中排在第一位的商品进行深入分析
            if self.leaderboard and not self.selected_product:
                yield SalesState.select_product(self.leaderboard[0].product_name)

        finally:
            db.close()
            self.is_loading = False

    @rx.event
    def select_product(self, product_name: str):
        """选中某个特定产品，拉取并结算其销量明细、交叉表、柱状图及日志"""
        self.selected_product = product_name
        self.page = 1
        yield SalesState.load_selected_product_details()

    @rx.event
    def load_selected_product_details(self):
        """深度结算当前选中商品的一切销量构成"""
        db = self.get_db()
        try:
            if self._cached_df is not None:
                df = self._cached_df
            else:
                if self.active_tab == "v2":
                    df = SalesService.process_sales_data_v2(db)
                else:
                    raw_logs = SalesService.get_raw_sales_logs_v1(db)
                    df = SalesService.process_sales_data_v1(db, raw_logs)
                self._cached_df = df
                
            if df.empty or not self.selected_product:
                return

            df_p = df[df['product'] == self.selected_product].copy()
            if df_p.empty:
                self.p_net_qty = 0.0
                self.p_cny_equiv = 0.0
                self.p_active_platforms = 0
                self.pivot_headers = []
                self.pivot_rows = []
                self.pivot_platforms = []
                self.chart_data = []
                self.logs = []
                return

            # 1. 销量/销售额折合/活跃平台数
            self.p_net_qty = round(float(df_p['qty'].sum()), 2)
            
            p_grand_total = 0.0
            for _, r in df_p.iterrows():
                p_grand_total += to_cny(float(r['amount']), str(r['currency']), self.rates_map)
            self.p_cny_equiv = round(p_grand_total, 2)
            self.p_active_platforms = int(df_p[df_p['qty'] != 0]['platform'].nunique())

            # 2. 款式-平台交叉透视数据构建 (完全动态列)
            from models import SalesPlatform
            plats = db.query(SalesPlatform).order_by(SalesPlatform.id.asc()).all()
            self.pivot_headers = ["款式"] + [p.name for p in plats] + ["总计"]
            self.pivot_platforms = [p.name for p in plats]

            plat_name_by_code_or_name = {}
            for p in plats:
                plat_name_by_code_or_name[p.code.lower()] = p.name
                plat_name_by_code_or_name[p.name.lower()] = p.name

            df_p = df_p.copy()
            df_p['plat_display_name'] = df_p['platform'].apply(lambda x: plat_name_by_code_or_name.get(str(x).lower(), str(x)))

            var_sums = df_p.groupby(['variant', 'plat_display_name'])['qty'].sum().to_dict()
            var_totals = df_p.groupby('variant')['qty'].sum().to_dict()

            p_rows = []
            for var in df_p['variant'].unique():
                qtys_by_plat = {p.name: 0 for p in plats}
                for p in plats:
                    qty_val = int(var_sums.get((var, p.name), 0))
                    qtys_by_plat[p.name] = qty_val
                total_qty = int(var_totals.get(var, 0))
                
                p_rows.append(VariantPivotRow(
                    variant=str(var),
                    qtys_by_platform=qtys_by_plat,
                    total_qty=total_qty
                ))

            # Bottom total row
            total_qtys_by_plat = {p.name: 0 for p in plats}
            for p in plats:
                col_sum = int(df_p[df_p['plat_display_name'] == p.name]['qty'].sum())
                total_qtys_by_plat[p.name] = col_sum
            grand_total_qty = int(df_p['qty'].sum())

            p_rows.append(VariantPivotRow(
                variant="总计",
                qtys_by_platform=total_qtys_by_plat,
                total_qty=grand_total_qty
            ))
            self.pivot_rows = p_rows

            # 3. 产生适用于 CSS 堆叠条形图的数据字典序列
            c_data = []
            color_palette = [
                "var(--violet-9)",
                "var(--crimson-9)",
                "var(--blue-9)",
                "var(--jade-9)",
                "var(--pink-9)",
                "var(--amber-9)",
                "var(--orange-9)",
                "var(--teal-9)",
                "var(--indigo-9)",
                "var(--ruby-9)",
                "var(--grass-9)",
            ]
            plat_colors = {}
            for idx, p in enumerate(plats):
                plat_colors[p.name] = color_palette[idx % len(color_palette)]

            for var in df_p['variant'].unique():
                var_df = df_p[df_p['variant'] == var]
                total_qty = int(var_df['qty'].sum())
                if total_qty <= 0:
                    continue
                    
                platform_list = []
                for p in plats:
                    qty = int(var_df[var_df['plat_display_name'] == p.name]['qty'].sum())
                    if qty > 0:
                        pct = (qty / total_qty) * 100
                        platform_list.append(PlatformSale(
                            name=p.name,
                            qty=qty,
                            pct_str=f"{pct:.1f}%",
                            color=plat_colors.get(p.name, "var(--slate-9)")
                        ))
                if platform_list:
                    c_data.append(VariantSaleChartData(
                        variant=str(var),
                        total_qty=total_qty,
                        platforms=platform_list
                    ))
            self.chart_data = c_data

            # 4. 产生 paginated 变动流水明细
            df_logs_all = df_p.sort_values(by='id', ascending=False) if 'id' in df_p.columns else df_p.copy()
            self.total_rows = len(df_logs_all)
            self.total_pages = max(1, (self.total_rows + 19) // 20)
            
            if self.page > self.total_pages:
                self.page = self.total_pages
            
            start_idx = (self.page - 1) * 20
            end_idx = self.page * 20
            df_slice = df_logs_all.iloc[start_idx:end_idx]

            log_items = []
            for _, row in df_slice.iterrows():
                t = row['type']
                if t == 'sale':
                    lbl = "📤 售出"
                elif t == 'return':
                    lbl = "↩️ 退货入库"
                elif t == 'refund':
                    lbl = "💸 仅退款"
                else:
                    lbl = "🔙 撤销"

                log_items.append(SalesLogItem(
                    id=str(row.get('id', '')),
                    date=str(row['date']),
                    type_label=lbl,
                    variant=str(row.get('variant', '')),
                    qty=round(float(row.get('qty', 0.0)), 2),
                    platform=plat_name_by_code_or_name.get(str(row.get('platform', '')).lower(), str(row.get('platform', ''))),
                    amount=round(float(row.get('amount', 0.0)), 2),
                    currency=str(row.get('currency', 'CNY'))
                ))
            self.logs = log_items

        finally:
            db.close()

    @rx.event
    def change_log_page(self, delta: int):
        """翻页查看特定产品的销量变动流水记录"""
        new_page = self.page + delta
        if 1 <= new_page <= self.total_pages:
            self.page = new_page
            yield SalesState.load_selected_product_details()
