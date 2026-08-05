// frontend/src/pages/SalesPage.tsx
import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { TrendingUp, ShoppingBag, Award, Banknote, Layers, Globe, Search, RefreshCw, ChevronLeft, ChevronRight, Info, AlertTriangle } from 'lucide-react';

interface LeaderboardItem {
  product_name: string;
  grand_total_cny: number;
  total_cny: number;
  total_jpy: number;
}

interface SalesRecord {
  id: string;
  date: string;
  product: string;
  variant: string;
  platform: string;
  currency: string;
  qty: number;
  amount: number;
  type: string;
}

interface SalesAnalyticsData {
  mode: 'v2' | 'v1';
  metrics: {
    total_cny: number;
    total_jpy: number;
    grand_total_cny: number;
    total_qty: number;
  };
  leaderboard: LeaderboardItem[];
  records: SalesRecord[];
  products: string[];
}

const PLATFORM_COLORS: Record<string, string> = {
  '微信私域': '#8B5CF6',
  '国内线下': '#10B981',
  '日本线下': '#3B82F6',
  '线下展会': '#F59E0B',
  'Booth': '#EC4899',
  '微店': '#6366F1',
};

const getPlatformColor = (plat: string, idx: number) => {
  if (PLATFORM_COLORS[plat]) return PLATFORM_COLORS[plat];
  const defaultColors = ['#8B5CF6', '#3B82F6', '#10B981', '#F59E0B', '#EC4899', '#6366F1', '#14B8A6'];
  return defaultColors[idx % defaultColors.length];
};

