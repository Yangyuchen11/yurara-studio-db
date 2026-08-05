// frontend/src/components/AppLayout.tsx
import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';

export const AppLayout: React.FC = () => {
  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
    return localStorage.getItem('sidebar_collapsed') === 'true';
  });

  const toggleCollapse = () => {
    setIsCollapsed(prev => {
      const next = !prev;
      localStorage.setItem('sidebar_collapsed', String(next));
      return next;
    });
  };

  // Touch Swipe Gesture State
  const [touchStartPos, setTouchStartPos] = useState<{ x: number; y: number } | null>(null);

  const handleTouchStart = (e: React.TouchEvent) => {
    if (e.touches.length === 1) {
      setTouchStartPos({ x: e.touches[0].clientX, y: e.touches[0].clientY });
    }
  };

  const handleTouchEnd = (e: React.TouchEvent) => {
    if (!touchStartPos || e.changedTouches.length === 0) return;
    const endX = e.changedTouches[0].clientX;
    const endY = e.changedTouches[0].clientY;
    const deltaX = endX - touchStartPos.x;
    const deltaY = endY - touchStartPos.y;

    // Horizontal swipe check: |deltaX| > 40 & |deltaX| > |deltaY|
    if (Math.abs(deltaX) > 40 && Math.abs(deltaX) > Math.abs(deltaY)) {
      if (deltaX < -40 && !isCollapsed) {
        // Swipe Left -> Collapse
        setIsCollapsed(true);
        localStorage.setItem('sidebar_collapsed', 'true');
      } else if (deltaX > 40 && isCollapsed) {
        // Swipe Right -> Expand
        setIsCollapsed(false);
        localStorage.setItem('sidebar_collapsed', 'false');
      }
    }
    setTouchStartPos(null);
  };

  return (
    <div
      className="flex min-h-screen bg-[#0B0F17] text-slate-200 relative overflow-x-hidden font-sans select-none"
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      {/* Background Ambient Blur Lights matching Reflex HSL glow */}
      <div className="fixed -top-40 -left-40 w-96 h-96 bg-violet-600/10 rounded-full blur-[128px] pointer-events-none" />
      <div className="fixed top-1/3 -right-40 w-96 h-96 bg-indigo-600/10 rounded-full blur-[128px] pointer-events-none" />

      {/* Fixed Sidebar */}
      <Sidebar isCollapsed={isCollapsed} onToggleCollapse={toggleCollapse} />

      {/* Main Content Area */}
      <main className={`flex-1 min-w-0 p-8 overflow-y-auto z-10 space-y-6 transition-all duration-300 ${isCollapsed ? 'ml-16' : 'ml-64'}`}>
        {/* Top Header Environment Status Badge matching Reflex layout */}
        <div className="flex justify-end items-center pb-2">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            🟢 正式环境 (Django API Backend)
          </span>
        </div>

        <Outlet />
      </main>
    </div>
  );
};
