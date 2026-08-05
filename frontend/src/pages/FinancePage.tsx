// frontend/src/pages/FinancePage.tsx
import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { CompanyBalanceItem, Product } from '../types';
import { Modal } from '../components/ui/Modal';
import { StatCard } from '../components/ui/StatCard';
import { DataCard } from '../components/ui/DataCard';
import { FormField } from '../components/ui/FormField';
import { PageHeader } from '../components/ui/PageHeader';
import {
  Plus,
  Search,
  ArrowUpRight,
  ArrowDownRight,
  Trash2,
  Edit2,
  TrendingUp,
  RefreshCw,
  Repeat,
  Info,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  CheckCircle2,
  Save,
  PlusCircle,
  XCircle,
  Coins
} from 'lucide-react';

const CATS_INCOME = ["销售收入", "退款", "投资", "现有资产增加", "其他资产增加", "新资产增加", "其他现金收入"];
const CATS_EXPENSE = ["商品成本", "商品成本待付款", "固定资产购入", "其他资产购入", "其他待付款", "撤资", "分红", "现有资产减少", "公司经营费用", "其他"];
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
const ASSET_SUB_CATEGORIES = ["包装材", "无实体", "备用素材", "其他", "商品周边", "办公用品"];
const NON_CASH_CATEGORIES = new Set(["现有资产增加", "新资产增加", "现有资产减少", "其他资产增加"]);

interface BatchItem {
  key: string;
  name: string;
  amount: number;
  qty: number;
  desc: string;
  url: string;
}

interface ProcessedRecord {
  id: number;
  date: string;
  currency: string;
  type: string;
  amount: number;
  category: string;
  description: string;
  url: string;
  cny_bal: number;
  jpy_bal: number;
  account_id?: number;
  related_item_id?: number;
}