export const SalesPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'v2' | 'v1'>('v2');
  const [selectedProduct, setSelectedProduct] = useState<string>('');
  const [logPage, setLogPage] = useState<number>(1);
  const LOGS_PER_PAGE = 8;

  // Fetch Sales Analytics
  const { data: analyticsData, isLoading, refetch } = useQuery<SalesAnalyticsData>({
    queryKey: ['salesAnalytics', activeTab],
    queryFn: async () => {
      const res = await apiClient.get(`/sales/analytics/?mode=${activeTab}`);
      return res.data;
    },
  });

  const leaderboard = analyticsData?.leaderboard || [];
  const records = analyticsData?.records || [];
  const products = analyticsData?.products || [];
  const metrics = analyticsData?.metrics || { total_cny: 0, total_jpy: 0, grand_total_cny: 0, total_qty: 0 };

  // Set default selected product when data loads
  const currentProduct = useMemo(() => {
    if (selectedProduct && products.includes(selectedProduct)) {
      return selectedProduct;
    }
    return leaderboard.length > 0 ? leaderboard[0].product_name : (products[0] || '');
  }, [selectedProduct, products, leaderboard]);

  // Filter records for selected product
  const productRecords = useMemo(() => {
    if (!currentProduct) return [];
    return records.filter(r => r.product === currentProduct);
  }, [records, currentProduct]);

  // Metrics for selected product
  const pNetQty = useMemo(() => {
    return productRecords.reduce((sum, r) => sum + (Number(r.qty) || 0), 0);
  }, [productRecords]);

  const pCnyEquiv = useMemo(() => {
    return productRecords.reduce((sum, r) => {
      const amt = Number(r.amount) || 0;
      const cny = r.currency === 'JPY' ? amt * 0.048 : amt;
      return sum + cny;
    }, 0);
  }, [productRecords]);

  const pActivePlatforms = useMemo(() => {
    const plats = new Set(productRecords.map(r => r.platform).filter(Boolean));
    return plats.size;
  }, [productRecords]);

  // Pivot Table Calculation (Variants x Platforms)
  const pivotData = useMemo(() => {
    if (!productRecords.length) return { headers: [], rows: [] };

    const variantsSet = new Set<string>();
    const platformsSet = new Set<string>();
    const cellMap: Record<string, Record<string, number>> = {};

    productRecords.forEach(r => {
      const v = r.variant || '默认款式';
      const p = r.platform || '未知平台';
      const q = Number(r.qty) || 0;
      variantsSet.add(v);
      platformsSet.add(p);

      if (!cellMap[v]) cellMap[v] = {};
      cellMap[v][p] = (cellMap[v][p] || 0) + q;
    });

    const variants = Array.from(variantsSet).sort();
    const platforms = Array.from(platformsSet).sort();

    const rows = variants.map(v => {
      let rowTotal = 0;
      const qtys: Record<string, number> = {};
      platforms.forEach(p => {
        const qty = cellMap[v]?.[p] || 0;
        qtys[p] = qty;
        rowTotal += qty;
      });
      return { variant: v, qtys, totalQty: rowTotal };
    });

    // Summary Total Row
    const grandQtys: Record<string, number> = {};
    let totalAll = 0;
    platforms.forEach(p => {
      const sum = rows.reduce((acc, r) => acc + (r.qtys[p] || 0), 0);
      grandQtys[p] = sum;
      totalAll += sum;
    });

    rows.push({ variant: '总计', qtys: grandQtys, totalQty: totalAll });

    return { headers: ['款式', ...platforms, '总计'], platforms, rows };
  }, [productRecords]);

  // Stacked Bar Chart Data
  const chartData = useMemo(() => {
    if (!pivotData.rows.length) return [];
    return pivotData.rows
      .filter(r => r.variant !== '总计')
      .map(r => {
        const total = r.totalQty || 1;
        const platformBreakdown = pivotData.platforms.map((pName, pIdx) => {
          const qty = r.qtys[pName] || 0;
          const pct = Math.max(0, (qty / total) * 100);
          return {
            name: pName,
            qty,
            pctStr: `${pct.toFixed(1)}%`,
            color: getPlatformColor(pName, pIdx)
          };
        }).filter(item => item.qty > 0);

        return {
          variant: r.variant,
          totalQty: r.totalQty,
          platforms: platformBreakdown
        };
      });
  }, [pivotData]);

  // Paginated Log Records for Selected Product
  const totalLogPages = Math.ceil(productRecords.length / LOGS_PER_PAGE) || 1;
  const paginatedLogs = useMemo(() => {
    const start = (logPage - 1) * LOGS_PER_PAGE;
    return productRecords.slice(start, start + LOGS_PER_PAGE);
  }, [productRecords, logPage]);

  return (
    <div className="space-y-6 text-xs text-slate-100">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
            <span className="p-2 bg-violet-500/10 text-violet-400 rounded-xl border border-violet-500/20">📈</span>
            销售数据分析透视
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            多维度销量销售额聚合分析、热销排行榜与多渠道透视大屏
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="px-3.5 py-2 bg-[#18202F] hover:bg-[#222C3E] text-slate-200 font-medium rounded-xl border border-[#2A3447] transition flex items-center gap-1.5 shadow"
        >
          <RefreshCw className="w-3.5 h-3.5 text-violet-400" />
          刷新大屏数据
        </button>
      </div>

      {/* Mode Switcher Tabs */}
      <div className="space-y-3">
        <div className="flex border-b border-[#2A3447] text-xs font-bold gap-2">
          <button
            onClick={() => { setActiveTab('v2'); setLogPage(1); }}
            className={`px-4 py-2.5 rounded-t-xl transition flex items-center gap-2 border-t border-x ${
              activeTab === 'v2'
                ? 'bg-[#131924] border-[#2A3447] text-violet-400 border-b-transparent'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            🚀 V2.0 订单系统精准版
          </button>
          <button
            onClick={() => { setActiveTab('v1'); setLogPage(1); }}
            className={`px-4 py-2.5 rounded-t-xl transition flex items-center gap-2 border-t border-x ${
              activeTab === 'v1'
                ? 'bg-[#131924] border-[#2A3447] text-amber-400 border-b-transparent'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            🕰️ V1.0 历史兼容版
          </button>
        </div>

        {activeTab === 'v2' ? (
          <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-300 flex items-center gap-2">
            <Info className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>💡 【精准订单模式】：数据仅来源于「销售订单」和「售后管理」。数据完全隔离，剔除了早期反推中的冗余重复，兼容了“仅退款”场景。(推荐使用)</span>
          </div>
        ) : (
          <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-300 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>⚠️ 【历史兼容模式】：数据强行从底层的「物理库存变动日志」反向推演。包含无订单系统的早期历史脏数据，可能因物理入出库存在部分重复记录，仅供对账参考。</span>
          </div>
        )}
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center p-16 space-y-3 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447]">
          <RefreshCw className="w-6 h-6 animate-spin text-violet-400" />
          <p className="text-slate-400">正在加载全盘销售分析数据...</p>
        </div>
      ) : (
        <>
          {/* Top 3 Key Analytics Metric Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] space-y-1.5">
              <div className="flex items-center justify-between text-slate-400 font-medium">
                <span className="flex items-center gap-1.5">
                  <Banknote className="w-4 h-4 text-emerald-400" />
                  纯 CNY 累计收款额
                </span>
              </div>
              <div className="text-2xl font-bold font-mono text-emerald-400">
                ¥ {metrics.total_cny.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
              </div>
            </div>

            <div className="p-4 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] space-y-1.5">
              <div className="flex items-center justify-between text-slate-400 font-medium">
                <span className="flex items-center gap-1.5">
                  <TrendingUp className="w-4 h-4 text-violet-400" />
                  折合总销售额 (CNY总计)
                </span>
              </div>
              <div className="text-2xl font-bold font-mono text-violet-400">
                ¥ {metrics.grand_total_cny.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
              </div>
            </div>

            <div className="p-4 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] space-y-1.5">
              <div className="flex items-center justify-between text-slate-400 font-medium">
                <span className="flex items-center gap-1.5">
                  <Layers className="w-4 h-4 text-amber-400" />
                  累计销量总数
                </span>
              </div>
              <div className="text-2xl font-bold font-mono text-slate-100">
                {metrics.total_qty.toLocaleString()} 件
              </div>
            </div>
          </div>

          {/* Main 2-Column Split Dashboard Layout */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Left 4 Columns: Leaderboard */}
            <div className="lg:col-span-4 p-5 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] space-y-4">
              <div>
                <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                  <Award className="w-4 h-4 text-amber-400" />
                  🏆 热销产品榜单
                </h3>
                <p className="text-[11px] text-slate-400 mt-1">
                  点击产品行可以直接在右侧进行销售深度剖析。
                </p>
              </div>

              {leaderboard.length === 0 ? (
                <div className="text-center py-12 text-slate-400">暂无销售榜单数据</div>
              ) : (
                <div className="overflow-x-auto max-h-[600px] overflow-y-auto pr-1">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="border-b border-[#2A3447] text-slate-400 uppercase font-medium">
                        <th className="pb-2.5 px-2">排名</th>
                        <th className="pb-2.5 px-2">产品</th>
                        <th className="pb-2.5 px-2 text-right">折合总额</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#2A3447]/50">
                      {leaderboard.map((item, idx) => {
                        const isSelected = currentProduct === item.product_name;
                        return (
                          <tr
                            key={idx}
                            onClick={() => { setSelectedProduct(item.product_name); setLogPage(1); }}
                            className={`cursor-pointer transition ${
                              isSelected
                                ? 'bg-violet-600/15 border-l-4 border-l-violet-500 font-semibold'
                                : 'hover:bg-[#18202F] border-l-4 border-l-transparent'
                            }`}
                          >
                            <td className="py-2.5 px-2 font-mono text-slate-400 font-bold">
                              #{idx + 1}
                            </td>
                            <td className="py-2.5 px-2 text-slate-100 font-medium">
                              {item.product_name}
                            </td>
                            <td className="py-2.5 px-2 text-right font-mono font-bold text-violet-400">
                              ¥ {item.grand_total_cny.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Right 8 Columns: Deep Dive Product Analytics Panel */}
            <div className="lg:col-span-8 p-5 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] space-y-5">
              {!currentProduct ? (
                <div className="flex flex-col items-center justify-center p-16 text-slate-400 space-y-2 border border-dashed border-[#2A3447] rounded-xl">
                  <Search className="w-8 h-8 text-slate-500" />
                  <p>请选择左侧热卖产品或在上方下拉选择产品开始深入分析</p>
                </div>
              ) : (
                <>
                  {/* Deep Dive Panel Header */}
                  <div className="flex items-center justify-between gap-4 pb-3 border-b border-[#2A3447]">
                    <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
                      <span>📦</span>
                      <span className="text-violet-400">{currentProduct}</span>
                      <span>销售深度详情</span>
                    </h2>

                    <select
                      value={currentProduct}
                      onChange={(e) => { setSelectedProduct(e.target.value); setLogPage(1); }}
                      className="bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-1.5 text-slate-200 text-xs focus:outline-none focus:border-violet-500 max-w-[200px]"
                    >
                      {products.map(p => (
                        <option key={p} value={p}>{p}</option>
                      ))}
                    </select>
                  </div>

                  {/* 3 Metric Cards for Selected Product */}
                  <div className="grid grid-cols-3 gap-3">
                    <div className="p-3 bg-[#0B0F17] border border-[#2A3447] rounded-xl space-y-1">
                      <div className="flex items-center gap-1.5 text-slate-400 font-medium">
                        <ShoppingBag className="w-3.5 h-3.5 text-emerald-400" />
                        <span>净销量</span>
                      </div>
                      <div className="text-lg font-bold font-mono text-emerald-400">
                        {pNetQty.toLocaleString()} 件
                      </div>
                    </div>

                    <div className="p-3 bg-[#0B0F17] border border-[#2A3447] rounded-xl space-y-1">
                      <div className="flex items-center gap-1.5 text-slate-400 font-medium">
                        <Banknote className="w-3.5 h-3.5 text-violet-400" />
                        <span>折合销售额</span>
                      </div>
                      <div className="text-lg font-bold font-mono text-violet-400">
                        ¥ {pCnyEquiv.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                      </div>
                    </div>

                    <div className="p-3 bg-[#0B0F17] border border-[#2A3447] rounded-xl space-y-1">
                      <div className="flex items-center gap-1.5 text-slate-400 font-medium">
                        <Globe className="w-3.5 h-3.5 text-blue-400" />
                        <span>活跃平台数</span>
                      </div>
                      <div className="text-lg font-bold font-mono text-blue-400">
                        {pActivePlatforms} 个
                      </div>
                    </div>
                  </div>

                  {/* Pivot Table: Variant x Platform */}
                  <div className="space-y-3 pt-2">
                    <h3 className="text-xs font-bold text-slate-200 flex items-center gap-2">
                      <span>🧩</span> 款式-平台 交叉销量透视
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left border-collapse">
                        <thead>
                          <tr className="border-b border-[#2A3447] text-slate-400 font-medium">
                            {pivotData.headers.map((h, i) => (
                              <th key={i} className={`pb-2 px-2 ${i === 0 ? 'text-left' : 'text-center'}`}>
                                {h}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#2A3447]/40 text-slate-300">
                          {pivotData.rows.map((row, rIdx) => {
                            const isTotalRow = row.variant === '总计';
                            return (
                              <tr
                                key={rIdx}
                                className={isTotalRow ? 'bg-slate-800/60 font-bold text-slate-100' : 'hover:bg-[#18202F]'}
                              >
                                <td className="py-2 px-2 font-medium">{row.variant}</td>
                                {pivotData.platforms.map((pName, pIdx) => (
                                  <td key={pIdx} className="py-2 px-2 text-center font-mono">
                                    {row.qtys[pName] || 0}
                                  </td>
                                ))}
                                <td className="py-2 px-2 text-center font-mono font-bold text-violet-400">
                                  {row.totalQty}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Stacked Histogram Component */}
                  <div className="space-y-3 pt-2">
                    <h3 className="text-xs font-bold text-slate-200 flex items-center gap-2">
                      <span>📊</span> 各款式平台销量分布直方图
                    </h3>
                    <div className="space-y-3 bg-[#0B0F17] p-4 rounded-xl border border-[#2A3447]">
                      {chartData.map((item, idx) => (
                        <div key={idx} className="space-y-1.5">
                          <div className="flex justify-between items-center text-xs">
                            <span className="font-bold text-slate-200">{item.variant}</span>
                            <span className="px-2 py-0.5 rounded bg-violet-600/20 text-violet-300 font-mono text-[10px] font-bold">
                              {item.totalQty} 件
                            </span>
                          </div>
                          <div className="w-full h-3 bg-[#131924] rounded-full overflow-hidden flex border border-[#2A3447]">
                            {item.platforms.map((plat, pIdx) => (
                              <div
                                key={pIdx}
                                style={{ width: plat.pctStr, backgroundColor: plat.color }}
                                className="h-full transition-all hover:opacity-80"
                                title={`${plat.name}: ${plat.qty} 件 (${plat.pctStr})`}
                              />
                            ))}
                          </div>
                          <div className="flex flex-wrap gap-2 pt-1 text-[10px] text-slate-400">
                            {item.platforms.map((plat, pIdx) => (
                              <span key={pIdx} className="flex items-center gap-1">
                                <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: plat.color }} />
                                {plat.name}: <strong className="text-slate-200">{plat.qty}</strong> 件
                              </span>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Log Records 流水日志 */}
                  <div className="space-y-3 pt-2">
                    <h3 className="text-xs font-bold text-slate-200 flex items-center gap-2">
                      <span>📝</span> 销售流转日志流水 (含退款及撤销记录)
                    </h3>

                    {productRecords.length === 0 ? (
                      <div className="text-center py-6 text-slate-400">该产品暂无历史销量变动流水</div>
                    ) : (
                      <div className="space-y-3">
                        <div className="overflow-x-auto">
                          <table className="w-full text-left">
                            <thead>
                              <tr className="border-b border-[#2A3447] text-slate-400 uppercase font-medium">
                                <th className="pb-2 px-2">日期</th>
                                <th className="pb-2 px-2">类型</th>
                                <th className="pb-2 px-2">款式</th>
                                <th className="pb-2 px-2 text-center">数量</th>
                                <th className="pb-2 px-2">平台</th>
                                <th className="pb-2 px-2 text-right">金额明细</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-[#2A3447]/40 text-slate-300">
                              {paginatedLogs.map((log) => {
                                const isSale = log.type === 'sale';
                                const isRefund = log.type === 'refund';
                                const isReturn = log.type === 'return';
                                const qtyPrefix = log.qty > 0 ? '+' : '';

                                return (
                                  <tr key={log.id} className="hover:bg-[#18202F]">
                                    <td className="py-2 px-2 font-mono text-slate-400">{log.date}</td>
                                    <td className="py-2 px-2">
                                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                        isSale ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                                        isRefund ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20' :
                                        isReturn ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                                        'bg-slate-800 text-slate-400'
                                      }`}>
                                        {isSale ? '📤 售出' : isRefund ? '↩️ 退款' : isReturn ? '📦 退货' : log.type}
                                      </span>
                                    </td>
                                    <td className="py-2 px-2 font-medium">{log.variant}</td>
                                    <td className="py-2 px-2 text-center font-mono font-bold">
                                      <span className={log.qty < 0 ? 'text-rose-400' : 'text-emerald-400'}>
                                        {qtyPrefix}{log.qty}
                                      </span>
                                    </td>
                                    <td className="py-2 px-2 text-slate-300">{log.platform}</td>
                                    <td className="py-2 px-2 text-right font-mono font-bold text-slate-100">
                                      {log.amount >= 0 ? `¥ ${log.amount.toFixed(2)}` : `- ¥ ${Math.abs(log.amount).toFixed(2)}`} {log.currency}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>

                        {/* Pagination Controls */}
                        {totalLogPages > 1 && (
                          <div className="flex items-center justify-between pt-2 border-t border-[#2A3447]/50 text-xs">
                            <span className="text-slate-400">
                              显示第 {(logPage - 1) * LOGS_PER_PAGE + 1} - {Math.min(logPage * LOGS_PER_PAGE, productRecords.length)} 条，共 {productRecords.length} 条记录
                            </span>
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => setLogPage(p => Math.max(1, p - 1))}
                                disabled={logPage === 1}
                                className="px-3 py-1 bg-[#0B0F17] hover:bg-[#18202F] disabled:opacity-40 text-slate-300 rounded-lg border border-[#2A3447] flex items-center gap-1"
                              >
                                <ChevronLeft className="w-3.5 h-3.5" /> 上一页
                              </button>
                              <span className="font-mono text-slate-400">
                                第 <strong className="text-slate-200">{logPage}</strong> / {totalLogPages} 页
                              </span>
                              <button
                                onClick={() => setLogPage(p => Math.min(totalLogPages, p + 1))}
                                disabled={logPage === totalLogPages}
                                className="px-3 py-1 bg-[#0B0F17] hover:bg-[#18202F] disabled:opacity-40 text-slate-300 rounded-lg border border-[#2A3447] flex items-center gap-1"
                              >
                                下一页 <ChevronRight className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default SalesPage;
