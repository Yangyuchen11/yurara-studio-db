import discord
from discord import ui
from datetime import date
from typing import Optional

# 导入工具
from bot_src.utils import run_db_task

# 导入业务逻辑
from services.finance_service import FinanceService
from services.inventory_service import InventoryService
from services.balance_service import BalanceService
from services.product_service import ProductService
from services.cost_service import CostService
from services.sales_service import SalesService
from services.consumable_service import ConsumableService
from constants import Currency, PRODUCT_COST_CATEGORIES

# ==========================================
# === 第一部分：记账相关组件 (Modals & Selects) ===
# ==========================================

# --- 1. 普通支出 Modal ---
class SimpleExpenseModal(ui.Modal, title="记一笔 - 普通支出"):
    amount = ui.TextInput(label="金额", placeholder="例如: 100.50", required=True)
    currency = ui.TextInput(label="币种 (CNY/JPY)", default="CNY", min_length=3, max_length=3, required=True)
    category = ui.TextInput(label="分类", placeholder="如: 交通费, 餐饮, 运营杂费", required=True)
    content = ui.TextInput(label="内容/备注", placeholder="具体说明", required=True)
    shop = ui.TextInput(label="店铺/来源", placeholder="选填", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await _handle_expense_submit(interaction, self, "normal")

# --- 2. 商品成本 Modal ---
class CostExpenseModal(ui.Modal, title="记一笔 - 商品成本"):
    def __init__(self, product_id, product_name, cost_category):
        super().__init__()
        self.product_id = product_id
        self.cost_category = cost_category
        # 动态标题，显示当前分类
        self.title = f"{cost_category}: {product_name[:10]}..."
    
    amount = ui.TextInput(label="实付金额", placeholder="例如: 500", required=True)
    currency = ui.TextInput(label="币种 (CNY/JPY)", default="CNY", min_length=3, max_length=3, required=True)
    shop = ui.TextInput(label="店铺/来源", placeholder="选填", required=False)
    content = ui.TextInput(label="具体内容", placeholder="如: 布料", required=True)
    qty = ui.TextInput(label="数量", default="1", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        extra_data = {
            "product_id": self.product_id,
            "cost_cat": self.cost_category,
            "qty": self.qty.value
        }
        await _handle_expense_submit(interaction, self, "cost", extra_data)

# --- 成本分类选择 View ---
class CostCategorySelect(ui.Select):
    def __init__(self, product_id, product_name):
        self.product_id = product_id
        self.product_name = product_name
        
        # 从常量加载选项
        options = []
        for cat in PRODUCT_COST_CATEGORIES:
            options.append(discord.SelectOption(label=cat, value=cat))
            
        super().__init__(placeholder="👇 请选择成本分类...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):

        selected_cat = self.values[0]
        await interaction.response.send_modal(
            CostExpenseModal(self.product_id, self.product_name, selected_cat)
        )

class CostCategorySelectView(ui.View):
    def __init__(self, product_id, product_name):
        super().__init__()
        self.add_item(CostCategorySelect(product_id, product_name))

# --- 3. 资产购入 Modal ---
class AssetExpenseModal(ui.Modal, title="记一笔 - 资产购入"):
    def __init__(self, asset_type):
        super().__init__()
        self.asset_type = asset_type
        type_name = "固定资产" if asset_type == 'fixed_asset' else "耗材/其他资产"
        self.title = f"资产购入: {type_name}"

    amount = ui.TextInput(label="总价", placeholder="例如: 2000", required=True)
    currency = ui.TextInput(label="币种 (CNY/JPY)", default="CNY", min_length=3, max_length=3, required=True)
    name = ui.TextInput(label="资产名称", placeholder="如: 打印机 / 飞机盒", required=True)
    shop = ui.TextInput(label="店铺/来源", placeholder="如: 淘宝/京东", required=False)
    qty = ui.TextInput(label="数量", default="1", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        extra_data = {"link_type": self.asset_type, "qty": self.qty.value}
        await _handle_expense_submit(interaction, self, "asset", extra_data)

# --- 通用提交处理逻辑 ---
async def _handle_expense_submit(interaction, modal, mode, extra_data=None):
    try:
        try:
            amt_val = float(modal.amount.value)
        except ValueError:
            await interaction.response.send_message("❌ 金额必须是数字", ephemeral=True)
            return
        
        curr_val = modal.currency.value.upper()
        if curr_val not in ["CNY", "JPY"]:
            await interaction.response.send_message("❌ 币种只能是 CNY 或 JPY", ephemeral=True)
            return

        base_data = {
            "date": date.today(),
            "type": "支出",
            "currency": curr_val,
            "amount": amt_val,
            "category": "",
            "shop": getattr(modal, 'shop', type('obj', (object,), {'value': ''})).value or "Discord Bot",
            "desc": getattr(modal, 'content', type('obj', (object,), {'value': ''})).value
        }
        
        link_config = {"link_type": None, "name": base_data["desc"], "qty": 1.0, "unit_price": 0.0}

        if mode == "normal":
            base_data["category"] = modal.category.value
            link_config["name"] = modal.content.value
        elif mode == "cost":
            base_data["category"] = extra_data["cost_cat"]
            link_config["link_type"] = "cost"
            link_config["product_id"] = extra_data["product_id"]
            link_config["name"] = modal.content.value
            try:
                q = float(extra_data["qty"])
                link_config["qty"] = q
                link_config["unit_price"] = amt_val / q if q else 0
            except: pass
        elif mode == "asset":
            base_data["category"] = "固定资产购入" if extra_data["link_type"] == 'fixed_asset' else "其他资产购入"
            link_config["link_type"] = extra_data["link_type"]
            link_config["name"] = modal.name.value
            try:
                q = float(extra_data["qty"])
                link_config["qty"] = q
                link_config["unit_price"] = amt_val / q if q else 0
            except: pass
            if extra_data["link_type"] == 'consumable':
                link_config["cat"] = "其他"

        exchange_rate = 0.048
        def logic(db):
            return FinanceService.create_general_transaction(db, base_data, link_config, exchange_rate)

        await interaction.response.defer(ephemeral=True)
        msg = await run_db_task(logic)
        await interaction.followup.send(f"✅ **记账成功!**\n💸 **{amt_val} {curr_val}** - {base_data['category']}\n📝 {link_config['name']}\n⚙️ {msg}", ephemeral=True)

    except Exception as e:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ 系统错误: {str(e)}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ 系统错误: {str(e)}", ephemeral=True)

# --- 记账类型选择 View ---
class ExpenseTypeSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="普通支出", description="交通、餐饮、运营杂费等", emoji="💸", value="normal"),
            discord.SelectOption(label="商品成本", description="面料、加工、物流等 (需关联商品)", emoji="🧵", value="cost"),
            discord.SelectOption(label="固定资产", description="设备、工具等长期资产", emoji="🏢", value="fixed"),
            discord.SelectOption(label="耗材/其他资产", description="包装、赠品、办公用品", emoji="📦", value="consumable"),
        ]
        super().__init__(placeholder="请选择支出类型...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "normal": await interaction.response.send_modal(SimpleExpenseModal())
        elif val == "fixed": await interaction.response.send_modal(AssetExpenseModal('fixed_asset'))
        elif val == "consumable": await interaction.response.send_modal(AssetExpenseModal('consumable'))
        elif val == "cost":
            await interaction.response.defer(ephemeral=True)
            def logic(db): return ProductService(db).get_all_products()
            try:
                products = await run_db_task(logic)
                if not products:
                    await interaction.followup.send("⚠️ 暂无商品数据。", ephemeral=True)
                    return
                view = ProductSelectForCostView(products)
                await interaction.followup.send("👇 请选择该笔成本归属的商品：", view=view, ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ 失败: {e}", ephemeral=True)

class ExpenseTypeSelectView(ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(ExpenseTypeSelect())

# --- 记账用商品选择 View (不需要实时库存) ---
class ProductSelectForCost(ui.Select):
    def __init__(self, products):
        options = []
        for p in products[:25]:
            options.append(discord.SelectOption(label=p.name[:25], value=f"{p.id}|{p.name}"))
        super().__init__(placeholder="选择归属商品...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        pid, pname = val.split("|")
        view = CostCategorySelectView(int(pid), pname)
        await interaction.response.send_message(
            f"✅ 已选商品：**{pname}**\n👇 请继续选择成本分类：", 
            view=view, 
            ephemeral=True
        )

class ProductSelectForCostView(ui.View):
    def __init__(self, products):
        super().__init__()
        self.add_item(ProductSelectForCost(products))


# ==========================================
# === 第二部分：库存查询组件 (已修复库存显示) ===
# ==========================================

class StockSelect(ui.Select):
    """
    用于库存查询的下拉菜单
    """
    def __init__(self, product_data_list):
        # product_data_list 是 (product_obj, real_qty_int) 的列表
        options = []
        for p, qty in product_data_list:
            # 根据库存数量显示不同emoji
            icon = "🟢" if qty > 0 else "🔴"
            options.append(discord.SelectOption(
                label=p.name[:25], 
                value=f"{p.id}|{p.name}",
                description=f"现货库存: {qty} (点击查看详情)",
                emoji=icon
            ))
        
        if not options:
            options.append(discord.SelectOption(label="暂无商品", value="none"))

        super().__init__(placeholder="🔍 请选择要查询库存的商品...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("没有商品数据", ephemeral=True)
            return

        val = self.values[0]
        _, pname = val.split("|") # 只需要名字来查库存
        
        await interaction.response.defer(ephemeral=True)

        def logic(db):
            service = InventoryService(db)
            real, pre_in, _, _ = service.get_stock_overview(pname)
            return pname, real, pre_in

        try:
            p_name, real_stock, pre_in = await run_db_task(logic)
            
            # 构建显示结果
            embed = discord.Embed(title=f"📦 库存查询: {p_name}", color=discord.Color.green())
            
            # 现货部分
            real_str = ""
            total_real = 0
            for v, q in real_stock.items():
                if q != 0:
                    icon = "🟢" if q > 5 else ("🟡" if q > 0 else "🔴")
                    real_str += f"{icon} **{v}**: {int(q)}\n"
                    total_real += q
            
            embed.add_field(name="✅ 现货在库", value=real_str or "💨 暂无现货", inline=True)
            
            # 预入库部分
            pre_in_str = ""
            for v, q in pre_in.items():
                if q > 0:
                    pre_in_str += f"⚙️ **{v}**: {int(q)}\n"
            
            if pre_in_str:
                embed.add_field(name="🏭 生产中/预入库", value=pre_in_str, inline=True)
                
            embed.set_footer(text=f"现货总计: {int(total_real)} 件")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 查询出错: {e}", ephemeral=True)

class StockSelectView(ui.View):
    def __init__(self, product_data_list):
        super().__init__()
        self.add_item(StockSelect(product_data_list))


# ==========================================
# === 第三部分：产品透视组件 (Dashboard) ===
# ==========================================

class ProductDashboardView(ui.View):
    def __init__(self, product_id, product_name):
        super().__init__(timeout=600)
        self.product_id = product_id
        self.product_name = product_name

    async def update_display(self, interaction: discord.Interaction, embed: discord.Embed):
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="基础信息", style=discord.ButtonStyle.primary, emoji="📋")
    async def info_btn(self, interaction: discord.Interaction, button: ui.Button):
        def logic(db): return ProductService(db).get_product_by_id(self.product_id)
        prod = await run_db_task(logic)
        embed = discord.Embed(title=f"📋 商品详情: {prod.name}", color=discord.Color.blue())
        embed.add_field(name="平台", value=prod.target_platform or "无", inline=True)
        embed.add_field(name="总生产数", value=str(prod.total_quantity), inline=True)
        
        prices_list = []
        if prod.colors:
            seen_prices = set()
            for c in prod.colors:
                if c.prices:
                    for p in c.prices:
                        # 格式化显示：平台: 价格 币种
                        p_str = f"{p.platform}: {p.price} {p.currency}"
                        # 简单去重：如果不同颜色的同平台定价一致，只显示一次
                        if p_str not in seen_prices:
                            prices_list.append(p_str)
                            seen_prices.add(p_str)
        
        prices_str = "\n".join(prices_list)
        embed.add_field(name="定价", value=prices_str or "未设置", inline=False)
        
        colors_str = " | ".join([f"{c.color_name}({c.quantity})" for c in prod.colors])
        embed.add_field(name="规格", value=colors_str or "无", inline=False)
        await self.update_display(interaction, embed)

    @ui.button(label="成本分析", style=discord.ButtonStyle.blurple, emoji="💰")
    async def cost_btn(self, interaction: discord.Interaction, button: ui.Button):
        def logic(db):
            service = CostService(db)
            return service.get_cost_items(self.product_id), service.get_product_by_name(self.product_name)
        
        # 获取成本项和商品信息
        items, prod = await run_db_task(logic)
        
        # 1. 计算分母 (可销售数量)
        denom = prod.marketable_quantity if (prod and prod.marketable_quantity) else (prod.total_quantity if prod else 0)
        if denom == 0: denom = 1 # 防止除零
        
        # 2. 聚合数据 (按分类)
        cat_data = {}
        total_actual = 0
        
        for i in items:
            cat = i.category or "其他"
            if cat not in cat_data:
                cat_data[cat] = {"actual": 0.0, "budget": 0.0}
            
            # 实付累加
            cat_data[cat]["actual"] += i.actual_cost
            total_actual += i.actual_cost
            
            # 预算累加 (仅统计明确标记为预算的条目)
            if i.supplier == "预算设定":
                cat_data[cat]["budget"] += (i.unit_price * i.quantity)

        # 3. 构建显示
        unit_total = total_actual / denom
        embed = discord.Embed(title=f"💰 成本分析: {self.product_name}", color=discord.Color.gold())
        embed.description = f"**总实际投入**: ¥{total_actual:,.2f}\n**单品实际成本**: ¥{unit_total:,.2f}\n(核算数量: {denom})"
        
        # 排序分类 (按常量定义的顺序)
        sorted_cats = [c for c in PRODUCT_COST_CATEGORIES if c in cat_data]
        for c in cat_data:
            if c not in sorted_cats: sorted_cats.append(c)
        
        # 添加字段
        for cat in sorted_cats:
            d = cat_data[cat]
            act = d["actual"]
            bud = d["budget"]
            
            # 如果都没有数据则跳过
            if act == 0 and bud == 0: continue
            
            act_unit = act / denom
            bud_unit = bud / denom
            
            content = (
                f"小计实付: ¥{act:,.2f}\n"
                f"实付单价: ¥{act_unit:,.2f}\n"
                f"小计预算: ¥{bud:,.2f}\n"
                f"预算单价: ¥{bud_unit:,.2f}"
            )
            embed.add_field(name=f"🔹 {cat}", value=content, inline=True)
            
        await self.update_display(interaction, embed)

    @ui.button(label="库存状态", style=discord.ButtonStyle.blurple, emoji="📦")
    async def stock_btn(self, interaction: discord.Interaction, button: ui.Button):
        def logic(db): return InventoryService(db).get_stock_overview(self.product_name)
        real, pre, _, _ = await run_db_task(logic)
        embed = discord.Embed(title=f"📦 库存: {self.product_name}", color=discord.Color.green())
        embed.add_field(name="✅ 现货", value="\n".join([f"**{k}**: {int(v)}" for k,v in real.items() if v!=0]) or "无", inline=True)
        embed.add_field(name="🏭 生产中", value="\n".join([f"**{k}**: {int(v)}" for k,v in pre.items() if v>0]) or "无", inline=True)
        await self.update_display(interaction, embed)

    @ui.button(label="销售统计", style=discord.ButtonStyle.blurple, emoji="📈")
    async def sales_btn(self, interaction: discord.Interaction, button: ui.Button):
        def logic(db):
            s = SalesService()
            return s.process_sales_data(db, s.get_raw_sales_logs(db))
        df = await run_db_task(logic)
        embed = discord.Embed(title=f"📈 销售: {self.product_name}", color=discord.Color.red())
        if df.empty: embed.description = "无数据"
        else:
            p_df = df[df['product'] == self.product_name]
            if p_df.empty: embed.description = "无数据"
            else:
                embed.description = f"**净销量**: {int(p_df['qty'].sum())}"
                embed.add_field(name="CNY", value=f"¥ {p_df[p_df['currency']=='CNY']['amount'].sum():,.2f}", inline=True)
                embed.add_field(name="JPY", value=f"¥ {p_df[p_df['currency']=='JPY']['amount'].sum():,.0f}", inline=True)
        await self.update_display(interaction, embed)

class ProductSelect(ui.Select):
    def __init__(self, product_data_list):
        options = []
        # 这里也传入了计算好的 qty
        for p, qty in product_data_list:
            options.append(discord.SelectOption(
                label=p.name[:25], 
                value=f"{p.id}|{p.name}",
                description=f"现货: {qty} | 总产: {p.total_quantity}"
            ))
            
        if not options:
            options.append(discord.SelectOption(label="暂无商品", value="none"))
        super().__init__(placeholder="🔍 请选择商品...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none": return
        pid, pname = self.values[0].split("|")
        await interaction.response.send_message(
            embed=discord.Embed(title=f"⏳ 加载中: {pname}..."), 
            view=ProductDashboardView(int(pid), pname), 
            ephemeral=True
        )

class ProductSelectionView(ui.View):
    def __init__(self, product_data_list):
        super().__init__()
        self.add_item(ProductSelect(product_data_list))


# ==========================================
# === 第四部分：主控制面板 (ControlView) ===
# ==========================================

class ControlView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="记一笔", style=discord.ButtonStyle.green, emoji="💸", row=0)
    async def expense_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("👇 **请选择支出类型**：", view=ExpenseTypeSelectView(), ephemeral=True)

    @ui.button(label="公司财务", style=discord.ButtonStyle.blurple, emoji="🏦", row=0)
    async def balance_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        def logic(db): return BalanceService.get_financial_summary(db)
        try:
            s = await run_db_task(logic)
            e = discord.Embed(title="🏦 资产负债表 (概览)", color=discord.Color.purple(), timestamp=discord.utils.utcnow())
            e.add_field(name="💵 流动CNY", value=f"¥ {s['cash']['CNY']:,.2f}", inline=True)
            e.add_field(name="💵 流动JPY", value=f"¥ {s['cash']['JPY']:,.0f}", inline=True)
            e.add_field(name="\u200b", value="\u200b", inline=True)
            e.add_field(name="🏛 总资产", value=f"¥ {s['totals']['asset']['CNY']:,.2f}", inline=True)
            e.add_field(name="📉 总负债", value=f"¥ {s['totals']['liability']['CNY']:,.2f}", inline=True)
            e.add_field(name="💎 净资产", value=f"**¥ {s['totals']['net']['CNY']:,.2f}**", inline=True)
            await interaction.followup.send(embed=e, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 失败: {e}", ephemeral=True)

    # [搜库存] - 改为发送下拉菜单 View (修正了数据获取逻辑)
    @ui.button(label="搜库存", style=discord.ButtonStyle.blurple, emoji="🔍", row=1)
    async def stock_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # 优化逻辑：获取产品同时计算实时库存
        def logic(db):
            p_service = ProductService(db)
            i_service = InventoryService(db)
            # 获取前25个产品
            products = p_service.get_all_products()[:25]
            
            # 计算每个产品的实时库存
            data_list = []
            for p in products:
                real_map, _, _, _ = i_service.get_stock_overview(p.name)
                current_qty = int(sum(real_map.values()))
                data_list.append((p, current_qty))
            return data_list
        
        try:
            product_data_list = await run_db_task(logic)
            if not product_data_list:
                await interaction.followup.send("⚠️ 暂无商品。", ephemeral=True)
                return
            
            # 发送下拉菜单 View
            view = StockSelectView(product_data_list)
            await interaction.followup.send("👇 **请选择库存查询商品**：", view=view, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 获取列表失败: {e}", ephemeral=True)

    @ui.button(label="产品详情 (库存/成本/销售)", style=discord.ButtonStyle.primary, emoji="📊", row=1)
    async def product_master_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        # 同样优化：这里也预先计算库存，让下拉框显示准确数字
        def logic(db):
            p_service = ProductService(db)
            i_service = InventoryService(db)
            products = p_service.get_all_products()[:25]
            
            data_list = []
            for p in products:
                real_map, _, _, _ = i_service.get_stock_overview(p.name)
                current_qty = int(sum(real_map.values()))
                data_list.append((p, current_qty))
            return data_list

        try:
            product_data_list = await run_db_task(logic)
            if not product_data_list:
                await interaction.followup.send("⚠️ 暂无商品。", ephemeral=True)
                return
            view = ProductSelectionView(product_data_list)
            await interaction.followup.send("👇 **请选择一个商品**：", view=view, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 失败: {e}", ephemeral=True)