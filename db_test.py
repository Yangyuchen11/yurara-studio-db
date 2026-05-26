# test.py
from sqlalchemy import text
from database import get_db, engine

def test_connection():
    print("⏳ 正在读取配置并尝试连接数据库...")
    
    try:
        # 1. 打印一下当前引擎的脱敏 URL，确认是否正确加载了 .env
        # 注意：这里隐藏了密码，确保安全
        safe_url = engine.url.render_as_string(hide_password=True)
        print(f"🔗 目标数据库: {safe_url}")

        # 2. 从生成器中获取 session
        db_generator = get_db()
        db = next(db_generator)
        
        # 3. 执行一个最基础的 SQL 查询来测试连通性
        result = db.execute(text("SELECT 1")).scalar()
        
        if result == 1:
            print("✅ 数据库连接完全成功！你的 .env 和 database.py 配置无误，可以放心进入下一步。")
        else:
            print("⚠️ 连接可能成功，但测试查询返回了异常结果。")
            
    except Exception as e:
        print("\n❌ 数据库连接失败！")
        print("请检查以下几点：")
        print("  1. .env 文件是否存在且与 test.py 在同一目录下？")
        print("  2. DATABASE_URL 的格式是否正确（密码是否包含特殊字符需要 urlencode）？")
        print("  3. 你的网络是否可以访问该数据库（例如 Supabase 数据库是否需要开启特定 IP 白名单）？")
        print(f"\n🔍 详细报错信息:\n{e}")
        
    finally:
        # 安全关闭会话
        try:
            db.close()
            print("🔒 数据库会话已关闭。")
        except:
            pass

if __name__ == "__main__":
    test_connection()