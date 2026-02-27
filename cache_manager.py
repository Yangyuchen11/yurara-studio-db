# cache_manager.py
import streamlit as st

def sync_all_caches():
    """
    万能同步函数：一键清空全系统所有带 @st.cache_data 的缓存。
    在任何 View 中，只要执行了增、删、改数据库的操作，在 st.rerun() 前调用此函数即可保证数据 100% 同步。
    """
    st.cache_data.clear()