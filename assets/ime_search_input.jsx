// assets/ime_search_input.jsx
// 支持中文输入法（IME）的搜索输入框：
//  - 输入法组字（打拼音）期间不触发搜索；
//  - 选定汉字（compositionend）后才把最终文本发给后端；
//  - 英文/数字照常实时搜索，并带防抖，避免频繁请求；
//  - 输入框内容由前端自行管理（不受后端回传打断），
//    当后端 value 被外部修改（如「清除筛选」）时会同步重置。
import { useEffect, useRef, useState } from "react";
import { TextField } from "@radix-ui/themes";

export function ImeSearchInput({ value = "", onSearch, debounce = 300, ...rest }) {
  const [text, setText] = useState(value ?? "");
  const composingRef = useRef(false);
  const timerRef = useRef(null);
  const lastSentRef = useRef(value ?? "");

  // 外部 value 变化（例如清除筛选）时同步到输入框
  useEffect(() => {
    const v = value ?? "";
    if (v !== lastSentRef.current) {
      lastSentRef.current = v;
      setText(v);
    }
  }, [value]);

  // 卸载时清理定时器
  useEffect(() => () => clearTimeout(timerRef.current), []);

  const scheduleSearch = (v) => {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      if (v !== lastSentRef.current) {
        lastSentRef.current = v;
        onSearch && onSearch(v);
      }
    }, debounce);
  };

  return (
    <TextField.Root
      {...rest}
      value={text}
      onChange={(e) => {
        const v = e.target.value;
        setText(v);
        // 组字中不搜索
        if (composingRef.current || e.nativeEvent?.isComposing) return;
        scheduleSearch(v);
      }}
      onCompositionStart={() => {
        composingRef.current = true;
        clearTimeout(timerRef.current);
      }}
      onCompositionEnd={(e) => {
        composingRef.current = false;
        const v = e.currentTarget.value;
        setText(v);
        scheduleSearch(v);
      }}
      onKeyDown={(e) => {
        // 回车立即搜索（组字中的回车用于确认候选词，忽略）
        if (e.key === "Enter" && !composingRef.current && !e.nativeEvent?.isComposing) {
          clearTimeout(timerRef.current);
          const v = e.currentTarget.value;
          if (v !== lastSentRef.current) {
            lastSentRef.current = v;
            onSearch && onSearch(v);
          }
        }
      }}
    />
  );
}
