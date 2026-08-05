// frontend/src/components/Sidebar.tsx
import React, { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { MemoNote } from '../types';
import { Modal } from './ui/Modal';
import {
  CircleDollarSign,
  ClipboardList,
  Package,
  ShoppingCart,
  ShoppingBasket,
  ArrowLeftRight,
  Sparkles,
  ChevronRight,
  LogOut,
  NotebookPen,
  RefreshCw,
  Database,
  Calculator,
  Download,
  AlertTriangle,
  PieChart,
  Store,
  TrendingUp,
  Globe,
  Camera,
  Box,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Trash2
} from 'lucide-react';

interface SidebarProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isCollapsed, onToggleCollapse }) => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const authUser = localStorage.getItem('username') || 'yurara_admin';

  // State
  const [testMode, setTestMode] = useState(false);
  const [isRatesModalOpen, setIsRatesModalOpen] = useState(false);
  const [isMemoModalOpen, setIsMemoModalOpen] = useState(false);
  const [isBackupModalOpen, setIsBackupModalOpen] = useState(false);

  // Rate calculator & Management state
  const [calcAmount, setCalcAmount] = useState(1000);
  const [calcFrom, setCalcFrom] = useState('JPY');
  const [calcTo, setCalcTo] = useState('CNY');
  const [newCurrCode, setNewCurrCode] = useState('');
  const [newCurrRate100, setNewCurrRate100] = useState('');

  // Backup state
  const [deleteConfirm, setDeleteConfirm] = useState('');

  // Fetch rates
  const { data: ratesData } = useQuery<Record<string, number>>({
    queryKey: ['rates'],
    queryFn: async () => {
      const res = await apiClient.get('/rates/');
      return res.data.rates || { JPY: 0.048 };
    },
  });

  const saveRateMutation = useMutation({
    mutationFn: async ({ currency, rate100 }: { currency: string; rate100: number }) => {
      await apiClient.post('/rates/', { currency, rate: rate100 });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rates'] });
      setNewCurrCode('');
      setNewCurrRate100('');
    },
  });

  const deleteRateMutation = useMutation({
    mutationFn: async (currency: string) => {
      await apiClient.delete(`/rates/?currency=${currency}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rates'] });
    },
  });

  const fetchLiveRatesMutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post('/rates/fetch-live/');
      return res.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['rates'] });
      alert(`🌐 实时汇率同步成功！包含已更新币种: ${Object.keys(data.updated || {}).join(', ') || '无变动'}`);
    },
    onError: (err: any) => {
      alert(`抓取实时汇率失败: ${err.response?.data?.error || err.message}`);
    }
  });

  // Memo search & state
  const [memoSearch, setMemoSearch] = useState('');

  // Fetch memos
  const { data: memosData, refetch: refetchMemos } = useQuery<any>({
    queryKey: ['memos'],
    queryFn: async () => {
      const res = await apiClient.get('/memos/');
      return res.data;
    },
  });

  const createMemoMutation = useMutation({
    mutationFn: async () => {
      const todayStr = new Date().toISOString().split('T')[0];
      const res = await apiClient.post('/memos/', { date: todayStr, content: '' });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memos'] });
    },
  });

  const updateMemoMutation = useMutation({
    mutationFn: async ({ id, content, date }: { id: number; content: string; date?: string }) => {
      const res = await apiClient.patch(`/memos/${id}/`, { content, date });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memos'] });
    },
  });

  const deleteMemoMutation = useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/memos/${id}/`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['memos'] });
    },
  });

  const memoList = Array.isArray(memosData)
    ? memosData
    : memosData && Array.isArray(memosData.results)
    ? memosData.results
    : [];

  const latestMemo = memoList.length > 0 ? memoList[0] : null;

  const filteredMemos = memoList.filter((m: any) => {
    if (!m) return false;
    const q = (memoSearch || '').trim().toLowerCase();
    if (!q) return true;
    return String(m.date || '').toLowerCase().includes(q) || String(m.content || '').toLowerCase().includes(q);
  });

  const ratesMap: Record<string, number> = ratesData || { JPY: 0.048 };

  // Calculate conversion
  const getConvertedAmount = () => {
    if (calcFrom === calcTo) return calcAmount;
    let amountInCNY = calcAmount;
    if (calcFrom !== 'CNY') {
      const rateFrom = ratesMap[calcFrom] || 0;
      amountInCNY = calcAmount * rateFrom;
    }
    if (calcTo === 'CNY') return amountInCNY;
    const rateTo = ratesMap[calcTo] || 1;
    return rateTo > 0 ? amountInCNY / rateTo : 0;
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('username');
    navigate('/login');
  };

  const handleDownloadBackup = async () => {
    try {
      const response = await apiClient.get('/backup/download/', {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `yurara-db-backup_${new Date().toISOString().split('T')[0]}.zip`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      alert('下载备份失败');
    }
  };

  const navGroups = [
    {
      group: '财务管理',
      items: [
        { label: '财务流水录入', icon: CircleDollarSign, href: '/finance' },
        { label: '公司账面概览', icon: ClipboardList, href: '/balance' },
        { label: '财务报表与分析', icon: PieChart, href: '/report' },
      ]
    },
    {
      group: '商品管理',
      items: [
        { label: '商品管理', icon: Package, href: '/products' },
        { label: '商品成本核算', icon: Calculator, href: '/cost' },
      ]
    },
    {
      group: '销售管理',
      items: [
        { label: '线上销售管理', icon: ShoppingCart, href: '/sales-orders' },
        { label: '预售销售管理', icon: ShoppingBasket, href: '/presale' },
        { label: '线下销售管理', icon: Store, href: '/offline-sales' },
        { label: '销售额一览', icon: TrendingUp, href: '/sales' },
        { label: '销售平台管理', icon: Globe, href: '/platforms' },
      ]
    },
    {
      group: '仓储资产',
      items: [
        { label: '仓库库存管理', icon: ArrowLeftRight, href: '/inventory' },
        { label: '固定资产管理', icon: Camera, href: '/asset' },
        { label: '其他资产管理', icon: Box, href: '/consumable' },
      ]
    },
  ];

  return (
    <>
      <aside
        className={`fixed top-0 left-0 bottom-0 h-screen bg-[#131924]/95 backdrop-blur-xl border-r border-[#2A3447] flex flex-col select-none z-40 shadow-2xl transition-all duration-300 ease-in-out ${
          isCollapsed ? 'w-16' : 'w-64'
        }`}
      >
        {/* Header Branding & Collapse Toggle Button */}
        <div className="p-3 border-b border-[#2A3447] flex items-center justify-between min-h-[57px]">
          {!isCollapsed ? (
            <div className="flex items-center gap-2.5 overflow-hidden">
              <div className="p-1.5 bg-gradient-to-tr from-violet-600 to-indigo-500 text-white rounded-xl shadow-lg shadow-violet-500/25 ring-1 ring-white/20 flex-shrink-0">
                <Sparkles className="w-4 h-4 animate-pulse" />
              </div>
              <div className="truncate">
                <h1 className="font-display font-extrabold text-slate-100 text-sm tracking-tight leading-none bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent truncate">
                  Yurara Studio
                </h1>
                <span className="text-[9px] font-mono text-violet-400 font-medium tracking-wide uppercase mt-0.5 block">
                  DB System v3.0
                </span>
              </div>
            </div>
          ) : (
            <div className="mx-auto p-1.5 bg-gradient-to-tr from-violet-600 to-indigo-500 text-white rounded-xl shadow-lg shadow-violet-500/25 ring-1 ring-white/20">
              <Sparkles className="w-4 h-4 animate-pulse" />
            </div>
          )}

          {/* Top-Right Collapse Toggle Button */}
          <button
            onClick={onToggleCollapse}
            className="p-1.5 text-slate-400 hover:text-slate-100 hover:bg-[#18202F] rounded-lg transition flex-shrink-0 ml-1"
            title={isCollapsed ? '展开导航栏 (向右滑动)' : '收起导航栏 (向左滑动)'}
          >
            {isCollapsed ? (
              <PanelLeftOpen className="w-4 h-4 text-violet-400" />
            ) : (
              <PanelLeftClose className="w-4 h-4" />
            )}
          </button>
        </div>

        {/* Test Mode Switch & Rate Preview Widgets */}
        {!isCollapsed ? (
          <div className="px-3 pt-3 space-y-2">
            {/* Test Mode Toggle */}
            <div className="flex items-center justify-between p-2 bg-[#0B0F17]/80 rounded-xl border border-[#2A3447]">
              <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${testMode ? 'bg-amber-500/10 text-amber-400 border-amber-500/30' : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'}`}>
                {testMode ? '🧪 测试模式' : '🟢 正式环境'}
              </span>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={testMode}
                  onChange={() => setTestMode(!testMode)}
                  className="sr-only peer"
                />
                <div className="w-7 h-3.5 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[1px] after:left-[1px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-amber-500"></div>
              </label>
            </div>

            {/* Rate Widget */}
            <div
              onClick={() => setIsRatesModalOpen(true)}
              className="p-2 bg-[#0B0F17]/80 hover:bg-[#18202F] rounded-xl border border-violet-500/20 hover:border-violet-500/40 cursor-pointer transition-all space-y-1 group text-xs"
            >
              <div className="flex items-center justify-between text-[11px]">
                <span className="font-semibold text-slate-300 flex items-center gap-1">
                  <RefreshCw className="w-3 h-3 text-violet-400 group-hover:rotate-180 transition-transform" />
                  全局汇率
                </span>
                <span className="text-[10px] text-violet-400 group-hover:underline">计算器</span>
              </div>
              <div className="text-[10px] font-mono text-slate-400 space-y-0.5">
                {Object.entries(ratesMap).map(([curr, r]) => (
                  <div key={curr} className="flex justify-between">
                    <span>100 {curr}</span>
                    <span className="text-slate-200 font-semibold">{(r * 100).toFixed(3)} CNY</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Memo Widget */}
            <div
              onClick={() => setIsMemoModalOpen(true)}
              className="p-2 bg-[#0B0F17]/80 hover:bg-[#18202F] rounded-xl border border-slate-700/60 hover:border-slate-600 cursor-pointer transition-all space-y-0.5 group"
            >
              <div className="flex items-center justify-between text-[11px]">
                <span className="font-semibold text-slate-300 flex items-center gap-1">
                  <NotebookPen className="w-3 h-3 text-violet-400" />
                  备忘录
                </span>
                <span className="text-[10px] text-slate-500">查看</span>
              </div>
              <p className="text-[10px] text-slate-400 line-clamp-1 leading-tight">
                {latestMemo ? latestMemo.content : '添加备忘录...'}
              </p>
            </div>
          </div>
        ) : (
          /* Compact Icon Bar Widgets when Collapsed */
          <div className="py-2 px-2 border-b border-[#2A3447] flex flex-col items-center gap-2">
            <button
              onClick={() => setIsRatesModalOpen(true)}
              className="p-2 bg-[#0B0F17] hover:bg-[#18202F] text-violet-400 rounded-xl border border-violet-500/30 transition"
              title="全局汇率看板与计算器"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <button
              onClick={() => setIsMemoModalOpen(true)}
              className="p-2 bg-[#0B0F17] hover:bg-[#18202F] text-slate-400 hover:text-slate-200 rounded-xl border border-slate-700/60 transition"
              title="备忘录"
            >
              <NotebookPen className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Navigation list */}
        <div className="flex-1 overflow-y-auto px-2 py-3 space-y-3 text-xs">
          {navGroups.map((group, gIdx) => (
            <div key={gIdx} className="space-y-1">
              {!isCollapsed && (
                <h3 className="px-2.5 text-[9px] font-display font-bold tracking-wider text-slate-500 uppercase">
                  {group.group}
                </h3>
              )}
              <div className="space-y-0.5">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <NavLink
                      key={item.href}
                      to={item.href}
                      title={isCollapsed ? item.label : undefined}
                      className={({ isActive }) =>
                        `group flex items-center ${isCollapsed ? 'justify-center px-0 py-2.5' : 'justify-between px-2.5 py-2'} rounded-xl transition-all duration-200 ${
                          isActive
                            ? 'bg-gradient-to-r from-violet-600/30 to-indigo-600/20 border border-violet-500/40 text-white font-semibold shadow-md'
                            : 'text-slate-400 hover:bg-[#18202F] hover:text-slate-200 border border-transparent'
                        }`
                      }
                    >
                      {({ isActive }) => (
                        <>
                          <div className={`flex items-center ${isCollapsed ? 'justify-center' : 'gap-2.5'}`}>
                            <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-violet-400' : 'text-slate-500 group-hover:text-slate-300'}`} />
                            {!isCollapsed && <span className="text-xs truncate">{item.label}</span>}
                          </div>
                          {!isCollapsed && isActive && <ChevronRight className="w-3.5 h-3.5 text-violet-400 opacity-80 flex-shrink-0" />}
                        </>
                      )}
                    </NavLink>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {/* Footer User / Backup Section */}
        <div className="p-2 border-t border-[#2A3447] space-y-2 bg-[#0B0F17]/50 backdrop-blur-md">
          {!isCollapsed ? (
            <>
              <button
                onClick={() => setIsBackupModalOpen(true)}
                className="w-full px-2.5 py-1.5 bg-violet-600/20 hover:bg-violet-600/30 border border-violet-500/30 text-violet-300 rounded-xl text-xs font-semibold flex items-center justify-center gap-2 transition-all"
              >
                <Database className="w-3.5 h-3.5" />
                <span>数据管理与备份</span>
              </button>

              <div className="flex items-center justify-between pt-1">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-violet-500 to-purple-600 text-white flex items-center justify-center font-bold text-xs shadow-md flex-shrink-0">
                    {authUser.charAt(0).toUpperCase()}
                  </div>
                  <div className="text-xs truncate">
                    <p className="font-semibold text-slate-200 leading-none truncate">{authUser}</p>
                    <span className="text-[9px] text-emerald-400 font-medium">Online</span>
                  </div>
                </div>
                <button
                  onClick={handleLogout}
                  className="p-1 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors flex-shrink-0"
                  title="退出登录"
                >
                  <LogOut className="w-3.5 h-3.5" />
                </button>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center gap-2 py-1">
              <button
                onClick={() => setIsBackupModalOpen(true)}
                className="p-2 text-violet-400 hover:bg-violet-600/20 rounded-xl transition"
                title="数据管理与备份"
              >
                <Database className="w-4 h-4" />
              </button>
              <button
                onClick={handleLogout}
                className="p-2 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-xl transition"
                title="退出登录"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Global Rates & Calculator Modal */}
      <Modal isOpen={isRatesModalOpen} onClose={() => setIsRatesModalOpen(false)} title="🌐 全局登记汇率看板与计算器" maxWidth="xl">
        <div className="space-y-5 text-xs">
          {/* Header Action: Fetch Live Rates */}
          <div className="flex items-center justify-between pb-2 border-b border-[#2A3447]">
            <span className="text-slate-300 font-medium">配置对 CNY (人民币) 的外币换算比率</span>
            <button
              onClick={() => fetchLiveRatesMutation.mutate()}
              disabled={fetchLiveRatesMutation.isPending}
              className="px-3 py-1.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white font-bold rounded-lg transition flex items-center gap-1.5 shadow"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${fetchLiveRatesMutation.isPending ? 'animate-spin' : ''}`} />
              <span>{fetchLiveRatesMutation.isPending ? '抓取中...' : '🌐 一键抓取最新实时汇率'}</span>
            </button>
          </div>

          {/* Registered Rates List & Inline Rate Editor */}
          <div className="space-y-2">
            <h3 className="font-bold text-slate-200">已登记外币汇率列表 (输入基准: 100外币 = X CNY)</h3>
            <div className="bg-[#0B0F17] border border-[#2A3447] rounded-xl p-3 space-y-2.5">
              {Object.entries(ratesMap).map(([curr, r]) => {
                const rate100 = (r * 100).toFixed(4);
                return (
                  <div key={curr} className="flex items-center justify-between gap-2 py-1 border-b border-[#2A3447]/50 last:border-0">
                    <span className="font-mono text-violet-400 font-bold w-20">100 {curr}</span>
                    <div className="flex items-center gap-1.5 flex-1">
                      <span className="text-slate-400 font-mono">=</span>
                      <input
                        type="number"
                        step="0.0001"
                        defaultValue={rate100}
                        onBlur={(e) => {
                          const val = parseFloat(e.target.value);
                          if (val && val > 0 && val !== r * 100) {
                            saveRateMutation.mutate({ currency: curr, rate100: val });
                          }
                        }}
                        className="w-28 bg-[#131924] border border-[#2A3447] rounded px-2 py-1 text-slate-100 font-mono text-xs focus:border-violet-500"
                      />
                      <span className="text-slate-300 font-mono font-bold">CNY</span>
                      <span className="text-slate-500 text-[10px] ml-auto font-mono">
                        (1 CNY = {(1 / r).toFixed(2)} {curr})
                      </span>
                    </div>
                    {curr !== 'JPY' && (
                      <button
                        onClick={() => {
                          if (confirm(`确定要移除 ${curr} 货币配置吗？`)) {
                            deleteRateMutation.mutate(curr);
                          }
                        }}
                        title="删除此外币"
                        className="p-1 text-slate-500 hover:text-rose-400 transition"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Inline Form to Add New Currency */}
          <div className="p-3 bg-[#0B0F17] border border-[#2A3447] rounded-xl space-y-2">
            <h4 className="font-bold text-slate-200 flex items-center gap-1.5">
              <Plus className="w-4 h-4 text-violet-400" />
              <span>➕ 追加外币汇率登记</span>
            </h4>
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="外币代号 (如: USD / EUR / HKD)"
                value={newCurrCode}
                onChange={(e) => setNewCurrCode(e.target.value.toUpperCase())}
                className="w-1/2 bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-1.5 text-slate-100 font-mono uppercase"
              />
              <input
                type="number"
                step="0.0001"
                placeholder="100外币折合CNY (如: 725)"
                value={newCurrRate100}
                onChange={(e) => setNewCurrRate100(e.target.value)}
                className="w-1/2 bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-1.5 text-slate-100 font-mono"
              />
              <button
                onClick={() => {
                  const c = newCurrCode.trim();
                  const r = parseFloat(newCurrRate100);
                  if (!c) { alert('请输入外币代号'); return; }
                  if (!r || r <= 0) { alert('请输入有效的汇率数值'); return; }
                  saveRateMutation.mutate({ currency: c, rate100: r });
                }}
                disabled={saveRateMutation.isPending}
                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 font-bold text-white rounded-lg transition shadow shrink-0"
              >
                添加
              </button>
            </div>
          </div>

          {/* Calculator Section */}
          <div className="bg-[#0B0F17] border border-[#2A3447] rounded-xl p-4 space-y-3">
            <h3 className="font-bold text-slate-200 flex items-center gap-1.5">
              <Calculator className="w-4 h-4 text-violet-400" />
              <span>汇率计算器</span>
            </h3>
            <div className="grid grid-cols-3 gap-2">
              <input
                type="number"
                value={calcAmount}
                onChange={(e) => setCalcAmount(parseFloat(e.target.value) || 0)}
                className="bg-[#131924] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100 font-mono"
              />
              <select
                value={calcFrom}
                onChange={(e) => setCalcFrom(e.target.value)}
                className="bg-[#131924] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100 font-mono"
              >
                {['CNY', ...Object.keys(ratesMap)].map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <select
                value={calcTo}
                onChange={(e) => setCalcTo(e.target.value)}
                className="bg-[#131924] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100 font-mono"
              >
                {['CNY', ...Object.keys(ratesMap)].map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div className="p-3 bg-violet-600/10 border border-violet-500/30 rounded-lg text-center">
              <span className="text-slate-400 text-[11px] block">折算结果</span>
              <span className="text-xl font-bold font-mono text-violet-300">
                = {getConvertedAmount().toLocaleString(undefined, { maximumFractionDigits: 2 })} {calcTo}
              </span>
            </div>
          </div>
        </div>
      </Modal>

      {/* Memo Dialog */}
      <Modal isOpen={isMemoModalOpen} onClose={() => setIsMemoModalOpen(false)} title="📝 备忘录管理" maxWidth="2xl">
        <div className="space-y-4 text-xs">
          <div className="flex items-center justify-between gap-3">
            <input
              type="text"
              placeholder="🔍 搜索备忘录 (按日期或内容)..."
              value={memoSearch}
              onChange={(e) => setMemoSearch(e.target.value)}
              className="bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100 flex-1"
            />
            <button
              onClick={() => createMemoMutation.mutate()}
              disabled={createMemoMutation.isPending}
              className="px-3 py-2 bg-violet-600 hover:bg-violet-500 text-white font-bold rounded-xl transition shadow-lg shadow-violet-500/20 flex items-center gap-1.5 flex-shrink-0"
            >
              <Plus className="w-4 h-4" />
              新增今日备忘
            </button>
          </div>

          <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
            {filteredMemos.length === 0 ? (
              <div className="text-slate-500 py-8 text-center bg-[#0B0F17] rounded-xl border border-[#2A3447]">
                {memoSearch ? '未匹配到相关备忘录' : '暂无备忘录，点击右上角新建'}
              </div>
            ) : (
              filteredMemos.map((m: any) => (
                <div key={m.id} className="p-3 bg-[#0B0F17] border border-[#2A3447] rounded-xl space-y-2">
                  <div className="flex items-center justify-between text-slate-400 text-[11px] pb-1 border-b border-[#2A3447]/60">
                    <span className="font-mono font-bold text-violet-300">📅 {m.date || '今日'}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-slate-500">{m.created_at ? new Date(m.created_at).toLocaleString() : ''}</span>
                      <button
                        onClick={() => deleteMemoMutation.mutate(m.id)}
                        className="text-slate-400 hover:text-rose-400 p-0.5 rounded"
                        title="删除备忘录"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                  <textarea
                    rows={3}
                    placeholder="请输入备忘内容..."
                    defaultValue={m.content || ''}
                    onBlur={(e) => {
                      if (e.target.value !== (m.content || '')) {
                        updateMemoMutation.mutate({ id: m.id, content: e.target.value, date: m.date });
                      }
                    }}
                    className="w-full bg-[#131924] border border-[#2A3447] focus:border-violet-500 rounded-lg p-2 text-slate-100 resize-none text-xs focus:outline-none"
                  />
                </div>
              ))
            )}
          </div>
        </div>
      </Modal>

      {/* Data Management & Backup Modal */}
      <Modal isOpen={isBackupModalOpen} onClose={() => setIsBackupModalOpen(false)} title="💾 数据管理与备份">
        <div className="space-y-5">
          <div className="space-y-2">
            <h3 className="font-bold text-slate-200 text-xs">备份下载</h3>
            <button
              onClick={handleDownloadBackup}
              className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-semibold flex items-center justify-center gap-2 shadow-lg shadow-emerald-600/20"
            >
              <Download className="w-4 h-4" />
              <span>下载全量数据备份 (ZIP)</span>
            </button>
          </div>

          <div className="space-y-2 pt-2 border-t border-slate-800">
            <h3 className="font-bold text-rose-400 text-xs flex items-center gap-1">
              <AlertTriangle className="w-4 h-4" />
              <span>危险操作：环境数据清空</span>
            </h3>
            <input
              type="text"
              placeholder="请输入 DELETE 以确认"
              value={deleteConfirm}
              onChange={(e) => setDeleteConfirm(e.target.value)}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-xs text-slate-100"
            />
            <button
              disabled={deleteConfirm !== 'DELETE'}
              className="w-full py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-xl text-xs font-semibold disabled:opacity-40"
            >
              确认清空所有数据
            </button>
          </div>
        </div>
      </Modal>
    </>
  );
};

export default Sidebar;
