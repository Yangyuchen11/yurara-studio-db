# cache_manager.py
# 在 Reflex 中，缓存失效通过 State 更新自动驱动
# 此文件保留兼容接口，方便 Service 层直接复用时不报错

def sync_all_caches():
    """
    Reflex 版本中，此函数为空操作（no-op）。
    Reflex 采用响应式状态，数据更新后 UI 自动同步，无需手动清缓存。
    """
    pass