import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
from dotenv import load_dotenv
from datetime import date

# === 项目模块导入 ===
# 确保 bot.py 在项目根目录下，与 database.py 同级
from database import SessionLocal
from services.finance_service import FinanceService
from services.inventory_service import InventoryService
from services.balance_service import BalanceService
from constants import Currency

# 1. 加载环境变量
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
ALLOWED_CHANNEL_ID = os.getenv("DISCORD_ALLOWED_CHANNEL_ID")

if not TOKEN or not ALLOWED_CHANNEL_ID:
    raise ValueError("❌ 请检查 .env 文件，确保 DISCORD_TOKEN 和 DISCORD_ALLOWED_CHANNEL_ID 已设置")

ALLOWED_CHANNEL_ID = int(ALLOWED_CHANNEL_ID)

# 2. 初始化 Bot
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# === 核心工具：频道检查装饰器 (方式A) ===
# ==========================================

def is_in_allowed_channel():
    """
    自定义检查器：只有在指定频道才允许执行命令
    """
    def predicate(interaction: discord.Interaction) -> bool:
        # 检查当前频道ID是否匹配配置的允许ID
        if interaction.channel_id != ALLOWED_CHANNEL_ID:
            return False
        return True
    return app_commands.check(predicate)

# 全局错误处理器：捕获频道检查失败的情况
@bot.tree.error
async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        # ephemeral=True 只有点击者能看到这条提示，不会打扰别人
        await interaction.response.send_message(
            f"🚫 **权限不足**：请在指定的操作频道 <#{ALLOWED_CHANNEL_ID}> 使用此 Bot。", 
            ephemeral=True
        )
    else:
        # 其他报错（如代码报错）
        err_msg = str(error)
        print(f"❌ 命令执行出错: {err_msg}")
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ 系统错误: {err_msg}", ephemeral=True)

# ==========================================
# === 核心工具：异步数据库执行器 ===
# ==========================================

async def run_db_task(task_func, *args, **kwargs):
    """
    在线程池中运行同步的数据库任务，管理 Session 生命周期
    task_func: 接受 (db, *args, **kwargs) 的函数
    """
    def wrapper():
        db = SessionLocal()
        try:
            return task_func(db, *args, **kwargs)
        except Exception as e:
            raise e
        finally:
            db.close()
    
    # 将同步的 wrapper 函数扔到 asyncio 线程池中跑，不阻塞 Bot
    return await asyncio.to_thread(wrapper)

# ==========================================
# === Bot 生命周期事件 ===
# ==========================================

@bot.event
async def on_ready():
    print(f'🤖 Bot 已登录: {bot.user}')
    print(f'🔒 锁定操作频道 ID: {ALLOWED_CHANNEL_ID}')
    try:
        synced = await bot.tree.sync()
        print(f"✅ 已同步 {len(synced)} 个 Slash 命令")
    except Exception as e:
        print(f"❌ 同步命令失败: {e}")

# ==========================================
# === Command 1: 查看财务概览 (/balance) ===
# ==========================================

@bot.tree.command(name="balance", description="查看公司资产净值概览")
@is_in_allowed_channel() # <--- 方式 A：挂上装饰器
async def balance(interaction: discord.Interaction):
    await interaction.response.defer() # 数据库查询可能较慢，先 defer

    def logic(db):
        return BalanceService.get_financial_summary(db)

    try:
        summary = await run_db_task(logic)
        
        totals = summary["totals"]
        cash = summary["cash"]
        
        # 构建漂亮的卡片 (Embed)
        embed = discord.Embed(title="📊 财务概览", color=discord.Color.blue(), timestamp=discord.utils.utcnow())
        
        # 第一行：流动资金
        embed.add_field(name="流动资金 (CNY)", value=f"¥ {cash['CNY']:,.2f}", inline=True)
        embed.add_field(name="流动资金 (JPY)", value=f"¥ {cash['JPY']:,.0f}", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True) # 占位符换行
        
        # 第二行：总资产与净资产
        embed.add_field(name="总资产 (CNY折算)", value=f"¥ {totals['asset']['CNY']:,.2f}", inline=True)
        embed.add_field(name="📉 净资产 (CNY折算)", value=f"**¥ {totals['net']['CNY']:,.2f}**", inline=True)
        
        embed.set_footer(text="数据来源: Yurara Studio DB")
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(f"❌ 查询失败: {str(e)}")

