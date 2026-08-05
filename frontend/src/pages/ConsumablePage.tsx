// frontend/src/pages/ConsumablePage.tsx
import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { ConsumableItem } from '../types';
import { Modal } from '../components/ui/Modal';
import { StatCard } from '../components/ui/StatCard';
import { DataCard } from '../components/ui/DataCard';
import { FormField } from '../components/ui/FormField';
import { PageHeader } from '../components/ui/PageHeader';
import {
  Boxes,
  Zap,
  Search,
  X,
  Pencil,
  Link as LinkIcon,
  Play,
  RefreshCw,
  DollarSign
} from 'lucide-react';

const PRODUCT_COST_CATEGORIES = [
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

interface ConsumableLog {
  id: number;
  item_name: string;
  change_qty: number;
  value_cny?: number;
  note: string;
  date: string;
}

export const ConsumablePage: React.FC = () => {
  const queryClient = useQueryClient();

  // Search & Filter States
  const [searchQuery, setSearchQuery] = useState('');
  const [filterCurrency, setFilterCurrency] = useState('all');
  const [filterCategory, setFilterCategory] = useState('all');

  // Edit Modal State
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<ConsumableItem | null>(null);
  const [editName, setEditName] = useState('');
  const [editCategory, setEditCategory] = useState('');
  const [editUnitPrice, setEditUnitPrice] = useState<number>(0);
  const [editCurrency, setEditCurrency] = useState('CNY');
  const [editRemainingQty, setEditRemainingQty] = useState<number>(0);
  const [editShopName, setEditShopName] = useState('');
  const [editUrl, setEditUrl] = useState('');
  const [editRemarks, setEditRemarks] = useState('');

  // Quick Movement Form State
  const [opDate, setOpDate] = useState<string>(new Date().toISOString().split('T')[0]);
  const [opItemName, setOpItemName] = useState<string>('');
  const [opType, setOpType] = useState<'出库' | '入库'>('出库');
  const [opQty, setOpQty] = useState<number>(1);

  // Outbound Sub-branches State
  const [outMode, setOutMode] = useState<'内部消耗' | '对外销售'>('内部消耗');
  // Sale mode
  const [saleContent, setSaleContent] = useState<string>('');
  const [saleSource, setSaleSource] = useState<string>('');
  const [saleAmount, setSaleAmount] = useState<number>(0);
  const [saleCurrency, setSaleCurrency] = useState<string>('CNY');
  const [saleAccountId, setSaleAccountId] = useState<number | ''>('');
  const [saleRemark, setSaleRemark] = useState<string>('');
  // Cost Link mode
  const [isLinkProduct, setIsLinkProduct] = useState<boolean>(false);
  const [targetProductId, setTargetProductId] = useState<number | ''>('');
  const [targetCostCategory, setTargetCostCategory] = useState<string>(PRODUCT_COST_CATEGORIES[0]);
  const [opRemark, setOpRemark] = useState<string>('');

  const [formError, setFormError] = useState<string>('');

  // Fetch Consumable Items
  const { data: items, isLoading: loadingItems, refetch: refetchItems } = useQuery<ConsumableItem[]>({
    queryKey: ['consumableItems'],
    queryFn: async () => {
      const res = await apiClient.get('/assets/consumables/');
      return res.data.results || res.data || [];
    },
  });

  // Fetch Consumable Summary
  const { data: summaryData, refetch: refetchSummary } = useQuery({
    queryKey: ['consumableSummary'],
    queryFn: async () => {
      const res = await apiClient.get('/assets/consumables/summary/');
      return res.data;
    },
  });

  // Fetch Consumable Logs
  const { data: logs, isLoading: loadingLogs, refetch: refetchLogs } = useQuery<ConsumableLog[]>({
    queryKey: ['consumableLogs'],
    queryFn: async () => {
      const res = await apiClient.get('/assets/consumable-logs/');
      return res.data.results || res.data || [];
    },
  });

  // Fetch Products for Cost Linking
  const { data: products } = useQuery({
    queryKey: ['products'],
    queryFn: async () => {
      const res = await apiClient.get('/products/');
      return res.data.results || res.data || [];
    },
  });

  const itemList = Array.isArray(items) ? items : [];
  const logList = Array.isArray(logs) ? logs : [];

  // Default selected item name
  React.useEffect(() => {
    if (itemList.length > 0 && !opItemName) {
      setOpItemName(itemList[0].name);
    }
  }, [itemList, opItemName]);

  // Available Currencies and Categories for Filtering
  const availableCurrencies = summaryData?.currencies || ['CNY', 'JPY'];
  const availableCategories = summaryData?.categories || ['包装材', '备用素材', '周边'];
  const cashAccounts = summaryData?.cash_accounts || [];

  // Filtered Items
  const filteredItems = useMemo(() => {
    return itemList.filter((i) => {
      const q = searchQuery.trim().toLowerCase();
      const matchSearch =
        !q ||
        (i.name || '').toLowerCase().includes(q) ||
        (i.shop_name || '').toLowerCase().includes(q) ||
        (i.remarks || '').toLowerCase().includes(q);

      const matchCurr = filterCurrency === 'all' || i.currency === filterCurrency;
      const matchCat = filterCategory === 'all' || i.category === filterCategory;

      return matchSearch && matchCurr && matchCat;
    });
  }, [itemList, searchQuery, filterCurrency, filterCategory]);

  // Mutations
  const movementMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await apiClient.post('/assets/consumables/movement/', data);
      return res.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['consumableItems'] });
      queryClient.invalidateQueries({ queryKey: ['consumableSummary'] });
      queryClient.invalidateQueries({ queryKey: ['consumableLogs'] });
      setOpRemark('');
      setSaleContent('');
      setSaleSource('');
      setSaleAmount(0);
      setFormError('');
      alert(data.message || '🚀 耗材库存变动更新成功！');
    },
    onError: (err: any) => {
      setFormError(err.response?.data?.error || '耗材库存变动更新失败');
    },
  });

  const updateItemMutation = useMutation({
    mutationFn: async ({ id, data }: { id: number; data: any }) => {
      const res = await apiClient.patch(`/assets/consumables/${id}/`, data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['consumableItems'] });
      queryClient.invalidateQueries({ queryKey: ['consumableSummary'] });
      setIsEditOpen(false);
      setEditingItem(null);
    },
  });

  const updateLogDateMutation = useMutation({
    mutationFn: async ({ id, date }: { id: number; date: string }) => {
      const res = await apiClient.patch(`/assets/consumable-logs/${id}/update_date/`, { date });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['consumableLogs'] });
    },
  });

  // Handlers
  const handleSubmitMovement = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');

    if (!opItemName) {
      setFormError('请选择耗材项目');
      return;
    }
    if (opQty <= 0) {
      setFormError('变动数量必须大于 0');
      return;
    }

    const deltaQty = opType === '出库' ? -Math.abs(opQty) : Math.abs(opQty);
    const mode = opType === '出库' ? (outMode === '对外销售' ? 'sale' : isLinkProduct ? 'cost' : 'normal') : 'normal';

    let saleInfo = null;
    if (mode === 'sale') {
      if (saleAmount < 0) {
        setFormError('销售金额不能为负数');
        return;
      }
      saleInfo = {
        content: saleContent.trim() || `销售耗材: ${opItemName}`,
        source: saleSource.trim(),
        amount: Number(saleAmount),
        currency: saleCurrency,
        account_id: saleAccountId || null,
        remark: saleRemark.trim(),
      };
    }

    let costInfo = null;
    if (mode === 'cost') {
      if (!targetProductId) {
        setFormError('请选择要分摊成本的归属商品');
        return;
      }
      costInfo = {
        product_id: Number(targetProductId),
        category: targetCostCategory,
        remark: opRemark.trim(),
      };
    }

    movementMutation.mutate({
      item_name: opItemName,
      date: opDate,
      change_qty: deltaQty,
      mode,
      sale_info: saleInfo,
      cost_info: costInfo,
      remark: opRemark.trim(),
    });
  };

  const handleOpenEdit = (item: ConsumableItem) => {
    setEditingItem(item);
    setEditName(item.name || '');
    setEditCategory(item.category || '');
    setEditUnitPrice(Number(item.unit_price) || 0);
    setEditCurrency(item.currency || 'CNY');
    setEditRemainingQty(Number(item.remaining_qty) || 0);
    setEditShopName(item.shop_name || '');
    setEditUrl(item.url || '');
    setEditRemarks(item.remarks || '');
    setIsEditOpen(true);
  };

  const handleSaveEdit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingItem) return;

    updateItemMutation.mutate({
      id: editingItem.id,
      data: {
        name: editName.trim(),
        category: editCategory.trim(),
        unit_price: Number(editUnitPrice),
        currency: editCurrency,
        remaining_qty: Number(editRemainingQty),
        shop_name: editShopName.trim(),
        url: editUrl.trim(),
        remarks: editRemarks.trim(),
      },
    });
  };

  const resetFilters = () => {
    setSearchQuery('');
    setFilterCurrency('all');
    setFilterCategory('all');
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="📦 其他资产(耗材)管理"
        subtitle="打包包装材、宣传品及备用素材物料进销存，支持直接销售记账与大货成本自动分摊"
        action={
          <button
            onClick={() => {
              refetchItems();
              refetchSummary();
              refetchLogs();
            }}
            className="px-3.5 py-2 bg-[#18202F] hover:bg-[#222C3E] text-slate-200 text-xs font-medium rounded-xl border border-[#2A3447] transition flex items-center gap-1.5 shadow"
          >
            <RefreshCw className="w-3.5 h-3.5 text-violet-400" />
            刷新数据
          </button>
        }
      />

      {/* Top 2 Columns: Quick Operation Panel & Valuation Metric Card */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column (8 cols): Quick Movement Form */}
        <div className="lg:col-span-8 p-4 bg-[#131924] rounded-2xl border border-[#2A3447] space-y-4 text-xs">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Zap className="w-4 h-4 text-violet-400" />
              ⚡ 快速库存操作
            </h3>
            <p className="text-slate-400 mt-1">
              在此执行货物的物理入库补货，或者物理出库消耗（可计入商品成本或记账销售）。
            </p>
          </div>

          {formError && (
            <div className="p-2.5 bg-rose-500/10 border border-rose-500/30 rounded-lg text-rose-400">
              {formError}
            </div>
          )}

          <form onSubmit={handleSubmitMovement} className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <FormField label="📅 变动日期" required>
                <input
                  type="date"
                  value={opDate}
                  onChange={(e) => setOpDate(e.target.value)}
                  className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100"
                />
              </FormField>

              <FormField label="📦 选择项目" required>
                <select
                  value={opItemName}
                  onChange={(e) => setOpItemName(e.target.value)}
                  className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100 font-bold"
                >
                  {itemList.map((i) => (
                    <option key={i.id} value={i.name}>
                      {i.name} (余: {i.remaining_qty})
                    </option>
                  ))}
                </select>
              </FormField>

              <FormField label="⚙️ 操作类型" required>
                <div className="flex gap-4 pt-1 text-slate-200">
                  <label className="flex items-center gap-1.5 cursor-pointer font-bold">
                    <input
                      type="radio"
                      name="opType"
                      value="出库"
                      checked={opType === '出库'}
                      onChange={() => setOpType('出库')}
                    />
                    <span>出库</span>
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer font-bold">
                    <input
                      type="radio"
                      name="opType"
                      value="入库"
                      checked={opType === '入库'}
                      onChange={() => setOpType('入库')}
                    />
                    <span>入库</span>
                  </label>
                </div>
              </FormField>

              <FormField label="🔢 变动数量" required>
                <input
                  type="number"
                  value={opQty}
                  onChange={(e) => setOpQty(parseInt(e.target.value) || 1)}
                  className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100 font-mono font-bold"
                />
              </FormField>
            </div>

            <hr className="border-[#2A3447]/60" />

            {/* Outbound Branches */}
            {opType === '出库' ? (
              <div className="space-y-3">
                <FormField label="📤 出库目的">
                  <div className="flex gap-6 text-slate-200 font-medium">
                    <label className="flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="radio"
                        name="outMode"
                        value="内部消耗"
                        checked={outMode === '内部消耗'}
                        onChange={() => setOutMode('内部消耗')}
                      />
                      <span>内部消耗 (计入成本)</span>
                    </label>
                    <label className="flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="radio"
                        name="outMode"
                        value="对外销售"
                        checked={outMode === '对外销售'}
                        onChange={() => setOutMode('对外销售')}
                      />
                      <span>对外销售 (计入收入)</span>
                    </label>
                  </div>
                </FormField>

                {outMode === '对外销售' ? (
                  <div className="p-3 bg-[#0B0F17] border border-[#2A3447] rounded-xl space-y-3">
                    <div className="flex items-center gap-1.5 text-emerald-400 font-bold">
                      <DollarSign className="w-4 h-4" />
                      <span>请填写财务记账信息 (将自动在选定的现金账户中生成【销售收入】流水)</span>
                    </div>

                    <div className="grid grid-cols-3 gap-3">
                      <FormField label="收入内容说明">
                        <input
                          type="text"
                          placeholder="例如: 展会散卖耗材"
                          value={saleContent}
                          onChange={(e) => setSaleContent(e.target.value)}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100"
                        />
                      </FormField>

                      <FormField label="收入来源 (如: 线下/闲鱼/Booth)">
                        <input
                          type="text"
                          placeholder="线下/闲鱼/Booth"
                          value={saleSource}
                          onChange={(e) => setSaleSource(e.target.value)}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100"
                        />
                      </FormField>

                      <FormField label="销售总额 (原币)">
                        <input
                          type="number"
                          step="0.01"
                          value={saleAmount}
                          onChange={(e) => setSaleAmount(parseFloat(e.target.value) || 0)}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100 font-mono"
                        />
                      </FormField>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <FormField label="交易币种">
                        <select
                          value={saleCurrency}
                          onChange={(e) => setSaleCurrency(e.target.value)}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100 font-mono"
                        >
                          <option value="CNY">CNY</option>
                          <option value="JPY">JPY</option>
                        </select>
                      </FormField>

                      <FormField label="收款入账账户">
                        <select
                          value={saleAccountId}
                          onChange={(e) => setSaleAccountId(e.target.value ? Number(e.target.value) : '')}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100"
                        >
                          <option value="">-- 选择现金账户 --</option>
                          {cashAccounts.map((acc: any) => (
                            <option key={acc.id} value={acc.id}>
                              {acc.label}
                            </option>
                          ))}
                        </select>
                      </FormField>
                    </div>

                    <FormField label="流水备注 (选填)">
                      <input
                        type="text"
                        placeholder="将显示在财务流水的备注一栏中"
                        value={saleRemark}
                        onChange={(e) => setSaleRemark(e.target.value)}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100"
                      />
                    </FormField>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="grid grid-cols-3 gap-3 items-center">
                      <label className="flex items-center gap-2 text-slate-300 font-medium cursor-pointer pt-3">
                        <input
                          type="checkbox"
                          checked={isLinkProduct}
                          onChange={(e) => setIsLinkProduct(e.target.checked)}
                          className="w-4 h-4 accent-violet-500 cursor-pointer"
                        />
                        <span>🔗 计入商品大货成本</span>
                      </label>

                      {isLinkProduct && (
                        <FormField label="归属商品">
                          <select
                            value={targetProductId}
                            onChange={(e) => setTargetProductId(e.target.value ? Number(e.target.value) : '')}
                            className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100"
                          >
                            <option value="">-- 选择归属商品 --</option>
                            {(products || []).map((p: any) => (
                              <option key={p.id} value={p.id}>
                                {p.name}
                              </option>
                            ))}
                          </select>
                        </FormField>
                      )}

                      {isLinkProduct && (
                        <FormField label="分摊成本分类">
                          <select
                            value={targetCostCategory}
                            onChange={(e) => setTargetCostCategory(e.target.value)}
                            className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100"
                          >
                            {PRODUCT_COST_CATEGORIES.map((cat) => (
                              <option key={cat} value={cat}>
                                {cat}
                              </option>
                            ))}
                          </select>
                        </FormField>
                      )}
                    </div>

                    <FormField label="出库备注说明 (选填)">
                      <input
                        type="text"
                        placeholder="如：打包用去 / 损耗弃置"
                        value={opRemark}
                        onChange={(e) => setOpRemark(e.target.value)}
                        className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100"
                      />
                    </FormField>
                  </div>
                )}
              </div>
            ) : (
              <FormField label="入库/补货备注说明 (选填)">
                <input
                  type="text"
                  placeholder="如：淘宝店自主补货购入"
                  value={opRemark}
                  onChange={(e) => setOpRemark(e.target.value)}
                  className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-100"
                />
              </FormField>
            )}

            <button
              type="submit"
              disabled={movementMutation.isPending}
              className="w-full py-2.5 bg-violet-600 hover:bg-violet-500 font-bold text-white rounded-xl transition shadow-lg shadow-violet-500/20 flex items-center justify-center gap-1.5"
            >
              <Play className="w-4 h-4 fill-white" />
              <span>{movementMutation.isPending ? '提交中...' : '确认并提交库存变动更新'}</span>
            </button>
          </form>
        </div>

        {/* Right Column (4 cols): Valuation Metric Card */}
        <div className="lg:col-span-4 p-4 bg-[#131924] rounded-2xl border border-[#2A3447] space-y-3 text-xs">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Boxes className="w-4 h-4 text-violet-400" />
              📊 耗材库存总值
            </h3>
            <p className="text-slate-400 mt-1">
              计算当前所有在库耗材的资产账面折算总价。
            </p>
          </div>

          <div className="space-y-2 pt-2">
            {(summaryData?.valuation_indicators || []).map((ind: any, idx: number) => (
              <div key={idx} className="flex justify-between items-center py-1 border-b border-[#2A3447]/50">
                <span className="text-slate-400 font-medium">{ind.currency} 实物总值:</span>
                <span className="font-mono font-bold text-slate-200">{ind.amount_str}</span>
              </div>
            ))}
          </div>

          <hr className="border-[#2A3447]" />

          <div className="flex justify-between items-center pt-1">
            <span className="font-bold text-violet-300">折算 CNY 总价值:</span>
            <span className="text-xl font-bold font-mono text-violet-400">
              {summaryData?.grand_total_cny_str || '¥ 0.00'}
            </span>
          </div>
        </div>
      </div>

      {/* Main Data Card: Consumables List */}
      <DataCard title="📦 其他耗材清单明细">
        <div className="space-y-4">
          {/* Search & Filter Controls */}
          <div className="flex items-center gap-2 flex-wrap text-xs">
            <div className="relative flex-1 min-w-[200px] max-w-xs">
              <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="搜索项目名称、店铺、备注..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl pl-9 pr-3 py-2 text-slate-100 focus:outline-none focus:border-violet-500"
              />
            </div>

            <select
              value={filterCurrency}
              onChange={(e) => setFilterCurrency(e.target.value)}
              className="bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100 font-mono"
            >
              <option value="all">全部币种</option>
              {availableCurrencies.map((c: string) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>

            <select
              value={filterCategory}
              onChange={(e) => setFilterCategory(e.target.value)}
              className="bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100"
            >
              <option value="all">全部分类</option>
              {availableCategories.map((cat: string) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>

            {(searchQuery || filterCurrency !== 'all' || filterCategory !== 'all') && (
              <button
                onClick={resetFilters}
                className="px-2.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl transition flex items-center gap-1"
              >
                <X className="w-3.5 h-3.5" />
                <span>重置</span>
              </button>
            )}
          </div>

          {/* Table */}
          {loadingItems ? (
            <div className="text-xs text-slate-400 py-8 text-center">加载耗材列表中...</div>
          ) : filteredItems.length === 0 ? (
            <div className="text-xs text-slate-400 py-8 text-center bg-[#0B0F17] rounded-xl border border-[#2A3447]">
              {searchQuery || filterCurrency !== 'all' || filterCategory !== 'all'
                ? '未找到匹配的耗材资产记录'
                : '当前无有效在库库存资产。'}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#2A3447] text-slate-400 font-medium uppercase">
                    <th className="pb-2.5 px-2">项目</th>
                    <th className="pb-2.5 px-2">分类</th>
                    <th className="pb-2.5 px-2">币种</th>
                    <th className="pb-2.5 px-2 text-right">单价(原币)</th>
                    <th className="pb-2.5 px-2 text-right">剩余数量</th>
                    <th className="pb-2.5 px-2 text-right">剩余价值(CNY)</th>
                    <th className="pb-2.5 px-2 text-right">剩余价值(原币)</th>
                    <th className="pb-2.5 px-2">店铺</th>
                    <th className="pb-2.5 px-2 text-center">相关链接</th>
                    <th className="pb-2.5 px-2">备注</th>
                    <th className="pb-2.5 px-2 text-center">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#2A3447]/50 text-slate-300">
                  {filteredItems.map((item) => {
                    const remainQty = Number(item.remaining_qty) || 0;
                    const unitP = Number(item.unit_price) || 0;
                    const remainOrig = unitP * remainQty;

                    return (
                      <tr key={item.id} className="hover:bg-[#18202F]">
                        <td className="py-2.5 px-2 font-bold text-slate-100">{item.name}</td>
                        <td className="py-2.5 px-2">
                          <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300 border border-slate-700">
                            {item.category}
                          </span>
                        </td>
                        <td className="py-2.5 px-2 font-mono text-slate-400">{item.currency}</td>
                        <td className="py-2.5 px-2 text-right font-mono">{unitP.toFixed(2)}</td>
                        <td className="py-2.5 px-2 text-right font-mono">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              remainQty > 0.01
                                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                : 'bg-slate-800 text-slate-500'
                            }`}
                          >
                            {remainQty}
                          </span>
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono font-bold text-violet-300">
                          ¥ {(item.remaining_cny || 0).toFixed(2)}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-slate-400">
                          {remainOrig > 0.001 ? `${remainOrig.toFixed(2)} ${item.currency}` : '-'}
                        </td>
                        <td className="py-2.5 px-2 text-slate-300 truncate max-w-xs">{item.shop_name || '-'}</td>
                        <td className="py-2.5 px-2 text-center">
                          {item.url ? (
                            <a
                              href={item.url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 px-2 py-0.5 bg-violet-500/10 hover:bg-violet-500/20 text-violet-400 rounded text-[10px] font-bold border border-violet-500/20 transition"
                            >
                              <LinkIcon className="w-3 h-3" />
                              <span>访问</span>
                            </a>
                          ) : (
                            <span className="text-slate-600">-</span>
                          )}
                        </td>
                        <td className="py-2.5 px-2 text-slate-400 truncate max-w-xs">{item.remarks || '-'}</td>
                        <td className="py-2.5 px-2 text-center">
                          <button
                            onClick={() => handleOpenEdit(item)}
                            title="修改资产单价、库存、链接与备注"
                            className="p-1 text-slate-400 hover:text-violet-400 transition"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </DataCard>

      {/* Bottom Data Card: Consumable Logs */}
      <DataCard title="📜 耗材出入库历史记录">
        <div className="space-y-3">
          <div className="p-2.5 bg-blue-500/10 border border-blue-500/30 rounded-xl text-blue-300 text-xs">
            💡 提示：你可以直接在表格的【日期】单元格中重新选择，以修正该笔操作的账期。
          </div>

          {loadingLogs ? (
            <div className="text-xs text-slate-400 py-6 text-center">加载出入库日志中...</div>
          ) : logList.length === 0 ? (
            <div className="text-xs text-slate-400 py-6 text-center">暂无相关耗材操作的变动日志流水记录</div>
          ) : (
            <div className="overflow-x-auto max-h-80 overflow-y-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#2A3447] text-slate-400 uppercase font-medium">
                    <th className="pb-2 px-2">日期 (支持修改)</th>
                    <th className="pb-2 px-2">名称</th>
                    <th className="pb-2 px-2 text-center">变动数量</th>
                    <th className="pb-2 px-2">详情说明</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#2A3447]/50 text-slate-300">
                  {logList.map((log) => {
                    const isPos = log.change_qty > 0;
                    return (
                      <tr key={log.id} className="hover:bg-[#18202F]">
                        <td className="py-2 px-2">
                          <input
                            type="date"
                            defaultValue={log.date}
                            onBlur={(e) => {
                              const newD = e.target.value;
                              if (newD && newD !== log.date) {
                                updateLogDateMutation.mutate({ id: log.id, date: newD });
                              }
                            }}
                            className="bg-[#0B0F17] border border-[#2A3447] rounded px-2 py-0.5 text-xs text-slate-200 font-mono"
                          />
                        </td>
                        <td className="py-2 px-2 font-bold text-slate-100">{log.item_name}</td>
                        <td className="py-2 px-2 text-center">
                          <span
                            className={`px-2 py-0.5 rounded font-mono font-bold text-[10px] ${
                              isPos
                                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                            }`}
                          >
                            {isPos ? `+${log.change_qty}` : log.change_qty}
                          </span>
                        </td>
                        <td className="py-2 px-2 text-slate-300">{log.note || '-'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </DataCard>

      {/* Edit Consumable Item Modal */}
      <Modal isOpen={isEditOpen} onClose={() => setIsEditOpen(false)} title={`⚙️ 修改资产信息: ${editingItem?.name || ''}`}>
        <form onSubmit={handleSaveEdit} className="space-y-4 text-xs">
          <p className="text-slate-400">在这里安全修改其他耗材的单价、当前库存数量、备注和采购店铺链接。</p>

          <FormField label="耗材名称 (必填)" required>
            <input
              type="text"
              required
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
            />
          </FormField>

          <FormField label="分类说明">
            <input
              type="text"
              placeholder="如: 包装材/备用素材/周边"
              value={editCategory}
              onChange={(e) => setEditCategory(e.target.value)}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
            />
          </FormField>

          <div className="grid grid-cols-2 gap-3">
            <FormField label="单价 (原币)">
              <input
                type="number"
                step="0.01"
                value={editUnitPrice}
                onChange={(e) => setEditUnitPrice(parseFloat(e.target.value) || 0)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
              />
            </FormField>

            <FormField label="交易币种">
              <select
                value={editCurrency}
                onChange={(e) => setEditCurrency(e.target.value)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
              >
                <option value="CNY">CNY</option>
                <option value="JPY">JPY</option>
              </select>
            </FormField>
          </div>

          <FormField label="当前库存数量">
            <input
              type="number"
              value={editRemainingQty}
              onChange={(e) => setEditRemainingQty(parseFloat(e.target.value) || 0)}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
            />
          </FormField>

          <FormField label="店铺来源">
            <input
              type="text"
              value={editShopName}
              onChange={(e) => setEditShopName(e.target.value)}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
            />
          </FormField>

          <FormField label="购买链接 / 网址">
            <input
              type="url"
              placeholder="https://..."
              value={editUrl}
              onChange={(e) => setEditUrl(e.target.value)}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
            />
          </FormField>

          <FormField label="备注说明">
            <input
              type="text"
              value={editRemarks}
              onChange={(e) => setEditRemarks(e.target.value)}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
            />
          </FormField>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setIsEditOpen(false)}
              className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg font-bold"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={updateItemMutation.isPending}
              className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white font-bold rounded-lg shadow"
            >
              确认保存
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default ConsumablePage;
