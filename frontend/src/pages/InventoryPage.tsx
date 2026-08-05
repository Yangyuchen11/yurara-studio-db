// frontend/src/pages/InventoryPage.tsx
import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { InventoryLog } from '../types';
import { Modal } from '../components/ui/Modal';
import { StatCard } from '../components/ui/StatCard';
import { DataCard } from '../components/ui/DataCard';
import { FormField } from '../components/ui/FormField';
import { PageHeader } from '../components/ui/PageHeader';
import {
  Boxes,
  Warehouse as WhIcon,
  Plus,
  Trash2,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  Layers,
  Search,
  Wrench,
  Pencil,
  Filter,
  X,
  Lock,
  Zap
} from 'lucide-react';

const COST_CATEGORIES = [
  '面料采购',
  '辅料采购',
  '加工缝制',
  '后整包装',
  '打样研发',
  '物流运输',
  '检测检验',
  '营销宣发',
  '其他直接成本'
];

export const InventoryPage: React.FC = () => {
  const queryClient = useQueryClient();

  // Active Tab: 'stock' | 'warehouse'
  const [activeTab, setActiveTab] = useState<'stock' | 'warehouse'>('stock');

  // Selected Product for Tab 1
  const [selectedProdId, setSelectedProdId] = useState<number | ''>('');

  // Expanded Variant for Part Breakdown Table
  const [expandedVariant, setExpandedVariant] = useState<string | null>(null);

  // Modals
  const [isLogEditOpen, setIsLogEditOpen] = useState(false);
  const [editingLog, setEditingLog] = useState<InventoryLog | null>(null);
  const [editNote, setEditNote] = useState('');

  // Warehouse Form State
  const [newWhName, setNewWhName] = useState('');
  const [newWhRemarks, setNewWhRemarks] = useState('');
  const [isWhAccordionOpen, setIsWhAccordionOpen] = useState(false);

  // Warehouse Filter in Tab 2
  const [whFilterProduct, setWhFilterProduct] = useState<string>('');

  // Stock Movement Form State
  const [opDate, setOpDate] = useState<string>(new Date().toISOString().split('T')[0]);
  const [opType, setOpType] = useState<string>('入库 (验收完结成套)');
  const [opWhId, setOpWhId] = useState<number | ''>('');
  const [opToWhId, setOpToWhId] = useState<number | ''>('');
  const [opVariant, setOpVariant] = useState<string>('');
  const [opQty, setOpQty] = useState<number>(1);
  const [opIsSet, setOpIsSet] = useState<boolean>(true);
  const [opPart, setOpPart] = useState<string>('');
  const [opOutMode, setOpOutMode] = useState<'消耗' | '其他'>('其他');
  const [opConsCat, setOpConsCat] = useState<string>(COST_CATEGORIES[0]);
  const [opConsContent, setOpConsContent] = useState<string>('');
  const [opRemark, setOpRemark] = useState<string>('');
  const [movementError, setMovementError] = useState<string>('');

  // Fetch Inventory Summary
  const { data: summary, refetch: refetchSummary } = useQuery<any>({
    queryKey: ['inventory-summary', selectedProdId],
    queryFn: async () => {
      const url = selectedProdId ? `/inventory/summary/?product_id=${selectedProdId}` : '/inventory/summary/';
      const res = await apiClient.get(url);
      return res.data;
    },
  });

  // Fetch Inventory Logs
  const { data: logs, isLoading: logsLoading, refetch: refetchLogs } = useQuery<InventoryLog[]>({
    queryKey: ['inventory-logs'],
    queryFn: async () => {
      const res = await apiClient.get('/inventory/logs/');
      return res.data.results || res.data;
    },
  });

  // Derived Summary States
  const products = summary?.products || [];
  const currentProdId = summary?.selected_product_id || selectedProdId || (products[0]?.id ?? '');
  const currentProdName = summary?.selected_product_name || (products.find((p: any) => p.id === currentProdId)?.name ?? '');
  const isProductionCompleted = summary?.is_production_completed || false;
  const wipBalanceStr = summary?.wip_balance_str || '¥ 0.00';
  const stats = summary?.stats || {};
  const excessParts = summary?.excess_parts || [];
  const warehouseList = summary?.warehouses || [];

  // Variant & Part Options
  const activeVariants = useMemo(() => {
    return Object.keys(stats);
  }, [stats]);

  const activeParts = useMemo(() => {
    if (!opVariant || !stats[opVariant]) return [];
    const partsDetail = stats[opVariant].parts || [];
    return partsDetail.map((pt: any) => pt.part_name);
  }, [stats, opVariant]);

  // Set default variant when stats load
  React.useEffect(() => {
    if (activeVariants.length > 0 && !opVariant) {
      setOpVariant(activeVariants[0]);
    }
  }, [activeVariants, opVariant]);

  // Mutations
  const movementMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await apiClient.post('/inventory/logs/movement/', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['inventory-summary'] });
      queryClient.invalidateQueries({ queryKey: ['inventory-logs'] });
      setOpRemark('');
      setOpConsContent('');
      setMovementError('');
      alert('🚀 库存变动提交成功！');
    },
    onError: (err: any) => {
      setMovementError(err.response?.data?.error || '库存移动提交失败');
    },
  });

  const clearWipMutation = useMutation({
    mutationFn: async (productId: number) => {
      const res = await apiClient.post('/inventory/clear-wip/', { product_id: productId });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['inventory-summary'] });
      alert('✨ 在制资产已结算/重算完成！');
    },
    onError: (err: any) => {
      alert(`在制结算失败: ${err.response?.data?.error || err.message}`);
    }
  });

  const updateLogNoteMutation = useMutation({
    mutationFn: async ({ id, note }: { id: number; note: string }) => {
      const res = await apiClient.patch(`/inventory/logs/${id}/update_note/`, { note });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['inventory-logs'] });
      setIsLogEditOpen(false);
      setEditingLog(null);
    },
  });

  const deleteLogMutation = useMutation({
    mutationFn: async (logId: number) => {
      const res = await apiClient.delete(`/inventory/logs/${logId}/cascade_delete/`);
      return res.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['inventory-summary'] });
      queryClient.invalidateQueries({ queryKey: ['inventory-logs'] });
      alert(`🗑️ 变动日志已回滚删除: ${data.message || '操作成功'}`);
    },
    onError: (err: any) => {
      alert(`删除失败: ${err.response?.data?.error || err.message}`);
    }
  });

  const createWarehouseMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await apiClient.post('/warehouses/', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['inventory-summary'] });
      queryClient.invalidateQueries({ queryKey: ['warehouses'] });
      setNewWhName('');
      setNewWhRemarks('');
      setIsWhAccordionOpen(false);
      alert('🏢 物理仓库创建成功！');
    },
    onError: (err: any) => {
      alert(`创建仓库失败: ${err.response?.data?.error || err.message}`);
    }
  });

  const deleteWarehouseMutation = useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/warehouses/${id}/`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['inventory-summary'] });
      queryClient.invalidateQueries({ queryKey: ['warehouses'] });
      alert('🗑️ 仓库已成功注销！');
    },
    onError: (err: any) => {
      alert(`注销仓库失败: ${err.response?.data?.error || err.message}`);
    }
  });

  // Handle Movement Form Submit
  const handleSubmitMovement = (e: React.FormEvent) => {
    e.preventDefault();
    setMovementError('');

    if (!currentProdId || !currentProdName) {
      setMovementError('请先选择有效的商品');
      return;
    }
    if (!opVariant) {
      setMovementError('请选择颜色款式');
      return;
    }
    if (opQty <= 0) {
      setMovementError('变动数量必须大于 0');
      return;
    }

    let mappedReason = opType;
    if (opType === '入库 (验收完结成套)') mappedReason = '验收完成入库';
    if (opType === '入库验收中') mappedReason = '入库验收中';
    if (opType === '其他入库') mappedReason = '其他入库';
    if (opType === '出库') mappedReason = '出库';
    if (opType === '调拨') mappedReason = '调拨';

    if (mappedReason === '调拨') {
      if (!opWhId || !opToWhId) {
        setMovementError('调拨操作必须同时选择移出仓库与移入仓库');
        return;
      }
      if (opWhId === opToWhId) {
        setMovementError('移出仓库与移入仓库不能相同');
        return;
      }
    }

    if (mappedReason === '出库' && opOutMode === '消耗' && !opConsContent.trim()) {
      setMovementError('选择“消耗”出库模式时，必须填写“消耗内容描述”');
      return;
    }

    movementMutation.mutate({
      product_id: Number(currentProdId),
      product_name: currentProdName,
      variant: opVariant,
      quantity: Number(opQty),
      move_type: mappedReason,
      date: opDate,
      remark: opRemark,
      warehouse_id: opWhId || null,
      to_warehouse_id: opToWhId || null,
      is_set: opIsSet,
      part_name: opIsSet ? null : opPart,
      out_type: mappedReason === '出库' ? opOutMode : null,
      cons_cat: mappedReason === '出库' && opOutMode === '消耗' ? opConsCat : null,
      cons_content: mappedReason === '出库' && opOutMode === '消耗' ? opConsContent : null,
    });
  };

  const isTransferMode = opType === '调拨';
  const isOutMode = opType === '出库';

  const logList = Array.isArray(logs) ? logs : [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="↔️ 仓库库存管理"
        subtitle="适配成套拆分与散件实存计算、在制资产冲销及出入库/调拨/销毁回滚日志追溯"
        action={
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                refetchSummary();
                refetchLogs();
              }}
              className="px-3.5 py-2 bg-[#18202F] hover:bg-[#222C3E] text-slate-200 text-xs font-medium rounded-xl border border-[#2A3447] transition flex items-center gap-1.5 shadow"
            >
              <RefreshCw className="w-3.5 h-3.5 text-violet-400" />
              刷新数据
            </button>
          </div>
        }
      />

      {/* Primary Tab Bar */}
      <div className="flex border-b border-[#2A3447] text-xs font-bold">
        <button
          onClick={() => setActiveTab('stock')}
          className={`px-4 py-2.5 border-b-2 transition flex items-center gap-2 ${
            activeTab === 'stock'
              ? 'border-violet-500 text-violet-400 bg-violet-500/10'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Boxes className="w-4 h-4 text-violet-400" />
          <span>库存管理与盘点</span>
        </button>
        <button
          onClick={() => setActiveTab('warehouse')}
          className={`px-4 py-2.5 border-b-2 transition flex items-center gap-2 ${
            activeTab === 'warehouse'
              ? 'border-violet-500 text-violet-400 bg-violet-500/10'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <WhIcon className="w-4 h-4 text-violet-400" />
          <span>物理仓库与明细</span>
        </button>
      </div>

      {/* ==================== TAB 1: STOCK MANAGEMENT ==================== */}
      {activeTab === 'stock' && (
        <div className="space-y-6">
          {/* Top Product Switch Bar */}
          <div className="p-4 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="text-xs font-bold text-slate-200">当前核算商品:</span>
              <select
                value={currentProdId}
                onChange={(e) => {
                  const val = Number(e.target.value);
                  setSelectedProdId(val);
                }}
                className="bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-1.5 text-xs text-slate-100 font-bold focus:outline-none focus:border-violet-500"
              >
                {products.map((p: any) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              {isProductionCompleted ? (
                <span className="px-3 py-1 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-full text-xs font-bold flex items-center gap-1.5">
                  <Lock className="w-3.5 h-3.5" />
                  🔒 生产结单
                </span>
              ) : (
                <span className="px-3 py-1 bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded-full text-xs font-bold flex items-center gap-1.5">
                  <Zap className="w-3.5 h-3.5" />
                  ⚡ WIP 流转中
                </span>
              )}
            </div>
          </div>

          {products.length === 0 ? (
            <div className="p-8 text-center bg-amber-500/10 border border-amber-500/30 rounded-2xl text-amber-300 text-xs">
              ⚠️ 系统里没有任何商品，请先前往商品管理模块开户创建商品！
            </div>
          ) : (
            <>
              {/* 2-Column Main Content */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                {/* Left 7 Columns: Variant Progress Table */}
                <div className="lg:col-span-7 space-y-4">
                  <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-violet-400" />
                    🎨 款式生产及实存进度表
                  </h3>

                  <DataCard title="各款式细化统计 (成套)">
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs">
                        <thead>
                          <tr className="border-b border-[#2A3447] text-slate-400 font-medium uppercase">
                            <th className="pb-2 px-2">款式颜色</th>
                            <th className="pb-2 px-2 text-right">计划生产数</th>
                            <th className="pb-2 px-2 text-right">验收完成入库</th>
                            <th className="pb-2 px-2 text-right">入库验收中</th>
                            <th className="pb-2 px-2 text-right">仓储实物(成套)</th>
                            <th className="pb-2 px-2 text-center">供货状态</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#2A3447]/50 text-slate-300">
                          {Object.entries(stats).map(([vName, row]: [string, any]) => {
                            const isExpanded = expandedVariant === vName;
                            return (
                              <React.Fragment key={vName}>
                                <tr
                                  onClick={() => setExpandedVariant(isExpanded ? null : vName)}
                                  className={`hover:bg-[#18202F] cursor-pointer transition ${
                                    isExpanded ? 'bg-violet-500/10' : ''
                                  }`}
                                >
                                  <td className="py-2.5 px-2 font-medium text-slate-100 flex items-center gap-1.5">
                                    {isExpanded ? (
                                      <ChevronDown className="w-3.5 h-3.5 text-violet-400 shrink-0" />
                                    ) : (
                                      <ChevronRight className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                                    )}
                                    <span>🎨 {vName}</span>
                                  </td>
                                  <td className="py-2.5 px-2 text-right font-mono font-bold text-slate-300">
                                    {row.planned}
                                  </td>
                                  <td className="py-2.5 px-2 text-right font-mono text-slate-300">
                                    {row.produced}
                                  </td>
                                  <td className="py-2.5 px-2 text-right font-mono text-slate-400">
                                    {row.inspecting}
                                  </td>
                                  <td className="py-2.5 px-2 text-right font-mono font-bold text-emerald-400">
                                    {row.actual}
                                  </td>
                                  <td className="py-2.5 px-2 text-center">
                                    <span
                                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                        row.actual > 0
                                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                          : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                                      }`}
                                    >
                                      {row.actual > 0 ? '现货在库' : '暂无成套'}
                                    </span>
                                  </td>
                                </tr>

                                {/* Expanded Child Breakdown */}
                                {isExpanded && (
                                  <tr>
                                    <td colSpan={6} className="p-3 bg-[#0B0F17]/80">
                                      <div className="p-3 bg-[#131924] rounded-xl border border-violet-500/30 space-y-2">
                                        <div className="flex items-center gap-1.5 text-xs font-bold text-violet-300">
                                          <Layers className="w-4 h-4 text-violet-400" />
                                          <span>【{vName}】各部件独立入库与库存拆分明细</span>
                                        </div>
                                        <table className="w-full text-left text-[11px]">
                                          <thead>
                                            <tr className="border-b border-[#2A3447] text-slate-400">
                                              <th className="pb-1.5 px-2">部件名称</th>
                                              <th className="pb-1.5 px-2 text-center">单套配比</th>
                                              <th className="pb-1.5 px-2 text-right">部件入库完成(件)</th>
                                              <th className="pb-1.5 px-2 text-right">部件验收中(件)</th>
                                              <th className="pb-1.5 px-2 text-right">部件仓储实物(件)</th>
                                            </tr>
                                          </thead>
                                          <tbody className="divide-y divide-[#2A3447]/40 text-slate-300">
                                            {(row.parts || []).map((pt: any, ptIdx: number) => (
                                              <tr key={ptIdx}>
                                                <td className="py-1.5 px-2 font-medium text-slate-200">
                                                  ↳ {pt.part_name}
                                                </td>
                                                <td className="py-1.5 px-2 text-center font-mono">
                                                  <span className="px-1.5 py-0.5 bg-slate-800 rounded text-slate-400">
                                                    1套配 {pt.req_qty} 件
                                                  </span>
                                                </td>
                                                <td className="py-1.5 px-2 text-right font-mono text-slate-400">
                                                  {pt.produced}
                                                </td>
                                                <td className="py-1.5 px-2 text-right font-mono text-slate-400">
                                                  {pt.inspecting}
                                                </td>
                                                <td className="py-1.5 px-2 text-right font-mono font-bold text-slate-100">
                                                  {pt.actual_qty}
                                                </td>
                                              </tr>
                                            ))}
                                          </tbody>
                                        </table>
                                      </div>
                                    </td>
                                  </tr>
                                )}
                              </React.Fragment>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </DataCard>

                  {/* Excess Parts Accordion */}
                  {excessParts.length > 0 && (
                    <div className="p-3 bg-[#131924]/90 rounded-xl border border-violet-500/30 text-xs space-y-2">
                      <div className="flex items-center gap-1.5 font-bold text-violet-300">
                        <Search className="w-3.5 h-3.5 text-violet-400" />
                        <span>查看无法成套的散落部件物理余量</span>
                      </div>
                      <table className="w-full text-left text-xs">
                        <thead>
                          <tr className="border-b border-[#2A3447] text-slate-400">
                            <th className="pb-1 px-2">款式</th>
                            <th className="pb-1 px-2">散落部件</th>
                            <th className="pb-1 px-2 text-right">物理数量</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#2A3447]/40 text-slate-300">
                          {excessParts.map((ex: any, idx: number) => (
                            <tr key={idx}>
                              <td className="py-1.5 px-2 font-mono text-slate-400">{ex.variant}</td>
                              <td className="py-1.5 px-2 font-medium text-slate-200">{ex.part_name}</td>
                              <td className="py-1.5 px-2 text-right font-mono">
                                <span className="px-2 py-0.5 bg-amber-500/20 text-amber-300 font-bold rounded">
                                  {ex.qty} 件
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {/* Right 5 Columns: Operations & WIP Clearance */}
                <div className="lg:col-span-5 space-y-4">
                  <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                    <Wrench className="w-4 h-4 text-violet-400" />
                    ⚙️ 仓储操作与在制资产
                  </h3>

                  {/* WIP Stat Card */}
                  <StatCard
                    label="在制资产估值 (WIP)"
                    value={wipBalanceStr}
                    unit=""
                    icon={Wrench}
                    colorScheme="orange"
                  />

                  {/* Production Completion / Clear WIP Action Card */}
                  <div className="p-4 bg-[#131924] rounded-xl border border-[#2A3447] space-y-3 text-xs">
                    {isProductionCompleted ? (
                      <>
                        <p className="text-slate-400 leading-relaxed">
                          💡 该商品已生产结单（在制资产已清零）。若后期追加了新的真实物理成本项，请点击下方按钮重新触发木桶还原估值与大货资产的同步核算：
                        </p>
                        <button
                          onClick={() => clearWipMutation.mutate(Number(currentProdId))}
                          disabled={clearWipMutation.isPending}
                          className="w-full py-2 bg-violet-600/20 hover:bg-violet-600/30 text-violet-300 border border-violet-500/30 font-bold rounded-xl transition flex items-center justify-center gap-2"
                        >
                          <RefreshCw className="w-3.5 h-3.5" />
                          <span>重新核算大货成本与资产</span>
                        </button>
                      </>
                    ) : (
                      <>
                        <p className="text-slate-400 leading-relaxed">
                          💡 当前未完结生产，可在生产大货全部进入仓库后，清零在制折旧冲账大货：
                        </p>
                        <button
                          onClick={() => clearWipMutation.mutate(Number(currentProdId))}
                          disabled={clearWipMutation.isPending}
                          className="w-full py-2 bg-rose-600 hover:bg-rose-500 text-white font-bold rounded-xl transition shadow-lg shadow-rose-500/20 flex items-center justify-center gap-2"
                        >
                          <Lock className="w-3.5 h-3.5" />
                          <span>🚀 生产结单 (在制资产清零)</span>
                        </button>
                      </>
                    )}
                  </div>

                  {/* Inventory Movement Form Card */}
                  <div className="p-4 bg-[#131924] rounded-xl border border-[#2A3447] space-y-4 text-xs">
                    <h4 className="font-bold text-slate-100 text-sm flex items-center gap-2">
                      <Plus className="w-4 h-4 text-violet-400" />
                      📝 新增库存变动录入
                    </h4>

                    {movementError && (
                      <div className="p-2.5 bg-rose-500/10 border border-rose-500/30 rounded-lg text-rose-400">
                        {movementError}
                      </div>
                    )}

                    <form onSubmit={handleSubmitMovement} className="space-y-3">
                      <div className="grid grid-cols-2 gap-2.5">
                        <FormField label="变动日期" required>
                          <input
                            type="date"
                            value={opDate}
                            onChange={(e) => setOpDate(e.target.value)}
                            className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100"
                          />
                        </FormField>

                        <FormField label="变动操作类型" required>
                          <select
                            value={opType}
                            onChange={(e) => setOpType(e.target.value)}
                            className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100 font-bold"
                          >
                            <option value="入库 (验收完结成套)">入库 (验收完结成套)</option>
                            <option value="入库验收中">入库验收中</option>
                            <option value="其他入库">其他入库</option>
                            <option value="出库">出库 (消耗/其他)</option>
                            <option value="调拨">调拨 (仓库间移动)</option>
                          </select>
                        </FormField>
                      </div>

                      {/* Warehouse Selector */}
                      {isTransferMode ? (
                        <div className="grid grid-cols-2 gap-2.5">
                          <FormField label="移出仓库 (源库)" required>
                            <select
                              value={opWhId}
                              onChange={(e) => setOpWhId(e.target.value ? Number(e.target.value) : '')}
                              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100"
                            >
                              <option value="">-- 选择移出仓库 --</option>
                              {warehouseList.map((w: any) => (
                                <option key={w.id} value={w.id}>
                                  {w.name}
                                </option>
                              ))}
                            </select>
                          </FormField>
                          <FormField label="移入仓库 (目的库)" required>
                            <select
                              value={opToWhId}
                              onChange={(e) => setOpToWhId(e.target.value ? Number(e.target.value) : '')}
                              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100"
                            >
                              <option value="">-- 选择移入仓库 --</option>
                              {warehouseList.map((w: any) => (
                                <option key={w.id} value={w.id}>
                                  {w.name}
                                </option>
                              ))}
                            </select>
                          </FormField>
                        </div>
                      ) : (
                        <FormField label="目标操作仓库">
                          <select
                            value={opWhId}
                            onChange={(e) => setOpWhId(e.target.value ? Number(e.target.value) : '')}
                            className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100"
                          >
                            <option value="">-- 选择目标仓库 --</option>
                            {warehouseList.map((w: any) => (
                              <option key={w.id} value={w.id}>
                                {w.name}
                              </option>
                            ))}
                          </select>
                        </FormField>
                      )}

                      <div className="grid grid-cols-2 gap-2.5">
                        <FormField label="选择款式" required>
                          <select
                            value={opVariant}
                            onChange={(e) => setOpVariant(e.target.value)}
                            className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100"
                          >
                            {activeVariants.map((v: string) => (
                              <option key={v} value={v}>
                                {v}
                              </option>
                            ))}
                          </select>
                        </FormField>

                        <FormField label="变动套数/物理件数" required>
                          <input
                            type="number"
                            value={opQty}
                            onChange={(e) => setOpQty(parseInt(e.target.value) || 1)}
                            className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100 font-mono"
                          />
                        </FormField>
                      </div>

                      {/* Is Set vs Part Toggle */}
                      <div className="p-2.5 bg-[#0B0F17] border border-[#2A3447] rounded-xl space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-slate-300 font-medium">整套动作 (所有部件同比例变动)</span>
                          <input
                            type="checkbox"
                            checked={opIsSet}
                            onChange={(e) => setOpIsSet(e.target.checked)}
                            className="w-4 h-4 accent-violet-500 cursor-pointer"
                          />
                        </div>
                        {!opIsSet && (
                          <FormField label="选择归属物理散件">
                            <select
                              value={opPart}
                              onChange={(e) => setOpPart(e.target.value)}
                              className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-2 py-1 text-slate-100"
                            >
                              <option value="">-- 选择具体部件 --</option>
                              {activeParts.map((pt: string) => (
                                <option key={pt} value={pt}>
                                  {pt}
                                </option>
                              ))}
                            </select>
                          </FormField>
                        )}
                      </div>

                      {/* Extra Out Mode Fields */}
                      {isOutMode && (
                        <div className="p-3 bg-[#0B0F17] border border-[#2A3447] rounded-xl space-y-2">
                          <label className="block text-slate-300 font-medium">出库分类模式</label>
                          <div className="flex gap-4 text-slate-200">
                            <label className="flex items-center gap-1.5 cursor-pointer">
                              <input
                                type="radio"
                                name="outMode"
                                value="消耗"
                                checked={opOutMode === '消耗'}
                                onChange={() => setOpOutMode('消耗')}
                              />
                              <span>消耗 (自动计入成本)</span>
                            </label>
                            <label className="flex items-center gap-1.5 cursor-pointer">
                              <input
                                type="radio"
                                name="outMode"
                                value="其他"
                                checked={opOutMode === '其他'}
                                onChange={() => setOpOutMode('其他')}
                              />
                              <span>其他 (不增加成本)</span>
                            </label>
                          </div>

                          {opOutMode === '消耗' && (
                            <div className="grid grid-cols-2 gap-2 pt-2">
                              <FormField label="计入成本科目">
                                <select
                                  value={opConsCat}
                                  onChange={(e) => setOpConsCat(e.target.value)}
                                  className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-2 py-1 text-slate-100"
                                >
                                  {COST_CATEGORIES.map((cat) => (
                                    <option key={cat} value={cat}>
                                      {cat}
                                    </option>
                                  ))}
                                </select>
                              </FormField>
                              <FormField label="消耗描述 (必填)">
                                <input
                                  type="text"
                                  placeholder="如: 拍摄样衣"
                                  value={opConsContent}
                                  onChange={(e) => setOpConsContent(e.target.value)}
                                  className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-2 py-1 text-slate-100"
                                />
                              </FormField>
                            </div>
                          )}
                        </div>
                      )}

                      <FormField label="备注 (选填)">
                        <input
                          type="text"
                          placeholder="操作补充说明"
                          value={opRemark}
                          onChange={(e) => setOpRemark(e.target.value)}
                          className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100"
                        />
                      </FormField>

                      <button
                        type="submit"
                        disabled={movementMutation.isPending}
                        className="w-full py-2.5 bg-violet-600 hover:bg-violet-500 font-bold text-white rounded-xl transition shadow-lg shadow-violet-500/20"
                      >
                        {movementMutation.isPending ? '提交中...' : '🚀 提交库存移动/盘点'}
                      </button>
                    </form>
                  </div>
                </div>
              </div>

              {/* Bottom Section: Inventory Logs & Rollback */}
              <div className="space-y-4">
                <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-indigo-400" />
                  📜 仓储物理日志与操作审计变动历史
                </h3>

                <DataCard title="物理仓储移动变动明细 (支持精准级联回滚)">
                  {logsLoading ? (
                    <div className="text-xs text-slate-400 py-6 text-center">加载日志记录中...</div>
                  ) : logList.length === 0 ? (
                    <div className="text-xs text-slate-400 py-6 text-center">该商品近期没有进行过物理变动操作</div>
                  ) : (
                    <div className="overflow-x-auto max-h-96 overflow-y-auto">
                      <table className="w-full text-left text-xs">
                        <thead>
                          <tr className="border-b border-[#2A3447] text-slate-400 uppercase font-medium">
                            <th className="pb-2 px-2">日期</th>
                            <th className="pb-2 px-2">商品</th>
                            <th className="pb-2 px-2">款式</th>
                            <th className="pb-2 px-2">规格/模式</th>
                            <th className="pb-2 px-2">所属仓库</th>
                            <th className="pb-2 px-2 text-right">变动量</th>
                            <th className="pb-2 px-2 text-center">物理类型</th>
                            <th className="pb-2 px-2">审计说明 (可改)</th>
                            <th className="pb-2 px-2 text-center">操作</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#2A3447]/50 text-slate-300">
                          {logList.map((log) => {
                            const amt = log.change_amount ?? 0;
                            const isPositive = amt > 0;
                            const partDisp = log.part_name ? log.part_name : '整套';
                            return (
                              <tr key={log.id} className="hover:bg-[#18202F]">
                                <td className="py-2.5 px-2 font-mono text-slate-400">{log.date}</td>
                                <td className="py-2.5 px-2 font-bold text-slate-200">{log.product_name}</td>
                                <td className="py-2.5 px-2 font-medium text-slate-300">{log.variant}</td>
                                <td className="py-2.5 px-2">
                                  <span className="px-2 py-0.5 bg-violet-500/10 text-violet-300 rounded border border-violet-500/20 text-[10px]">
                                    {partDisp}
                                  </span>
                                </td>
                                <td className="py-2.5 px-2 font-mono text-slate-400">
                                  {log.warehouse_name || '未分配仓库'}
                                </td>
                                <td
                                  className={`py-2.5 px-2 text-right font-mono font-bold ${
                                    isPositive ? 'text-emerald-400' : 'text-rose-400'
                                  }`}
                                >
                                  {isPositive ? `+${amt}` : amt}
                                </td>
                                <td className="py-2.5 px-2 text-center">
                                  <span className="px-2 py-0.5 bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded text-[10px] font-bold">
                                    {log.reason}
                                  </span>
                                </td>
                                <td className="py-2.5 px-2 text-slate-400 truncate max-w-xs">{log.note || '-'}</td>
                                <td className="py-2.5 px-2 text-center">
                                  <div className="flex items-center justify-center gap-1">
                                    <button
                                      onClick={() => {
                                        setEditingLog(log);
                                        setEditNote(log.note || '');
                                        setIsLogEditOpen(true);
                                      }}
                                      title="修改审计备注"
                                      className="p-1 text-slate-400 hover:text-violet-400 transition"
                                    >
                                      <Pencil className="w-3.5 h-3.5" />
                                    </button>
                                    <button
                                      onClick={() => {
                                        if (confirm(`确定要级联撤销该笔库存变动吗？ (ID: ${log.id})`)) {
                                          deleteLogMutation.mutate(log.id);
                                        }
                                      }}
                                      title="撤销/删除此变动记录"
                                      className="p-1 text-slate-400 hover:text-rose-400 transition"
                                    >
                                      <Trash2 className="w-3.5 h-3.5" />
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </DataCard>
              </div>
            </>
          )}
        </div>
      )}

      {/* ==================== TAB 2: WAREHOUSE DETAIL ==================== */}
      {activeTab === 'warehouse' && (
        <div className="space-y-6">
          <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <WhIcon className="w-4 h-4 text-violet-400" />
            🏢 物理仓储实体网点配置
          </h3>

          {/* Add Warehouse Inline Card Accordion */}
          <div className="p-4 bg-[#131924] rounded-2xl border border-[#2A3447] space-y-3">
            <button
              onClick={() => setIsWhAccordionOpen(!isWhAccordionOpen)}
              className="w-full flex items-center justify-between text-xs font-bold text-slate-200"
            >
              <span className="flex items-center gap-1.5">
                <Plus className="w-4 h-4 text-violet-400" />
                开立配置新仓库
              </span>
              {isWhAccordionOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </button>

            {isWhAccordionOpen && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!newWhName.trim()) return;
                  createWarehouseMutation.mutate({ name: newWhName.trim(), remarks: newWhRemarks.trim() });
                }}
                className="space-y-3 pt-2 text-xs"
              >
                <div className="grid grid-cols-2 gap-3">
                  <FormField label="仓库名称" required>
                    <input
                      type="text"
                      placeholder="如: 北京1号分拣仓"
                      value={newWhName}
                      onChange={(e) => setNewWhName(e.target.value)}
                      className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-1.5 text-slate-100"
                    />
                  </FormField>
                  <FormField label="仓库备注">
                    <input
                      type="text"
                      placeholder="如: 地址/联系人电话"
                      value={newWhRemarks}
                      onChange={(e) => setNewWhRemarks(e.target.value)}
                      className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-1.5 text-slate-100"
                    />
                  </FormField>
                </div>
                <button
                  type="submit"
                  disabled={createWarehouseMutation.isPending}
                  className="px-4 py-2 bg-violet-600 hover:bg-violet-500 font-bold text-white rounded-xl transition shadow"
                >
                  新建并持久化该仓库
                </button>
              </form>
            )}
          </div>

          {/* Warehouse Product Filter Header */}
          <div className="flex items-center justify-between gap-4">
            <h4 className="text-xs font-bold text-slate-200">
              🏬 各实体网点散落实存清单明细 (成套木桶还原折算)
            </h4>

            <div className="flex items-center gap-2 text-xs">
              <Filter className="w-3.5 h-3.5 text-violet-400" />
              <span className="text-slate-400 font-medium">商品筛选:</span>
              <select
                value={whFilterProduct}
                onChange={(e) => setWhFilterProduct(e.target.value)}
                className="bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-1 text-slate-100 font-bold"
              >
                <option value="">全部商品</option>
                {products.map((p: any) => (
                  <option key={p.id} value={p.name}>
                    {p.name}
                  </option>
                ))}
              </select>
              {whFilterProduct && (
                <button
                  onClick={() => setWhFilterProduct('')}
                  className="p-1 text-slate-400 hover:text-slate-200 flex items-center gap-1"
                >
                  <X className="w-3.5 h-3.5" />
                  <span>清除筛选</span>
                </button>
              )}
            </div>
          </div>

          {/* Physical Warehouses Cards Grid */}
          <div className="space-y-4">
            {warehouseList.length === 0 ? (
              <div className="text-xs text-slate-400 py-8 text-center bg-[#131924] rounded-xl border border-[#2A3447]">
                尚未创建任何实体物理仓库，请先在上方进行仓库开立。
              </div>
            ) : (
              warehouseList.map((wh: any) => {
                const stockMap = wh.stock || {};
                const filteredStockEntries: any[] = [];

                Object.entries(stockMap).forEach(([pName, vMap]: [string, any]) => {
                  if (whFilterProduct && pName !== whFilterProduct) return;

                  Object.entries(vMap).forEach(([vName, ptMap]: [string, any]) => {
                    Object.entries(ptMap).forEach(([ptName, qty]: [string, any]) => {
                      if (qty !== 0) {
                        filteredStockEntries.push({
                          product_name: pName,
                          variant: vName,
                          part_name: ptName,
                          physical_qty: qty,
                        });
                      }
                    });
                  });
                });

                return (
                  <div key={wh.id} className="p-4 bg-[#131924] rounded-2xl border border-[#2A3447] space-y-3">
                    <div className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <WhIcon className="w-4 h-4 text-violet-400" />
                        <span className="font-bold text-slate-100 text-sm">{wh.name}</span>
                        {wh.remarks && <span className="text-slate-400">({wh.remarks})</span>}
                      </div>

                      {wh.is_empty && (
                        <button
                          onClick={() => {
                            if (confirm(`确定要注销此空置仓库吗？ (${wh.name})`)) {
                              deleteWarehouseMutation.mutate(wh.id);
                            }
                          }}
                          className="px-2.5 py-1 bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 rounded-lg font-bold border border-rose-500/20 transition flex items-center gap-1"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          <span>注销仓库</span>
                        </button>
                      )}
                    </div>

                    {filteredStockEntries.length === 0 ? (
                      <div className="text-xs text-slate-500 py-3">
                        {wh.is_empty
                          ? '该仓库当前空置，没有存储任何物料散件或商品大货。'
                          : '该商品在此仓库暂无库存。'}
                      </div>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs">
                          <thead>
                            <tr className="border-b border-[#2A3447] text-slate-400 font-medium">
                              <th className="pb-2 px-2">商品名称</th>
                              <th className="pb-2 px-2">款式</th>
                              <th className="pb-2 px-2">部件</th>
                              <th className="pb-2 px-2 text-right">物理余量</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-[#2A3447]/50 text-slate-300">
                            {filteredStockEntries.map((row, rIdx) => (
                              <tr key={rIdx} className="hover:bg-[#18202F]">
                                <td className="py-2 px-2 font-bold text-slate-100">{row.product_name}</td>
                                <td className="py-2 px-2">
                                  <span className="px-2 py-0.5 bg-violet-500/10 text-violet-300 rounded text-[10px]">
                                    {row.variant}
                                  </span>
                                </td>
                                <td className="py-2 px-2 font-medium text-slate-300">{row.part_name}</td>
                                <td className="py-2 px-2 text-right font-mono font-bold text-emerald-400">
                                  {row.physical_qty} 件
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* Edit Audit Note Modal */}
      <Modal isOpen={isLogEditOpen} onClose={() => setIsLogEditOpen(false)} title="📝 修改操作日志备注">
        <div className="space-y-4 text-xs">
          <p className="text-slate-400">更改已发生库存变动记录的审计详情备注说明。</p>
          <FormField label="审计备注">
            <input
              type="text"
              value={editNote}
              onChange={(e) => setEditNote(e.target.value)}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
            />
          </FormField>
          <div className="flex justify-end gap-2 pt-2">
            <button
              onClick={() => setIsLogEditOpen(false)}
              className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg font-bold"
            >
              取消
            </button>
            <button
              onClick={() => {
                if (editingLog) {
                  updateLogNoteMutation.mutate({ id: editingLog.id, note: editNote });
                }
              }}
              disabled={updateLogNoteMutation.isPending}
              className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white font-bold rounded-lg shadow"
            >
              确认保存
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default InventoryPage;