# ==========================================
# === Command 2: 快速记账 (/expense) ===
# ==========================================

@bot.tree.command(name="expense", description="快速记录一笔普通支出")
@app_commands.describe(
    amount="金额", 
    category="分类 (如: 交通费, 餐饮, 采购)", 
    desc="备注说明", 
    currency="币种"
)
@app_commands.choices(currency=[
    app_commands.Choice(name="CNY", value="CNY"),
    app_commands.Choice(name="JPY", value="JPY")
])
@is_in_allowed_channel() # <--- 方式 A：挂上装饰器
async def expense(interaction: discord.Interaction, amount: float, category: str, desc: str, currency: str = "CNY"):
    await interaction.response.defer()

    # 准备传给 Service 的数据
    base_data = {
        "date": date.today(),
        "type": "支出",
        "currency": currency,
        "amount": amount,
        "category": category,
        "shop": "Discord Bot", # 标记来源
        "desc": desc
    }
    # 简单支出不需要关联复杂资产
    link_config = {"link_type": None, "name": desc}
    # 默认汇率 (实际项目中建议存入数据库配置或实时获取)
    exchange_rate = 0.048 

    def logic(db):
        return FinanceService.create_general_transaction(db, base_data, link_config, exchange_rate)

    try:
        msg = await run_db_task(logic)
        await interaction.followup.send(
            f"✅ **记账成功!**\n"
            f"💸 **{amount} {currency}** - {category}\n"
            f"📝 {desc}\n"
            f"Startus: {msg}"
        )
    except Exception as e:
        await interaction.followup.send(f"❌ 记账失败: {str(e)}")

# ==========================================
# === Command 3: 查库存 (/stock) ===
# ==========================================

@bot.tree.command(name="stock", description="查询商品实时库存")
@app_commands.describe(product_name="商品名称关键词")
@is_in_allowed_channel() # <--- 方式 A：挂上装饰器
async def stock(interaction: discord.Interaction, product_name: str):
    await interaction.response.defer()

    def logic(db):
        service = InventoryService(db)
        # 1. 模糊搜索产品
        products = service.get_all_products()
        # 简单的包含匹配
        target = next((p for p in products if product_name in p.name), None)
        
        if not target:
            return None, None
        
        # 2. 获取该产品的库存详情
        # get_stock_overview 返回: (real_stock_map, pre_in_map, pre_out_map, ...)
        real, pre_in, pre_out, _ = service.get_stock_overview(target.name)
        return target.name, real

    try:
        p_name, real_stock = await run_db_task(logic)
        
        if not p_name:
            await interaction.followup.send(f"⚠️ 未找到包含 `{product_name}` 的商品。", ephemeral=True)
            return

        # 构建库存显示
        embed = discord.Embed(title=f"📦 库存查询: {p_name}", color=discord.Color.green())
        
        content = ""
        total_qty = 0
        
        if real_stock:
            for variant, qty in real_stock.items():
                if qty != 0:
                    icon = "🟢" if qty > 5 else ("🟡" if qty > 0 else "🔴")
                    content += f"{icon} **{variant}**: {int(qty)}\n"
                    total_qty += qty
        
        if not content:
            content = "💨 暂无现货库存"
        
        embed.description = content
        embed.set_footer(text=f"现货总量: {int(total_qty)}")
        
        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ 查询出错: {str(e)}")

# ==========================================
# === 启动入口 ===
# ==========================================

if __name__ == "__main__":
    bot.run(TOKEN)