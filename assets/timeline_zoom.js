// assets/timeline_zoom.js
/**
 * Yurara Studio - 时间轴全景甘特图鼠标滚轮平滑定点缩放与交互控制器
 */

(function () {
    const MIN_SLOT_WIDTH = 40;    // 40% 紧凑
    const MAX_SLOT_WIDTH = 280;   // 280% 宽展
    const DEFAULT_SLOT_WIDTH = 100; // 100% 默认

    function getContainer() {
        return document.getElementById('timeline-scroll-container');
    }

    function getCurrentSlotWidth() {
        const container = getContainer();
        if (!container) return DEFAULT_SLOT_WIDTH;
        const raw = container.style.getPropertyValue('--timeline-slot-width') ||
                    document.documentElement.style.getPropertyValue('--timeline-slot-width') ||
                    getComputedStyle(container).getPropertyValue('--timeline-slot-width');
        const parsed = parseFloat(raw);
        return isNaN(parsed) || parsed <= 0 ? DEFAULT_SLOT_WIDTH : parsed;
    }

    function updateZoomUI(slotWidth) {
        const badge = document.getElementById('timeline-zoom-text');
        if (badge) {
            badge.innerText = Math.round((slotWidth / DEFAULT_SLOT_WIDTH) * 100) + '%';
        }
    }

    function applyZoom(newSlotWidth, focalClientX) {
        const container = getContainer();
        if (!container) return;

        newSlotWidth = Math.max(MIN_SLOT_WIDTH, Math.min(MAX_SLOT_WIDTH, newSlotWidth));
        const currentSlotWidth = getCurrentSlotWidth();
        if (Math.abs(newSlotWidth - currentSlotWidth) < 0.1) return;

        const rect = container.getBoundingClientRect();
        const headerWidth = 240; // 左侧「业务主体 / 商品项目」固定 Sticky 列宽度
        let effectiveCursorX = 0;

        if (focalClientX !== undefined && focalClientX !== null) {
            const cursorX = focalClientX - rect.left;
            effectiveCursorX = Math.max(0, cursorX - headerWidth);
        } else {
            // 若无光标坐标（如点击按钮缩放），以可视区中间作为锚点
            effectiveCursorX = Math.max(0, (container.clientWidth - headerWidth) / 2);
        }

        const contentX = container.scrollLeft + effectiveCursorX;
        const ratio = newSlotWidth / currentSlotWidth;
        const newScrollLeft = (contentX * ratio) - effectiveCursorX;

        // 同时更新容器与根节点 CSS 变量，确保所有子元素即时继承
        container.style.setProperty('--timeline-slot-width', newSlotWidth + 'px');
        container.style.setProperty('--timeline-zoom', (newSlotWidth / 100).toFixed(4));
        document.documentElement.style.setProperty('--timeline-slot-width', newSlotWidth + 'px');
        document.documentElement.style.setProperty('--timeline-zoom', (newSlotWidth / 100).toFixed(4));

        container.scrollLeft = newScrollLeft;
        updateZoomUI(newSlotWidth);
    }

    // 暴露全局 API 供按钮及 Python State 触发
    window.timelineZoomIn = function () {
        const cur = getCurrentSlotWidth();
        applyZoom(cur * 1.2);
    };

    window.timelineZoomOut = function () {
        const cur = getCurrentSlotWidth();
        applyZoom(cur * 0.833);
    };

    window.timelineZoomReset = function () {
        applyZoom(DEFAULT_SLOT_WIDTH);
    };

    window.timelineSetZoom = function (percent) {
        const p = parseFloat(percent);
        if (!isNaN(p) && p > 0) {
            applyZoom(DEFAULT_SLOT_WIDTH * (p / 100));
        }
    };

    function attachListeners() {
        const container = getContainer();
        if (!container) return false;

        if (container._timelineZoomAttached) {
            return true;
        }
        container._timelineZoomAttached = true;

        // 滚轮事件监听 (passive: false 以支持 preventDefault)
        container.addEventListener('wheel', function (e) {
            const isHeader = e.target && (e.target.closest('#timeline-header-area') || e.target.closest('.timeline-header-area'));
            const isZoomTrigger = e.ctrlKey || e.altKey || e.metaKey || isHeader;

            if (isZoomTrigger) {
                e.preventDefault();
                e.stopPropagation();

                const cur = getCurrentSlotWidth();
                const delta = e.deltaY || e.deltaX;
                // 缩放步长（平滑灵敏）
                const factor = delta < 0 ? 1.09 : 0.917;
                applyZoom(cur * factor, e.clientX);
            }
        }, { passive: false });

        // 双击表头标尺区重置 100% 缩放
        const headerArea = document.getElementById('timeline-header-area');
        if (headerArea) {
            headerArea.addEventListener('dblclick', function (e) {
                if (e.target.tagName !== 'BUTTON' && !e.target.closest('button')) {
                    applyZoom(DEFAULT_SLOT_WIDTH, e.clientX);
                }
            });
        }

        updateZoomUI(getCurrentSlotWidth());
        return true;
    }

    window.initTimelineZoom = function () {
        if (!attachListeners()) {
            setTimeout(attachListeners, 100);
            setTimeout(attachListeners, 400);
            setTimeout(attachListeners, 1000);
        }
    };

    // 页面加载及 DOM 变化时自启动
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', window.initTimelineZoom);
    } else {
        window.initTimelineZoom();
    }

    // 监听 DOM 树变化以防 SPA 页面切换后重绘
    const observer = new MutationObserver(function (mutations) {
        const container = getContainer();
        if (container && !container._timelineZoomAttached) {
            attachListeners();
        }
    });

    if (document.body) {
        observer.observe(document.body, { childList: true, subtree: true });
    } else {
        window.addEventListener('load', function () {
            observer.observe(document.body, { childList: true, subtree: true });
            window.initTimelineZoom();
        });
    }

    // 定时重试兜底
    setTimeout(window.initTimelineZoom, 200);
    setTimeout(window.initTimelineZoom, 800);
    setTimeout(window.initTimelineZoom, 2000);
})();
