# 文件路径: bot_src/utils.py
import os
import asyncio
import discord
from discord import app_commands
from dotenv import load_dotenv

# 确保能从根目录导入 database
# 注意：只要并在根目录运行 python bot.py，这里就能直接 import database
from database import SessionLocal

# 加载环境变量
load_dotenv()
raw_ids = os.getenv("DISCORD_ALLOWED_CHANNEL_ID", "")
ALLOWED_CHANNEL_IDS = []

if raw_ids:
    try:
        # 将逗号分隔的字符串转换成整数列表
        ALLOWED_CHANNEL_IDS = [int(x.strip()) for x in raw_ids.split(",") if x.strip()]
    except ValueError:
        print("⚠️ 警告: DISCORD_ALLOWED_CHANNEL_ID 格式错误，请使用逗号分隔的数字")

# ==========================================
# === 通用工具：频道检查装饰器 ===
# ==========================================
def is_in_allowed_channel():
    """
    自定义检查器：允许在配置列表中的任意频道使用
    """
    def predicate(interaction: discord.Interaction) -> bool:
        # 如果没有配置任何 ID，默认允许所有频道（或者你可以选择默认禁止）
        if not ALLOWED_CHANNEL_IDS:
            return True 
        
        # 检查当前频道 ID 是否在允许列表中
        if interaction.channel_id not in ALLOWED_CHANNEL_IDS:
            return False
        return True
    return app_commands.check(predicate)

# ==========================================
# === 通用工具：异步数据库执行器 ===
# ==========================================
async def run_db_task(task_func, *args, **kwargs):
    def wrapper():
        db = SessionLocal()
        try:
            return task_func(db, *args, **kwargs)
        except Exception as e:
            raise e
        finally:
            db.close()
    return await asyncio.to_thread(wrapper)