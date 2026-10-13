# yurara_app/components/ime_search_input.py
"""
支持中文输入法的搜索框（封装 assets/ime_search_input.jsx）。

用法：
    ime_search_input(
        value=SomeState.search_query,
        on_search=SomeState.set_search_query,
        placeholder="搜索...",
    )

- 打拼音（输入法组字）期间不会触发 on_search；
- 选定汉字后 / 英文数字停止输入 debounce 毫秒后触发；
- 按回车立即触发；
- 后端修改 value（如清空）时，输入框会同步。
"""
import reflex as rx
from reflex.event import passthrough_event_spec


class ImeSearchInput(rx.Component):
    library = "$/public/ime_search_input.jsx"
    tag = "ImeSearchInput"

    # 后端当前搜索词（用于外部重置同步）
    value: rx.Var[str]
    # 防抖毫秒数
    debounce: rx.Var[int]
    placeholder: rx.Var[str]
    # Radix TextField 尺寸 "1" | "2" | "3"
    size: rx.Var[str]

    # 最终确定的搜索文本
    on_search: rx.EventHandler[passthrough_event_spec(str)]


ime_search_input = ImeSearchInput.create
