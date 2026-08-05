// frontend/src/pages/CostPage.tsx
import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { Product, CostItem, SalesPlatform } from '../types';
import { Modal } from '../components/ui/Modal';
import { StatCard } from '../components/ui/StatCard';
import { DataCard } from '../components/ui/DataCard';
import { FormField } from '../components/ui/FormField';
import { PageHeader } from '../components/ui/PageHeader';
import {
  Plus,
  Trash2,
  Edit2,
  Package,
  RefreshCw,
  Calculator,
  ChevronDown,
  ChevronUp,
  CircleDollarSign,
  TrendingUp,
  PiggyBank,
  CheckCircle2,
  ExternalLink,
  Tag
} from 'lucide-react';

const PRODUCT_COST_CATEGORIES = [
  "大货材料费", 
  "大货加工费", 
  "物流邮费", 
  "包装费", 
  "设计开发费", 
  "检品发货等人工费", 
  "宣发费", 
  "售后成本",
  "其他成本"
];

const DETAILED_CATEGORIES = ["大货材料费", "大货加工费", "物流邮费", "包装费"];

export const CostPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [selectedProductId, setSelectedProductId] = useState<number | ''>('');
  
  // Accordion state for budget form
  const [isBudgetFormOpen, setIsBudgetFormOpen] = useState(false);

  // Add Budget Form state
  const [bCat, setBCat] = useState(PRODUCT_COST_CATEGORIES[0]);
  const [bName, setBName] = useState('');
  const [bUnitPrice, setBUnitPrice] = useState<number | ''>('');
  const [bQty, setBQty] = useState<number | ''>(1);
  const [bUnitText, setBUnitText] = useState('');
  const [bRemarks, setBRemarks] = useState('');
  const [bCurrency, setBCurrency] = useState('CNY');

  // Edit Item Modal state
  const [editingItem, setEditingItem] = useState<CostItem | null>(null);
  const [editUnitPrice, setEditUnitPrice] = useState<number | ''>('');
  const [editQty, setEditQty] = useState<number | ''>('');
  const [editUnit, setEditUnit] = useState('');
  const [editSupplier, setEditSupplier] = useState('');
  const [editUrl, setEditUrl] = useState('');
  const [editRemarks, setEditRemarks] = useState('');

  // Fetch Products
  const { data: products = [], isLoading: isLoadingProds, refetch: refetchProds } = useQuery<Product[]>({
    queryKey: ['products'],
    queryFn: async () => {
      const res = await apiClient.get('/products/');
      return res.data.results || res.data || [];
    },
  });

  // Fetch Rates (CNY / JPY)
  const { data: ratesMap = { JPY: 0.04288 } } = useQuery<Record<string, number>>({
    queryKey: ['rates'],
    queryFn: async () => {
      const res = await apiClient.get('/rates/');
      return res.data;
    },
  });

  // Fetch Platforms
  const { data: platforms = [] } = useQuery<SalesPlatform[]>({
    queryKey: ['platforms'],
    queryFn: async () => {
      const res = await apiClient.get('/platforms/');
      return res.data.results || res.data || [];
    },
  });

  // Automatically select first product if not set
  const currentProduct = products.find(p => p.id === selectedProductId) || products[0] || null;
  const activeProductId = currentProduct ? currentProduct.id : '';

  // Filter cost items for selected product
  const currentCostItems = currentProduct?.costs || [];

  // Mutations
  const addBudgetMutation = useMutation({
    mutationFn: async (payload: any) => {
      const res = await apiClient.post('/cost-items/add_budget/', payload);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      setBName('');
      setBUnitPrice('');
      setBQty(1);
      setBUnitText('');
      setBRemarks('');
      setIsBudgetFormOpen(false);
    },
    onError: (err: any) => {
      alert(err.response?.data?.error || '添加预算项目失败');
    },
  });

  const saveEditMutation = useMutation({
    mutationFn: async (payload: any) => {
      if (!editingItem) return;
      const res = await apiClient.put(`/cost-items/${editingItem.id}/`, payload);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      setEditingItem(null);
    },
    onError: (err: any) => {
      alert(err.response?.data?.error || '修改费用项目失败');
    },
  });

  const deleteCostItemMutation = useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/cost-items/${id}/`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
    },
  });

  const wipFixMutation = useMutation({
    mutationFn: async (productIdNum: number) => {
      const res = await apiClient.post('/cost-items/wip_fix/', { product_id: productIdNum });
      return res.data;
    },
    onSuccess: (data: any) => {
      alert(data.message || '生产已顺利完工核算！');
      queryClient.invalidateQueries({ queryKey: ['products'] });
    },
    onError: (err: any) => {
      alert(err.response?.data?.error || 'WIP冲销结算失败');
    },
  });

  // Calculate Costs Metrics for currentProduct
  const jpyRate = ratesMap['JPY'] || 0.04288;
  const toCNY = (amount: number, curr?: string) => {
    if (!curr || curr === 'CNY') return amount;
    if (curr === 'JPY') return amount * jpyRate;
    return amount;
  };

  const totalRealCost = currentCostItems.reduce((sum, item) => sum + (item.actual_cost || 0), 0);

  // Calculate Budget Total Cost (CNY)
  const budgetMap: Record<string, number> = {};
  currentCostItems.forEach(item => {
    if (item.is_budget) {
      const equiv = toCNY((item.unit_price || 0) * (item.quantity || 0), item.currency);
      budgetMap[item.item_name || ''] = equiv;
    }
  });

  let totalBudgetCost = Object.values(budgetMap).reduce((a, b) => a + b, 0);
  currentCostItems.forEach(item => {
    if (!item.is_budget && item.item_name && !(item.item_name in budgetMap)) {
      totalBudgetCost += (item.actual_cost || 0);
    }
  });

  // Calculate Make Quantity (Total SKU quantities)
  const colors = currentProduct?.colors || [];
  const makeQty = colors.reduce((sum, c) => sum + (c.quantity || 0), 0);
  const unitRealCost = makeQty > 0 ? totalRealCost / makeQty : 0;
  const unitBudgetCost = makeQty > 0 ? totalBudgetCost / makeQty : 0;

  const isProductionCompleted = currentProduct?.is_production_completed || false;
  const remainingWIP = isProductionCompleted ? 0 : totalRealCost;

  // Open Edit Modal
  const openEditModal = (item: CostItem) => {
    setEditingItem(item);
    setEditUnitPrice(item.unit_price || '');
    setEditQty(item.quantity || '');
    setEditUnit(item.unit || '');
    setEditSupplier(item.supplier || '');
    setEditUrl(item.url || '');
    setEditRemarks(item.remarks || '');
  };

  const handleSaveBudget = (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeProductId || !bName.trim()) {
      alert('请填写预算项目名称');
      return;
    }
    addBudgetMutation.mutate({
      product_id: activeProductId,
      category: bCat,
      name: bName,
      unit_price: Number(bUnitPrice) || 0,
      quantity: Number(bQty) || 1,
      unit: bUnitText,
      remarks: bRemarks,
      currency: bCurrency,
    });
  };

  const handleSaveEdit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingItem) return;
    saveEditMutation.mutate({
      ...editingItem,
      unit_price: Number(editUnitPrice) || 0,
      quantity: Number(editQty) || 1,
      unit: editUnit,
      supplier: editSupplier,
      url: editUrl,
      remarks: editRemarks,
    });
  };

  const isDetailedCat = DETAILED_CATEGORIES.includes(bCat);
  const bTotalVal = (Number(bUnitPrice) || 0) * (Number(bQty) || 1);

  // Generate Multi-platform Profit Matrix Rows
  const profitRows: any[] = [];
  colors.forEach(c => {
    (c.prices || []).forEach(pr => {
      const priceVal = pr.price || 0;
      const curr = pr.currency || 'CNY';
      const priceCNY = toCNY(priceVal, curr);

      // Match platform fee rate if defined
      const matchedPlat = platforms.find(p => p.code === pr.platform || p.name === pr.platform);
      const feeRate = matchedPlat?.fee_rate || (pr.platform === 'booth' ? 0.056 : 0.006);
      const feeCNY = priceCNY * feeRate;

      const marginCNY = priceCNY - feeCNY - unitRealCost;
      const marginRate = priceCNY > 0 ? (marginCNY / priceCNY) * 100 : 0;
      const expectedTotalProfit = marginCNY * (c.quantity || 0);

      profitRows.push({
        colorName: c.color_name,
        platformLabel: matchedPlat?.name || pr.platform,
        presetPriceStr: curr === 'JPY' ? `${priceVal.toLocaleString()} JPY` : `¥${priceVal.toFixed(2)}`,
        estimatedFeeCnyStr: `¥${feeCNY.toFixed(2)}`,
        marginCny: marginCNY,
        marginCnyStr: `¥${marginCNY.toFixed(2)}`,
        marginRateStr: `${marginRate.toFixed(1)}%`,
        expectedTotalProfit: expectedTotalProfit,
        expectedTotalProfitStr: `¥${expectedTotalProfit.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
      });
    });
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="🧮 商品成本核算与 BOM 管理"
        subtitle="核算商品 BOM 物料、加工、运费及预算，支持 WIP 在制资产清算冲销与多平台毛利矩阵分析"
        action={
          <div className="flex items-center gap-2">
            <button
              onClick={() => refetchProds()}
              className="px-3 py-1.5 bg-[#18202F] hover:bg-[#222C3E] text-slate-200 text-xs font-medium rounded-lg border border-[#2A3447] transition flex items-center gap-1.5"
            >
              <RefreshCw className="w-3.5 h-3.5 text-violet-400" />
              刷新
            </button>
          </div>
        }
      />

      {/* Top Product Selector & Production Status Card */}
      <div className="p-4 bg-[#0B0F17] rounded-2xl border border-[#2A3447] flex flex-wrap items-center justify-between gap-4 shadow-xl">
        <div className="flex items-center gap-3">
          <label className="text-xs font-bold text-slate-300">请选择要核算的商品:</label>
          <select
            value={activeProductId}
            onChange={(e) => setSelectedProductId(Number(e.target.value))}
            className="bg-[#131924] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100 font-bold text-xs focus:border-violet-500 min-w-[220px]"
          >
            {products.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>

        {currentProduct && (
          <div className="flex items-center gap-3 text-xs">
            {isProductionCompleted ? (
              <span className="px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                🔒 生产已结单
              </span>
            ) : (
              <span className="px-3 py-1 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 font-bold flex items-center gap-1.5">
                <RefreshCw className="w-4 h-4 text-amber-400 animate-spin" />
                ⚡ 在制流转中
              </span>
            )}
          </div>
        )}
      </div>

      {/* Accordion Form: Add Budget Item */}
      <div className="bg-[#0B0F17] rounded-2xl border border-[#2A3447] overflow-hidden">
        <button
          onClick={() => setIsBudgetFormOpen(!isBudgetFormOpen)}
          className="w-full p-4 flex items-center justify-between text-xs font-bold text-slate-200 hover:bg-[#131924]/60 transition"
        >
          <span className="flex items-center gap-2 text-violet-300">
            <Plus className="w-4 h-4 text-violet-400" />
            添加预算项目 (Budget)
          </span>
          {isBudgetFormOpen ? <ChevronUp className="w-4 h-4 text-violet-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
        </button>

        {isBudgetFormOpen && (
          <form onSubmit={handleSaveBudget} className="p-4 pt-0 space-y-4 border-t border-[#2A3447]/60 text-xs">
            <p className="text-[11px] text-slate-400 pt-3">
              在此处录入的条目仅作为预算参考，实付金额默认为 0。
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <FormField label="预算分类">
                <select
                  value={bCat}
                  onChange={(e) => setBCat(e.target.value)}
                  className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                >
                  {PRODUCT_COST_CATEGORIES.map(cat => (
                    <option key={cat} value={cat}>{cat}</option>
                  ))}
                </select>
              </FormField>

              <FormField label="项目名称" required>
                <input
                  type="text"
                  required
                  placeholder="如：面料预算 / 扣子"
                  value={bName}
                  onChange={(e) => setBName(e.target.value)}
                  className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                />
              </FormField>

              <FormField label="预算币种">
                <select
                  value={bCurrency}
                  onChange={(e) => setBCurrency(e.target.value)}
                  className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                >
                  <option value="CNY">CNY (¥)</option>
                  <option value="JPY">JPY (￥)</option>
                </select>
              </FormField>
            </div>

            {isDetailedCat ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <FormField label="预算单价">
                  <input
                    type="number"
                    step="0.01"
                    placeholder="0.00"
                    value={bUnitPrice}
                    onChange={(e) => setBUnitPrice(e.target.value ? parseFloat(e.target.value) : '')}
                    className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                  />
                </FormField>
                <FormField label="预算数量">
                  <input
                    type="number"
                    step="0.1"
                    value={bQty}
                    onChange={(e) => setBQty(e.target.value ? parseFloat(e.target.value) : '')}
                    className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                  />
                </FormField>
                <FormField label="单位">
                  <input
                    type="text"
                    placeholder="米/个/套"
                    value={bUnitText}
                    onChange={(e) => setBUnitText(e.target.value)}
                    className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                  />
                </FormField>
              </div>
            ) : (
              <FormField label="预算总额 (简易项目)">
                <input
                  type="number"
                  step="0.01"
                  placeholder="0.00"
                  value={bUnitPrice}
                  onChange={(e) => setBUnitPrice(e.target.value ? parseFloat(e.target.value) : '')}
                  className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                />
              </FormField>
            )}

            {isDetailedCat && (
              <div className="flex items-center gap-2 text-xs font-bold text-violet-300">
                <span>💰 预算总价:</span>
                <span className="font-mono text-sm text-emerald-400">
                  {bCurrency === 'JPY' ? `${bTotalVal.toLocaleString()} JPY` : `¥${bTotalVal.toFixed(2)}`}
                </span>
              </div>
            )}

            <FormField label="备注 (选填)">
              <input
                type="text"
                placeholder="预算备注信息"
                value={bRemarks}
                onChange={(e) => setBRemarks(e.target.value)}
                className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
              />
            </FormField>

            <button
              type="submit"
              disabled={addBudgetMutation.isPending}
              className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white font-bold rounded-xl transition shadow-lg shadow-violet-500/20"
            >
              保存预算
            </button>
          </form>
        )}
      </div>

      {/* 2-Column Core Layout (Span 8 Left + Span 4 Right) */}
      {products.length === 0 ? (
        <div className="p-8 bg-[#0B0F17] rounded-2xl border border-amber-500/30 text-center text-amber-400 text-xs">
          ⚠️ 请先在「商品管理」中添加商品，方可进行核算！
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column (Span 8): Cost Items Grouped Table */}
          <div className="lg:col-span-8 space-y-4">
            <h2 className="font-bold text-base text-slate-100 flex items-center gap-2">
              📋 项目支出明细表
            </h2>

            <DataCard title="费用流向明细分组表">
              <div className="space-y-6">
                {PRODUCT_COST_CATEGORIES.map(cat => {
                  const catItems = currentCostItems.filter(item => item.category === cat);
                  if (catItems.length === 0) return null;

                  const subRealCNY = catItems.reduce((sum, item) => sum + (item.actual_cost || 0), 0);
                  const subRealUnitCNY = makeQty > 0 ? subRealCNY / makeQty : 0;

                  const subBudgetCNY = catItems.reduce((sum, item) => {
                    if (item.is_budget) {
                      return sum + toCNY((item.unit_price || 0) * (item.quantity || 0), item.currency);
                    }
                    return sum;
                  }, 0);
                  const subBudgetUnitCNY = makeQty > 0 ? subBudgetCNY / makeQty : 0;

                  return (
                    <div key={cat} className="space-y-3">
                      <h4 className="font-bold text-xs text-violet-400 flex items-center justify-between border-b border-[#2A3447] pb-1.5">
                        <span>🔹 {cat} ({catItems.length}项)</span>
                        <span className="font-mono text-[11px] text-slate-400">小计实付: ¥{subRealCNY.toFixed(2)}</span>
                      </h4>

                      <div className="overflow-x-auto">
                        <table className="w-full text-left text-xs border-collapse min-w-[700px]">
                          <thead>
                            <tr className="border-b border-[#2A3447] text-slate-400 text-[11px] uppercase">
                              <th className="pb-2 px-2">项目名称</th>
                              <th className="pb-2 px-2">单位</th>
                              <th className="pb-2 px-2">币种</th>
                              <th className="pb-2 px-2 text-right">预算数量</th>
                              <th className="pb-2 px-2 text-right">预算单价</th>
                              <th className="pb-2 px-2 text-right">预算总额</th>
                              <th className="pb-2 px-2 text-right">实际数量</th>
                              <th className="pb-2 px-2 text-right">实付单价</th>
                              <th className="pb-2 px-2 text-right">实付总额</th>
                              <th className="pb-2 px-2">供应商</th>
                              <th className="pb-2 px-2">链接</th>
                              <th className="pb-2 px-2">备注</th>
                              <th className="pb-2 px-2 text-right">操作</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-[#2A3447]/40">
                            {catItems.map(item => {
                              const isB = item.is_budget;
                              const bTotal = (item.unit_price || 0) * (item.quantity || 0);

                              return (
                                <tr key={item.id} className="hover:bg-[#131924]/40 transition">
                                  <td className="py-2 px-2 font-medium text-slate-100">{item.item_name}</td>
                                  <td className="py-2 px-2 text-slate-400">{item.unit || '-'}</td>
                                  <td className="py-2 px-2 font-mono text-slate-400">{item.currency || 'CNY'}</td>

                                  {/* Budget columns */}
                                  <td className="py-2 px-2 text-right font-mono text-slate-400">
                                    {isB ? item.quantity : '-'}
                                  </td>
                                  <td className="py-2 px-2 text-right font-mono text-slate-400">
                                    {isB ? item.unit_price?.toFixed(2) : '-'}
                                  </td>
                                  <td className="py-2 px-2 text-right font-mono font-medium text-slate-300">
                                    {isB ? (item.currency === 'JPY' ? `${bTotal.toLocaleString()} JPY` : `¥${bTotal.toFixed(2)}`) : '-'}
                                  </td>

                                  {/* Actual columns */}
                                  <td className="py-2 px-2 text-right font-mono text-slate-200 font-medium">
                                    {!isB ? (item.actual_qty || item.quantity || 1) : '-'}
                                  </td>
                                  <td className="py-2 px-2 text-right font-mono text-slate-200 font-medium">
                                    {!isB ? (item.actual_unit_price || item.unit_price || 0).toFixed(2) : '-'}
                                  </td>
                                  <td className="py-2 px-2 text-right font-mono font-bold text-emerald-400">
                                    {!isB ? (item.currency === 'JPY' ? `${item.actual_cost?.toLocaleString()} JPY` : `¥${item.actual_cost?.toFixed(2)}`) : '-'}
                                  </td>

                                  <td className="py-2 px-2 text-slate-300 truncate max-w-[100px]">{item.supplier || '-'}</td>
                                  <td className="py-2 px-2">
                                    {item.url ? (
                                      <a
                                        href={item.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-violet-400 hover:underline flex items-center gap-0.5 text-[11px]"
                                      >
                                        <ExternalLink className="w-3 h-3" /> 访问
                                      </a>
                                    ) : (
                                      <span className="text-slate-600">-</span>
                                    )}
                                  </td>
                                  <td className="py-2 px-2 text-slate-400 truncate max-w-[120px]">{item.remarks || '-'}</td>
                                  <td className="py-2 px-2 text-right">
                                    <div className="flex items-center justify-end gap-1">
                                      <button
                                        onClick={() => openEditModal(item)}
                                        className="p-1 text-slate-400 hover:text-violet-400"
                                        title="编辑"
                                      >
                                        <Edit2 className="w-3.5 h-3.5" />
                                      </button>
                                      <button
                                        onClick={() => {
                                          if (confirm(`确认删除费用项目 [${item.item_name}] ？`)) {
                                            deleteCostItemMutation.mutate(item.id);
                                          }
                                        }}
                                        className="p-1 text-slate-400 hover:text-rose-400"
                                        title="删除"
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

                      {/* Subtotal Bar */}
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 p-2.5 bg-[#0B0F17] rounded-xl border border-[#2A3447] text-[11px]">
                        <div className="flex items-center gap-1.5">
                          <span className="text-slate-400">小计实付:</span>
                          <strong className="text-emerald-400 font-mono">¥{subRealCNY.toFixed(2)} CNY</strong>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span className="text-slate-400">实付单价:</span>
                          <strong className="text-slate-200 font-mono">¥{subRealUnitCNY.toFixed(2)} /件</strong>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span className="text-slate-400">小计预算:</span>
                          <strong className="text-violet-300 font-mono">¥{subBudgetCNY.toFixed(2)} CNY</strong>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span className="text-slate-400">预算单价:</span>
                          <strong className="text-slate-300 font-mono">¥{subBudgetUnitCNY.toFixed(2)} /件</strong>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </DataCard>
          </div>

          {/* Right Column (Span 4): Financial Accounting Panel & WIP Clear */}
          <div className="lg:col-span-4 space-y-4">
            <h2 className="font-bold text-base text-slate-100 flex items-center gap-2">
              📊 财务核算面板
            </h2>

            <div className="space-y-3">
              <StatCard
                label="项目总支出 (实付)"
                value={`¥${totalRealCost.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                icon={CircleDollarSign}
                colorScheme="emerald"
                borderLeft
              />
              <StatCard
                label="项目预算总成本"
                value={`¥${totalBudgetCost.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                icon={Calculator}
                colorScheme="indigo"
                borderLeft
              />
              <StatCard
                label="预计可销售总数"
                value={makeQty}
                unit="件"
                icon={Package}
                colorScheme="violet"
                borderLeft
              />
              <StatCard
                label="单套综合成本 (实付)"
                value={`¥${unitRealCost.toFixed(2)}`}
                icon={PiggyBank}
                colorScheme="emerald"
                borderLeft
              />
              <StatCard
                label="预算单套成本"
                value={`¥${unitBudgetCost.toFixed(2)}`}
                icon={TrendingUp}
                colorScheme="indigo"
                borderLeft
              />
            </div>

            {/* WIP Settlement Box */}
            <div className="p-4 bg-[#0B0F17] rounded-2xl border border-violet-500/30 space-y-3 shadow-xl">
              <h3 className="font-bold text-sm text-slate-100 flex items-center gap-2">
                🛠️ 生产完成 / 清零在制资产
              </h3>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                ⚠️ 功能说明：如果该商品已经生产完成，请点击下方按钮。此操作会将在制资产冲归大货资产，并根据已生产数量重算毛利。
              </p>
              <div className="pt-2 border-t border-[#2A3447]/60 flex items-center justify-between text-xs">
                <span className="text-slate-400">当前在制资产 (WIP):</span>
                <span className="font-bold font-mono text-amber-400 text-sm">
                  ¥{remainingWIP.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} CNY
                </span>
              </div>

              {isProductionCompleted ? (
                <div className="space-y-2 pt-1">
                  <div className="p-2.5 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-center text-emerald-400 font-bold text-xs">
                    ✅ 已完成生产结单
                  </div>
                  <button
                    onClick={() => activeProductId && wipFixMutation.mutate(activeProductId as number)}
                    disabled={wipFixMutation.isPending}
                    className="w-full py-2 bg-violet-600/20 hover:bg-violet-600/30 text-violet-300 border border-violet-500/30 font-semibold rounded-xl text-xs transition"
                  >
                    🔄 重新计算大货单价与资产
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => activeProductId && wipFixMutation.mutate(activeProductId as number)}
                  disabled={wipFixMutation.isPending}
                  className="w-full py-2.5 bg-rose-600 hover:bg-rose-500 text-white font-bold rounded-xl shadow-lg shadow-rose-500/20 text-xs transition"
                >
                  🚀 生产完成 (清零在制)
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Bottom Full-Width Card: Multi-platform Profit Matrix */}
      {currentProduct && (
        <DataCard title="📈 款式定价与毛利参考 (基于实付)">
          <div className="space-y-3">
            <h4 className="text-xs font-bold text-slate-300">多平台毛利矩阵分析</h4>
            {profitRows.length === 0 ? (
              <div className="p-8 text-center text-slate-400 text-xs">
                该商品暂未设置任何价格或预计销售数
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-[#2A3447] text-slate-400 text-[11px] uppercase">
                      <th className="pb-2.5 px-3">款式规格</th>
                      <th className="pb-2.5 px-3">销售平台</th>
                      <th className="pb-2.5 px-3 text-right">平台定价</th>
                      <th className="pb-2.5 px-3 text-right">扣除手续费(CNY)</th>
                      <th className="pb-2.5 px-3 text-right">单件毛利</th>
                      <th className="pb-2.5 px-3 text-center">毛利率</th>
                      <th className="pb-2.5 px-3 text-right">预期款式总毛利</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#2A3447]/40 font-mono">
                    {profitRows.map((r, rIdx) => {
                      const isPositive = r.marginCny > 0;

                      return (
                        <tr key={rIdx} className="hover:bg-[#131924]/40 transition">
                          <td className="py-3 px-3 font-sans font-bold text-slate-100">
                            <span className="px-2 py-0.5 rounded bg-violet-500/10 text-violet-300 border border-violet-500/20">
                              {r.colorName}
                            </span>
                          </td>
                          <td className="py-3 px-3 font-sans text-slate-300 flex items-center gap-1">
                            <Tag className="w-3 h-3 text-emerald-400" />
                            {r.platformLabel}
                          </td>
                          <td className="py-3 px-3 text-right text-slate-200">{r.presetPriceStr}</td>
                          <td className="py-3 px-3 text-right text-slate-400">{r.estimatedFeeCnyStr}</td>
                          <td className={`py-3 px-3 text-right font-bold ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {r.marginCnyStr}
                          </td>
                          <td className="py-3 px-3 text-center">
                            <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${isPositive ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'}`}>
                              {r.marginRateStr}
                            </span>
                          </td>
                          <td className={`py-3 px-3 text-right font-bold ${isPositive ? 'text-violet-300' : 'text-rose-400'}`}>
                            {r.expectedTotalProfitStr}
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
      )}

      {/* Edit Cost Item Modal */}
      {editingItem && (
        <Modal
          isOpen={!!editingItem}
          onClose={() => setEditingItem(null)}
          title={`⚙️ 编辑项目支出信息 - ${editingItem.item_name}`}
        >
          <form onSubmit={handleSaveEdit} className="space-y-4 text-xs">
            <FormField label="项目名称 (不可改)">
              <input
                type="text"
                disabled
                value={editingItem.item_name}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-400 cursor-not-allowed"
              />
            </FormField>

            {editingItem.is_budget && (
              <div className="grid grid-cols-2 gap-3">
                <FormField label="预算单价">
                  <input
                    type="number"
                    step="0.01"
                    value={editUnitPrice}
                    onChange={(e) => setEditUnitPrice(e.target.value ? parseFloat(e.target.value) : '')}
                    className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                  />
                </FormField>
                <FormField label="预算数量">
                  <input
                    type="number"
                    step="0.1"
                    value={editQty}
                    onChange={(e) => setEditQty(e.target.value ? parseFloat(e.target.value) : '')}
                    className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                  />
                </FormField>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <FormField label="物理单位">
                <input
                  type="text"
                  placeholder="如：套/米"
                  value={editUnit}
                  onChange={(e) => setEditUnit(e.target.value)}
                  className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                />
              </FormField>

              <FormField label="供应商">
                <input
                  type="text"
                  placeholder="如：淘宝网"
                  value={editSupplier}
                  onChange={(e) => setEditSupplier(e.target.value)}
                  className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                />
              </FormField>
            </div>

            <FormField label="相关链接">
              <input
                type="text"
                placeholder="如淘宝宝贝网址"
                value={editUrl}
                onChange={(e) => setEditUrl(e.target.value)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
              />
            </FormField>

            <FormField label="说明备注">
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
                onClick={() => setEditingItem(null)}
                className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg"
              >
                取消
              </button>
              <button
                type="submit"
                disabled={saveEditMutation.isPending}
                className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white font-medium rounded-lg"
              >
                保存修改
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
};

export default CostPage;