export const FinancePage: React.FC = () => {
  const queryClient = useQueryClient();

  // 分页与筛选 State
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterCategory, setFilterCategory] = useState('');

  // 核心业务大类 Tab Header: 支出 / 收入 / 货币兑换 / 债务 / 资金移动
  const [recType, setRecType] = useState<'支出' | '收入' | '货币兑换' | '债务' | '资金移动'>('支出');

  // 通用表单 State
  const [recDate, setRecDate] = useState(new Date().toISOString().split('T')[0]);
  const [recCategory, setRecCategory] = useState('商品成本');
  const [recAmount, setRecAmount] = useState<number | ''>('');
  const [recCurrency, setRecCurrency] = useState('CNY');
  const [recShop, setRecShop] = useState('');
  const [recUrl, setRecUrl] = useState('');
  const [recDesc, setRecDesc] = useState('');
  const [accountId, setAccountId] = useState<number | ''>('');
  const [formError, setFormError] = useState('');

  // 货币兑换 State
  const [exSourceCurr, setExSourceCurr] = useState('CNY');
  const [exTargetCurr, setExTargetCurr] = useState('JPY');
  const [exSourceAccId, setExSourceAccId] = useState<number | ''>('');
  const [exTargetAccId, setExTargetAccId] = useState<number | ''>('');
  const [exAmountOut, setExAmountOut] = useState<number | ''>('');
  const [exAmountIn, setExAmountIn] = useState<number | ''>('');
  const [exDesc, setExDesc] = useState('');

  // 债务管理 State
  const [debtOp, setDebtOp] = useState<'➕ 新增债务' | '💸 偿还债务'>('➕ 新增债务');
  const [debtName, setDebtName] = useState('');
  const [debtDest, setDebtDest] = useState<'存入流动资金 (拿到现金)' | '新增资产项 (形成实物/挂账资产)'>('存入流动资金 (拿到现金)');
  const [debtRelContent, setDebtRelContent] = useState('');
  const [debtAmount, setDebtAmount] = useState<number | ''>('');
  const [debtCurr, setDebtCurr] = useState('CNY');
  const [debtTargetAccId, setDebtTargetAccId] = useState<number | ''>('');
  const [debtSource, setDebtSource] = useState('');
  const [debtRemark, setDebtRemark] = useState('');
  // 偿还债务
  const [debtSelectedId, setDebtSelectedId] = useState<number | ''>('');
  const [debtRepayType, setDebtRepayType] = useState<'💸 资金还款' | '🔄 资产抵消'>('💸 资金还款');
  const [debtRepayAmount, setDebtRepayAmount] = useState<number | ''>('');
  const [debtRepaySourceAccId, setDebtRepaySourceAccId] = useState<number | ''>('');
  const [debtRepayOffsetAssetId, setDebtRepayOffsetAssetId] = useState<number | ''>('');
  const [debtRepayRemark, setDebtRepayRemark] = useState('');

  // 资金移动 State
  const [moveFromAssetId, setMoveFromAssetId] = useState<number | ''>('');
  const [moveToAssetId, setMoveToAssetId] = useState<number | ''>('');
  const [moveAmount, setMoveAmount] = useState<number | ''>('');
  const [moveDesc, setMoveDesc] = useState('');

  // 批量购入 & 商品成本 State
  const [batchProductId, setBatchProductId] = useState<number | ''>('');
  const [batchCostCat, setBatchCostCat] = useState('大货材料费');
  const [batchAssetCat, setBatchAssetCat] = useState('包装材');
  const [batchSelectedBudgetId, setBatchSelectedBudgetId] = useState<number | ''>('');
  const [batchShippingFee, setBatchShippingFee] = useState<number | ''>('');

  // 补充现有资产库存 Mode State
  const [assetPurchaseMode, setAssetPurchaseMode] = useState<'new' | 'replenish'>('new');
  const [replenishAssetId, setReplenishAssetId] = useState<number | ''>('');
  const [replenishQty, setReplenishQty] = useState<number>(1);

  // 批量物品明细 List
  const [batchItems, setBatchItems] = useState<BatchItem[]>([]);
  const [editingBatchKey, setEditingBatchKey] = useState<string | null>(null);
  const [tempName, setTempName] = useState('');
  const [tempAmount, setTempAmount] = useState<number | ''>('');
  const [tempQty, setTempQty] = useState<number>(1);
  const [tempDesc, setTempDesc] = useState('');
  const [tempUrl, setTempUrl] = useState('');

  // 模态框与折叠状态
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);

  // 编辑 / 删除独立 Accordion State (页面下半部分)
  const [editSelectedId, setEditSelectedId] = useState<string>('');
  const [editDate, setEditDate] = useState('');
  const [editType, setEditType] = useState('支出');
  const [editAmount, setEditAmount] = useState<number | ''>('');
  const [editCategory, setEditCategory] = useState('');
  const [editAccId, setEditAccId] = useState<number | ''>('');
  const [editUrl, setEditUrl] = useState('');
  const [editDesc, setEditDesc] = useState('');

  const [deleteSelectedId, setDeleteSelectedId] = useState<string>('');
  const [deleteIncludeBudget, setDeleteIncludeBudget] = useState(false);

  // ================= Queries =================

  // 1. 流水明细真分页数据
  const { data: recordsData, isLoading: isLoadingRecords, refetch: refetchRecords } = useQuery({
    queryKey: ['finance-records', page, search, filterType, filterCategory],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: '50',
        search,
        filter_type: filterType,
        filter_category: filterCategory,
      });
      const res = await apiClient.get(`/finance/records/?${params.toString()}`);
      return res.data;
    },
  });

  // 2. 财务大盘指标数据
  const { data: summary, refetch: refetchSummary } = useQuery({
    queryKey: ['financial-summary'],
    queryFn: async () => {
      const res = await apiClient.get('/finance/summary/');
      return res.data;
    },
  });

  // 3. 现金账户列表
  const { data: cashAccounts } = useQuery<CompanyBalanceItem[]>({
    queryKey: ['cash-accounts'],
    queryFn: async () => {
      const res = await apiClient.get('/finance/records/cash-accounts/');
      return res.data;
    },
  });

  // 4. 商品列表
  const { data: products } = useQuery<Product[]>({
    queryKey: ['products'],
    queryFn: async () => {
      const res = await apiClient.get('/products/');
      return res.data.results || res.data;
    },
  });

  // 5. 未结负债列表
  const { data: unsettledDebts } = useQuery<any[]>({
    queryKey: ['unsettled-debts'],
    queryFn: async () => {
      const res = await apiClient.get('/finance/records/unsettled-debts/');
      return res.data;
    },
  });

  // 6. 抵债资产列表
  const { data: offsetAssets } = useQuery<any[]>({
    queryKey: ['offset-assets'],
    queryFn: async () => {
      const res = await apiClient.get('/finance/records/offset-assets/');
      return res.data;
    },
  });

  // 7. 消耗品/资产列表 (补充库存)
  const { data: consumableItems } = useQuery<any[]>({
    queryKey: ['consumable-items'],
    queryFn: async () => {
      const res = await apiClient.get('/finance/records/consumable-items/');
      return res.data;
    },
  });

  // 8. 预算匹配列表 (根据选中的商品和成本分类)
  const { data: budgetItems } = useQuery<any[]>({
    queryKey: ['budget-items', batchProductId, batchCostCat],
    queryFn: async () => {
      if (!batchProductId) return [];
      const res = await apiClient.get(`/finance/records/budget-items/?product_id=${batchProductId}&category=${encodeURIComponent(batchCostCat)}`);
      return res.data;
    },
    enabled: !!batchProductId,
  });

  // ================= 自动填入与联动计算 =================

  // 自动选择默认现金账户
  useEffect(() => {
    if (cashAccounts && cashAccounts.length > 0) {
      if (!accountId) {
        setAccountId(cashAccounts[0].id);
        setRecCurrency(cashAccounts[0].currency || 'CNY');
      }
      if (!exSourceAccId) setExSourceAccId(cashAccounts[0].id);
      if (!exTargetAccId) setExTargetAccId(cashAccounts[0].id);
      if (!debtTargetAccId) setDebtTargetAccId(cashAccounts[0].id);
      if (!debtRepaySourceAccId) setDebtRepaySourceAccId(cashAccounts[0].id);
      if (!moveFromAssetId) setMoveFromAssetId(cashAccounts[0].id);
      if (!moveToAssetId && cashAccounts.length > 1) setMoveToAssetId(cashAccounts[1].id);
    }
  }, [cashAccounts]);

  // 自动选择默认商品 & 消耗品
  useEffect(() => {
    if (products && products.length > 0 && !batchProductId) {
      setBatchProductId(products[0].id);
    }
  }, [products]);

  useEffect(() => {
    if (consumableItems && consumableItems.length > 0 && !replenishAssetId) {
      setReplenishAssetId(consumableItems[0].id);
    }
  }, [consumableItems]);

  useEffect(() => {
    if (unsettledDebts && unsettledDebts.length > 0 && !debtSelectedId) {
      setDebtSelectedId(unsettledDebts[0].id);
      setDebtRepayAmount(unsettledDebts[0].amount);
    }
  }, [unsettledDebts]);

  useEffect(() => {
    if (offsetAssets && offsetAssets.length > 0 && !debtRepayOffsetAssetId) {
      setDebtRepayOffsetAssetId(offsetAssets[0].id);
    }
  }, [offsetAssets]);

  // 选择账户自动更新币种
  const handleAccountChange = (accId: number) => {
    setAccountId(accId);
    const acc = (cashAccounts || []).find(a => a.id === accId);
    if (acc) {
      setRecCurrency(acc.currency || 'CNY');
    }
  };

  // 货币兑换源账户切换自动联动币种和预估
  const handleExSourceAccChange = (accId: number) => {
    setExSourceAccId(accId);
    const acc = (cashAccounts || []).find(a => a.id === accId);
    if (acc) {
      const srcCurr = acc.currency || 'CNY';
      setExSourceCurr(srcCurr);
      if (srcCurr === 'CNY') {
        setExTargetCurr('JPY');
      } else {
        setExTargetCurr('CNY');
      }
      calcExchangeEstimate(Number(exAmountOut), srcCurr, srcCurr === 'CNY' ? 'JPY' : 'CNY');
    }
  };

  // 汇率估算
  const calcExchangeEstimate = (outAmt: number, src: string, tgt: string) => {
    if (outAmt <= 0) {
      setExAmountIn('');
      return;
    }
    const rateSrc = src === 'JPY' ? 0.048 : 1.0;
    const rateTgt = tgt === 'JPY' ? 0.048 : 1.0;
    const est = (outAmt * rateSrc) / rateTgt;
    setExAmountIn(Math.round(est * 100) / 100);
  };

  // 切换目标债务自动填入最大偿还金额
  const handleDebtSelectChange = (dId: number) => {
    setDebtSelectedId(dId);
    const d = (unsettledDebts || []).find(item => item.id === dId);
    if (d) {
      setDebtRepayAmount(d.amount);
      setDebtCurr(d.currency || 'CNY');
    }
  };

  // 选择编辑记录填入编辑表单
  const handleEditSelectChange = (recIdStr: string) => {
    setEditSelectedId(recIdStr);
    if (!recIdStr) return;
    const recId = Number(recIdStr);
    const records = recordsData?.results || [];
    const r = records.find((item: ProcessedRecord) => item.id === recId);
    if (r) {
      setEditDate(r.date);
      setEditType(r.type);
      setEditAmount(r.amount);
      setEditCategory(r.category);
      setEditAccId(r.account_id || '');
      setEditUrl(r.url || '');
      setEditDesc(r.description || '');
    }
  };

  // 批量物品明细小计 & 总计
  const batchItemsSubtotal = batchItems.reduce((acc, item) => acc + item.amount * item.qty, 0);
  const batchTotalWithShipping = batchItemsSubtotal + (Number(batchShippingFee) || 0);

  // 选中的预算详情
  const selectedBudgetDetail = (budgetItems || []).find(b => b.id === Number(batchSelectedBudgetId));

  // 是否非现金
  const isNonCash = NON_CASH_CATEGORIES.has(recCategory);

  // ================= Mutations =================

  const generalCreateMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await apiClient.post('/finance/records/create-general/', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['finance-records'] });
      queryClient.invalidateQueries({ queryKey: ['financial-summary'] });
      queryClient.invalidateQueries({ queryKey: ['cash-accounts'] });
      closeModal();
    },
    onError: (err: any) => setFormError(err.response?.data?.error || '记账失败'),
  });

  const pendingCreateMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await apiClient.post('/finance/records/create-pending/', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['finance-records'] });
      queryClient.invalidateQueries({ queryKey: ['financial-summary'] });
      queryClient.invalidateQueries({ queryKey: ['unsettled-debts'] });
      closeModal();
    },
    onError: (err: any) => setFormError(err.response?.data?.error || '创建待付款失败'),
  });

  const batchCreateMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await apiClient.post('/finance/records/batch-create/', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['finance-records'] });
      queryClient.invalidateQueries({ queryKey: ['financial-summary'] });
      queryClient.invalidateQueries({ queryKey: ['cash-accounts'] });
      closeModal();
    },
    onError: (err: any) => setFormError(err.response?.data?.error || '批量记账失败'),
  });

  const exchangeMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await apiClient.post('/finance/records/exchange/', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['finance-records'] });
      queryClient.invalidateQueries({ queryKey: ['financial-summary'] });
      queryClient.invalidateQueries({ queryKey: ['cash-accounts'] });
      closeModal();
    },
    onError: (err: any) => setFormError(err.response?.data?.error || '货币兑换失败'),
  });

  const debtCreateMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await apiClient.post('/finance/records/debt-create/', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['finance-records'] });
      queryClient.invalidateQueries({ queryKey: ['financial-summary'] });
      queryClient.invalidateQueries({ queryKey: ['unsettled-debts'] });
      closeModal();
    },
    onError: (err: any) => setFormError(err.response?.data?.error || '新增债务失败'),
  });

  const debtRepayMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await apiClient.post('/finance/records/debt-repay/', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['finance-records'] });
      queryClient.invalidateQueries({ queryKey: ['financial-summary'] });
      queryClient.invalidateQueries({ queryKey: ['unsettled-debts'] });
      queryClient.invalidateQueries({ queryKey: ['offset-assets'] });
      closeModal();
    },
    onError: (err: any) => setFormError(err.response?.data?.error || '偿还债务失败'),
  });

  const transferMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await apiClient.post('/finance/records/transfer/', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['finance-records'] });
      queryClient.invalidateQueries({ queryKey: ['financial-summary'] });
      queryClient.invalidateQueries({ queryKey: ['cash-accounts'] });
      closeModal();
    },
    onError: (err: any) => setFormError(err.response?.data?.error || '资金划转失败'),
  });

  const editMutation = useMutation({
    mutationFn: async ({ id, data }: { id: number; data: any }) => {
      const res = await apiClient.put(`/finance/records/${id}/`, data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['finance-records'] });
      queryClient.invalidateQueries({ queryKey: ['financial-summary'] });
      setEditSelectedId('');
      alert('💾 流水修改保存成功！');
    },
    onError: (err: any) => alert(err.response?.data?.error || '修改失败'),
  });

  const deleteCascadeMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await apiClient.post('/finance/records/delete-with-cascade/', data);
      return res.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['finance-records'] });
      queryClient.invalidateQueries({ queryKey: ['financial-summary'] });
      setDeleteSelectedId('');
      alert(data.message || '🗑️ 删除流水成功！');
    },
    onError: (err: any) => alert(err.response?.data?.error || '删除失败'),
  });

  // ================= Handlers =================

  const closeModal = () => {
    setIsAddModalOpen(false);
    setBatchItems([]);
    setEditingBatchKey(null);
    setFormError('');
  };

  const addBatchItem = () => {
    if (!tempName.trim()) {
      setFormError('明细名称不能为空！');
      return;
    }
    if (!tempAmount || Number(tempAmount) <= 0) {
      setFormError('明细单价必须大于 0！');
      return;
    }
    setFormError('');

    if (editingBatchKey) {
      setBatchItems(batchItems.map(item => item.key === editingBatchKey ? {
        ...item,
        name: tempName.trim(),
        amount: Number(tempAmount),
        qty: Number(tempQty) || 1,
        desc: tempDesc.trim(),
        url: tempUrl.trim(),
      } : item));
      setEditingBatchKey(null);
    } else {
      setBatchItems([
        ...batchItems,
        {
          key: `item_${Date.now()}`,
          name: tempName.trim(),
          amount: Number(tempAmount),
          qty: Number(tempQty) || 1,
          desc: tempDesc.trim(),
          url: tempUrl.trim(),
        },
      ]);
    }

    setTempName('');
    setTempAmount('');
    setTempQty(1);
    setTempDesc('');
    setTempUrl('');
  };

  const startEditBatchItem = (item: BatchItem) => {
    setTempName(item.name);
    setTempAmount(item.amount);
    setTempQty(item.qty);
    setTempDesc(item.desc || '');
    setTempUrl(item.url || '');
    setEditingBatchKey(item.key);
  };

  const cancelEditBatchItem = () => {
    setEditingBatchKey(null);
    setTempName('');
    setTempAmount('');
    setTempQty(1);
    setTempDesc('');
    setTempUrl('');
  };

  const removeBatchItem = (key: string) => {
    if (editingBatchKey === key) cancelEditBatchItem();
    setBatchItems(batchItems.filter(i => i.key !== key));
  };

  const handleSubmitAddForm = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');

    // 1. 货币兑换
    if (recType === '货币兑换') {
      if (!exAmountOut || Number(exAmountOut) <= 0 || !exAmountIn || Number(exAmountIn) <= 0) {
        setFormError('兑换出入账金额必须大于 0！');
        return;
      }
      if (!exSourceAccId || !exTargetAccId) {
        setFormError('请选择扣款侧与入账侧现金账户');
        return;
      }
      exchangeMutation.mutate({
        source_account_id: exSourceAccId,
        target_account_id: exTargetAccId,
        source_currency: exSourceCurr,
        target_currency: exTargetCurr,
        amount_out: Number(exAmountOut),
        amount_in: Number(exAmountIn),
        description: exDesc,
        date: recDate,
      });
      return;
    }

    // 2. 债务
    if (recType === '债务') {
      if (debtOp === '➕ 新增债务') {
        if (!debtName.trim() || !debtAmount || Number(debtAmount) <= 0) {
          setFormError('请填写债务名称并确保金额大于 0！');
          return;
        }
        if (debtDest !== '存入流动资金 (拿到现金)' && !debtRelContent.trim()) {
          setFormError('请填写关联挂账的资产名称！');
          return;
        }
        debtCreateMutation.mutate({
          debt_name: debtName,
          destination: debtDest === '存入流动资金 (拿到现金)' ? 'cash' : 'asset',
          amount: Number(debtAmount),
          currency: debtCurr,
          target_account_id: debtDest === '存入流动资金 (拿到现金)' ? debtTargetAccId : null,
          related_asset_name: debtRelContent,
          creditor: debtSource,
          remark: debtRemark,
          date: recDate,
        });
      } else {
        if (!debtSelectedId || !debtRepayAmount || Number(debtRepayAmount) <= 0) {
          setFormError('请选择目标债务并输入偿还金额！');
          return;
        }
        debtRepayMutation.mutate({
          debt_id: debtSelectedId,
          repay_type: debtRepayType === '💸 资金还款' ? 'cash' : 'offset',
          amount: Number(debtRepayAmount),
          source_account_id: debtRepayType === '💸 资金还款' ? debtRepaySourceAccId : null,
          offset_asset_id: debtRepayType === '🔄 资产抵消' ? debtRepayOffsetAssetId : null,
          remark: debtRepayRemark,
          date: recDate,
        });
      }
      return;
    }

    // 3. 资金移动
    if (recType === '资金移动') {
      if (!moveFromAssetId || !moveToAssetId) {
        setFormError('请选择转出账户和转入账户！');
        return;
      }
      if (moveFromAssetId === moveToAssetId) {
        setFormError('转出和转入不能是同一个现金账户！');
        return;
      }
      if (!moveAmount || Number(moveAmount) <= 0) {
        setFormError('资金划转金额必须大于 0！');
        return;
      }
      transferMutation.mutate({
        from_account_id: moveFromAssetId,
        to_account_id: moveToAssetId,
        amount: Number(moveAmount),
        date: recDate,
        description: moveDesc || '内部资金划转',
      });
      return;
    }

    // 4. 普通收入与支出
    if (recType === '支出' && recCategory === '商品成本待付款') {
      if (batchItems.length === 0 && (!batchShippingFee || Number(batchShippingFee) <= 0)) {
        setFormError('请至少录入一条物品明细或提供邮费金额！');
        return;
      }
      if (!batchProductId) {
        setFormError('请选择归属商品！');
        return;
      }
      pendingCreateMutation.mutate({
        date: recDate,
        category: '商品成本待付款',
        currency: recCurrency,
        product_id: batchProductId,
        cost_cat: batchCostCat,
        items: batchItems,
        shipping_fee: Number(batchShippingFee) || 0,
        shop: recShop,
        description: recDesc,
      });
      return;
    }

    if (recType === '支出' && recCategory === '其他待付款') {
      if (!recAmount || Number(recAmount) <= 0) {
        setFormError('待付款金额必须大于 0！');
        return;
      }
      if (!recDesc.trim()) {
        setFormError('请填写业务明细描述！');
        return;
      }
      pendingCreateMutation.mutate({
        date: recDate,
        category: '其他待付款',
        currency: recCurrency,
        total_amount: Number(recAmount),
        shop: recShop,
        description: recDesc,
      });
      return;
    }

    // 批量录入模式 / 补充库存模式 / 普通单项模式
    const isBatchExpenseCategory = recType === '支出' && ['商品成本', '固定资产购入', '其他资产购入'].includes(recCategory);
    const isReplenishMode = recCategory === '其他资产购入' && assetPurchaseMode === 'replenish';

    if (isBatchExpenseCategory && !isReplenishMode) {
      if (batchItems.length === 0 && (!batchShippingFee || Number(batchShippingFee) <= 0)) {
        setFormError('请先在明细表中至少录入一项明细或提供邮费金额！');
        return;
      }
      if (!accountId) {
        setFormError('未指定操作现金扣款账户！');
        return;
      }
      batchCreateMutation.mutate({
        date: recDate,
        category: recCategory,
        currency: recCurrency,
        account_id: accountId,
        shop: recShop,
        shipping_fee: Number(batchShippingFee) || 0,
        product_id: batchProductId,
        cost_cat: batchCostCat,
        asset_cat: batchAssetCat,
        items: batchItems,
      });
      return;
    }

    // 单项通用录入 (含补充库存及普通单项)
    if (!recAmount || Number(recAmount) <= 0) {
      setFormError('录入金额必须大于 0！');
      return;
    }

    let finalDesc = recDesc;
    if (isReplenishMode) {
      const selectedCons = (consumableItems || []).find(c => c.id === Number(replenishAssetId));
      const name = selectedCons?.name || '资产项目';
      finalDesc = `【补充库存: ${name} (x${replenishQty})】 ${recShop ? `店铺:${recShop}` : ''} ${recDesc}`.trim();
    }

    generalCreateMutation.mutate({
      date: recDate,
      type: recType,
      category: recCategory,
      amount: Number(recAmount),
      currency: recCurrency,
      shop: recShop,
      description: finalDesc,
      url: recUrl,
      account_id: accountId || null,
      is_non_cash: isNonCash,
    });
  };

  const handleEditSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editSelectedId) return;
    if (!editAmount || Number(editAmount) <= 0) {
      alert('金额必须大于 0！');
      return;
    }
    editMutation.mutate({
      id: Number(editSelectedId),
      data: {
        date: editDate,
        amount: editType === '收入' ? Number(editAmount) : -Number(editAmount),
        category: editCategory,
        description: editDesc,
        url: editUrl,
        account_id: editAccId || null,
      },
    });
  };

  const handleDeleteSubmit = () => {
    if (!deleteSelectedId) return;
    deleteCascadeMutation.mutate({
      record_id: Number(deleteSelectedId),
      include_budget: deleteIncludeBudget,
    });
  };

  // 动态多币种现金卡片
  const dynamicIndicators = summary?.dynamic_cash_indicators || [];
  const totalCashCnyStr = summary?.total_cash_cny_str || '¥ 0.00';
  const totalPages = recordsData?.total_pages || 1;
  const recordsList: ProcessedRecord[] = recordsData?.results || [];

  // 判断选中的删除记录是否为商品成本类型
  const selectedDeleteRecord = recordsList.find(r => r.id === Number(deleteSelectedId));
  const isBudgetRelatedDelete = selectedDeleteRecord?.category === '商品成本' && !!selectedDeleteRecord?.related_item_id;

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        title="📝 财务流水录入与流水明细"
        subtitle="提供完整的收支记账表单、支持真分页流水展示、高亮余额卡片及编辑/删除流水模块"
        action={
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                refetchRecords();
                refetchSummary();
              }}
              className="px-3 py-1.5 bg-[#18202F] hover:bg-[#222C3E] text-slate-200 text-xs font-medium rounded-lg border border-[#2A3447] transition flex items-center gap-1.5"
            >
              <RefreshCw className="w-3.5 h-3.5 text-violet-400" />
              刷新大盘
            </button>
            <button
              onClick={() => {
                setFormError('');
                setIsAddModalOpen(true);
              }}
              className="px-4 py-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white text-xs font-bold rounded-xl shadow-lg shadow-violet-500/20 transition flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              新增记账流水
            </button>
          </div>
        }
      />

      {/* 1. 动态多币种现金余额高亮卡片 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
        {dynamicIndicators.map((ind: any, idx: number) => (
          <StatCard
            key={ind.currency || idx}
            label={`${ind.currency} 现金当前余额`}
            value={ind.amount_str}
            unit={ind.cny_equiv_str}
            icon={Coins}
            colorScheme={ind.color || 'violet'}
            borderLeft
          />
        ))}
        <StatCard
          label="流动现金总计 (CNY)"
          value={totalCashCnyStr}
          unit="CNY"
          icon={TrendingUp}
          colorScheme="amber"
          borderLeft
        />
      </div>

      {/* 2. 核心流水只读明细表格 (真分页) */}
      <DataCard title="📜 流水历史明细">
        {/* 顶部工具栏: 搜索 + 业务大类筛选 + 细分类型筛选 + 清除 */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4 text-xs">
          <div className="flex items-center gap-2 flex-1 min-w-[280px]">
            <div className="relative flex-1">
              <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
              <input
                type="text"
                placeholder="🔍 输入关键字搜索分类、说明备注、币种、金额或日期..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg pl-8 pr-3 py-1.5 text-slate-200 focus:outline-none focus:border-violet-500"
              />
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* 业务大类筛选 */}
            <select
              value={filterType}
              onChange={(e) => {
                setFilterType(e.target.value);
                setFilterCategory('');
                setPage(1);
              }}
              className="bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-1.5 text-slate-300 focus:outline-none focus:border-violet-500"
            >
              <option value="">全部大类</option>
              <option value="收入">收入</option>
              <option value="支出">支出</option>
              <option value="货币兑换">货币兑换</option>
              <option value="债务">债务</option>
              <option value="资金移动">资金移动</option>
            </select>

            {/* 收支细分类型筛选 (联动) */}
            <select
              value={filterCategory}
              onChange={(e) => {
                setFilterCategory(e.target.value);
                setPage(1);
              }}
              disabled={filterType !== '收入' && filterType !== '支出'}
              className="bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-1.5 text-slate-300 disabled:opacity-50 focus:outline-none focus:border-violet-500"
            >
              <option value="">全部细分</option>
              {filterType === '收入' && CATS_INCOME.map(c => <option key={c} value={c}>{c}</option>)}
              {filterType === '支出' && CATS_EXPENSE.map(c => <option key={c} value={c}>{c}</option>)}
            </select>

            {/* 清除筛选条件 */}
            <button
              onClick={() => {
                setSearch('');
                setFilterType('');
                setFilterCategory('');
                setPage(1);
              }}
              disabled={!search && !filterType && !filterCategory}
              className="px-3 py-1.5 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded-lg disabled:opacity-40 transition flex items-center gap-1"
            >
              <XCircle className="w-3.5 h-3.5" />
              清除筛选
            </button>
          </div>
        </div>

        {/* 流水表格 */}
        {isLoadingRecords ? (
          <div className="text-center py-12 text-slate-400 text-xs flex items-center justify-center gap-2">
            <RefreshCw className="w-4 h-4 animate-spin text-violet-400" />
            加载流水明细中...
          </div>
        ) : recordsList.length === 0 ? (
          <div className="text-center py-12 text-slate-400 text-xs">暂无满足搜索条件的财务流水明细数据</div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#2A3447] text-slate-400 uppercase font-medium">
                    <th className="pb-3 px-2">日期</th>
                    <th className="pb-3 px-2">类型</th>
                    <th className="pb-3 px-2">分类</th>
                    <th className="pb-3 px-2 text-right">交易金额</th>
                    <th className="pb-3 px-2">说明备注</th>
                    <th className="pb-3 px-2 text-center">链接</th>
                    <th className="pb-3 px-2 text-right">CNY账户余额</th>
                    <th className="pb-3 px-2 text-right">JPY账户余额</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#2A3447]/50 text-slate-300">
                  {recordsList.map((rec) => {
                    const isIncome = rec.type === '收入';
                    const isEx = (rec.category || '').includes('兑换') || (rec.category || '').includes('转账');
                    return (
                      <tr key={rec.id} className="hover:bg-[#18202F] transition">
                        <td className="py-2.5 px-2 font-mono text-slate-300">{rec.date}</td>
                        <td className="py-2.5 px-2">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold ${
                            isEx
                              ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20'
                              : isIncome
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                              : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                          }`}>
                            {isEx ? <Repeat className="w-3 h-3" /> : isIncome ? <ArrowDownRight className="w-3 h-3" /> : <ArrowUpRight className="w-3 h-3" />}
                            {rec.type}
                          </span>
                        </td>
                        <td className="py-2.5 px-2 font-medium text-slate-200">{rec.category}</td>
                        <td className={`py-2.5 px-2 text-right font-mono font-bold ${
                          isEx ? 'text-purple-400' : isIncome ? 'text-emerald-400' : 'text-rose-400'
                        }`}>
                          {isIncome ? '+' : isEx ? '' : '-'}{(rec.amount || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })} {rec.currency}
                        </td>
                        <td className="py-2.5 px-2 text-slate-300 max-w-xs truncate">{rec.description || '-'}</td>
                        <td className="py-2.5 px-2 text-center">
                          {rec.url ? (
                            <a
                              href={rec.url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex p-1 text-violet-400 hover:text-violet-300 transition"
                              title="打开参考链接"
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                          ) : (
                            <span className="text-slate-600">-</span>
                          )}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-slate-400">¥{(rec.cny_bal || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}</td>
                        <td className="py-2.5 px-2 text-right font-mono text-slate-400">￥{(rec.jpy_bal || 0).toLocaleString('zh-CN', { minimumFractionDigits: 0 })}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* 真分页 翻页按钮 */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between pt-4 border-t border-[#2A3447] text-xs">
                <span className="text-slate-400">共 {recordsData?.total_count || 0} 条记录</span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="px-3 py-1.5 bg-[#0B0F17] hover:bg-[#18202F] text-slate-300 rounded-lg border border-[#2A3447] disabled:opacity-40 transition flex items-center gap-1"
                  >
                    <ChevronLeft className="w-3.5 h-3.5" /> 上一页
                  </button>
                  <span className="text-slate-300 px-2 font-mono">
                    第 {page} / {totalPages} 页
                  </span>
                  <button
                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                    className="px-3 py-1.5 bg-[#0B0F17] hover:bg-[#18202F] text-slate-300 rounded-lg border border-[#2A3447] disabled:opacity-40 transition flex items-center gap-1"
                  >
                    下一页 <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </DataCard>

      {/* 3. 修改与删除级联回退区 (页面下半部分 Grid) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* 修改流水记录 */}
        <DataCard title="✏️ 修改流水记录 (仅限当页明细)">
          <form onSubmit={handleEditSubmit} className="space-y-3 text-xs">
            <FormField label="选择要修改的当页记录" required>
              <select
                value={editSelectedId}
                onChange={(e) => handleEditSelectChange(e.target.value)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
              >
                <option value="">-- 请选择一条记录 --</option>
                {recordsList.map(r => (
                  <option key={r.id} value={r.id}>
                    {r.date} | {r.type} {r.amount} {r.currency} | {r.description || r.category}
                  </option>
                ))}
              </select>
            </FormField>

            {editSelectedId && (
              <div className="space-y-3 pt-2 border-t border-[#2A3447]">
                <div className="grid grid-cols-2 gap-3">
                  <FormField label="日期" required>
                    <input
                      type="date"
                      value={editDate}
                      onChange={(e) => setEditDate(e.target.value)}
                      className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-1.5 text-slate-100 font-mono"
                    />
                  </FormField>

                  <FormField label="收支大类" required>
                    <select
                      value={editType}
                      onChange={(e) => setEditType(e.target.value)}
                      className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-1.5 text-slate-100"
                    >
                      <option value="收入">收入</option>
                      <option value="支出">支出</option>
                    </select>
                  </FormField>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <FormField label="金额" required>
                    <input
                      type="number"
                      step="0.01"
                      value={editAmount}
                      onChange={(e) => setEditAmount(e.target.value ? parseFloat(e.target.value) : '')}
                      className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-1.5 text-slate-100 font-mono"
                    />
                  </FormField>

                  <FormField label="具体分类" required>
                    <select
                      value={editCategory}
                      onChange={(e) => setEditCategory(e.target.value)}
                      className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-1.5 text-slate-100"
                    >
                      {(editType === '收入' ? CATS_INCOME : CATS_EXPENSE).map(c => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </FormField>
                </div>

                <FormField label="操作关联现金账户">
                  <select
                    value={editAccId}
                    onChange={(e) => setEditAccId(e.target.value ? Number(e.target.value) : '')}
                    className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-1.5 text-slate-100"
                  >
                    <option value="">-- 未选账户 / 非现金 --</option>
                    {(cashAccounts || []).map(a => (
                      <option key={a.id} value={a.id}>[{a.currency}] {a.name}</option>
                    ))}
                  </select>
                </FormField>

                <FormField label="相关页面网址">
                  <input
                    type="url"
                    value={editUrl}
                    onChange={(e) => setEditUrl(e.target.value)}
                    placeholder="https://..."
                    className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-1.5 text-slate-100"
                  />
                </FormField>

                <FormField label="具体备注/明细说明">
                  <input
                    type="text"
                    value={editDesc}
                    onChange={(e) => setEditDesc(e.target.value)}
                    className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-1.5 text-slate-100"
                  />
                </FormField>

                <button
                  type="submit"
                  disabled={editMutation.isPending}
                  className="w-full py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-lg transition flex items-center justify-center gap-1.5"
                >
                  <Save className="w-4 h-4" />
                  {editMutation.isPending ? '保存中...' : '保存修改内容'}
                </button>
              </div>
            )}
          </form>
        </DataCard>

        {/* 删除流水记录 (安全级联) */}
        <DataCard title="🗑️ 删除流水记录 (仅限当页明细)">
          <div className="space-y-3 text-xs">
            <FormField label="选择要删除的流水记录" required>
              <select
                value={deleteSelectedId}
                onChange={(e) => {
                  setDeleteSelectedId(e.target.value);
                  setDeleteIncludeBudget(false);
                }}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
              >
                <option value="">-- 请选择要删除的记录 --</option>
                {recordsList.map(r => (
                  <option key={r.id} value={r.id}>
                    {r.date} | {r.amount} {r.currency} | {r.description || r.category}
                  </option>
                ))}
              </select>
            </FormField>

            {deleteSelectedId && (
              <div className="space-y-3 pt-2 border-t border-[#2A3447]">
                {/* 预算关联 Cascade Delete Checkbox */}
                {isBudgetRelatedDelete && (
                  <div className="flex items-center gap-2 p-2 bg-amber-500/10 border border-amber-500/30 rounded-lg">
                    <input
                      type="checkbox"
                      id="delete_budget"
                      checked={deleteIncludeBudget}
                      onChange={(e) => setDeleteIncludeBudget(e.target.checked)}
                      className="rounded border-slate-700 bg-slate-900 text-amber-500 focus:ring-amber-500"
                    />
                    <label htmlFor="delete_budget" className="text-amber-400 font-medium cursor-pointer">
                      一并物理删除绑定的预算项目记录 (Cascade Delete)
                    </label>
                  </div>
                )}

                <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl space-y-1 text-rose-300">
                  <div className="flex items-center gap-1.5 font-bold text-rose-400">
                    <AlertTriangle className="w-4 h-4" />
                    安全级联警告
                  </div>
                  <p>
                    删除流水会将关联的资产、负债、或库存成本明细一并安全级联撤回！如果是【销售收入】流水请必须去线上订单列表删除，严禁在此直接删除核心流水。
                  </p>
                </div>

                <button
                  type="button"
                  onClick={handleDeleteSubmit}
                  disabled={deleteCascadeMutation.isPending}
                  className="w-full py-2 bg-rose-600 hover:bg-rose-500 text-white font-bold rounded-lg transition flex items-center justify-center gap-1.5 shadow-lg shadow-rose-600/20"
                >
                  <Trash2 className="w-4 h-4" />
                  {deleteCascadeMutation.isPending ? '执行中...' : '确认安全回滚删除'}
                </button>
              </div>
            )}
          </div>
        </DataCard>
      </div>

      {/* 4. 新增记账 Modal 弹窗 */}
      <Modal
        isOpen={isAddModalOpen}
        onClose={closeModal}
        title="新增财务收支 / 兑换 / 债务 / 内部划拨"
        maxWidth="4xl"
      >
        <form onSubmit={handleSubmitAddForm} className="space-y-4 text-xs">
          {formError && (
            <div className="p-2.5 bg-rose-500/10 border border-rose-500/30 rounded-lg text-rose-400 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              {formError}
            </div>
          )}

          {/* 顶栏: 日期与业务大类选择 */}
          <div className="grid grid-cols-2 gap-3 p-3 bg-[#0B0F17] rounded-xl border border-[#2A3447]">
            <FormField label="流水录入日期" required>
              <input
                type="date"
                required
                value={recDate}
                onChange={(e) => setRecDate(e.target.value)}
                className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-1.5 text-slate-100 font-mono"
              />
            </FormField>

            <FormField label="业务大类" required>
              <select
                value={recType}
                onChange={(e) => {
                  const val = e.target.value as any;
                  setRecType(val);
                  if (val === '收入') setRecCategory('销售收入');
                  if (val === '支出') setRecCategory('商品成本');
                }}
                className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-1.5 text-slate-100 font-bold"
              >
                <option value="支出">支出</option>
                <option value="收入">收入</option>
                <option value="货币兑换">货币兑换</option>
                <option value="债务">债务</option>
                <option value="资金移动">资金移动</option>
              </select>
            </FormField>
          </div>

          {/* Tab 1: 货币兑换 */}
          {recType === '货币兑换' && (
            <div className="space-y-3 p-3 bg-[#0B0F17] rounded-xl border border-[#2A3447]">
              <div className="p-2 bg-purple-500/10 border border-purple-500/30 rounded-lg text-purple-300 flex items-center gap-2">
                <Info className="w-4 h-4 flex-shrink-0" />
                💱 货币资金互转 (此操作不会改变总净资产，只调整账户余额分布)
              </div>

              <div className="grid grid-cols-2 gap-3">
                <FormField label="扣款侧源币种" required>
                  <select
                    value={exSourceCurr}
                    onChange={(e) => {
                      setExSourceCurr(e.target.value);
                      calcExchangeEstimate(Number(exAmountOut), e.target.value, exTargetCurr);
                    }}
                    className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                  >
                    <option value="CNY">CNY</option>
                    <option value="JPY">JPY</option>
                  </select>
                </FormField>

                <FormField label="扣款现金账户" required>
                  <select
                    value={exSourceAccId}
                    onChange={(e) => handleExSourceAccChange(Number(e.target.value))}
                    className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                  >
                    <option value="">-- 选择扣款账户 --</option>
                    {(cashAccounts || []).map(a => (
                      <option key={a.id} value={a.id}>[{a.currency}] {a.name} (余额: ¥{a.amount})</option>
                    ))}
                  </select>
                </FormField>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <FormField label="入账侧目标币种" required>
                  <select
                    value={exTargetCurr}
                    onChange={(e) => {
                      setExTargetCurr(e.target.value);
                      calcExchangeEstimate(Number(exAmountOut), exSourceCurr, e.target.value);
                    }}
                    className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                  >
                    <option value="JPY">JPY</option>
                    <option value="CNY">CNY</option>
                  </select>
                </FormField>

                <FormField label="入账现金账户" required>
                  <select
                    value={exTargetAccId}
                    onChange={(e) => setExTargetAccId(Number(e.target.value))}
                    className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                  >
                    <option value="">-- 选择入账账户 --</option>
                    {(cashAccounts || []).map(a => (
                      <option key={a.id} value={a.id}>[{a.currency}] {a.name} (余额: ¥{a.amount})</option>
                    ))}
                  </select>
                </FormField>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <FormField label="转出/流出金额" required>
                  <input
                    type="number"
                    step="0.01"
                    placeholder="流出金额"
                    value={exAmountOut}
                    onChange={(e) => {
                      const val = e.target.value ? parseFloat(e.target.value) : '';
                      setExAmountOut(val);
                      calcExchangeEstimate(Number(val), exSourceCurr, exTargetCurr);
                    }}
                    className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                  />
                </FormField>

                <FormField label="转入/入账金额 (自动估算)" required>
                  <input
                    type="number"
                    step="0.01"
                    placeholder="入账金额"
                    value={exAmountIn}
                    onChange={(e) => setExAmountIn(e.target.value ? parseFloat(e.target.value) : '')}
                    className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                  />
                </FormField>
              </div>

              <FormField label="兑换备注说明">
                <input
                  type="text"
                  placeholder="如：购汇、信用卡日元结算扣款等"
                  value={exDesc}
                  onChange={(e) => setExDesc(e.target.value)}
                  className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                />
              </FormField>
            </div>
          )}

          {/* Tab 2: 债务管理 */}
          {recType === '债务' && (
            <div className="space-y-3 p-3 bg-[#0B0F17] rounded-xl border border-[#2A3447]">
              <div className="grid grid-cols-2 gap-2 p-1 bg-[#131924] rounded-lg">
                <button
                  type="button"
                  onClick={() => setDebtOp('➕ 新增债务')}
                  className={`py-1.5 rounded-lg text-xs font-bold transition ${debtOp === '➕ 新增债务' ? 'bg-violet-600 text-white' : 'text-slate-400'}`}
                >
                  ➕ 新增债务
                </button>
                <button
                  type="button"
                  onClick={() => setDebtOp('💸 偿还债务')}
                  className={`py-1.5 rounded-lg text-xs font-bold transition ${debtOp === '💸 偿还债务' ? 'bg-violet-600 text-white' : 'text-slate-400'}`}
                >
                  💸 偿还债务
                </button>
              </div>

              {debtOp === '➕ 新增债务' ? (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <FormField label="债务名称/欠款事由" required>
                      <input
                        type="text"
                        placeholder="如：工厂挂账货款、借款"
                        value={debtName}
                        onChange={(e) => setDebtName(e.target.value)}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                      />
                    </FormField>

                    <FormField label="借入价值去向" required>
                      <select
                        value={debtDest}
                        onChange={(e) => setDebtDest(e.target.value as any)}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                      >
                        <option value="存入流动资金 (拿到现金)">存入流动资金 (拿到现金)</option>
                        <option value="新增资产项 (形成实物/挂账资产)">新增资产项 (形成实物/挂账资产)</option>
                      </select>
                    </FormField>
                  </div>

                  {debtDest !== '存入流动资金 (拿到现金)' && (
                    <FormField label="新增挂账资产名称" required>
                      <input
                        type="text"
                        placeholder="如：未付款的打包机"
                        value={debtRelContent}
                        onChange={(e) => setDebtRelContent(e.target.value)}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                      />
                    </FormField>
                  )}

                  <div className="grid grid-cols-2 gap-3">
                    <FormField label="债务金额" required>
                      <input
                        type="number"
                        step="0.01"
                        placeholder="0.00"
                        value={debtAmount}
                        onChange={(e) => setDebtAmount(e.target.value ? parseFloat(e.target.value) : '')}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                      />
                    </FormField>

                    <FormField label="币种" required>
                      <select
                        value={debtCurr}
                        onChange={(e) => setDebtCurr(e.target.value)}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                      >
                        <option value="CNY">CNY</option>
                        <option value="JPY">JPY</option>
                      </select>
                    </FormField>
                  </div>

                  {debtDest === '存入流动资金 (拿到现金)' && (
                    <FormField label="收款现金账户">
                      <select
                        value={debtTargetAccId}
                        onChange={(e) => setDebtTargetAccId(Number(e.target.value))}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                      >
                        <option value="">-- 选择收款账户 --</option>
                        {(cashAccounts || []).map(a => (
                          <option key={a.id} value={a.id}>[{a.currency}] {a.name}</option>
                        ))}
                      </select>
                    </FormField>
                  )}

                  <div className="grid grid-cols-2 gap-3">
                    <FormField label="债权方/资金来源">
                      <input
                        type="text"
                        placeholder="如：工商银行、加工厂A"
                        value={debtSource}
                        onChange={(e) => setDebtSource(e.target.value)}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                      />
                    </FormField>

                    <FormField label="备注说明">
                      <input
                        type="text"
                        placeholder="其他说明"
                        value={debtRemark}
                        onChange={(e) => setDebtRemark(e.target.value)}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                      />
                    </FormField>
                  </div>
                </>
              ) : (
                /* 偿还债务 */
                <>
                  {(!unsettledDebts || unsettledDebts.length === 0) ? (
                    <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-emerald-400 flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4" />
                      当前无未结负债记录，债务清结完毕！
                    </div>
                  ) : (
                    <>
                      <FormField label="选择目标债务" required>
                        <select
                          value={debtSelectedId}
                          onChange={(e) => handleDebtSelectChange(Number(e.target.value))}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                        >
                          <option value="">-- 请选择未结负债 --</option>
                          {(unsettledDebts || []).map(d => (
                            <option key={d.id} value={d.id}>{d.label || d.name}</option>
                          ))}
                        </select>
                      </FormField>

                      {/* 如果是商品成本待付款, 显示说明提示 */}
                      {unsettledDebts.find(d => d.id === Number(debtSelectedId))?.source_type === '商品成本待付款' && (
                        <div className="p-2 bg-violet-500/10 border border-violet-500/30 rounded-lg text-violet-300 text-[11px] flex items-center gap-2">
                          <Info className="w-4 h-4 flex-shrink-0" />
                          ℹ️ 偿还商品成本待付款负债，系统将自动把此笔还款（含超额款）同步记录到商品成本明细的【实付】中，用于商品成本核算与大货资产计算。
                        </div>
                      )}

                      <div className="grid grid-cols-2 gap-3">
                        <FormField label="偿还方式" required>
                          <select
                            value={debtRepayType}
                            onChange={(e) => setDebtRepayType(e.target.value as any)}
                            className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                          >
                            <option value="💸 资金还款">💸 资金还款</option>
                            <option value="🔄 资产抵消">🔄 资产抵消</option>
                          </select>
                        </FormField>

                        <FormField label="偿还金额" required>
                          <input
                            type="number"
                            step="0.01"
                            value={debtRepayAmount}
                            onChange={(e) => setDebtRepayAmount(e.target.value ? parseFloat(e.target.value) : '')}
                            className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                          />
                        </FormField>
                      </div>

                      {debtRepayType === '💸 资金还款' ? (
                        <FormField label="付款现金账户" required>
                          <select
                            value={debtRepaySourceAccId}
                            onChange={(e) => setDebtRepaySourceAccId(Number(e.target.value))}
                            className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                          >
                            <option value="">-- 选择付款账户 --</option>
                            {(cashAccounts || []).map(a => (
                              <option key={a.id} value={a.id}>[{a.currency}] {a.name}</option>
                            ))}
                          </select>
                        </FormField>
                      ) : (
                        <FormField label="抵消账面资产项" required>
                          <select
                            value={debtRepayOffsetAssetId}
                            onChange={(e) => setDebtRepayOffsetAssetId(Number(e.target.value))}
                            className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                          >
                            <option value="">-- 选择抵债资产 --</option>
                            {(offsetAssets || []).map(a => (
                              <option key={a.id} value={a.id}>{a.label || a.name}</option>
                            ))}
                          </select>
                        </FormField>
                      )}

                      <FormField label="偿还备注">
                        <input
                          type="text"
                          placeholder="其他还款说明 (选填)"
                          value={debtRepayRemark}
                          onChange={(e) => setDebtRepayRemark(e.target.value)}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                        />
                      </FormField>
                    </>
                  )}
                </>
              )}
            </div>
          )}

          {/* Tab 3: 资金移动 */}
          {recType === '资金移动' && (
            <div className="space-y-3 p-3 bg-[#0B0F17] rounded-xl border border-[#2A3447]">
              <div className="p-2 bg-blue-500/10 border border-blue-500/30 rounded-lg text-blue-300 flex items-center gap-2">
                <Info className="w-4 h-4 flex-shrink-0" />
                🔄 内部现金划转（此操作不会改变总净资产，仅在不同账户之间调配流动性）
              </div>

              {(!cashAccounts || cashAccounts.length < 2) && (
                <div className="p-2 bg-amber-500/10 border border-amber-500/30 rounded-lg text-amber-300 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4" />
                  ⚠️ 当前系统中的现金账户不足 2 个，无法执行内部划拨。
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <FormField label="转出账户 (From)" required>
                  <select
                    value={moveFromAssetId}
                    onChange={(e) => setMoveFromAssetId(Number(e.target.value))}
                    className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                  >
                    <option value="">-- 选择转出账户 --</option>
                    {(cashAccounts || []).map(a => (
                      <option key={a.id} value={a.id}>[{a.currency}] {a.name}</option>
                    ))}
                  </select>
                </FormField>

                <FormField label="转入账户 (To)" required>
                  <select
                    value={moveToAssetId}
                    onChange={(e) => setMoveToAssetId(Number(e.target.value))}
                    className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                  >
                    <option value="">-- 选择转入账户 --</option>
                    {(cashAccounts || []).map(a => (
                      <option key={a.id} value={a.id}>[{a.currency}] {a.name}</option>
                    ))}
                  </select>
                </FormField>
              </div>

              <FormField label="划转金额" required>
                <input
                  type="number"
                  step="0.01"
                  placeholder="请输入划转金额"
                  value={moveAmount}
                  onChange={(e) => setMoveAmount(e.target.value ? parseFloat(e.target.value) : '')}
                  className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                />
              </FormField>

              <FormField label="划转备注">
                <input
                  type="text"
                  placeholder="如：转入日常备用金账户 (选填)"
                  value={moveDesc}
                  onChange={(e) => setMoveDesc(e.target.value)}
                  className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                />
              </FormField>
            </div>
          )}

          {/* Tab 4 & 5: 普通收入与支出表单 */}
          {(recType === '收入' || recType === '支出') && (
            <div className="space-y-3 p-3 bg-[#0B0F17] rounded-xl border border-[#2A3447]">
              {/* 收支细分类型 & 关联组件 */}
              <div className="grid grid-cols-3 gap-3">
                <FormField label="收支细分类型" required>
                  <select
                    value={recCategory}
                    onChange={(e) => setRecCategory(e.target.value)}
                    className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                  >
                    {(recType === '收入' ? CATS_INCOME : CATS_EXPENSE).map(c => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </FormField>

                {recCategory === '商品成本' && (
                  <>
                    <FormField label="归属商品">
                      <select
                        value={batchProductId}
                        onChange={(e) => setBatchProductId(e.target.value ? Number(e.target.value) : '')}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                      >
                        <option value="">-- 选择归属商品 --</option>
                        {(products || []).map(p => (
                          <option key={p.id} value={p.id}>{p.name}</option>
                        ))}
                      </select>
                    </FormField>

                    <FormField label="共同成本分类">
                      <select
                        value={batchCostCat}
                        onChange={(e) => setBatchCostCat(e.target.value)}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                      >
                        {PRODUCT_COST_CATEGORIES.map(c => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                    </FormField>
                  </>
                )}

                {recCategory === '其他资产购入' && (
                  <FormField label="资产子分类">
                    <select
                      value={batchAssetCat}
                      onChange={(e) => setBatchAssetCat(e.target.value)}
                      className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                    >
                      {ASSET_SUB_CATEGORIES.map(c => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </FormField>
                )}
              </div>

              {/* 购入模式选择 (仅当收支细分类型为"其他资产购入"时) */}
              {recCategory === '其他资产购入' && (
                <FormField label="购入模式">
                  <div className="flex items-center gap-4">
                    <label className="flex items-center gap-1.5 cursor-pointer text-slate-300">
                      <input
                        type="radio"
                        name="purchase_mode"
                        value="new"
                        checked={assetPurchaseMode === 'new'}
                        onChange={() => setAssetPurchaseMode('new')}
                        className="text-violet-600 focus:ring-violet-500"
                      />
                      新增项目 (新建物品并展开明细表)
                    </label>
                    <label className="flex items-center gap-1.5 cursor-pointer text-slate-300">
                      <input
                        type="radio"
                        name="purchase_mode"
                        value="replenish"
                        checked={assetPurchaseMode === 'replenish'}
                        onChange={() => setAssetPurchaseMode('replenish')}
                        className="text-violet-600 focus:ring-violet-500"
                      />
                      补充现有项目库存
                    </label>
                  </div>
                </FormField>
              )}

              {/* 预算项目匹配 (仅商品成本或商品成本待付款时) */}
              {(recCategory === '商品成本' || recCategory === '商品成本待付款') && (
                <FormField label="🎯 预算项目匹配">
                  <select
                    value={batchSelectedBudgetId}
                    onChange={(e) => setBatchSelectedBudgetId(e.target.value ? Number(e.target.value) : '')}
                    className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                  >
                    <option value="">➕ 不匹配预算 (批量录入新成本)</option>
                    {(budgetItems || []).map(b => (
                      <option key={b.id} value={b.id}>{b.label}</option>
                    ))}
                  </select>
                </FormField>
              )}

              {/* 匹配预算后的提示与卡片 */}
              {!!batchSelectedBudgetId && selectedBudgetDetail && (
                <div className="space-y-2 p-3 bg-violet-950/20 border border-violet-500/30 rounded-xl text-slate-200">
                  <div className="p-2 bg-blue-500/10 border border-blue-500/30 rounded-lg text-blue-300 text-[11px] flex items-center gap-1.5">
                    <Info className="w-4 h-4 flex-shrink-0" />
                    ✅ 当前已匹配特定预算项：此模式下仅支持添加一条物品明细用于累加实付/待付成本，且共同邮费将设为0。
                  </div>
                  <div className="grid grid-cols-5 gap-2 text-center text-[11px] pt-1">
                    <div>
                      <div className="text-slate-400">项目名称</div>
                      <div className="font-bold text-slate-100">{selectedBudgetDetail.item_name}</div>
                    </div>
                    <div>
                      <div className="text-slate-400">预算数量</div>
                      <div className="font-bold text-slate-100">{selectedBudgetDetail.quantity}</div>
                    </div>
                    <div>
                      <div className="text-slate-400">预算单价</div>
                      <div className="font-bold text-slate-100">¥{selectedBudgetDetail.unit_price}</div>
                    </div>
                    <div>
                      <div className="text-slate-400">预算总额</div>
                      <div className="font-bold text-purple-400">¥{selectedBudgetDetail.total}</div>
                    </div>
                    <div>
                      <div className="text-slate-400">已付实付(已入账)</div>
                      <div className="font-bold text-emerald-400">¥{selectedBudgetDetail.actual_cost}</div>
                    </div>
                  </div>
                </div>
              )}

              {/* 补充现有资产库存子表单 */}
              {recCategory === '其他资产购入' && assetPurchaseMode === 'replenish' ? (
                <div className="space-y-3 pt-1">
                  <div className="grid grid-cols-3 gap-3">
                    <FormField label="选择补充项目" required>
                      <select
                        value={replenishAssetId}
                        onChange={(e) => setReplenishAssetId(Number(e.target.value))}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                      >
                        {(consumableItems || []).map(c => (
                          <option key={c.id} value={c.id}>{c.label || c.name}</option>
                        ))}
                      </select>
                    </FormField>

                    <FormField label="补充金额 (总价)" required>
                      <input
                        type="number"
                        step="0.01"
                        placeholder="请输入总价"
                        value={recAmount}
                        onChange={(e) => setRecAmount(e.target.value ? parseFloat(e.target.value) : '')}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                      />
                    </FormField>

                    <FormField label="补充数量" required>
                      <input
                        type="number"
                        step="1"
                        placeholder="请输入数量"
                        value={replenishQty}
                        onChange={(e) => setReplenishQty(e.target.value ? parseFloat(e.target.value) : 1)}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                      />
                    </FormField>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <FormField label="付款现金账户">
                      <select
                        value={accountId}
                        onChange={(e) => handleAccountChange(Number(e.target.value))}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                      >
                        {(cashAccounts || []).map(a => (
                          <option key={a.id} value={a.id}>[{a.currency}] {a.name}</option>
                        ))}
                      </select>
                    </FormField>

                    <FormField label="付款店铺/收款方">
                      <input
                        type="text"
                        placeholder="如：某工厂、淘宝商家"
                        value={recShop}
                        onChange={(e) => setRecShop(e.target.value)}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                      />
                    </FormField>
                  </div>

                  <FormField label="补充备注">
                    <input
                      type="text"
                      placeholder="补充备注/说明 (如：自主补货)"
                      value={recDesc}
                      onChange={(e) => setRecDesc(e.target.value)}
                      className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                    />
                  </FormField>
                </div>
              ) : recCategory === '其他待付款' ? (
                /* 其他待付款专属表单 (无付款账户) */
                <div className="space-y-3 pt-1">
                  <div className="grid grid-cols-2 gap-3">
                    <FormField label="待付款金额" required>
                      <input
                        type="number"
                        step="0.01"
                        placeholder="请输入金额"
                        value={recAmount}
                        onChange={(e) => setRecAmount(e.target.value ? parseFloat(e.target.value) : '')}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                      />
                    </FormField>

                    <FormField label="币种" required>
                      <select
                        value={recCurrency}
                        onChange={(e) => setRecCurrency(e.target.value)}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                      >
                        <option value="CNY">CNY (¥)</option>
                        <option value="JPY">JPY (￥)</option>
                      </select>
                    </FormField>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <FormField label="待付商家/收款方 (选填)">
                      <input
                        type="text"
                        placeholder="如：某淘宝店、公司A"
                        value={recShop}
                        onChange={(e) => setRecShop(e.target.value)}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                      />
                    </FormField>

                    <FormField label="业务明细描述/其他备注" required>
                      <input
                        type="text"
                        placeholder="如：欠某某的服务费/待付项目款"
                        value={recDesc}
                        onChange={(e) => setRecDesc(e.target.value)}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                      />
                    </FormField>
                  </div>
                </div>
              ) : (recType === '支出' && ['商品成本', '商品成本待付款', '固定资产购入', '其他资产购入'].includes(recCategory)) ? (
                /* 批量购入/待付款 物品明细表单 */
                <div className="space-y-3 pt-1">
                  {/* 付款账户 & 店铺 & 币种 (若非商品成本待付款) */}
                  {recCategory !== '商品成本待付款' && (
                    <div className="grid grid-cols-3 gap-3">
                      <FormField label="付款现金账户" required>
                        <select
                          value={accountId}
                          onChange={(e) => handleAccountChange(Number(e.target.value))}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                        >
                          {(cashAccounts || []).map(a => (
                            <option key={a.id} value={a.id}>[{a.currency}] {a.name}</option>
                          ))}
                        </select>
                      </FormField>

                      <FormField label="付款店铺/收款方">
                        <input
                          type="text"
                          placeholder="如：某工厂、淘宝商家"
                          value={recShop}
                          onChange={(e) => setRecShop(e.target.value)}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                        />
                      </FormField>

                      <FormField label="交易币种" required>
                        <select
                          value={recCurrency}
                          onChange={(e) => setRecCurrency(e.target.value)}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                        >
                          <option value="CNY">CNY (¥)</option>
                          <option value="JPY">JPY (￥)</option>
                        </select>
                      </FormField>
                    </div>
                  )}

                  {recCategory === '商品成本待付款' && (
                    <div className="grid grid-cols-2 gap-3">
                      <FormField label="待付店铺/商家">
                        <input
                          type="text"
                          placeholder="如：某工厂、淘宝商家"
                          value={recShop}
                          onChange={(e) => setRecShop(e.target.value)}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                        />
                      </FormField>

                      <FormField label="交易币种" required>
                        <select
                          value={recCurrency}
                          onChange={(e) => setRecCurrency(e.target.value)}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                        >
                          <option value="CNY">CNY (¥)</option>
                          <option value="JPY">JPY (￥)</option>
                        </select>
                      </FormField>
                    </div>
                  )}

                  {/* 共同邮费录入 (无匹配预算时显示) */}
                  {!batchSelectedBudgetId && (
                    <FormField label="订单共同邮费">
                      <input
                        type="number"
                        step="0.01"
                        placeholder="请输入共同邮费"
                        value={batchShippingFee}
                        onChange={(e) => setBatchShippingFee(e.target.value ? parseFloat(e.target.value) : '')}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                      />
                    </FormField>
                  )}

                  {/* 物品明细表格与输入行 */}
                  <div className="space-y-3 pt-1">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-200">物品明细表</span>
                      <span className="text-slate-400 text-[11px]">可连续添加多条商品/物品分割扣款</span>
                    </div>

                    {/* 明细项输入行 */}
                    <div className="grid grid-cols-6 gap-2 p-2.5 bg-[#0B0F17] rounded-xl border border-[#2A3447]/60 items-end">
                      <div className="col-span-2">
                        <label className="text-[10px] text-slate-400">物品名称 (必填)</label>
                        <input
                          type="text"
                          placeholder="物品名称"
                          value={tempName}
                          onChange={(e) => setTempName(e.target.value)}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded px-2.5 py-1 text-slate-100"
                        />
                      </div>
                      <div>
                        <label className="text-[10px] text-slate-400">单价 (必填)</label>
                        <input
                          type="number"
                          step="0.01"
                          placeholder="单价"
                          value={tempAmount}
                          onChange={(e) => setTempAmount(e.target.value ? parseFloat(e.target.value) : '')}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded px-2.5 py-1 text-slate-100 font-mono"
                        />
                      </div>
                      <div>
                        <label className="text-[10px] text-slate-400">数量</label>
                        <input
                          type="number"
                          step="1"
                          placeholder="数量"
                          value={tempQty}
                          onChange={(e) => setTempQty(e.target.value ? parseFloat(e.target.value) : 1)}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded px-2.5 py-1 text-slate-100 font-mono"
                        />
                      </div>
                      <div>
                        <label className="text-[10px] text-slate-400">具体备注</label>
                        <input
                          type="text"
                          placeholder="备注"
                          value={tempDesc}
                          onChange={(e) => setTempDesc(e.target.value)}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded px-2.5 py-1 text-slate-100"
                        />
                      </div>
                      <div className="flex gap-1">
                        <button
                          type="button"
                          onClick={addBatchItem}
                          className={`flex-1 py-1 px-2 ${editingBatchKey ? 'bg-amber-600 hover:bg-amber-500' : 'bg-emerald-600 hover:bg-emerald-500'} text-white font-bold rounded flex items-center justify-center gap-1 transition`}
                        >
                          <PlusCircle className="w-3.5 h-3.5" />
                          {editingBatchKey ? '更新' : '添加'}
                        </button>
                        {editingBatchKey && (
                          <button
                            type="button"
                            onClick={cancelEditBatchItem}
                            className="py-1 px-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded text-[10px]"
                          >
                            取消
                          </button>
                        )}
                      </div>
                    </div>

                    {/* 已加列表 (简化外框) */}
                    {batchItems.length > 0 && (
                      <div className="overflow-x-auto bg-[#0B0F17] rounded-xl border border-[#2A3447]/60">
                        <table className="w-full text-left text-[11px]">
                          <thead>
                            <tr className="border-b border-[#2A3447] text-slate-400 bg-[#131924]/40">
                              <th className="py-2 px-3">内容/名称</th>
                              <th className="py-2 px-3 text-right">金额(单价)</th>
                              <th className="py-2 px-3 text-center">数量</th>
                              <th className="py-2 px-3 text-right">小计</th>
                              <th className="py-2 px-3">具体备注</th>
                              <th className="py-2 px-3 text-center">操作</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-[#2A3447]/40">
                            {batchItems.map(item => (
                              <tr key={item.key} className={editingBatchKey === item.key ? 'bg-amber-500/10' : 'hover:bg-[#131924]/50'}>
                                <td className="py-2 px-3 font-medium text-slate-200">{item.name}</td>
                                <td className="py-2 px-3 text-right font-mono text-slate-300">¥{item.amount.toFixed(2)}</td>
                                <td className="py-2 px-3 text-center font-mono text-slate-300">{item.qty}</td>
                                <td className="py-2 px-3 text-right font-mono font-bold text-violet-400">¥{(item.amount * item.qty).toFixed(2)}</td>
                                <td className="py-2 px-3 text-slate-400">{item.desc || '-'}</td>
                                <td className="py-2 px-3 text-center">
                                  <div className="flex items-center justify-center gap-2">
                                    <button
                                      type="button"
                                      onClick={() => startEditBatchItem(item)}
                                      className="text-violet-400 hover:text-violet-300 hover:underline font-medium"
                                    >
                                      编辑
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => removeBatchItem(item.key)}
                                      className="text-rose-400 hover:text-rose-300 hover:underline font-medium"
                                    >
                                      移除
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {/* 结算汇总 */}
                    <div className="flex justify-end pt-2 text-xs text-right space-y-1 flex-col font-mono">
                      <div>物品小计: <span className="font-bold text-slate-200">¥{batchItemsSubtotal.toFixed(2)}</span></div>
                      <div>共同邮费: <span className="font-bold text-slate-200">¥{(Number(batchShippingFee) || 0).toFixed(2)}</span></div>
                      <div className="text-sm pt-1">
                        订单扣款总计: <span className="font-bold text-purple-400 text-base">¥{batchTotalWithShipping.toFixed(2)}</span>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                /* 普通单项收支表单 */
                <div className="space-y-3 pt-1">
                  <div className="grid grid-cols-2 gap-3">
                    <FormField label="金额" required>
                      <input
                        type="number"
                        step="0.01"
                        placeholder="请输入金额"
                        value={recAmount}
                        onChange={(e) => setRecAmount(e.target.value ? parseFloat(e.target.value) : '')}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                      />
                    </FormField>

                    <FormField label="币种" required>
                      <select
                        value={recCurrency}
                        onChange={(e) => setRecCurrency(e.target.value)}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                      >
                        <option value="CNY">CNY (¥)</option>
                        <option value="JPY">JPY (￥)</option>
                      </select>
                    </FormField>
                  </div>

                  {/* 账户选择 vs 非现金提示 */}
                  {!isNonCash ? (
                    <FormField label={recType === '收入' ? '入账账户' : '操作账户'} required>
                      <select
                        value={accountId}
                        onChange={(e) => handleAccountChange(Number(e.target.value))}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                      >
                        <option value="">-- 选择账户 --</option>
                        {(cashAccounts || []).map(a => (
                          <option key={a.id} value={a.id}>[{a.currency}] {a.name} (余额: ¥{a.amount})</option>
                        ))}
                      </select>
                    </FormField>
                  ) : (
                    <div className="p-2 bg-blue-500/10 border border-blue-500/30 rounded-lg text-blue-300 text-[11px] flex items-center gap-2">
                      <Info className="w-4 h-4 flex-shrink-0" />
                      💡 此操作为纯资产账面价值核销或增加，不影响流动资金账户。
                    </div>
                  )}

                  <div className="grid grid-cols-2 gap-3">
                    <FormField label={recType === '收入' ? '付款方/资金来源 (选填)' : '收款方/店铺名称 (选填)'}>
                      <input
                        type="text"
                        placeholder="如：某淘宝店、公司A"
                        value={recShop}
                        onChange={(e) => setRecShop(e.target.value)}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                      />
                    </FormField>

                    <FormField label="相关页面网址 (选填)">
                      <input
                        type="url"
                        placeholder="如：淘宝或Booth宝贝链接"
                        value={recUrl}
                        onChange={(e) => setRecUrl(e.target.value)}
                        className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                      />
                    </FormField>
                  </div>

                  <FormField label="业务明细描述/其他备注">
                    <input
                      type="text"
                      placeholder="如：顺丰快递费、购买打包纸箱等 (必填)"
                      value={recDesc}
                      onChange={(e) => setRecDesc(e.target.value)}
                      className="w-full bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                    />
                  </FormField>
                </div>
              )}
            </div>
          )}

          {/* 模态框底部确认按钮 */}
          <div className="flex justify-end gap-2 pt-3 border-t border-[#2A3447]">
            <button
              type="button"
              onClick={closeModal}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={
                generalCreateMutation.isPending ||
                pendingCreateMutation.isPending ||
                batchCreateMutation.isPending ||
                exchangeMutation.isPending ||
                debtCreateMutation.isPending ||
                debtRepayMutation.isPending ||
                transferMutation.isPending
              }
              className="px-6 py-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white font-bold rounded-lg shadow-lg shadow-violet-600/20 transition"
            >
              确认保存记账
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default FinancePage;
