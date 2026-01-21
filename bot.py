import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
from dotenv import load_dotenv

# 导入工具和视图
from bot_src.utils import run_db_task, is_in_allowed_channel, ALLOWED_CHANNEL_IDS
from bot_src.views import ControlView

# 加载环境变量
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise ValueError("❌ 请设置 DISCORD_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# === Bot 生命周期 ===
@bot.event
async def on_ready():
    print(f'🤖 Bot 已登录: {bot.user}')
    print(f'🔒 允许的操作频道 IDs: {ALLOWED_CHANNEL_IDS}')
    
    try:
        synced = await bot.tree.sync()
        print(f"✅ 已同步 {len(synced)} 个全局命令")
    except Exception as e:
        print(f"❌ 同步失败: {e}")

# === 【核心修复】全局错误处理器 ===
@bot.tree.error
async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # 捕获权限检查失败 (CheckFailure)
    if isinstance(error, app_commands.CheckFailure):
        # 生成允许频道的链接列表
        if ALLOWED_CHANNEL_IDS:
            channels_str = " ".join([f"<#{gid}>" for gid in ALLOWED_CHANNEL_IDS])
            msg = f"🚫 **操作受限**：此频道不在白名单中。\n请前往以下频道使用: {channels_str}"
        else:
            msg = "🚫 **配置错误**：未设置允许的频道 ID (DISCORD_ALLOWED_CHANNEL_ID)。"
        
        # 尝试回复用户 (ephemeral=True 仅自己可见)
        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)
            
    else:
        # 其他代码报错
        err_msg = f"❌ 系统错误: {str(error)}"
        print(f"命令执行异常: {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message(err_msg, ephemeral=True)
        else:
            await interaction.followup.send(err_msg, ephemeral=True)

# === 核心入口命令 ===
@bot.tree.command(name="menu", description="打开 Yurara Studio 综合管理面板")
@is_in_allowed_channel()
async def menu(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=True)

        view = ControlView()
        
        embed = discord.Embed(
            title="🤖 Yurara Studio 综合管理",
            description=(
                "请选择操作：\n"
                "• **记一笔**: 快速录入支出\n"
                "• **公司财务**: 查看资产负债表概览\n"
                "• **搜库存**: 模糊搜索商品库存\n"
                "• **产品透视**: 选择特定商品，查看详细成本、库存和销售数据"
            ),
            color=discord.Color.gold()
        )
        
        await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        await interaction.followup.send(f"❌ 运行出错: {e}", ephemeral=True)

if __name__ == "__main__":
    bot.run(TOKEN)