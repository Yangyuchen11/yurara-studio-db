// frontend/src/pages/SalesOrdersPage.tsx
import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as XLSX from 'xlsx';
import { apiClient } from '../api/client';
import type { SalesOrder, Product, Warehouse, SalesPlatform } from '../types';
import { StatCard } from '../components/ui/StatCard';
import { DataCard } from '../components/ui/DataCard';
import { FormField } from '../components/ui/FormField';
import { PageHeader } from '../components/ui/PageHeader';
import { Modal } from '../components/ui/Modal';
import {
  ShoppingCart,
  Plus,
  Trash2,
  RefreshCw,
  CheckCircle2,
  Search,
  Truck,
  RotateCcw,
  Package,
  Clock,
  Wrench,
  ChevronDown,
  ChevronUp,
  Upload,
  FileSpreadsheet,
  AlertCircle,
  AlertTriangle,
  Check,
  Edit2,
  Rocket
} from 'lucide-react';

interface CartItem {
  id: number;
  productId: number;
  productName: string;
  variant: string;
  warehouseId?: number;
  warehouseName?: string;
  quantity: number;
}

export const SalesOrdersPage: React.FC = () => {
  const queryClient = useQueryClient();

  // Top Card Collapsible & Tab State (Default COLLAPSED when switching/navigating to page)
  const [isCardExpanded, setIsCardExpanded] = useState(false);
  const [topTab, setTopTab] = useState<'manual' | 'excel'>('manual');

  // List Filter & Selection State
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [productFilter, setProductFilter] = useState('全部商品');
  const [selectedOrderIds, setSelectedOrderIds] = useState<number[]>([]);

  // Modals
  const [refundModalOrder, setRefundModalOrder] = useState<SalesOrder | null>(null);
  const [detailOrder, setDetailOrder] = useState<SalesOrder | null>(null);

  // Manual Order Form State
  const [orderNoInput, setOrderNoInput] = useState(`ON-${Date.now().toString().slice(-6)}`);
  const [orderDateInput, setOrderDateInput] = useState(new Date().toISOString().split('T')[0]);
  const [platformInput, setPlatformInput] = useState('微店');
  const [currencyInput, setCurrencyInput] = useState('CNY');
  const [targetAccountInput, setTargetAccountInput] = useState('');
  const [totalPriceInput, setTotalPriceInput] = useState<number | ''>('');
  const [deductFeeInput, setDeductFeeInput] = useState(true);
  const [notesInput, setNotesInput] = useState('');
  const [orderCart, setOrderCart] = useState<CartItem[]>([]);

  // Cart item selector inputs
  const [selProdId, setSelProdId] = useState<number | ''>('');
  const [selVariant, setSelVariant] = useState('');
  const [selWarehouseId, setSelWarehouseId] = useState<number | ''>('');
  const [selQty, setSelQty] = useState<number>(1);
  const [formError, setFormError] = useState('');

  // Excel Bulk Import State
  const [excelFileName, setExcelFileName] = useState('');
  const [excelErrors, setExcelErrors] = useState<string[]>([]);
  const [parsedPreviewOrders, setParsedPreviewOrders] = useState<any[]>([]);
  const [anyOutOfStock, setAnyOutOfStock] = useState(false);
  const [isImporting, setIsImporting] = useState(false);

  // Queries
  const { data: platformsData } = useQuery({
    queryKey: ['platforms'],
    queryFn: async () => {
      const res = await apiClient.get('/platforms/');
      return res.data;
    },
  });

  const { data: ordersData, isLoading, refetch } = useQuery({
    queryKey: ['sales-orders'],
    queryFn: async () => {
      const res = await apiClient.get('/sales/orders/');
      return res.data;
    },
  });

  const { data: productsData } = useQuery({
    queryKey: ['products'],
    queryFn: async () => {
      const res = await apiClient.get('/products/');
      return res.data;
    },
  });

  const { data: warehousesData } = useQuery({
    queryKey: ['warehouses'],
    queryFn: async () => {
      const res = await apiClient.get('/warehouses/');
      return res.data;
    },
  });

  const { data: cashAccountsData } = useQuery({
    queryKey: ['cashAccounts'],
    queryFn: async () => {
      const res = await apiClient.get('/finance/records/cash-accounts/');
      return res.data || [];
    },
  });

  const safeArray = (d: any): any[] => {
    if (Array.isArray(d)) return d;
    if (d && Array.isArray(d.results)) return d.results;
    return [];
  };

  const platforms: SalesPlatform[] = safeArray(platformsData);
  const rawOrders: SalesOrder[] = safeArray(ordersData);
  const products: Product[] = safeArray(productsData);
  const warehouses: Warehouse[] = safeArray(warehousesData);
  const rawCashAccounts: any[] = safeArray(cashAccountsData);

  // 1. Base online sales orders query (strictly matching order_type == '线上' in Reflex)
  const onlineOrdersBase = rawOrders.filter(o => o && (o.order_type === '线上' || !o.order_type || (o.order_type !== '预售' && o.order_type !== '线下')));

  // 2. Orders filtered by Product Filter (used for both KPI Stat Cards & Table)
  const onlineOrdersForStats = onlineOrdersBase.filter(o => {
    if (productFilter === '全部商品') return true;
    return o.items?.some(i => i.product_name === productFilter);
  });

  // Filter ONLY cash accounts by current currency
  const cashAccounts = rawCashAccounts.filter((i: any) => i && (!currencyInput || i.currency === currencyInput));

  // Auto-set recommended cash account if not selected
  useEffect(() => {
    if (cashAccounts.length > 0 && !targetAccountInput) {
      let recommended = "流动资金-支付宝账户";
      if (platformInput === "微店") recommended = "流动资金-微店账户";
      else if (platformInput === "Booth") recommended = "流动资金-booth账户";
      else if (currencyInput !== "CNY") {
        recommended = cashAccounts[0]?.name || `流动资金-${currencyInput.toLowerCase()}临时账户`;
      }
      const match = cashAccounts.find((a: any) => a.name === recommended);
      setTargetAccountInput(match ? match.name : cashAccounts[0]?.name || recommended);
    }
  }, [cashAccounts, platformInput, currencyInput]);

  // Status Matching Helper (Matching Reflex OrderStatus Enum)
  const isPendingStatus = (s: string) => s === '待发货' || s === '📦 待发货' || s === '待出货';
  const isShippedStatus = (s: string) => s === '已发货' || s === '🚚 已发货';
  const isCompletedStatus = (s: string) => s === '订单完成' || s === '已完成' || s === '完成' || s === '✅ 完成';
  const isAfterSalesStatus = (s: string, o?: SalesOrder) => s === '售后中' || s === '售后' || s === '🔧 售后' || (o?.refunds && o.refunds.length > 0);

  // Mutations
  const createOrderMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await apiClient.post('/sales/orders/create_order/', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
      setOrderNoInput(`ON-${Date.now().toString().slice(-6)}`);
      setOrderCart([]);
      setTotalPriceInput('');
      setNotesInput('');
      setFormError('');
      // Maintain EXPANDED state after submitting order
      setIsCardExpanded(true);
      alert('✅ 手动创建线上销售订单成功！已扣减库存并自动录入财务流水。');
    },
    onError: (err: any) => {
      setFormError(err.response?.data?.error || err.message || '建单失败');
    },
  });

  // Cart Handlers
  const handleAddToCart = () => {
    if (!selProdId) {
      alert('请选择商品 SPU');
      return;
    }
    const pObj = products.find(p => p.id === selProdId);
    const whObj = warehouses.find(w => w.id === selWarehouseId);

    const newItem: CartItem = {
      id: Date.now(),
      productId: Number(selProdId),
      productName: pObj?.name || `商品 #${selProdId}`,
      variant: selVariant || '默认规格',
      warehouseId: selWarehouseId ? Number(selWarehouseId) : undefined,
      warehouseName: whObj?.name,
      quantity: selQty || 1,
    };
    setOrderCart([...orderCart, newItem]);
  };

  const handleCreateOrderSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    if (orderCart.length === 0) {
      setFormError('请在订单商品列表中添加至少一项商品');
      return;
    }

    const totalAmount = Number(totalPriceInput) || 0;
    const totalQty = orderCart.reduce((sum, item) => sum + item.quantity, 0);
    const unitPrice = totalQty > 0 ? totalAmount / totalQty : 0;

    createOrderMutation.mutate({
      order_no: orderNoInput,
      order_type: '线上',
      platform: platformInput,
      currency: currencyInput,
      total_amount: totalAmount,
      target_account_name: targetAccountInput || null,
      notes: notesInput,
      items: orderCart.map(item => ({
        product_id: item.productId,
        product_name: item.productName,
        variant: item.variant,
        warehouse_id: item.warehouseId,
        quantity: item.quantity,
        unit_price: unitPrice,
        subtotal: item.quantity * unitPrice,
      })),
    });
  };

  // Excel Upload & Parse Logic
  const parseSalesExcel = (file: File) => {
    setExcelFileName(file.name);
    setExcelErrors([]);
    setParsedPreviewOrders([]);
    setAnyOutOfStock(false);

    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = new Uint8Array(e.target?.result as ArrayBuffer);
        const workbook = XLSX.read(data, { type: 'array' });
        const sheetName = workbook.SheetNames[0];
        const sheet = workbook.Sheets[sheetName];
        const rows: any[] = XLSX.utils.sheet_to_json(sheet);

        if (!rows || rows.length === 0) {
          setExcelErrors(['上传的 Excel 表格内容为空']);
          return;
        }

        const errors: string[] = [];
        const previewOrders: any[] = [];
        let hasStockWarning = false;

        rows.forEach((row, idx) => {
          const rowNum = idx + 2;
          const orderNo = String(row['订单号'] || row['OrderNo'] || '').trim();
          const prodName = String(row['商品名'] || row['商品名称'] || row['ProductName'] || '').trim();
          const variant = String(row['商品型号'] || row['款式'] || row['Variant'] || '默认').trim();
          const qty = parseInt(row['数量'] || row['Qty'] || '1');
          const plat = String(row['销售平台'] || row['Platform'] || '微店').trim();
          const totalAmt = parseFloat(row['订单总额'] || row['总价'] || row['TotalAmount'] || '0');
          const curr = String(row['币种'] || row['Currency'] || 'CNY').trim();
          const whName = String(row['出货仓库'] || row['Warehouse'] || '主仓库').trim();

          if (!orderNo) errors.push(`第 ${rowNum} 行: 缺少订单号`);
          if (!prodName) errors.push(`第 ${rowNum} 行: 缺少商品名`);

          let accName = "流动资金-支付宝账户";
          if (plat === "微店") accName = "流动资金-微店账户";
          else if (plat === "Booth") accName = "流动资金-booth账户";
          else if (curr !== "CNY") accName = `流动资金-${curr.toLowerCase()}临时账户`;

          const fee = (plat === '微店' || plat === 'Booth') ? totalAmt * 0.05 : 0;
          const netPrice = Math.max(0, totalAmt - fee);

          previewOrders.push({
            stock_warning: '🟢 正常',
            order_no: orderNo,
            platform: plat,
            target_account: accName,
            currency: curr,
            total_qty: qty,
            gross_price: totalAmt,
            fee: Math.round(fee * 100) / 100,
            net_price: Math.round(netPrice * 100) / 100,
            items_str: `${prodName}-${variant}×${qty}`,
            items: [
              {
                product_name: prodName,
                variant,
                quantity: qty,
                unit_price: qty > 0 ? totalAmt / qty : 0,
                subtotal: totalAmt,
              }
            ]
          });
        });

        if (errors.length > 0) {
          setExcelErrors(errors);
        } else {
          setParsedPreviewOrders(previewOrders);
          setAnyOutOfStock(hasStockWarning);
        }
      } catch (err: any) {
        setExcelErrors([`解析文件失败: ${err.message}`]);
      }
    };
    reader.readAsArrayBuffer(file);
  };

  const handleBatchImportSubmit = async () => {
    if (parsedPreviewOrders.length === 0) return;
    setIsImporting(true);
    try {
      for (const order of parsedPreviewOrders) {
        await apiClient.post('/sales/orders/create_order/', {
          order_no: order.order_no,
          order_type: '线上',
          platform: order.platform,
          currency: order.currency,
          total_amount: order.gross_price,
          target_account_name: order.target_account,
          items: order.items,
        });
      }
      alert(`✅ 成功批量导入并记录 ${parsedPreviewOrders.length} 笔线上销售订单！`);
      setParsedPreviewOrders([]);
      setExcelFileName('');
      // Maintain EXPANDED state after batch submission
      setIsCardExpanded(true);
      queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
    } catch (err: any) {
      alert(`批量导入部分产生错误: ${err.response?.data?.error || err.message}`);
    } finally {
      setIsImporting(false);
    }
  };

  // KPI Stat Cards: Dynamically calculated based on selected Product Filter (Matching Reflex)
  const statTotal = onlineOrdersForStats.length;
  const statPending = onlineOrdersForStats.filter(o => isPendingStatus(o.status)).length;
  const statShipped = onlineOrdersForStats.filter(o => isShippedStatus(o.status)).length;
  const statCompleted = onlineOrdersForStats.filter(o => isCompletedStatus(o.status)).length;
  const statAfterSales = onlineOrdersForStats.filter(o => isAfterSalesStatus(o.status, o)).length;

  // Filtered Orders for Table (Applies Status tab and Search query on top of onlineOrdersForStats)
  const filteredOrders = onlineOrdersForStats.filter(o => {
    if (!o) return false;

    // Status Tab Filter
    if (statusFilter === 'pending' && !isPendingStatus(o.status)) return false;
    if (statusFilter === 'shipped' && !isShippedStatus(o.status)) return false;
    if (statusFilter === 'completed' && !isCompletedStatus(o.status)) return false;
    if (statusFilter === 'after_sales' && !isAfterSalesStatus(o.status, o)) return false;

    // Search Query
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      const matchNo = String(o.order_no || '').toLowerCase().includes(q);
      const matchPlat = String(o.platform || '').toLowerCase().includes(q);
      const matchNotes = String(o.notes || '').toLowerCase().includes(q);
      const matchItems = o.items?.some(i => i.product_name.toLowerCase().includes(q) || (i.variant || '').toLowerCase().includes(q));
      if (!matchNo && !matchPlat && !matchNotes && !matchItems) return false;
    }

    return true;
  });

  // Selected Amount Sum
  const selectedOrdersList = onlineOrdersForStats.filter(o => selectedOrderIds.includes(o.id));
  const selectedAmountSum = selectedOrdersList.reduce((sum, o) => {
    const amt = Number(o.total_amount) || 0;
    return sum + (o.currency === 'JPY' ? amt * 0.048 : amt);
  }, 0);

  // Cart Summary Calculations
  const cartTotalQty = orderCart.reduce((sum, i) => sum + i.quantity, 0);
  const totalVal = Number(totalPriceInput) || 0;
  const estimatedFee = (platformInput === '微店' || platformInput === 'Booth') ? totalVal * 0.05 : 0;
  const boothPeel = (platformInput === 'Booth' && currencyInput === 'JPY') ? 500 : 0;
  const netIncome = Math.max(0, totalVal - estimatedFee - boothPeel);
  const netUnitPrice = cartTotalQty > 0 ? netIncome / cartTotalQty : 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="🛒 线上销售订单管理"
        subtitle="购物车建单、Excel 批量导入解析、全渠道订单履约、发货状态流转与售后退款对账"
        action={
          <div className="flex items-center gap-2">
            <button
              onClick={() => refetch()}
              className="px-3 py-1.5 bg-[#18202F] hover:bg-[#222C3E] text-slate-200 text-xs font-medium rounded-lg border border-[#2A3447] transition flex items-center gap-1.5"
            >
              <RefreshCw className="w-3.5 h-3.5 text-violet-400" />
              刷新
            </button>
          </div>
        }
      />

      {/* Top Collapsible Order Creation & Excel Import Card (Defaults COLLAPSED on page load) */}
      <div className="bg-[#131924]/90 backdrop-blur-xl border border-[#2A3447] rounded-2xl p-5 space-y-4 shadow-xl">
        <div className="flex items-center justify-between border-b border-[#2A3447] pb-3">
          <div className="flex items-center gap-4">
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <span className="p-1.5 bg-violet-600/20 text-violet-400 rounded-lg">➕</span>
              手动创建订单 / 批量 Excel 导入
            </h3>
            <div className="flex gap-2 text-xs font-semibold">
              <button
                onClick={() => { setTopTab('manual'); setIsCardExpanded(true); }}
                className={`px-3 py-1 rounded-lg transition ${
                  topTab === 'manual'
                    ? 'bg-violet-600/20 text-violet-300 border border-violet-500/40 font-bold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                ➕ 手动创建线上订单
              </button>
              <button
                onClick={() => { setTopTab('excel'); setIsCardExpanded(true); }}
                className={`px-3 py-1 rounded-lg transition ${
                  topTab === 'excel'
                    ? 'bg-violet-600/20 text-violet-300 border border-violet-500/40 font-bold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                📥 批量导入订单 (Excel)
              </button>
            </div>
          </div>

          <button
            onClick={() => setIsCardExpanded(!isCardExpanded)}
            className="p-1.5 text-slate-400 hover:text-slate-100 hover:bg-[#18202F] rounded-lg transition flex items-center gap-1 text-xs"
            title={isCardExpanded ? '收起建单面板' : '展开建单面板'}
          >
            <span className="text-[11px]">{isCardExpanded ? '收起' : '展开'}</span>
            {isCardExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>

        {isCardExpanded && (
          <div>
            {topTab === 'manual' && (
              <form onSubmit={handleCreateOrderSubmit} className="space-y-4 text-xs">
                {formError && (
                  <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-400 text-xs">
                    {formError}
                  </div>
                )}

                <h4 className="font-bold text-slate-200 text-xs">1. 订单基础信息</h4>
                <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
                  <FormField label="订单号" required>
                    <input
                      type="text"
                      required
                      value={orderNoInput}
                      onChange={(e) => setOrderNoInput(e.target.value)}
                      className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100 font-mono"
                    />
                  </FormField>

                  <FormField label="订单日期">
                    <input
                      type="date"
                      value={orderDateInput}
                      onChange={(e) => setOrderDateInput(e.target.value)}
                      className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100 font-mono"
                    />
                  </FormField>

                  <FormField label="销售平台">
                    <select
                      value={platformInput}
                      onChange={(e) => setPlatformInput(e.target.value)}
                      className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100"
                    >
                      <option value="微店">微店</option>
                      <option value="Booth">Booth</option>
                      <option value="淘宝">淘宝</option>
                      {(platforms || []).map(p => (
                        <option key={p.id} value={p.name}>{p.name}</option>
                      ))}
                    </select>
                  </FormField>

                  <FormField label="币种">
                    <select
                      value={currencyInput}
                      onChange={(e) => setCurrencyInput(e.target.value)}
                      className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100 font-mono"
                    >
                      <option value="CNY">CNY (¥)</option>
                      <option value="JPY">JPY (￥)</option>
                    </select>
                  </FormField>

                  <FormField label="收款现金账户 (仅限现金账户)">
                    <select
                      value={targetAccountInput}
                      onChange={(e) => setTargetAccountInput(e.target.value)}
                      className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100"
                    >
                      {cashAccounts.map((a: any) => (
                        <option key={a.id} value={a.name}>{a.name} [{a.currency}]</option>
                      ))}
                    </select>
                  </FormField>
                </div>

                <h4 className="font-bold text-slate-200 text-xs pt-2 border-t border-[#2A3447]">2. 订单商品列表 (添加商品)</h4>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end p-3 bg-[#0B0F17] rounded-xl border border-[#2A3447]">
                  <div className="md:col-span-4">
                    <label className="text-[11px] text-slate-400 block mb-1">选择商品 SPU</label>
                    <select
                      value={selProdId}
                      onChange={(e) => {
                        const id = e.target.value ? Number(e.target.value) : '';
                        setSelProdId(id);
                        const pObj = products.find(p => p.id === id);
                        if (pObj && pObj.colors && pObj.colors.length > 0) {
                          setSelVariant(pObj.colors[0].color_name);
                        }
                      }}
                      className="w-full bg-[#131924] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100"
                    >
                      <option value="">-- 选择商品 --</option>
                      {products.map(p => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                      ))}
                    </select>
                  </div>

                  <div className="md:col-span-3">
                    <label className="text-[11px] text-slate-400 block mb-1">选择款式 SKU</label>
                    {(() => {
                      const selProd = products.find(p => p.id === selProdId);
                      const colorList = selProd?.colors || [];
                      if (colorList.length > 0) {
                        return (
                          <select
                            value={selVariant}
                            onChange={(e) => setSelVariant(e.target.value)}
                            className="w-full bg-[#131924] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100"
                          >
                            {colorList.map(c => (
                              <option key={c.id} value={c.color_name}>{c.color_name}</option>
                            ))}
                          </select>
                        );
                      }
                      return (
                        <input
                          type="text"
                          placeholder="款式 (如: 樱花粉/M)"
                          value={selVariant}
                          onChange={(e) => setSelVariant(e.target.value)}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100"
                        />
                      );
                    })()}
                  </div>

                  <div className="md:col-span-2">
                    <label className="text-[11px] text-slate-400 block mb-1">数量</label>
                    <input
                      type="number"
                      value={selQty}
                      onChange={(e) => setSelQty(parseInt(e.target.value) || 1)}
                      className="w-full bg-[#131924] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100 font-mono"
                    />
                  </div>

                  <div className="md:col-span-2">
                    <label className="text-[11px] text-slate-400 block mb-1">出货仓库</label>
                    <select
                      value={selWarehouseId}
                      onChange={(e) => setSelWarehouseId(e.target.value ? Number(e.target.value) : '')}
                      className="w-full bg-[#131924] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100"
                    >
                      <option value="">-- 选择出货仓库 --</option>
                      {warehouses.map(w => (
                        <option key={w.id} value={w.id}>{w.name}</option>
                      ))}
                    </select>
                  </div>

                  <div className="md:col-span-1">
                    <button
                      type="button"
                      onClick={handleAddToCart}
                      className="w-full py-2 bg-violet-600 hover:bg-violet-500 text-white font-bold rounded-xl transition shadow-md flex items-center justify-center gap-1"
                    >
                      <Plus className="w-4 h-4" />
                      加入订单
                    </button>
                  </div>
                </div>

                {orderCart.length > 0 && (
                  <div className="p-3 bg-[#0B0F17] rounded-xl border border-[#2A3447] space-y-2">
                    <div className="flex items-center justify-between text-[11px] text-slate-400 font-bold">
                      <span>当前已加入的商品：</span>
                      <button
                        type="button"
                        onClick={() => setOrderCart([])}
                        className="text-rose-400 hover:underline text-[10px]"
                      >
                        清空购物车
                      </button>
                    </div>
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-[#2A3447] text-slate-500 text-[10px] uppercase">
                          <th className="py-1 px-2">商品名称</th>
                          <th className="py-1 px-2">款式</th>
                          <th className="py-1 px-2">出货仓库</th>
                          <th className="py-1 px-2 text-center">数量</th>
                          <th className="py-1 px-2 text-center">操作</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#2A3447]/50">
                        {orderCart.map(c => (
                          <tr key={c.id}>
                            <td className="py-1.5 px-2 font-bold text-slate-200">{c.productName}</td>
                            <td className="py-1.5 px-2 text-violet-300">{c.variant}</td>
                            <td className="py-1.5 px-2 text-slate-400">{c.warehouseName || '未分配'}</td>
                            <td className="py-1.5 px-2 text-center font-mono font-bold text-slate-100">{c.quantity}</td>
                            <td className="py-1.5 px-2 text-center">
                              <button
                                type="button"
                                onClick={() => setOrderCart(orderCart.filter(i => i.id !== c.id))}
                                className="text-slate-500 hover:text-rose-400"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <h4 className="font-bold text-slate-200 text-xs pt-2 border-t border-[#2A3447]">3. 结算信息</h4>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <FormField label="订单总价 (含邮费)" required>
                    <input
                      type="number"
                      step="0.01"
                      placeholder="0.00"
                      value={totalPriceInput}
                      onChange={(e) => setTotalPriceInput(e.target.value ? parseFloat(e.target.value) : '')}
                      className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100 font-mono font-bold text-emerald-400"
                    />
                  </FormField>

                  <div className="flex items-center gap-2 pt-6">
                    <input
                      type="checkbox"
                      id="deductFee"
                      checked={deductFeeInput}
                      onChange={(e) => setDeductFeeInput(e.target.checked)}
                      className="rounded border-slate-700 text-violet-600 focus:ring-0"
                    />
                    <label htmlFor="deductFee" className="text-slate-300 font-medium cursor-pointer">
                      扣除平台手续费 (推荐)
                    </label>
                  </div>

                  <FormField label="订单备注">
                    <input
                      type="text"
                      placeholder="客户名称、渠道明细等说明..."
                      value={notesInput}
                      onChange={(e) => setNotesInput(e.target.value)}
                      className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100"
                    />
                  </FormField>
                </div>

                {cartTotalQty > 0 && (
                  <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl space-y-1 text-xs">
                    <div className="flex justify-between items-center font-bold">
                      <span className="text-slate-300">总数量: {cartTotalQty} 件</span>
                      <span className="text-emerald-400 font-mono">
                        商品净入账: {netIncome.toFixed(2)} {currencyInput} | 净单价: {netUnitPrice.toFixed(2)} {currencyInput}/件
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-400">
                      (预估手续费: {estimatedFee.toFixed(2)} {currencyInput})
                      {boothPeel > 0 && ` | 已自动剥离 Booth 预估邮费: ${boothPeel} JPY`}
                    </div>
                  </div>
                )}

                <button
                  type="submit"
                  disabled={createOrderMutation.isPending || orderCart.length === 0}
                  className="w-full py-3 bg-violet-600 hover:bg-violet-500 text-white font-bold rounded-xl shadow-lg shadow-violet-500/25 transition text-xs disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  {createOrderMutation.isPending ? '提交中...' : '✅ 提交新建订单'}
                </button>
              </form>
            )}

            {topTab === 'excel' && (
              <div className="space-y-4 text-xs">
                <div className="p-3 bg-violet-600/10 border border-violet-500/30 rounded-xl flex items-center gap-2 text-violet-300 text-xs">
                  <FileSpreadsheet className="w-4 h-4 shrink-0 text-violet-400" />
                  <span>📊 导入 Excel 列名规范：订单号 | 商品名 | 商品型号 | 数量 | 销售平台 | 订单总额 | 币种 | 出货仓库。多款式请用英文分号 (;) 隔开。</span>
                </div>

                <div className="p-6 border-2 border-dashed border-[#2A3447] hover:border-violet-500/50 rounded-xl bg-[#0B0F17] text-center space-y-2 transition">
                  <Upload className="w-8 h-8 text-violet-400 mx-auto animate-bounce" />
                  <p className="font-bold text-slate-200">选择或拖拽 Excel 表格文件到此处</p>
                  <p className="text-slate-500 text-[11px]">支持 .xlsx, .xls, .csv 格式</p>
                  <input
                    type="file"
                    accept=".xlsx, .xls, .csv"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) parseSalesExcel(file);
                    }}
                    className="hidden"
                    id="excel-file-input"
                  />
                  <label
                    htmlFor="excel-file-input"
                    className="inline-block px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white font-bold rounded-xl cursor-pointer transition shadow-md"
                  >
                    选择 Excel 模板文件
                  </label>
                  {excelFileName && (
                    <div className="pt-2 text-violet-400 font-mono font-bold">📁 {excelFileName}</div>
                  )}
                </div>

                {/* Error Output */}
                {excelErrors.length > 0 && (
                  <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl space-y-1 text-rose-400">
                    <div className="font-bold flex items-center gap-1.5">
                      <AlertCircle className="w-4 h-4" />
                      <span>❌ Excel 校验发现以下数据问题：</span>
                    </div>
                    {excelErrors.map((err, idx) => (
                      <div key={idx} className="text-[11px] font-mono">• {err}</div>
                    ))}
                  </div>
                )}

                {/* Parsed Preview Table */}
                {parsedPreviewOrders.length > 0 && (
                  <div className="space-y-3 pt-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-emerald-400 flex items-center gap-1.5">
                        <Check className="w-4 h-4" />
                        ✅ Excel 校验成功！待入库订单预览 ({parsedPreviewOrders.length} 笔)：
                      </span>
                      <button
                        type="button"
                        onClick={handleBatchImportSubmit}
                        disabled={isImporting}
                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-xl transition shadow-lg shadow-emerald-600/20 flex items-center gap-1.5"
                      >
                        <Rocket className="w-4 h-4" />
                        {isImporting ? '导入中...' : '🚀 确认无误，开始批量导入并记账'}
                      </button>
                    </div>

                    {anyOutOfStock && (
                      <div className="p-2.5 bg-amber-500/10 border border-amber-500/30 rounded-xl text-amber-400 text-[11px] flex items-center gap-1.5">
                        <AlertTriangle className="w-4 h-4" />
                        <span>⚠️ 包含缺货超卖订单，系统将自动允许在“待发货”阶段进行库存调整。</span>
                      </div>
                    )}

                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs bg-[#0B0F17] rounded-xl border border-[#2A3447]">
                        <thead>
                          <tr className="border-b border-[#2A3447] text-slate-400 text-[10px] uppercase">
                            <th className="py-2 px-3">状态盘点</th>
                            <th className="py-2 px-3">订单号</th>
                            <th className="py-2 px-3">平台</th>
                            <th className="py-2 px-3">收款账户</th>
                            <th className="py-2 px-3">币种</th>
                            <th className="py-2 px-3 text-center">数量</th>
                            <th className="py-2 px-3 text-right">原总价</th>
                            <th className="py-2 px-3 text-right">预估手续费</th>
                            <th className="py-2 px-3 text-right">净入账</th>
                            <th className="py-2 px-3">商品明细</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#2A3447]">
                          {parsedPreviewOrders.map((p, idx) => (
                            <tr key={idx}>
                              <td className="py-2 px-3 font-bold text-emerald-400">{p.stock_warning}</td>
                              <td className="py-2 px-3 font-mono font-bold text-slate-100">{p.order_no}</td>
                              <td className="py-2 px-3 text-slate-300">{p.platform}</td>
                              <td className="py-2 px-3 text-violet-300">{p.target_account}</td>
                              <td className="py-2 px-3 font-mono text-slate-400">{p.currency}</td>
                              <td className="py-2 px-3 text-center font-mono font-bold text-slate-100">{p.total_qty}</td>
                              <td className="py-2 px-3 text-right font-mono font-bold text-slate-200">¥{p.gross_price}</td>
                              <td className="py-2 px-3 text-right font-mono text-slate-400">¥{p.fee}</td>
                              <td className="py-2 px-3 text-right font-mono font-bold text-emerald-400">¥{p.net_price}</td>
                              <td className="py-2 px-3 text-slate-300 truncate max-w-xs">{p.items_str}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Product Filter Bar */}
      <div className="flex items-center gap-3 text-xs bg-[#131924]/60 p-3 rounded-xl border border-[#2A3447]">
        <span className="font-bold text-slate-300 flex items-center gap-1.5">
          <Search className="w-4 h-4 text-violet-400" />
          🔍 商品筛选：
        </span>
        <select
          value={productFilter}
          onChange={(e) => setProductFilter(e.target.value)}
          className="bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-1.5 text-slate-200 min-w-[200px] font-medium"
        >
          <option value="全部商品">全部商品</option>
          {products.map(p => (
            <option key={p.id} value={p.name}>{p.name}</option>
          ))}
        </select>
      </div>

      {/* KPI Stat Cards (Dynamically Linked to Product Filter, Matching Reflex) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard
          label="总订单数"
          value={statTotal}
          unit="笔"
          icon={Package}
          colorScheme="violet"
          borderLeft
        />
        <StatCard
          label="待发货 (仓储发货)"
          value={statPending}
          unit="笔"
          icon={Clock}
          colorScheme="amber"
          borderLeft
        />
        <StatCard
          label="已发货 (已扣物存)"
          value={statShipped}
          unit="笔"
          icon={Truck}
          colorScheme="indigo"
          borderLeft
        />
        <StatCard
          label="已完成 (收款对账)"
          value={statCompleted}
          unit="笔"
          icon={CheckCircle2}
          colorScheme="emerald"
          borderLeft
        />
        <StatCard
          label="售后中 (财务退款/补发)"
          value={statAfterSales}
          unit="笔"
          icon={Wrench}
          colorScheme="rose"
          borderLeft
        />
      </div>

      {/* Main Orders List DataCard */}
      <DataCard title="📋 线上销售订单列表">
        <div className="space-y-4">
          {/* Status Tabs */}
          <div className="flex border-b border-[#2A3447] text-xs font-semibold overflow-x-auto gap-2">
            {[
              { key: '', label: '全部' },
              { key: 'pending', label: '待发货' },
              { key: 'shipped', label: '已发货' },
              { key: 'completed', label: '已完成' },
              { key: 'after_sales', label: '售后中' },
            ].map(tab => (
              <button
                key={tab.key}
                onClick={() => setStatusFilter(tab.key)}
                className={`px-4 py-2 border-b-2 transition whitespace-nowrap ${
                  statusFilter === tab.key
                    ? 'border-violet-500 text-violet-400 font-bold'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Search Bar */}
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
            <input
              type="text"
              placeholder="🔍 输入订单号、平台、备注、状态或商品明细筛选..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl pl-9 pr-4 py-2 text-xs text-slate-100"
            />
          </div>

          {/* Batch Selection Summary Bar */}
          <div className="flex items-center justify-between bg-[#0B0F17] p-2.5 rounded-xl border border-[#2A3447] text-xs">
            <div className="flex items-center gap-3">
              <button
                onClick={() => {
                  if (selectedOrderIds.length === filteredOrders.length) setSelectedOrderIds([]);
                  else setSelectedOrderIds(filteredOrders.map(o => o.id));
                }}
                className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs transition"
              >
                ☑️ 全选
              </button>
              <span className="text-slate-400">已勾选 <strong className="text-violet-400">{selectedOrderIds.length}</strong> 项订单</span>
            </div>
            <div className="text-xs font-mono">
              <span className="text-slate-400">折合合计金额: </span>
              <span className="font-bold text-rose-400">¥{selectedAmountSum.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}</span>
            </div>
          </div>

          {/* Table */}
          {isLoading ? (
            <div className="text-center py-8 text-slate-400 text-xs">加载线上订单中...</div>
          ) : filteredOrders.length === 0 ? (
            <div className="text-center py-12 text-slate-500 text-xs bg-[#0B0F17] rounded-xl border border-[#2A3447]">
              该筛选分类下无对应的线上销售订单数据
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#2A3447] text-slate-400 text-[11px] uppercase">
                    <th className="py-3 px-3 w-10 text-center">选择</th>
                    <th className="py-3 px-3">订单号</th>
                    <th className="py-3 px-3">状态</th>
                    <th className="py-3 px-3">商品明细</th>
                    <th className="py-3 px-3 text-right">金额</th>
                    <th className="py-3 px-3 text-right">已退款</th>
                    <th className="py-3 px-3">平台</th>
                    <th className="py-3 px-3">日期</th>
                    <th className="py-3 px-3">备注说明</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#2A3447]/40">
                  {filteredOrders.map(o => {
                    const isSelected = selectedOrderIds.includes(o.id);
                    const itemsSummary = o.items && o.items.length > 0
                      ? o.items.map(i => `${i.product_name}-${i.variant}×${i.quantity}`).join(', ')
                      : '无明细';
                    const refundedTotal = o.refunds?.reduce((sum, r) => sum + r.refund_amount, 0) || 0;

                    return (
                      <tr
                        key={o.id}
                        onClick={() => {
                          if (isSelected) setSelectedOrderIds(selectedOrderIds.filter(i => i !== o.id));
                          else setSelectedOrderIds([...selectedOrderIds, o.id]);
                        }}
                        className={`transition cursor-pointer ${
                          isSelected ? 'bg-violet-600/10' : 'hover:bg-[#131924]/60'
                        }`}
                      >
                        <td className="py-3 px-3 text-center" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => {
                              if (isSelected) setSelectedOrderIds(selectedOrderIds.filter(i => i !== o.id));
                              else setSelectedOrderIds([...selectedOrderIds, o.id]);
                            }}
                            className="rounded border-slate-700 text-violet-600 focus:ring-0"
                          />
                        </td>
                        <td className="py-3 px-3 font-mono font-bold text-slate-100">{o.order_no}</td>
                        <td className="py-3 px-3">
                          <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${
                            isShippedStatus(o.status)
                              ? 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30'
                              : isCompletedStatus(o.status)
                              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                              : 'bg-violet-500/10 text-violet-300 border-violet-500/30'
                          }`}>
                            {o.status || '待发货'}
                          </span>
                        </td>
                        <td className="py-3 px-3 text-slate-300 truncate max-w-xs">{itemsSummary}</td>
                        <td className="py-3 px-3 text-right font-mono font-bold text-emerald-400">
                          {o.currency === 'JPY' ? `${o.total_amount} JPY` : `¥${(o.total_amount || 0).toFixed(2)}`}
                        </td>
                        <td className={`py-3 px-3 text-right font-mono ${refundedTotal > 0 ? 'text-rose-400 font-bold' : 'text-slate-500'}`}>
                          {refundedTotal > 0 ? `¥${refundedTotal.toFixed(2)}` : '-'}
                        </td>
                        <td className="py-3 px-3 text-slate-400">{o.platform}</td>
                        <td className="py-3 px-3 font-mono text-slate-400 text-[11px]">{o.created_date || '-'}</td>
                        <td className="py-3 px-3 text-slate-400 truncate max-w-xs">{o.notes || '-'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Action Bar */}
          <div className="flex flex-wrap items-center gap-2 pt-3 border-t border-[#2A3447]">
            <button
              onClick={async () => {
                if (!confirm(`确认将选中的 ${selectedOrderIds.length} 笔订单标记为【已发货】？`)) return;
                for (const id of selectedOrderIds) {
                  await apiClient.patch(`/sales/orders/${id}/`, { status: '已发货' });
                }
                setSelectedOrderIds([]);
                queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
              }}
              disabled={selectedOrderIds.length === 0}
              className="px-3 py-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5 shadow-md shadow-amber-600/20"
            >
              <Package className="w-3.5 h-3.5" />
              📦 发货 ({selectedOrderIds.length})
            </button>

            <button
              onClick={async () => {
                if (!confirm(`确认将选中的 ${selectedOrderIds.length} 笔订单标记为【已完成对账】？`)) return;
                for (const id of selectedOrderIds) {
                  await apiClient.patch(`/sales/orders/${id}/`, { status: '已完成' });
                }
                setSelectedOrderIds([]);
                queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
              }}
              disabled={selectedOrderIds.length === 0}
              className="px-3 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5 shadow-md shadow-emerald-600/20"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              ✅ 收款完成对账 ({selectedOrderIds.length})
            </button>

            <button
              onClick={() => {
                if (selectedOrderIds.length === 1) {
                  const target = onlineOrdersForStats.find(o => o.id === selectedOrderIds[0]);
                  if (target) setRefundModalOrder(target);
                } else {
                  alert('请选择单笔订单进行售后处理');
                }
              }}
              disabled={selectedOrderIds.length !== 1}
              className="px-3 py-2 bg-rose-600 hover:bg-rose-500 disabled:opacity-40 text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5 shadow-md shadow-rose-600/20"
            >
              <Wrench className="w-3.5 h-3.5" />
              🔧 售后处理
            </button>

            <button
              onClick={() => {
                if (selectedOrderIds.length === 1) {
                  const target = onlineOrdersForStats.find(o => o.id === selectedOrderIds[0]);
                  if (target) setDetailOrder(target);
                } else {
                  alert('请选择单笔订单查看详情');
                }
              }}
              disabled={selectedOrderIds.length !== 1}
              className="px-3 py-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200 rounded-xl text-xs font-semibold transition flex items-center gap-1.5"
            >
              <Edit2 className="w-3.5 h-3.5" />
              📄 查看/修改详情
            </button>
          </div>
        </div>
      </DataCard>

      {/* Order Detail Modal */}
      {detailOrder && (
        <Modal
          isOpen={!!detailOrder}
          onClose={() => setDetailOrder(null)}
          title={`📄 线上订单详情 #${detailOrder.order_no}`}
        >
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 gap-3 p-3 bg-[#0B0F17] rounded-xl border border-[#2A3447]">
              <div>订单号: <strong className="font-mono text-slate-100">{detailOrder.order_no}</strong></div>
              <div>销售平台: <span className="text-slate-200">{detailOrder.platform}</span></div>
              <div>当前状态: <span className="text-emerald-400 font-bold">{detailOrder.status}</span></div>
              <div>订单金额: <span className="font-mono text-emerald-400 font-bold">¥{detailOrder.total_amount || 0}</span></div>
            </div>

            <div>
              <h4 className="font-bold text-slate-200 mb-2">商品明细</h4>
              <table className="w-full text-left text-xs bg-[#0B0F17] rounded-xl border border-[#2A3447]">
                <thead>
                  <tr className="border-b border-[#2A3447] text-slate-500 text-[10px]">
                    <th className="py-2 px-3">商品名称</th>
                    <th className="py-2 px-3">款式</th>
                    <th className="py-2 px-3 text-center">数量</th>
                    <th className="py-2 px-3 text-right">单价</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#2A3447]">
                  {(detailOrder.items || []).map((i, idx) => (
                    <tr key={idx}>
                      <td className="py-2 px-3 text-slate-200 font-bold">{i.product_name}</td>
                      <td className="py-2 px-3 text-violet-300">{i.variant}</td>
                      <td className="py-2 px-3 text-center font-mono">{i.quantity}</td>
                      <td className="py-2 px-3 text-right font-mono">¥{i.unit_price}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex justify-between items-center pt-2 border-t border-[#2A3447]">
              <button
                type="button"
                onClick={async () => {
                  if (confirm(`确认删除订单 #${detailOrder.order_no}？`)) {
                    await apiClient.delete(`/sales/orders/${detailOrder.id}/`);
                    setDetailOrder(null);
                    queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
                  }
                }}
                className="px-3 py-1.5 bg-rose-600/20 text-rose-400 hover:bg-rose-600/30 rounded-lg text-xs border border-rose-500/30"
              >
                🗑️ 删除订单
              </button>

              <button
                type="button"
                onClick={() => setDetailOrder(null)}
                className="px-4 py-2 bg-slate-800 text-slate-300 rounded-xl"
              >
                关闭
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Refund Modal */}
      {refundModalOrder && (
        <Modal
          isOpen={!!refundModalOrder}
          onClose={() => setRefundModalOrder(null)}
          title={`🔧 售后处理 #${refundModalOrder.order_no}`}
        >
          <div className="space-y-4 text-xs">
            <FormField label="退款金额 (¥)">
              <input
                type="number"
                step="0.01"
                defaultValue={refundModalOrder.total_amount}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100 font-mono font-bold text-rose-400"
              />
            </FormField>

            <FormField label="售后说明 / 原因">
              <input
                type="text"
                placeholder="客户申请售后款..."
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100"
              />
            </FormField>

            <div className="flex justify-end gap-2 pt-2 border-t border-[#2A3447]">
              <button
                type="button"
                onClick={() => setRefundModalOrder(null)}
                className="px-4 py-2 bg-slate-800 text-slate-300 rounded-xl"
              >
                取消
              </button>
              <button
                type="button"
                onClick={async () => {
                  await apiClient.patch(`/sales/orders/${refundModalOrder.id}/`, {
                    status: '售后中',
                  });
                  setRefundModalOrder(null);
                  queryClient.invalidateQueries({ queryKey: ['sales-orders'] });
                  alert('✅ 售后处理更新成功！');
                }}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white font-bold rounded-xl shadow-lg shadow-rose-600/20"
              >
                确认提交售后
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};

export default SalesOrdersPage;
