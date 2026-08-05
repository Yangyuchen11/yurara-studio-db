// frontend/src/pages/PresalePage.tsx
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
  ShoppingBasket,
  Plus,
  Trash2,
  RefreshCw,
  CheckCircle2,
  Clock,
  Package,
  PackageCheck,
  Truck,
  Hourglass,
  Layers,
  Wrench,
  Search,
  Link as LinkIcon,
  Upload,
  Edit2,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  FileSpreadsheet,
  Check,
  Building2,
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

export const PresalePage: React.FC = () => {
  const queryClient = useQueryClient();

  // Top Card Collapsible & Tab State (Default COLLAPSED when switching/navigating to page)
  const [isCardExpanded, setIsCardExpanded] = useState(false);
  const [topTab, setTopTab] = useState<'create' | 'bulk'>('create');
  const [createMode, setCreateMode] = useState<'deposit' | 'final'>('deposit');
  const [bulkPresaleMode, setBulkPresaleMode] = useState<'deposit' | 'final'>('deposit');

  // Filter & Selection State
  const [activeTab, setActiveTab] = useState<'all' | 'deposit' | 'final' | 'pending' | 'shipped' | 'completed' | 'after_sales'>('all');
  const [productFilter, setProductFilter] = useState<string>('全部商品');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedOrderIds, setSelectedOrderIds] = useState<number[]>([]);

  // Mode 1: Create Deposit Order State
  const [orderNo, setOrderNo] = useState(`PRE-${Date.now().toString().slice(-6)}`);
  const [orderDate, setOrderDate] = useState(new Date().toISOString().split('T')[0]);
  const [platform, setPlatform] = useState('预售平台');
  const [currency, setCurrency] = useState('CNY');
  const [targetAccountName, setTargetAccountName] = useState('');
  const [depositPrice, setDepositPrice] = useState<number | ''>('');
  const [discountNote, setDiscountNote] = useState('');
  const [notes, setNotes] = useState('');
  const [cart, setCart] = useState<CartItem[]>([]);

  // Cart item selector inputs
  const [tempProdId, setTempProdId] = useState<number | ''>('');
  const [tempVariant, setTempVariant] = useState('');
  const [tempWarehouseId, setTempWarehouseId] = useState<number | ''>('');
  const [tempQty, setTempQty] = useState<number>(1);
  const [formError, setFormError] = useState('');

  // Mode 2: Bind Final Payment State
  const [searchDepNo, setSearchDepNo] = useState('');
  const [selectedDepositOrders, setSelectedDepositOrders] = useState<SalesOrder[]>([]);
  const [foundDepositOrder, setFoundDepositOrder] = useState<SalesOrder | null>(null);
  const [finalOrderNo, setFinalOrderNo] = useState('');
  const [finalAmount, setFinalAmount] = useState<number | ''>('');
  const [finalTargetAccount, setFinalTargetAccount] = useState('');
  const [bindMsg, setBindMsg] = useState({ text: '', isError: false });

  // Excel Bulk Import State
  const [excelFileName, setExcelFileName] = useState('');
  const [excelErrors, setExcelErrors] = useState<string[]>([]);
  const [parsedPreviewOrders, setParsedPreviewOrders] = useState<any[]>([]);
  const [isImporting, setIsImporting] = useState(false);

  // Modals state
  const [detailOrder, setDetailOrder] = useState<SalesOrder | null>(null);
  const [refundOrder, setRefundOrder] = useState<SalesOrder | null>(null);
  const [refundAmount, setRefundAmount] = useState<number | ''>('');
  const [refundReason, setRefundReason] = useState('');
  const [isBatchWhOpen, setIsBatchWhOpen] = useState(false);
  const [batchWarehouseId, setBatchWarehouseId] = useState<number | ''>('');

  // Queries
  const { data: ordersData, isLoading, refetch } = useQuery({
    queryKey: ['presale-orders'],
    queryFn: async () => {
      const res = await apiClient.get('/sales/orders/');
      const all = res.data.results || res.data || [];
      return all.filter((o: SalesOrder) => o.order_type === '预售' || o.deposit_amount > 0 || (o.platform && o.platform.includes('预售')));
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

  const { data: platformsData } = useQuery({
    queryKey: ['platforms'],
    queryFn: async () => {
      const res = await apiClient.get('/platforms/');
      return res.data;
    },
  });

  const { data: cashAccountsData } = useQuery({
    queryKey: ['cashAccountsPresale'],
    queryFn: async () => {
      const res = await apiClient.get('/finance/records/cash-accounts/');
      return res.data || [];
    },
  });

  const { data: ratesData } = useQuery<Record<string, number>>({
    queryKey: ['exchangeRates'],
    queryFn: async () => {
      const res = await apiClient.get('/rates/');
      return res.data.rates || { JPY: 0.048 };
    },
  });

  const safeArray = (d: any): any[] => {
    if (Array.isArray(d)) return d;
    if (d && Array.isArray(d.results)) return d.results;
    return [];
  };

  const rawOrders: SalesOrder[] = safeArray(ordersData);
  const products: Product[] = safeArray(productsData);
  const warehouses: Warehouse[] = safeArray(warehousesData);
  const platforms: SalesPlatform[] = safeArray(platformsData);
  const cashAccounts: any[] = safeArray(cashAccountsData);

  // 1. Base query for presale orders (matching order_type == '预售' in Reflex)
  const presaleOrdersBase = rawOrders.filter(o => o && (o.order_type === '预售' || o.deposit_amount > 0 || (o.platform && o.platform.includes('预售'))));

  // 2. Orders filtered by Product Filter (used for both KPI Stat Cards & Table)
  const presaleOrdersForStats = presaleOrdersBase.filter(o => {
    if (productFilter === '全部商品') return true;
    return o.items?.some(i => i.product_name === productFilter);
  });

  // Status Matching Helper (Matching Reflex OrderStatus Enum)
  const isPendingStatus = (s: string) => s === '待发货' || s === '📦 待发货' || s === '待出货';
  const isShippedStatus = (s: string) => s === '已发货' || s === '🚚 已发货';
  const isCompletedStatus = (s: string) => s === '订单完成' || s === '已完成' || s === '完成' || s === '✅ 完成';
  const isAfterSalesStatus = (s: string, o?: SalesOrder) => s === '售后中' || s === '售后' || s === '🔧 售后' || (o?.refunds && o.refunds.length > 0);
  const isDepositStatus = (s: string, o: SalesOrder) => s === '待完成定金' || s === '待确认定金' || s === '待定金' || s === '🕒 待完成定金' || (!o.deposit_amount && !o.total_amount);
  const isFinalStatus = (s: string, o: SalesOrder) => s === '待付尾款' || s === '⏳ 待付尾款' || (!o.final_order_no && !isShippedStatus(s) && !isCompletedStatus(s));

  // Auto-set default cash accounts
  useEffect(() => {
    if (cashAccounts.length > 0) {
      if (!targetAccountName) {
        const match = cashAccounts.find((a: any) => a.name === "流动资金-支付宝账户" || a.name.includes("微店"));
        setTargetAccountName(match ? match.name : cashAccounts[0].name);
      }
      if (!finalTargetAccount) {
        const match = cashAccounts.find((a: any) => a.name === "流动资金-支付宝账户" || a.name.includes("微店"));
        setFinalTargetAccount(match ? match.name : cashAccounts[0].name);
      }
    }
  }, [cashAccounts]);

  // Mutations
  const createPresaleOrderMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await apiClient.post('/sales/orders/create_order/', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['presale-orders'] });
      setOrderNo(`PRE-${Date.now().toString().slice(-6)}`);
      setCart([]);
      setDepositPrice('');
      setDiscountNote('');
      setNotes('');
      setFormError('');
      // Maintain EXPANDED state after submitting order
      setIsCardExpanded(true);
      alert('✅ 预售定金主订单创建成功！');
    },
    onError: (err: any) => {
      setFormError(err.response?.data?.error || err.message || '创建预售订单失败');
    },
  });

  const bindFinalPaymentMutation = useMutation({
    mutationFn: async ({ id, final_order_no, final_amount, target_account_name }: any) => {
      const res = await apiClient.patch(`/sales/orders/${id}/`, {
        final_order_no,
        final_amount,
        target_account_name,
        status: '待发货',
      });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['presale-orders'] });
      setFoundDepositOrder(null);
      setSearchDepNo('');
      setFinalOrderNo('');
      setFinalAmount('');
      // Maintain EXPANDED state after binding final payment
      setIsCardExpanded(true);
      setBindMsg({ text: '✅ 尾款绑定成功！订单状态已更新为【待发货】', isError: false });
    },
    onError: (err: any) => {
      setBindMsg({ text: `绑定失败: ${err.response?.data?.error || err.message}`, isError: true });
    },
  });

  // Handlers
  const handleAddToCart = () => {
    if (!tempProdId) {
      alert('请选择商品 SPU');
      return;
    }
    const pObj = products.find(p => p.id === tempProdId);
    const whObj = warehouses.find(w => w.id === tempWarehouseId);

    const newItem: CartItem = {
      id: Date.now(),
      productId: Number(tempProdId),
      productName: pObj?.name || `商品 #${tempProdId}`,
      variant: tempVariant || '默认规格',
      warehouseId: tempWarehouseId ? Number(tempWarehouseId) : undefined,
      warehouseName: whObj?.name,
      quantity: tempQty || 1,
    };
    setCart([...cart, newItem]);
  };

  const handleCreateDepositSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    if (cart.length === 0) {
      setFormError('请在定金商品清单中添加至少一项商品');
      return;
    }
    if (!depositPrice || Number(depositPrice) <= 0) {
      setFormError('预售定金总价必须大于 0');
      return;
    }

    const totalDep = Number(depositPrice);
    const unitPrice = totalDep / cart.reduce((sum, i) => sum + i.quantity, 0);

    createPresaleOrderMutation.mutate({
      order_no: orderNo,
      order_type: '预售',
      platform,
      currency,
      target_account_name: targetAccountName || null,
      deposit_amount: totalDep,
      total_amount: totalDep,
      notes,
      discount_note: discountNote,
      items: cart.map(i => ({
        product_id: i.productId,
        product_name: i.productName,
        variant: i.variant,
        warehouse_id: i.warehouseId,
        quantity: i.quantity,
        unit_price: unitPrice,
        subtotal: i.quantity * unitPrice,
      })),
    });
  };

  const handleSearchDepositOrder = () => {
    setBindMsg({ text: '', isError: false });
    if (!searchDepNo.trim()) {
      alert('请输入预售定金单号');
      return;
    }
    const q = searchDepNo.trim().toLowerCase();
    const found = presaleOrdersForStats.find(o => o.order_no.trim().toLowerCase() === q);
    if (found) {
      if (selectedDepositOrders.some(o => o.id === found.id)) {
        setBindMsg({ text: `⚠️ 定金单号 #${found.order_no} 已在绑定列表中`, isError: true });
        return;
      }
      setSelectedDepositOrders(prev => [...prev, found]);
      if (!finalOrderNo) {
        setFinalOrderNo(`FIN-${Date.now().toString().slice(-6)}`);
      }
      setSearchDepNo('');
      setBindMsg({ text: `✅ 已成功添加定金单 #${found.order_no}！可继续搜索追加更多单据。`, isError: false });
    } else {
      setBindMsg({ text: `❌ 未找到定金单号为 [${searchDepNo}] 的预售订单`, isError: true });
    }
  };

  const handleBindFinalSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedDepositOrders.length === 0) {
      alert('请先搜索并锁定至少一个定金订单');
      return;
    }
    if (!finalOrderNo.trim()) {
      alert('请输入尾款订单号');
      return;
    }

    try {
      await apiClient.post('/sales/orders/bind-presale-final/', {
        deposit_order_ids: selectedDepositOrders.map(o => o.id),
        final_order_no: finalOrderNo.trim(),
        final_net_amount: Number(finalAmount) || 0,
        notes: notes,
      });
      alert(`🔗 成功将尾款订单 #${finalOrderNo} 绑定至 ${selectedDepositOrders.length} 个定金订单！`);
      setSelectedDepositOrders([]);
      setFinalOrderNo('');
      setFinalAmount('');
      queryClient.invalidateQueries({ queryKey: ['presale-orders'] });
    } catch (err: any) {
      alert(`绑定失败: ${err.response?.data?.error || err.message}`);
    }
  };

  // Presale Excel Parse Logic
  const parsePresaleExcel = (file: File) => {
    setExcelFileName(file.name);
    setExcelErrors([]);
    setParsedPreviewOrders([]);

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

        rows.forEach((row, idx) => {
          const rowNum = idx + 2;
          const orderNoVal = String(row['订单号'] || row['OrderNo'] || '').trim();
          const depOrderNoRaw = String(row['关联定金单号'] || row['定金单号'] || '').trim();
          const prodName = String(row['商品名'] || row['商品名称'] || row['ProductName'] || '').trim();
          const variant = String(row['商品型号'] || row['款式'] || row['Variant'] || '默认').trim();
          const qty = parseInt(row['数量'] || row['Qty'] || '1');
          const plat = String(row['销售平台'] || row['Platform'] || '预售平台').trim();
          const totalAmt = parseFloat(row['订单总额'] || row['总价'] || row['TotalAmount'] || '0');
          const curr = String(row['币种'] || row['Currency'] || 'CNY').trim();
          const discount = String(row['优惠'] || row['Discount'] || '-').trim();

          if (!orderNoVal) errors.push(`第 ${rowNum} 行: 缺少订单号`);

          let accName = "流动资金-支付宝账户";
          if (plat === "微店") accName = "流动资金-微店账户";
          else if (plat === "Booth") accName = "流动资金-booth账户";
          else if (curr !== "CNY") accName = `流动资金-${curr.toLowerCase()}临时账户`;

          const fee = (plat === '微店' || plat === 'Booth') ? totalAmt * 0.05 : 0;
          const netPrice = Math.max(0, totalAmt - fee);

          if (bulkPresaleMode === 'deposit') {
            previewOrders.push({
              stock_warning: '🟢 盘点正常',
              order_no: orderNoVal,
              platform: plat,
              target_account: accName,
              currency: curr,
              total_qty: qty,
              gross_price: totalAmt,
              fee: Math.round(fee * 100) / 100,
              net_price: Math.round(netPrice * 100) / 100,
              discount_note: discount,
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
          } else {
            // Final Payment Binding Mode with semicolon / comma splitting
            const depOrderNos = depOrderNoRaw.split(/[;,；\s]+/).filter(Boolean);
            const matchedDeposits: SalesOrder[] = [];
            const missingNos: string[] = [];

            for (const depNo of depOrderNos) {
              const found = presaleOrdersForStats.find(o => o.order_no.trim().toLowerCase() === depNo.toLowerCase());
              if (found) {
                matchedDeposits.push(found);
              } else {
                missingNos.push(depNo);
              }
            }

            let matchStatus = `✅ 已精准锁定 ${matchedDeposits.length} 个关联定金单`;
            if (missingNos.length > 0) {
              matchStatus = `❌ 未搜寻到关联定金单 [${missingNos.join(', ')}]`;
              errors.push(`第 ${rowNum} 行: 关联定金单号 [${missingNos.join(', ')}] 在库中不存在`);
            }

            previewOrders.push({
              match_status: matchStatus,
              order_no: orderNoVal,
              dep_order_no: depOrderNoRaw,
              deposit_ids: matchedDeposits.map(o => o.id),
              deposit_id: matchedDeposits[0]?.id,
              platform: plat,
              target_account: accName,
              currency: curr,
              total_qty: qty,
              gross_price: totalAmt,
              fee: Math.round(fee * 100) / 100,
              net_price: Math.round(netPrice * 100) / 100,
              items_str: `${prodName}-${variant}×${qty}`,
            });
          }
        });

        if (errors.length > 0) {
          setExcelErrors(errors);
        } else {
          setParsedPreviewOrders(previewOrders);
        }
      } catch (err: any) {
        setExcelErrors([`解析文件失败: ${err.message}`]);
      }
    };
    reader.readAsArrayBuffer(file);
  };

  const handlePresaleBatchImportSubmit = async () => {
    if (parsedPreviewOrders.length === 0) return;
    setIsImporting(true);
    try {
      if (bulkPresaleMode === 'deposit') {
        for (const orderItem of parsedPreviewOrders) {
          await apiClient.post('/sales/orders/create_order/', {
            order_no: orderItem.order_no,
            order_type: '预售',
            platform: orderItem.platform,
            currency: orderItem.currency,
            deposit_amount: orderItem.gross_price,
            total_amount: orderItem.gross_price,
            target_account_name: orderItem.target_account,
            discount_note: orderItem.discount_note,
            items: orderItem.items,
          });
        }
        alert(`🚀 成功批量导入 ${parsedPreviewOrders.length} 笔预售定金主订单！`);
      } else {
        // Final payment binding batch
        for (const orderItem of parsedPreviewOrders) {
          const depIds = orderItem.deposit_ids || (orderItem.deposit_id ? [orderItem.deposit_id] : []);
          if (depIds.length > 0) {
            await apiClient.post('/sales/orders/bind-presale-final/', {
              deposit_order_ids: depIds,
              final_order_no: orderItem.order_no,
              final_net_amount: orderItem.gross_price,
              notes: '批量绑定尾款',
            });
          }
        }
        alert(`🔗 成功批量匹配并绑定 ${parsedPreviewOrders.length} 笔尾款订单，状态已激活为【待发货】！`);
      }

      setParsedPreviewOrders([]);
      setExcelFileName('');
      // Maintain EXPANDED state after submitting batch
      setIsCardExpanded(true);
      queryClient.invalidateQueries({ queryKey: ['presale-orders'] });
    } catch (err: any) {
      alert(`批量处理产生异常: ${err.response?.data?.error || err.message}`);
    } finally {
      setIsImporting(false);
    }
  };

  // Selection & Batch Actions
  const toggleSelectAll = () => {
    if (selectedOrderIds.length === filteredOrders.length) {
      setSelectedOrderIds([]);
    } else {
      setSelectedOrderIds(filteredOrders.map(o => o.id));
    }
  };

  const toggleSelectOrder = (id: number) => {
    if (selectedOrderIds.includes(id)) {
      setSelectedOrderIds(selectedOrderIds.filter(i => i !== id));
    } else {
      setSelectedOrderIds([...selectedOrderIds, id]);
    }
  };

  const handleBatchShip = async () => {
    if (!confirm(`确认将选中的 ${selectedOrderIds.length} 笔预售订单标记为【已发货】？`)) return;
    for (const id of selectedOrderIds) {
      await apiClient.patch(`/sales/orders/${id}/`, { status: '已发货' });
    }
    setSelectedOrderIds([]);
    queryClient.invalidateQueries({ queryKey: ['presale-orders'] });
  };

  const handleBatchComplete = async () => {
    if (!confirm(`确认将选中的 ${selectedOrderIds.length} 笔预售订单标记为【已完成对账】？`)) return;
    for (const id of selectedOrderIds) {
      await apiClient.patch(`/sales/orders/${id}/`, { status: '已完成' });
    }
    setSelectedOrderIds([]);
    queryClient.invalidateQueries({ queryKey: ['presale-orders'] });
  };

  // KPI Stat Cards: Dynamically calculated based on selected Product Filter (Matching Reflex PresaleState)
  const statTotal = presaleOrdersForStats.length;
  const statPendingDeposit = presaleOrdersForStats.filter(o => isDepositStatus(o.status, o)).length;
  const statPendingFinal = presaleOrdersForStats.filter(o => isFinalStatus(o.status, o)).length;
  const statPending = presaleOrdersForStats.filter(o => isPendingStatus(o.status)).length;
  const statShipped = presaleOrdersForStats.filter(o => isShippedStatus(o.status)).length;
  const statCompleted = presaleOrdersForStats.filter(o => isCompletedStatus(o.status)).length;

  // Filtered Orders for Table (Applies Status tab and Search query on top of presaleOrdersForStats)
  const filteredOrders = presaleOrdersForStats.filter(o => {
    if (!o) return false;

    // Status Tab Filter
    if (activeTab === 'deposit' && !isDepositStatus(o.status, o)) return false;
    if (activeTab === 'final' && !isFinalStatus(o.status, o)) return false;
    if (activeTab === 'pending' && !isPendingStatus(o.status)) return false;
    if (activeTab === 'shipped' && !isShippedStatus(o.status)) return false;
    if (activeTab === 'completed' && !isCompletedStatus(o.status)) return false;
    if (activeTab === 'after_sales' && !isAfterSalesStatus(o.status, o)) return false;

    // Search Query
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      const matchNo = String(o.order_no || '').toLowerCase().includes(q);
      const matchFinalNo = String(o.final_order_no || '').toLowerCase().includes(q);
      const matchPlat = String(o.platform || '').toLowerCase().includes(q);
      const matchNotes = String(o.notes || '').toLowerCase().includes(q);
      const matchItems = o.items?.some(i => i.product_name.toLowerCase().includes(q) || (i.variant || '').toLowerCase().includes(q));
      if (!matchNo && !matchFinalNo && !matchPlat && !matchNotes && !matchItems) return false;
    }

    return true;
  });

  // Pagination State & Reset
  const [pageIndex, setPageIndex] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  useEffect(() => {
    setPageIndex(1);
  }, [activeTab, searchQuery, productFilter]);

  const totalOrdersCount = filteredOrders.length;
  const totalPages = Math.max(1, Math.ceil(totalOrdersCount / pageSize));

  const paginatedOrders = React.useMemo(() => {
    const start = (pageIndex - 1) * pageSize;
    return filteredOrders.slice(start, start + pageSize);
  }, [filteredOrders, pageIndex, pageSize]);

  const startRow = totalOrdersCount === 0 ? 0 : (pageIndex - 1) * pageSize + 1;
  const endRow = Math.min(pageIndex * pageSize, totalOrdersCount);

  // Selected Amount Sum
  const selectedOrdersList = presaleOrdersForStats.filter(o => selectedOrderIds.includes(o.id));
  const jpyRate = ratesData?.JPY || 0.048;
  const selectedAmountSum = selectedOrdersList.reduce((sum, o) => {
    const dep = Number(o.deposit_amount) || 0;
    const fin = Number(o.final_amount) || 0;
    const total = dep + fin || Number(o.total_amount) || 0;
    return sum + (o.currency === 'JPY' ? total * jpyRate : total);
  }, 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="⏳ 预售销售管理"
        subtitle="支持定金购物车建单、尾款单号精确绑定、尾款一键物理解绑与分段预售履约"
        action={
          <div className="flex items-center gap-2">
            <button
              onClick={() => refetch()}
              className="px-3 py-1.5 bg-[#18202F] hover:bg-[#222C3E] text-slate-200 text-xs font-medium rounded-lg border border-[#2A3447] transition flex items-center gap-1.5"
            >
              <RefreshCw className="w-3.5 h-3.5 text-violet-400" />
              刷新数据
            </button>
          </div>
        }
      />

      {/* Top Collapsible Presale Creation & Binding Card (Defaults COLLAPSED on page load) */}
      <div className="bg-[#131924]/90 backdrop-blur-xl border border-[#2A3447] rounded-2xl p-5 space-y-4 shadow-xl">
        <div className="flex items-center justify-between border-b border-[#2A3447] pb-3">
          <div className="flex items-center gap-4">
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <span className="p-1.5 bg-violet-600/20 text-violet-400 rounded-lg">➕</span>
              创建预售单据 / 绑定尾款
            </h3>
            <div className="flex gap-2 text-xs font-semibold">
              <button
                onClick={() => { setTopTab('create'); setIsCardExpanded(true); }}
                className={`px-3 py-1 rounded-lg transition ${
                  topTab === 'create'
                    ? 'bg-violet-600/20 text-violet-300 border border-violet-500/40 font-bold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                ➕ 创建预售单据 / 绑定尾款
              </button>
              <button
                onClick={() => { setTopTab('bulk'); setIsCardExpanded(true); }}
                className={`px-3 py-1 rounded-lg transition ${
                  topTab === 'bulk'
                    ? 'bg-violet-600/20 text-violet-300 border border-violet-500/40 font-bold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                📥 批量导入预售 (Excel)
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
            {topTab === 'create' && (
              <div className="space-y-4">
                {/* Mode Switcher */}
                <div className="grid grid-cols-2 p-1 bg-[#0B0F17] rounded-xl border border-[#2A3447] text-xs font-bold">
                  <button
                    type="button"
                    onClick={() => setCreateMode('deposit')}
                    className={`py-2 rounded-lg transition ${
                      createMode === 'deposit'
                        ? 'bg-violet-600 text-white shadow-md'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    1️⃣ 创建主定金订单
                  </button>
                  <button
                    type="button"
                    onClick={() => setCreateMode('final')}
                    className={`py-2 rounded-lg transition ${
                      createMode === 'final'
                        ? 'bg-violet-600 text-white shadow-md'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    2️⃣ 绑定尾款单
                  </button>
                </div>

                {/* Mode 1: Create Deposit Order Form */}
                {createMode === 'deposit' && (
                  <form onSubmit={handleCreateDepositSubmit} className="space-y-4 text-xs">
                    {formError && (
                      <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-400 text-xs">
                        {formError}
                      </div>
                    )}

                    <h4 className="font-bold text-slate-200 text-xs">1. 定金基础信息</h4>
                    <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
                      <FormField label="定金单号" required>
                        <input
                          type="text"
                          required
                          value={orderNo}
                          onChange={(e) => setOrderNo(e.target.value)}
                          className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100 font-mono"
                        />
                      </FormField>

                      <FormField label="下单日期">
                        <input
                          type="date"
                          value={orderDate}
                          onChange={(e) => setOrderDate(e.target.value)}
                          className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100 font-mono"
                        />
                      </FormField>

                      <FormField label="销售平台">
                        <select
                          value={platform}
                          onChange={(e) => setPlatform(e.target.value)}
                          className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100"
                        >
                          <option value="预售平台">预售平台</option>
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
                          value={currency}
                          onChange={(e) => setCurrency(e.target.value)}
                          className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100 font-mono"
                        >
                          <option value="CNY">CNY (¥)</option>
                          <option value="JPY">JPY (￥)</option>
                        </select>
                      </FormField>

                      <FormField label="收款现金账户 (仅限现金账户)">
                        <select
                          value={targetAccountName}
                          onChange={(e) => setTargetAccountName(e.target.value)}
                          className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100"
                        >
                          {cashAccounts.map((a: any) => (
                            <option key={a.id} value={a.name}>{a.name} [{a.currency}]</option>
                          ))}
                        </select>
                      </FormField>
                    </div>

                    <h4 className="font-bold text-slate-200 text-xs pt-2 border-t border-[#2A3447]">2. 定金商品清单</h4>
                    <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end p-3 bg-[#0B0F17] rounded-xl border border-[#2A3447]">
                      <div className="md:col-span-4">
                        <label className="text-[11px] text-slate-400 block mb-1">选择商品 SPU</label>
                        <select
                          value={tempProdId}
                          onChange={(e) => {
                            const id = e.target.value ? Number(e.target.value) : '';
                            setTempProdId(id);
                            const pObj = products.find(p => p.id === id);
                            if (pObj && pObj.colors && pObj.colors.length > 0) {
                              setTempVariant(pObj.colors[0].color_name);
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
                          const selProd = products.find(p => p.id === tempProdId);
                          const colorList = selProd?.colors || [];
                          if (colorList.length > 0) {
                            return (
                              <select
                                value={tempVariant}
                                onChange={(e) => setTempVariant(e.target.value)}
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
                              placeholder="款式 (如: 藏青色/M)"
                              value={tempVariant}
                              onChange={(e) => setTempVariant(e.target.value)}
                              className="w-full bg-[#131924] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100"
                            />
                          );
                        })()}
                      </div>

                      <div className="md:col-span-2">
                        <label className="text-[11px] text-slate-400 block mb-1">数量</label>
                        <input
                          type="number"
                          value={tempQty}
                          onChange={(e) => setTempQty(parseInt(e.target.value) || 1)}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100 font-mono"
                        />
                      </div>

                      <div className="md:col-span-2">
                        <label className="text-[11px] text-slate-400 block mb-1">预售仓</label>
                        <select
                          value={tempWarehouseId}
                          onChange={(e) => setTempWarehouseId(e.target.value ? Number(e.target.value) : '')}
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
                          加进清单
                        </button>
                      </div>
                    </div>

                    {cart.length > 0 && (
                      <div className="p-3 bg-[#0B0F17] rounded-xl border border-[#2A3447] space-y-2">
                        <div className="text-[11px] text-slate-400 font-bold">已录入的商品清单：</div>
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
                            {cart.map(c => (
                              <tr key={c.id}>
                                <td className="py-1.5 px-2 font-bold text-slate-200">{c.productName}</td>
                                <td className="py-1.5 px-2 text-violet-300">{c.variant}</td>
                                <td className="py-1.5 px-2 text-slate-400">{c.warehouseName || '未分配'}</td>
                                <td className="py-1.5 px-2 text-center font-mono font-bold text-slate-100">{c.quantity}</td>
                                <td className="py-1.5 px-2 text-center">
                                  <button
                                    type="button"
                                    onClick={() => setCart(cart.filter(i => i.id !== c.id))}
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

                    <h4 className="font-bold text-slate-200 text-xs pt-2 border-t border-[#2A3447]">3. 结算提交</h4>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <FormField label="预售定金总价 (¥)" required>
                        <input
                          type="number"
                          step="0.01"
                          placeholder="0.00"
                          value={depositPrice}
                          onChange={(e) => setDepositPrice(e.target.value ? parseFloat(e.target.value) : '')}
                          className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100 font-mono font-bold text-emerald-400"
                        />
                      </FormField>

                      <FormField label="优惠说明 (选填)">
                        <input
                          type="text"
                          placeholder="如：减5元 / 包邮"
                          value={discountNote}
                          onChange={(e) => setDiscountNote(e.target.value)}
                          className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100"
                        />
                      </FormField>

                      <FormField label="备注">
                        <input
                          type="text"
                          placeholder="输入定金单备注信息..."
                          value={notes}
                          onChange={(e) => setNotes(e.target.value)}
                          className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100"
                        />
                      </FormField>
                    </div>

                    <button
                      type="submit"
                      disabled={createPresaleOrderMutation.isPending || cart.length === 0}
                      className="w-full py-3 bg-violet-600 hover:bg-violet-500 text-white font-bold rounded-xl shadow-lg shadow-violet-500/25 transition text-xs disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                      <Rocket className="w-4 h-4" />
                      {createPresaleOrderMutation.isPending ? '提交中...' : '🚀 创建定金主订单'}
                    </button>
                  </form>
                )}

                {/* Mode 2: Bind Final Payment Form */}
                {createMode === 'final' && (
                  <div className="space-y-4 text-xs">
                    <h4 className="font-bold text-slate-200">🔗 检索并添加关联的预售定金单 (支持多单合并绑定)</h4>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        placeholder="请输入原始预售定金单号 (例如 PRE-123456)..."
                        value={searchDepNo}
                        onChange={(e) => setSearchDepNo(e.target.value)}
                        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleSearchDepositOrder(); } }}
                        className="flex-1 bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100 font-mono"
                      />
                      <button
                        type="button"
                        onClick={handleSearchDepositOrder}
                        className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white font-bold rounded-xl transition flex items-center gap-1.5"
                      >
                        <Search className="w-4 h-4" />
                        查找并添加定金单
                      </button>
                    </div>

                    {bindMsg.text && (
                      <div className={`p-3 rounded-xl border text-xs ${bindMsg.isError ? 'bg-rose-500/10 border-rose-500/30 text-rose-400' : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'}`}>
                        {bindMsg.text}
                      </div>
                    )}

                    {selectedDepositOrders.length > 0 && (
                      <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-xl space-y-4">
                        <div className="flex items-center justify-between text-emerald-400 font-bold border-b border-emerald-500/20 pb-2">
                          <span>✅ 已绑定 {selectedDepositOrders.length} 个定金单据</span>
                          <span>累计定金金额: {selectedDepositOrders.reduce((sum, o) => sum + (Number(o.deposit_amount) || 0), 0).toFixed(2)}</span>
                        </div>

                        {/* Selected Deposit Orders List */}
                        <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                          {selectedDepositOrders.map(dep => (
                            <div key={dep.id} className="p-2.5 bg-[#0B0F17] rounded-xl border border-[#2A3447] flex items-center justify-between text-xs gap-2">
                              <div className="flex-1 min-w-0">
                                <div className="font-bold text-violet-300 font-mono flex items-center gap-2">
                                  <span>#{dep.order_no}</span>
                                  <span className="text-[10px] text-slate-400 font-sans">({dep.platform} | {dep.currency})</span>
                                </div>
                                <div className="text-[10px] text-slate-400 truncate">
                                  明细: {(dep.items || []).map(i => `${i.product_name}-${i.variant} ×${i.quantity}`).join(', ')}
                                </div>
                              </div>
                              <div className="flex items-center gap-3">
                                <span className="font-mono font-bold text-emerald-400 text-xs">
                                  {dep.currency === 'JPY' ? '￥' : '¥'}{(Number(dep.deposit_amount) || 0).toFixed(2)}
                                </span>
                                <button
                                  type="button"
                                  onClick={() => setSelectedDepositOrders(prev => prev.filter(o => o.id !== dep.id))}
                                  className="p-1 text-slate-500 hover:text-rose-400 transition"
                                  title="移除此定金单"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>

                        <form onSubmit={handleBindFinalSubmit} className="space-y-4 pt-3 border-t border-emerald-500/20">
                          <h4 className="font-bold text-slate-200">录入尾款订单信息并触发合并发货</h4>
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                            <FormField label="尾款订单号" required>
                              <input
                                type="text"
                                required
                                placeholder="输入尾款单号 (如 FIN-123456)"
                                value={finalOrderNo}
                                onChange={(e) => setFinalOrderNo(e.target.value)}
                                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100 font-mono"
                              />
                            </FormField>

                            <FormField label="尾款实际支付金额 (¥)" required>
                              <input
                                type="number"
                                step="0.01"
                                required
                                placeholder="0.00"
                                value={finalAmount}
                                onChange={(e) => setFinalAmount(e.target.value ? parseFloat(e.target.value) : '')}
                                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100 font-mono font-bold text-emerald-400"
                              />
                            </FormField>

                            <FormField label="尾款收款现金账户 (仅限现金账户)">
                              <select
                                value={finalTargetAccount}
                                onChange={(e) => setFinalTargetAccount(e.target.value)}
                                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100"
                              >
                                {cashAccounts.map((a: any) => (
                                  <option key={a.id} value={a.name}>{a.name} [{a.currency}]</option>
                                ))}
                              </select>
                            </FormField>
                          </div>

                          <button
                            type="submit"
                            className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-xl shadow-lg shadow-emerald-600/20 transition flex items-center justify-center gap-2"
                          >
                            <LinkIcon className="w-4 h-4" />
                            🔗 确认绑定尾款并更新定金单为【待发货】
                          </button>
                        </form>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {topTab === 'bulk' && (
              <div className="space-y-4 text-xs">
                {/* Mode Switcher for Presale Excel Bulk Import */}
                <div className="grid grid-cols-2 p-1 bg-[#0B0F17] rounded-xl border border-[#2A3447] text-xs font-bold">
                  <button
                    type="button"
                    onClick={() => { setBulkPresaleMode('deposit'); setParsedPreviewOrders([]); setExcelErrors([]); }}
                    className={`py-2 rounded-lg transition ${
                      bulkPresaleMode === 'deposit'
                        ? 'bg-violet-600 text-white shadow-md'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    🚀 批量导入定金
                  </button>
                  <button
                    type="button"
                    onClick={() => { setBulkPresaleMode('final'); setParsedPreviewOrders([]); setExcelErrors([]); }}
                    className={`py-2 rounded-lg transition ${
                      bulkPresaleMode === 'final'
                        ? 'bg-violet-600 text-white shadow-md'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    🔗 批量匹配并绑定尾款
                  </button>
                </div>

                <div className="p-3 bg-violet-600/10 border border-violet-500/30 rounded-xl flex items-center gap-2 text-violet-300 text-xs">
                  <FileSpreadsheet className="w-4 h-4 shrink-0 text-violet-400" />
                  <span>
                    {bulkPresaleMode === 'deposit'
                      ? '📋 定金导入列：订单号 | 商品名 | 商品型号 | 数量 | 销售平台 | 订单总额 | 币种 | 出货仓库 | 优惠'
                      : '📋 尾款绑定列：订单号 | 关联定金单号 | 商品名 | 商品型号 | 数量 | 销售平台 | 订单总额 | 币种 | 出货仓库'}
                  </span>
                </div>

                <div className="p-6 border-2 border-dashed border-[#2A3447] hover:border-violet-500/50 rounded-xl bg-[#0B0F17] text-center space-y-2 transition">
                  <Upload className="w-8 h-8 text-violet-400 mx-auto animate-bounce" />
                  <p className="font-bold text-slate-200">选择或拖拽预售 Excel 数据表到此处</p>
                  <p className="text-slate-500 text-[11px]">支持 .xlsx, .xls, .csv 格式</p>
                  <input
                    type="file"
                    accept=".xlsx, .xls, .csv"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) parsePresaleExcel(file);
                    }}
                    className="hidden"
                    id="presale-excel-file-input"
                  />
                  <label
                    htmlFor="presale-excel-file-input"
                    className="inline-block px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white font-bold rounded-xl cursor-pointer transition shadow-md"
                  >
                    上传预售 Excel 数据表
                  </label>
                  {excelFileName && (
                    <div className="pt-2 text-violet-400 font-mono font-bold">📁 {excelFileName}</div>
                  )}
                </div>

                {/* Excel Errors Output */}
                {excelErrors.length > 0 && (
                  <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl space-y-1 text-rose-400">
                    <div className="font-bold flex items-center gap-1.5">
                      <AlertTriangle className="w-4 h-4" />
                      <span>❌ Excel 校验发现以下异常错误：</span>
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
                        ✅ 数据校验成功！Excel 数据预览 ({parsedPreviewOrders.length} 笔)：
                      </span>
                      <button
                        type="button"
                        onClick={handlePresaleBatchImportSubmit}
                        disabled={isImporting}
                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-xl transition shadow-lg shadow-emerald-600/20 flex items-center gap-1.5"
                      >
                        <Rocket className="w-4 h-4" />
                        {isImporting ? '处理中...' : `🚀 立即开始批量处理 (${bulkPresaleMode === 'deposit' ? '批量导入定金' : '批量匹配绑定尾款'})`}
                      </button>
                    </div>

                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs bg-[#0B0F17] rounded-xl border border-[#2A3447]">
                        <thead>
                          <tr className="border-b border-[#2A3447] text-slate-400 text-[10px] uppercase">
                            <th className="py-2 px-3">{bulkPresaleMode === 'deposit' ? '状态盘点' : '匹配状态'}</th>
                            <th className="py-2 px-3">{bulkPresaleMode === 'deposit' ? '定金订单号' : '尾款订单号'}</th>
                            {bulkPresaleMode === 'final' && <th className="py-2 px-3">关联定金单号</th>}
                            <th className="py-2 px-3">平台</th>
                            <th className="py-2 px-3">收款账户</th>
                            <th className="py-2 px-3">币种</th>
                            <th className="py-2 px-3 text-center">数量</th>
                            <th className="py-2 px-3 text-right">订单金额</th>
                            <th className="py-2 px-3 text-right">预估手续费</th>
                            <th className="py-2 px-3 text-right">净入账</th>
                            {bulkPresaleMode === 'deposit' && <th className="py-2 px-3">优惠说明</th>}
                            <th className="py-2 px-3">商品明细</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#2A3447]">
                          {parsedPreviewOrders.map((p, idx) => (
                            <tr key={idx}>
                              <td className="py-2 px-3 font-bold text-emerald-400">{p.stock_warning || p.match_status}</td>
                              <td className="py-2 px-3 font-mono font-bold text-slate-100">{p.order_no}</td>
                              {bulkPresaleMode === 'final' && <td className="py-2 px-3 font-mono font-bold text-violet-300">{p.dep_order_no}</td>}
                              <td className="py-2 px-3 text-slate-300">{p.platform}</td>
                              <td className="py-2 px-3 text-violet-300">{p.target_account}</td>
                              <td className="py-2 px-3 font-mono text-slate-400">{p.currency}</td>
                              <td className="py-2 px-3 text-center font-mono font-bold text-slate-100">{p.total_qty}</td>
                              <td className="py-2 px-3 text-right font-mono font-bold text-slate-200">¥{p.gross_price}</td>
                              <td className="py-2 px-3 text-right font-mono text-slate-400">¥{p.fee}</td>
                              <td className="py-2 px-3 text-right font-mono font-bold text-emerald-400">¥{p.net_price}</td>
                              {bulkPresaleMode === 'deposit' && <td className="py-2 px-3 text-slate-400">{p.discount_note}</td>}
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

      {/* 6 KPI Stat Cards (Dynamically Linked to Product Filter, Matching Reflex PresaleState) */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <StatCard
          label="总预售单数"
          value={statTotal}
          unit="笔"
          icon={Layers}
          colorScheme="violet"
          borderLeft
        />
        <StatCard
          label="待确认定金"
          value={statPendingDeposit}
          unit="笔"
          icon={Clock}
          colorScheme="amber"
          borderLeft
        />
        <StatCard
          label="待付尾款"
          value={statPendingFinal}
          unit="笔"
          icon={ShoppingBasket}
          colorScheme="blue"
          borderLeft
        />
        <StatCard
          label="待发货(已绑尾)"
          value={statPending}
          unit="笔"
          icon={PackageCheck}
          colorScheme="purple"
          borderLeft
        />
        <StatCard
          label="已发货 (物理扣存)"
          value={statShipped}
          unit="笔"
          icon={Truck}
          colorScheme="indigo"
          borderLeft
        />
        <StatCard
          label="已完成对账结算"
          value={statCompleted}
          unit="笔"
          icon={CheckCircle2}
          colorScheme="emerald"
          borderLeft
        />
      </div>

      {/* Main Presale Orders DataCard */}
      <DataCard title="📋 预售订单管理列表">
        <div className="space-y-4">
          {/* Status Filter Tabs (7 Tabs matching Reflex) */}
          <div className="flex border-b border-[#2A3447] text-xs font-semibold overflow-x-auto gap-2">
            {[
              { key: 'all', label: '全部' },
              { key: 'deposit', label: '待确认定金' },
              { key: 'final', label: '待付尾款' },
              { key: 'pending', label: '待发货(已绑尾)' },
              { key: 'shipped', label: '已发货' },
              { key: 'completed', label: '已完成' },
              { key: 'after_sales', label: '售后中' },
            ].map(tab => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key as any)}
                className={`px-3 py-2 border-b-2 transition whitespace-nowrap ${
                  activeTab === tab.key
                    ? 'border-violet-500 text-violet-400 font-bold'
                    : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Search Input */}
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
            <input
              type="text"
              placeholder="🔍 输入订单号、尾款单号、平台、备注、状态、款式或商品明细筛选..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl pl-9 pr-4 py-2 text-xs text-slate-100"
            />
          </div>

          {/* Batch Selection Bar */}
          <div className="flex items-center justify-between bg-[#0B0F17] p-2.5 rounded-xl border border-[#2A3447] text-xs">
            <div className="flex items-center gap-3">
              <button
                onClick={toggleSelectAll}
                className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs transition"
              >
                ☑️ 全选
              </button>
              <span className="text-slate-400">已选中 <strong className="text-violet-400">{selectedOrderIds.length}</strong> 项订单</span>
            </div>
            <div className="text-xs font-mono">
              <span className="text-slate-400">已选定金+尾款合计: </span>
              <span className="font-bold text-rose-400">¥{selectedAmountSum.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}</span>
            </div>
          </div>

          {/* Table */}
          {isLoading ? (
            <div className="text-center py-8 text-slate-400 text-xs">加载预售订单中...</div>
          ) : filteredOrders.length === 0 ? (
            <div className="text-center py-12 text-slate-500 text-xs bg-[#0B0F17] rounded-xl border border-[#2A3447]">
              该筛选分类下无对应的预售销售订单记录数据
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#2A3447] text-slate-400 text-[11px] uppercase">
                    <th className="py-3 px-3 w-10 text-center">选择</th>
                    <th className="py-3 px-3">定金订单号</th>
                    <th className="py-3 px-3">尾款订单号</th>
                    <th className="py-3 px-3">状态</th>
                    <th className="py-3 px-3">商品明细</th>
                    <th className="py-3 px-3 text-right">定金金额</th>
                    <th className="py-3 px-3 text-right">尾款金额</th>
                    <th className="py-3 px-3 text-right">已退款</th>
                    <th className="py-3 px-3">优惠</th>
                    <th className="py-3 px-3">平台</th>
                    <th className="py-3 px-3">日期</th>
                    <th className="py-3 px-3">备注</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#2A3447]/40">
                  {paginatedOrders.map(o => {
                    const isSelected = selectedOrderIds.includes(o.id);
                    const itemsSummary = o.items && o.items.length > 0
                      ? o.items.map(i => `${i.product_name}-${i.variant}×${i.quantity}`).join(', ')
                      : '无明细';
                    const refundedTotal = o.refunds?.reduce((sum, r) => sum + r.refund_amount, 0) || 0;

                    return (
                      <tr
                        key={o.id}
                        onClick={() => toggleSelectOrder(o.id)}
                        className={`transition cursor-pointer ${
                          isSelected ? 'bg-violet-600/10' : 'hover:bg-[#131924]/60'
                        }`}
                      >
                        <td className="py-3 px-3 text-center" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelectOrder(o.id)}
                            className="rounded border-slate-700 text-violet-600 focus:ring-0"
                          />
                        </td>
                        <td className="py-3 px-3 font-mono font-bold text-slate-100">{o.order_no}</td>
                        <td className="py-3 px-3 font-mono font-bold text-violet-300">{o.final_order_no || '-'}</td>
                        <td className="py-3 px-3">
                          <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium border ${
                            isShippedStatus(o.status)
                              ? 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30'
                              : isCompletedStatus(o.status)
                              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                              : isDepositStatus(o.status, o)
                              ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                              : 'bg-violet-500/10 text-violet-300 border-violet-500/30'
                          }`}>
                            {o.status || '待发货'}
                          </span>
                        </td>
                        <td className="py-3 px-3 text-slate-300 truncate max-w-xs">{itemsSummary}</td>
                        <td className="py-3 px-3 text-right font-mono font-semibold text-emerald-400">
                          {o.currency === 'JPY' ? `${o.deposit_amount || 0} JPY` : `¥${(o.deposit_amount || 0).toFixed(2)}`}
                        </td>
                        <td className="py-3 px-3 text-right font-mono font-semibold text-violet-300">
                          {o.currency === 'JPY' ? `${o.final_amount || 0} JPY` : `¥${(o.final_amount || 0).toFixed(2)}`}
                        </td>
                        <td className={`py-3 px-3 text-right font-mono ${refundedTotal > 0 ? 'text-rose-400 font-bold' : 'text-slate-500'}`}>
                          {refundedTotal > 0 ? `¥${refundedTotal.toFixed(2)}` : '-'}
                        </td>
                        <td className="py-3 px-3 text-slate-400 text-[11px]">{o.discount_note || '-'}</td>
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

          {/* Pagination Controls Bar */}
          {totalOrdersCount > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-3 bg-[#0B0F17] p-3 rounded-xl border border-[#2A3447] text-xs">
              <div className="flex items-center gap-3 text-slate-400">
                <span>显示 <strong className="text-slate-200">{startRow}</strong> - <strong className="text-slate-200">{endRow}</strong> 条，共 <strong className="text-violet-400">{totalOrdersCount}</strong> 条订单</span>
                <div className="flex items-center gap-1.5">
                  <span>每页显示:</span>
                  <select
                    value={pageSize}
                    onChange={(e) => {
                      setPageSize(Number(e.target.value));
                      setPageIndex(1);
                    }}
                    className="bg-[#131924] border border-[#2A3447] rounded-lg px-2 py-1 text-slate-200 focus:outline-none focus:border-violet-500 font-mono"
                  >
                    <option value={20}>20 条/页</option>
                    <option value={50}>50 条/页</option>
                    <option value={100}>100 条/页</option>
                  </select>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setPageIndex(prev => Math.max(1, prev - 1))}
                  disabled={pageIndex <= 1}
                  className="px-3 py-1.5 bg-[#18202F] hover:bg-[#222C3E] disabled:opacity-30 disabled:hover:bg-[#18202F] text-slate-200 rounded-lg border border-[#2A3447] font-medium transition"
                >
                  ‹ 上一页
                </button>
                <span className="text-slate-400 font-mono px-2">
                  第 <strong className="text-violet-400">{pageIndex}</strong> / {totalPages} 页
                </span>
                <button
                  type="button"
                  onClick={() => setPageIndex(prev => Math.min(totalPages, prev + 1))}
                  disabled={pageIndex >= totalPages}
                  className="px-3 py-1.5 bg-[#18202F] hover:bg-[#222C3E] disabled:opacity-30 disabled:hover:bg-[#18202F] text-slate-200 rounded-lg border border-[#2A3447] font-medium transition"
                >
                  下一页 ›
                </button>
              </div>
            </div>
          )}

          {/* Action Bar */}
          <div className="flex flex-wrap items-center gap-2 pt-3 border-t border-[#2A3447]">
            <button
              onClick={() => handleBatchShip()}
              disabled={selectedOrderIds.length === 0}
              className="px-3 py-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5 shadow-md shadow-amber-600/20"
            >
              <Package className="w-3.5 h-3.5" />
              📦 发货 ({selectedOrderIds.length})
            </button>

            <button
              onClick={() => setIsBatchWhOpen(true)}
              disabled={selectedOrderIds.length === 0}
              className="px-3 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5 shadow-md shadow-violet-600/20"
            >
              <Building2 className="w-3.5 h-3.5" />
              🏭 批量修改发货仓库 ({selectedOrderIds.length})
            </button>

            <button
              onClick={() => handleBatchComplete()}
              disabled={selectedOrderIds.length === 0}
              className="px-3 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5 shadow-md shadow-emerald-600/20"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              ✅ 收尾款完成对账 ({selectedOrderIds.length})
            </button>

            <button
              onClick={() => {
                if (selectedOrderIds.length === 1) {
                  const target = presaleOrdersForStats.find(o => o.id === selectedOrderIds[0]);
                  if (target) {
                    setRefundOrder(target);
                    setRefundAmount(target.total_amount || 0);
                  }
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
                  const target = presaleOrdersForStats.find(o => o.id === selectedOrderIds[0]);
                  if (target) setDetailOrder(target);
                } else {
                  alert('请选择单笔订单查看详情');
                }
              }}
              disabled={selectedOrderIds.length !== 1}
              className="px-3 py-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 text-slate-200 rounded-xl text-xs font-semibold transition flex items-center gap-1.5"
            >
              <Edit2 className="w-3.5 h-3.5" />
              ✏️ 查看/编辑详情
            </button>
          </div>
        </div>
      </DataCard>

      {/* Batch Warehouse Assignment Modal */}
      <Modal
        isOpen={isBatchWhOpen}
        onClose={() => setIsBatchWhOpen(false)}
        title="🏭 批量修改发货仓库"
      >
        <div className="space-y-4 text-xs">
          <p className="text-slate-300">
            当前共选中了 <strong className="text-violet-400">{selectedOrderIds.length}</strong> 项预售订单。请选择统一修改的目标出货仓库：
          </p>

          <FormField label="目标发货仓库">
            <select
              value={batchWarehouseId}
              onChange={(e) => setBatchWarehouseId(e.target.value ? Number(e.target.value) : '')}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100"
            >
              <option value="">-- 选择目标发货仓库 --</option>
              {warehouses.map(w => (
                <option key={w.id} value={w.id}>{w.name}</option>
              ))}
            </select>
          </FormField>

          <div className="flex justify-end gap-2 pt-2 border-t border-[#2A3447]">
            <button
              type="button"
              onClick={() => setIsBatchWhOpen(false)}
              className="px-4 py-2 bg-slate-800 text-slate-300 rounded-xl"
            >
              取消
            </button>
            <button
              type="button"
              onClick={async () => {
                if (!batchWarehouseId) {
                  alert('请选择目标发货仓库');
                  return;
                }
                const whObj = warehouses.find(w => w.id === batchWarehouseId);
                for (const oId of selectedOrderIds) {
                  const targetOrder = presaleOrdersForStats.find(o => o.id === oId);
                  if (targetOrder && targetOrder.items) {
                    await apiClient.patch(`/sales/orders/${oId}/`, {
                      items: targetOrder.items.map(i => ({
                        ...i,
                        warehouse_id: batchWarehouseId
                      }))
                    });
                  }
                }
                setIsBatchWhOpen(false);
                setSelectedOrderIds([]);
                queryClient.invalidateQueries({ queryKey: ['presale-orders'] });
                alert(`✅ 已批量更新 ${selectedOrderIds.length} 笔订单的发货仓库为【${whObj?.name}】`);
              }}
              className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white font-bold rounded-xl"
            >
              💾 确认批量修改
            </button>
          </div>
        </div>
      </Modal>

      {/* Order Detail Modal */}
      {detailOrder && (
        <Modal
          isOpen={!!detailOrder}
          onClose={() => setDetailOrder(null)}
          title={`📄 预售订单详情 #${detailOrder.order_no}`}
        >
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 gap-3 p-3 bg-[#0B0F17] rounded-xl border border-[#2A3447]">
              <div>定金单号: <strong className="font-mono text-slate-100">{detailOrder.order_no}</strong></div>
              <div>尾款单号: <strong className="font-mono text-violet-300">{detailOrder.final_order_no || '-'}</strong></div>
              <div>销售平台: <span className="text-slate-200">{detailOrder.platform}</span></div>
              <div>当前状态: <span className="text-emerald-400 font-bold">{detailOrder.status}</span></div>
              <div>定金金额: <span className="font-mono text-emerald-400 font-bold">¥{detailOrder.deposit_amount || 0}</span></div>
              <div>尾款金额: <span className="font-mono text-violet-300 font-bold">¥{detailOrder.final_amount || 0}</span></div>
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
                  if (confirm(`确认删除预售订单 #${detailOrder.order_no}？`)) {
                    await apiClient.delete(`/sales/orders/${detailOrder.id}/`);
                    setDetailOrder(null);
                    queryClient.invalidateQueries({ queryKey: ['presale-orders'] });
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
      {refundOrder && (
        <Modal
          isOpen={!!refundOrder}
          onClose={() => setRefundOrder(null)}
          title={`🔧 售后处理 #${refundOrder.order_no}`}
        >
          <div className="space-y-4 text-xs">
            <FormField label="退款金额 (¥)">
              <input
                type="number"
                step="0.01"
                value={refundAmount}
                onChange={(e) => setRefundAmount(e.target.value ? parseFloat(e.target.value) : '')}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100 font-mono font-bold text-rose-400"
              />
            </FormField>

            <FormField label="退款/售后原因">
              <input
                type="text"
                placeholder="例如: 客户退货 / 质量问题退款"
                value={refundReason}
                onChange={(e) => setRefundReason(e.target.value)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl px-3 py-2 text-slate-100"
              />
            </FormField>

            <div className="flex justify-end gap-2 pt-2 border-t border-[#2A3447]">
              <button
                type="button"
                onClick={() => setRefundOrder(null)}
                className="px-4 py-2 bg-slate-800 text-slate-300 rounded-xl"
              >
                取消
              </button>
              <button
                type="button"
                onClick={async () => {
                  if (!refundAmount || Number(refundAmount) <= 0) {
                    alert('请输入有效退款金额');
                    return;
                  }
                  await apiClient.patch(`/sales/orders/${refundOrder.id}/`, {
                    status: '售后中',
                  });
                  setRefundOrder(null);
                  queryClient.invalidateQueries({ queryKey: ['presale-orders'] });
                  alert('✅ 售后记录与退款提交成功！');
                }}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white font-bold rounded-xl shadow-lg shadow-rose-600/20"
              >
                确认提交售后退款
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};

export default PresalePage;
