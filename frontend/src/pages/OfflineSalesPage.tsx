// frontend/src/pages/OfflineSalesPage.tsx
import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import {
  Store,
  ShoppingBag,
  CheckCircle2,
  Maximize2,
  Minimize2,
  Languages,
  Minus,
  Plus,
  ShoppingCart,
  History,
  AlertTriangle,
  Loader2
} from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Modal } from '../components/ui/Modal';
import { FormField } from '../components/ui/FormField';

const POS_TRANSLATIONS: Record<string, Record<string, string>> = {
  zh: {
    active_template: "当前活动收银模板：",
    back_to_cashier: "🔙 返回收银台",
    history_orders: "📜 历史交易流水",
    exit_fullscreen: "📴 退出专注全屏",
    open_fullscreen: "📺 开启收银全屏",
    history_orders_title: "📜 已结账历史交易全览",
    order_no: "交易单号",
    order_date: "成交日期",
    order_items: "购买商品明细",
    order_amount: "交易额",
    received_amount: "实收记账额",
    notes: "流向备注",
    action: "操作",
    delete_confirm_title: "确定要删除此订单并回滚吗？",
    delete_confirm_desc_1: "此操作将永久删除展会订单 ",
    delete_confirm_desc_2: "，回滚已扣减的模板分配额度、还原出货仓库对应的实物库存，并全额扣减已记账的现金流水与资产！是否确定？",
    delete_confirm_btn: "确定删除",
    exhibition_panel: "🛍️ 展会选购面板：",
    source_warehouse: "大货库存提取来源仓: ",
    added_cart_prefix: "已加购 ",
    added_cart_suffix: " 件",
    recent_ledger: "📋 近期本地模板成交流水 (快捷对账)",
    items_detail: "商品明细",
    original_subtotal: "原价小计",
    net_received: "实收净额",
    cart_title: "🧾 POS 结账清单",
    clear_cart: "清空选购",
    cart_empty: "购物车为空",
    select_payment: "💵 选择支付媒介：",
    pay_cash: "💵 现金支付",
    pay_paypay: "📱 PayPay 扫码",
    total_due: "应收总价:",
    paypay_fee_label: "PayPay 扣减扣点 (1.98%):",
    net_receive_label: "预计实际收款入账金额:",
    deposit_account: "物理入账账户",
    checkout_btn: "✅ 完成交易并扣减库存记账",
    submitting_btn: "结算中...",
    out_of_stock: "🚫 售罄",
    no_stock: "无货",
    revoke: "撤销",
    submitting_order: "正在提交订单中，请稍候...",
    empty_template_warning: "⚠️ 线下展会收银模板为空！请先点击右侧“模板配置”Tab建立至少一个收银模板配置。",
  },
  en: {
    active_template: "Active Template:",
    back_to_cashier: "🔙 Back to Cashier",
    history_orders: "📜 History Orders",
    exit_fullscreen: "📴 Exit Fullscreen",
    open_fullscreen: "📺 Open Fullscreen",
    history_orders_title: "📜 History Transaction List",
    order_no: "Order No",
    order_date: "Date",
    order_items: "Items Detail",
    order_amount: "Total Amt",
    received_amount: "Received Amt",
    notes: "Remarks",
    action: "Action",
    delete_confirm_title: "Delete Order & Rollback?",
    delete_confirm_desc_1: "This will permanently delete order ",
    delete_confirm_desc_2: ", rollback template quantity, restore physical stock, and reverse all asset ledgers! Confirm?",
    delete_confirm_btn: "Confirm Delete",
    exhibition_panel: "🛍️ Exhibition Panel:",
    source_warehouse: "Source Warehouse: ",
    added_cart_prefix: "Added ",
    added_cart_suffix: " qty",
    recent_ledger: "📋 Recent Template Transactions (Quick Audit)",
    items_detail: "Items Detail",
    original_subtotal: "Subtotal",
    net_received: "Net Received",
    cart_title: "🧾 POS Checkout List",
    clear_cart: "Clear Cart",
    cart_empty: "Cart is empty",
    select_payment: "💵 Select Payment:",
    pay_cash: "💵 Cash",
    pay_paypay: "📱 PayPay Scan",
    total_due: "Total Due:",
    paypay_fee_label: "PayPay Fee (1.98%):",
    net_receive_label: "Est. Net Income:",
    deposit_account: "Deposit Account",
    checkout_btn: "✅ Checkout & Update Stock/Ledger",
    submitting_btn: "Submitting...",
    out_of_stock: "🚫 Out of stock",
    no_stock: "No Stock",
    revoke: "Revoke",
    submitting_order: "Submitting order, please wait...",
    empty_template_warning: "⚠️ Offline checkout template is empty! Please click 'Template Config' on the right to create at least one template.",
  },
  ja: {
    active_template: "現在のレジテンプレート：",
    back_to_cashier: "🔙 レジに戻る",
    history_orders: "📜 取引履歴",
    exit_fullscreen: "📴 フルスクリーン終了",
    open_fullscreen: "📺 フルスクリーン開始",
    history_orders_title: "📜 会計済み取引履歴一覧",
    order_no: "注文番号",
    order_date: "成約日",
    order_items: "購入商品明細",
    order_amount: "取引額",
    received_amount: "実収額",
    notes: "備考",
    action: "操作",
    delete_confirm_title: "この注文を削除してロールバックしますか？",
    delete_confirm_desc_1: "この操作は展示会注文 ",
    delete_confirm_desc_2: " を永久に削除し、テンプレート割当量を戻し、実物在庫を復元し、記帳されたキャッシュフローと資産を全額差し引きます！よろしいですか？",
    delete_confirm_btn: "削除確定",
    exhibition_panel: "🛍️ 展示会商品パネル：",
    source_warehouse: "出庫元倉庫: ",
    added_cart_prefix: "加算済み ",
    added_cart_suffix: " 点",
    recent_ledger: "📋 最近のローカル取引履歴 (簡易照合)",
    items_detail: "商品明细",
    original_subtotal: "小計",
    net_received: "実収純額",
    cart_title: "🧾 POS 会計リスト",
    clear_cart: "カートを空にする",
    cart_empty: "カートは空です",
    select_payment: "💵 決済方法選択：",
    pay_cash: "💵 現金決済",
    pay_paypay: "📱 PayPay決済",
    total_due: "お会計金額：",
    paypay_fee_label: "PayPay決済手数料 (1.98%):",
    net_receive_label: "入金予定額：",
    deposit_account: "入金先口座",
    checkout_btn: "✅ 会計完了（在庫減算・記帳）",
    submitting_btn: "送信中...",
    out_of_stock: "🚫 完売",
    no_stock: "在庫なし",
    revoke: "キャンセル",
    submitting_order: "注文を送信中、しばらくお待ちください...",
    empty_template_warning: "⚠️ 展示会レジテンプレートが空です！右側の「テンプレート設定」タブをクリックして、少なくとも1つのテンプレートを作成してください。",
  }
};

interface OfflineTemplateItem {
  id?: number;
  product_color: number;
  product_name: string;
  variant: string;
  preset_price: number;
  remaining_quantity?: number;
  quantity?: number;
  image_data?: string;
}

interface OfflineTemplate {
  id: number;
  name: string;
  code: string;
  currency: string;
  warehouse_id?: number;
  warehouse_name?: string;
  platform?: string;
  items?: OfflineTemplateItem[];
}

interface CartItem {
  product_color: number;
  product_name: string;
  variant: string;
  unit_price: number;
  qty: number;
  image_data?: string;
}

interface AssignableItem {
  product_color: number;
  product_name: string;
  variant: string;
  sku_code: string;
  img_data: string;
  preset_price: number;
  quantity: number;
  max_stock: number;
  is_selected: boolean;
}

const getImageUrl = (url?: string) => {
  if (!url) return '';
  if (url.startsWith('data:') || url.startsWith('http://') || url.startsWith('https://')) {
    return url;
  }
  const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
  return `${baseUrl}${url.startsWith('/') ? '' : '/'}${url}`;
};

const applyTemplateToAssignableList = (tpl: OfflineTemplate | null, baseList: AssignableItem[]): AssignableItem[] => {
  if (!baseList || baseList.length === 0) return [];
  if (!tpl || !tpl.items || tpl.items.length === 0) {
    return baseList.map(item => ({ ...item, is_selected: false, quantity: 0 }));
  }
  const colorMap = new Map<number, OfflineTemplateItem>();
  const nameVariantMap = new Map<string, OfflineTemplateItem>();

  tpl.items.forEach(i => {
    if (i.product_color) {
      colorMap.set(i.product_color, i);
    }
    if (i.product_name && i.variant) {
      nameVariantMap.set(`${i.product_name.trim()}_${i.variant.trim()}`, i);
    }
  });

  return baseList.map(item => {
    const key = `${item.product_name.trim()}_${item.variant.trim()}`;
    const matched = (item.product_color ? colorMap.get(item.product_color) : undefined) || nameVariantMap.get(key);
    if (matched) {
      return {
        ...item,
        is_selected: true,
        preset_price: matched.preset_price !== undefined && matched.preset_price !== null ? matched.preset_price : item.preset_price,
        quantity: matched.quantity !== undefined && matched.quantity !== null ? matched.quantity : (matched.remaining_quantity || 0),
      };
    }
    return {
      ...item,
      is_selected: false,
      quantity: 0,
    };
  });
};

export const OfflineSalesPage: React.FC = () => {
  const queryClient = useQueryClient();

  // Mode & Lang State
  const [activeTab, setActiveTab] = useState<'pos' | 'template'>('pos');
  const [posLang, setPosLang] = useState<'zh' | 'en' | 'ja'>('zh');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showHistoryOnly, setShowHistoryOnly] = useState(false);
  const [revokeOrderNo, setRevokeOrderNo] = useState<string | null>(null);

  // Active POS State
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [payMethod, setPayMethod] = useState<'现金' | 'PayPay'>('现金');
  const [depositAccount, setDepositAccount] = useState('');
  const [orderNo, setOrderNo] = useState(`OFF-${Date.now().toString().slice(-6)}`);

  // Template Manager Form State
  const [tplMode, setTplMode] = useState<'create' | 'edit'>('create');
  const [tplId, setTplId] = useState<number | null>(null);
  const [tplName, setTplName] = useState('');
  const [tplCode, setTplCode] = useState('');
  const [tplCurrency, setTplCurrency] = useState('CNY');
  const [tplWarehouseName, setTplWarehouseName] = useState('未分配');
  const [tplPlatform, setTplPlatform] = useState('国内线下');
  const [assignableList, setAssignableList] = useState<AssignableItem[]>([]);

  const tr = POS_TRANSLATIONS[posLang];

  // Fetch Templates
  const { data: templates, refetch: refetchTemplates } = useQuery<OfflineTemplate[]>({
    queryKey: ['offlineTemplates'],
    queryFn: async () => {
      const res = await apiClient.get('/sales/offline-templates/');
      return res.data.results || res.data || [];
    },
  });

  // Fetch Sales Orders History
  const { data: posOrders } = useQuery({
    queryKey: ['posOrdersHistory'],
    queryFn: async () => {
      const res = await apiClient.get('/sales/orders/');
      return (res.data.results || res.data || []).filter((o: any) => o.order_type === '线下' || o.platform === '线下展会');
    },
  });

  // Fetch Deposit Accounts
  const { data: cashAccounts } = useQuery({
    queryKey: ['cashAccountsPOS'],
    queryFn: async () => {
      const res = await apiClient.get('/finance/records/cash-accounts/');
      return res.data || [];
    },
  });

  // Fetch Assignable Products for Template Config
  const { data: assignableData, isLoading: isAssignableLoading } = useQuery<AssignableItem[]>({
    queryKey: ['assignableItems'],
    queryFn: async () => {
      const res = await apiClient.get('/sales/offline-templates/assignable-items/');
      const raw = res.data;
      if (Array.isArray(raw)) return raw;
      if (raw && Array.isArray(raw.results)) return raw.results;
      if (raw && Array.isArray(raw.items)) return raw.items;
      return [];
    },
    enabled: activeTab === 'template',
  });

  useEffect(() => {
    if (Array.isArray(assignableData) && assignableData.length > 0) {
      if (tplMode === 'edit') {
        const target = templates?.find(t => t.id === tplId) || templates?.[0] || null;
        if (target && !tplId) {
          setTplId(target.id);
          setTplName(target.name);
          setTplCode(target.code);
          setTplCurrency(target.currency);
          setTplWarehouseName(target.warehouse_name || '未分配');
          setTplPlatform(target.platform || '国内线下');
        }
        setAssignableList(applyTemplateToAssignableList(target, assignableData));
      } else {
        setAssignableList(assignableData.map(i => ({ ...i, is_selected: false, quantity: 0 })));
      }
    }
  }, [assignableData, templates, tplMode, tplId]);

  // Set default active template
  useEffect(() => {
    if (templates && templates.length > 0 && selectedTemplateId === null) {
      setSelectedTemplateId(templates[0].id);
    }
  }, [templates]);

  const activeTemplate = templates?.find(t => t.id === selectedTemplateId) || templates?.[0];
  const templateCurrency = activeTemplate?.currency || 'CNY';

  const filteredCashAccounts = (cashAccounts || []).filter((a: any) => !templateCurrency || a.currency === templateCurrency);

  useEffect(() => {
    if (filteredCashAccounts.length > 0) {
      const exists = filteredCashAccounts.some((a: any) => a.name === depositAccount);
      if (!exists) {
        const defaultMatch = filteredCashAccounts.find((a: any) => a.name.includes("微信") || a.name.includes("展会") || a.name.includes("现金") || a.name.includes("支付宝"));
        setDepositAccount(defaultMatch ? defaultMatch.name : filteredCashAccounts[0].name);
      }
    }
  }, [filteredCashAccounts, activeTemplate]);

  const handlePayMethodChange = (method: '现金' | 'PayPay') => {
    setPayMethod(method);
    if (filteredCashAccounts && filteredCashAccounts.length > 0) {
      let matched = null;
      if (method === 'PayPay') {
        matched = filteredCashAccounts.find((a: any) => a.name.toLowerCase().includes('paypay'));
      } else {
        matched = filteredCashAccounts.find((a: any) => a.name.includes('现金') || a.name.toLowerCase().includes('cash'));
      }
      if (matched) {
        setDepositAccount(matched.name);
      }
    }
  };

  const toggleFullscreen = () => {
    const next = !isFullscreen;
    setIsFullscreen(next);
    if (next) {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
      }
    } else {
      if (document.fullscreenElement) {
        document.exitFullscreen().catch(() => {});
      }
    }
  };

  // POS Checkout Mutation
  const checkoutMutation = useMutation({
    mutationFn: async () => {
      const itemsPayload = cart.map(c => ({
        product_color: c.product_color,
        quantity: c.qty,
        unit_price: c.unit_price,
      }));

      await apiClient.post('/sales/orders/create_order/', {
        order_no: orderNo,
        platform: activeTemplate?.platform || '线下展会',
        currency: activeTemplate?.currency || 'CNY',
        order_type: '线下',
        target_account_name: depositAccount,
        pay_method: payMethod,
        items: itemsPayload,
      });
    },
    onSuccess: () => {
      alert('✅ 结算成功！已更新实物库存与现金流动资金流水。');
      setCart([]);
      setOrderNo(`OFF-${Date.now().toString().slice(-6)}`);
      queryClient.invalidateQueries({ queryKey: ['posOrdersHistory'] });
      queryClient.invalidateQueries({ queryKey: ['financialSummary'] });
    },
    onError: (err: any) => {
      alert(`结算失败: ${err.response?.data?.error || err.message}`);
    },
  });

  // Revoke Order Mutation
  const revokeMutation = useMutation({
    mutationFn: async (no: string) => {
      await apiClient.post('/sales/orders/revoke-order/', { order_no: no });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['posOrdersHistory'] });
      queryClient.invalidateQueries({ queryKey: ['financialSummary'] });
    },
  });

  // Save Template Mutation
  const saveTemplateMutation = useMutation({
    mutationFn: async () => {
      const selectedItems = assignableList
        .filter(i => i.is_selected)
        .map(i => ({
          product_color: i.product_color,
          preset_price: i.preset_price,
          quantity: i.quantity,
        }));

      await apiClient.post('/sales/offline-templates/save-template-full/', {
        id: tplMode === 'edit' ? tplId : 0,
        name: tplName,
        code: tplCode,
        currency: tplCurrency,
        warehouse_name: tplWarehouseName,
        platform: tplPlatform,
        items: selectedItems,
      });
    },
    onSuccess: () => {
      alert('💾 模板保存成功！');
      refetchTemplates();
      setTplName('');
      setTplCode('');
    },
    onError: (err: any) => {
      alert(`保存失败: ${err.response?.data?.error || err.message}`);
    }
  });

  // Delete Template Mutation
  const deleteTemplateMutation = useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/sales/offline-templates/${id}/`);
    },
    onSuccess: () => {
      alert('收银模板已成功注销！');
      refetchTemplates();
      setTplMode('create');
      setTplId(null);
      setTplName('');
      setTplCode('');
    },
    onError: (err: any) => {
      alert(`注销失败: ${err.response?.data?.error || err.message}`);
    }
  });

  // Cart operations
  const addToCart = (item: OfflineTemplateItem) => {
    setCart(prev => {
      const existing = prev.find(i => i.product_color === item.product_color);
      if (existing) {
        return prev.map(i => i.product_color === item.product_color ? { ...i, qty: i.qty + 1 } : i);
      }
      return [...prev, {
        product_color: item.product_color,
        product_name: item.product_name,
        variant: item.variant,
        unit_price: item.preset_price || 100,
        qty: 1,
        image_data: item.image_data,
      }];
    });
  };

  const removeFromCart = (productColorId: number) => {
    setCart(prev => {
      const existing = prev.find(i => i.product_color === productColorId);
      if (existing && existing.qty > 1) {
        return prev.map(i => i.product_color === productColorId ? { ...i, qty: i.qty - 1 } : i);
      }
      return prev.filter(i => i.product_color !== productColorId);
    });
  };

  const cartTotal = cart.reduce((sum, item) => sum + (item.unit_price * item.qty), 0);
  const paypayFee = payMethod === 'PayPay' ? cartTotal * 0.0198 : 0;
  const paypayEstimatedReceive = cartTotal - paypayFee;

  const currSymbol = activeTemplate?.currency === 'JPY' ? '￥' : '¥';

  const hasTemplates = (templates && templates.length > 0);

  return (
    <div className={`space-y-6 ${isFullscreen ? 'fixed inset-0 z-50 bg-[#0B0F17] p-6 overflow-y-auto' : ''}`}>
      {/* Submitting Loading Modal Overlay (Poor network prompt requirement) */}
      {checkoutMutation.isPending && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#131924] border border-[#2A3447] rounded-2xl p-6 max-w-xs w-full flex flex-col items-center justify-center space-y-4 shadow-2xl">
            <Loader2 className="w-10 h-10 text-violet-400 animate-spin" />
            <p className="text-sm font-medium text-slate-200 text-center">
              {tr.submitting_order}
            </p>
          </div>
        </div>
      )}

      {/* Revoke Order Modal Confirmation */}
      {revokeOrderNo && (
        <Modal
          isOpen={!!revokeOrderNo}
          onClose={() => setRevokeOrderNo(null)}
          title={tr.delete_confirm_title}
        >
          <div className="space-y-4 text-xs text-slate-300">
            <p>
              {tr.delete_confirm_desc_1}
              <span className="font-bold text-violet-400 font-mono">#{revokeOrderNo}</span>
              {tr.delete_confirm_desc_2}
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setRevokeOrderNo(null)}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition"
              >
                取消
              </button>
              <button
                onClick={() => {
                  revokeMutation.mutate(revokeOrderNo);
                  setRevokeOrderNo(null);
                }}
                className="px-3 py-1.5 bg-rose-600 hover:bg-rose-500 text-white font-bold rounded-lg transition"
              >
                {tr.delete_confirm_btn}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {!isFullscreen && (
        <PageHeader
          title="🏪 线下展会模式"
          subtitle="展会 POS 收银台、PayPay 1.98% 手续费自动清算与线下场景模板管理"
        />
      )}

      {/* Mode Tabs */}
      {!isFullscreen && (
        <div className="flex border-b border-[#2A3447]">
          <button
            onClick={() => setActiveTab('pos')}
            className={`px-4 py-2.5 text-xs font-bold transition flex items-center gap-2 border-b-2 ${
              activeTab === 'pos'
                ? 'border-emerald-500 text-emerald-300 bg-emerald-500/10'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Store className="w-4 h-4" />
            💻 POS 收银台
          </button>
          <button
            onClick={() => setActiveTab('template')}
            className={`px-4 py-2.5 text-xs font-bold transition flex items-center gap-2 border-b-2 ${
              activeTab === 'template'
                ? 'border-emerald-500 text-emerald-300 bg-emerald-500/10'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <ShoppingBag className="w-4 h-4" />
            ⚙️ 模板配置
          </button>
        </div>
      )}

      {/* TAB 1: POS CASHIER */}
      {activeTab === 'pos' && (
        <div className="space-y-6">
          {!hasTemplates ? (
            <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <span>{tr.empty_template_warning}</span>
            </div>
          ) : (
            <>
              {/* Top Bar: Template Selector & Actions */}
              <div className="p-4 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] flex flex-wrap items-center justify-between gap-3 text-xs">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-slate-200">{tr.active_template}</span>
                  <select
                    value={selectedTemplateId || ''}
                    onChange={(e) => setSelectedTemplateId(Number(e.target.value))}
                    disabled={isFullscreen}
                    className="bg-[#0B0F17] border border-[#2A3447] text-slate-100 rounded-lg px-3 py-1.5 font-mono"
                  >
                    {(templates || []).map((t) => (
                      <option key={t.id} value={t.id}>{t.name} ({t.code})</option>
                    ))}
                  </select>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowHistoryOnly(!showHistoryOnly)}
                    className="px-3 py-1.5 bg-violet-600/20 hover:bg-violet-600/30 text-violet-300 border border-violet-500/30 font-medium rounded-lg transition flex items-center gap-1.5"
                  >
                    <History className="w-3.5 h-3.5" />
                    {showHistoryOnly ? tr.back_to_cashier : tr.history_orders}
                  </button>
                  <button
                    onClick={toggleFullscreen}
                    className={`px-3 py-1.5 font-medium rounded-lg border transition flex items-center gap-1.5 ${
                      isFullscreen
                        ? 'bg-amber-600/20 text-amber-300 border-amber-500/30'
                        : 'bg-blue-600/20 text-blue-300 border-blue-500/30'
                    }`}
                  >
                    {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
                    {isFullscreen ? tr.exit_fullscreen : tr.open_fullscreen}
                  </button>
                </div>
              </div>

              {showHistoryOnly ? (
                /* Full History Orders View */
                <div className="p-5 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] space-y-4">
                  <h3 className="text-sm font-bold text-slate-100">{tr.history_orders_title}</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-[#2A3447] text-slate-400">
                          <th className="pb-2 px-2">{tr.order_no}</th>
                          <th className="pb-2 px-2">{tr.order_date}</th>
                          <th className="pb-2 px-2">{tr.order_items}</th>
                          <th className="pb-2 px-2 text-right">{tr.order_amount}</th>
                          <th className="pb-2 px-2 text-right">{tr.received_amount}</th>
                          <th className="pb-2 px-2 text-center">{tr.action}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#2A3447]/50 text-slate-200 font-mono">
                        {(posOrders || []).map((o: any) => (
                          <tr key={o.id} className="hover:bg-[#18202F]">
                            <td className="py-2.5 px-2 font-bold text-violet-300">{o.order_no}</td>
                            <td className="py-2.5 px-2 text-slate-400 font-sans">{o.created_at ? o.created_at.slice(0, 10) : '-'}</td>
                            <td className="py-2.5 px-2 font-sans truncate max-w-xs">
                              {(o.items || []).map((i: any) => `${i.product_name || '商品'} x${i.quantity}`).join(', ')}
                            </td>
                            <td className="py-2.5 px-2 text-right">{currSymbol}{Number(o.total_amount || 0).toFixed(2)}</td>
                            <td className="py-2.5 px-2 text-right font-bold text-emerald-400">
                              {currSymbol}{Number(o.total_amount || 0).toFixed(2)}
                            </td>
                            <td className="py-2.5 px-2 text-center">
                              <button
                                onClick={() => setRevokeOrderNo(o.order_no)}
                                className="px-2 py-1 bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 text-[10px] rounded transition"
                              >
                                {tr.revoke}
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                /* Core 2-Column POS Cashier Screen */
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  {/* Left Column: Product Cards Matrix */}
                  <div className="lg:col-span-2 space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-bold text-slate-200">{tr.exhibition_panel}</h3>
                      <span className="text-[11px] px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                        {tr.source_warehouse}{activeTemplate?.warehouse_name || '未分配'}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                      {(activeTemplate?.items || []).map((item) => {
                        const cartQty = cart.find(c => c.product_color === item.product_color)?.qty || 0;
                        const isOutOfStock = (item.remaining_quantity || 0) <= 0;

                        return (
                          <div
                            key={item.id || item.product_color}
                            onClick={() => !isOutOfStock && addToCart(item)}
                            className={`relative aspect-square rounded-2xl border p-3 flex flex-col justify-between overflow-hidden cursor-pointer transition-all ${
                              isOutOfStock
                                ? 'bg-[#0B0F17] border-slate-800 opacity-60'
                                : 'bg-[#131924] border-[#2A3447] hover:border-violet-500/50 hover:shadow-lg hover:shadow-violet-500/10'
                            }`}
                          >
                            {/* Background Image / Placeholder (Fix image display bug) */}
                            {item.image_data ? (
                              <img
                                src={getImageUrl(item.image_data)}
                                alt={item.product_name}
                                className="absolute inset-0 w-full h-full object-cover z-0 opacity-80"
                              />
                            ) : (
                              <div className="absolute inset-0 w-full h-full bg-gradient-to-br from-violet-900/30 to-violet-950/50 flex items-center justify-center z-0">
                                <ShoppingBag className="w-8 h-8 text-violet-400/40" />
                              </div>
                            )}

                            {/* Title */}
                            <div className="relative z-10 space-y-0.5 max-w-[calc(100%-0.5rem)]">
                              <div className="font-bold text-xs text-white truncate drop-shadow-md">{item.product_name}</div>
                              <div className="text-[10px] text-slate-200 truncate opacity-90 drop-shadow-md">{item.variant}</div>
                            </div>

                            {/* Stock & Price Badges */}
                            <div className="relative z-10 flex items-center justify-between">
                              <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                isOutOfStock ? 'bg-rose-500/80 text-white' : 'bg-emerald-600/90 text-white'
                              }`}>
                                {isOutOfStock ? tr.out_of_stock : `📦 ${item.remaining_quantity || 0}`}
                              </span>
                              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-violet-600/90 text-white">
                                {isOutOfStock ? tr.no_stock : `${currSymbol}${item.preset_price}`}
                              </span>
                            </div>

                            {/* Cart Overlay */}
                            {cartQty > 0 && (
                              <div className="absolute inset-0 bg-slate-950/85 backdrop-blur-xs flex flex-col items-center justify-center gap-1 z-20">
                                <ShoppingCart className="w-5 h-5 text-emerald-400" />
                                <span className="text-xs font-bold text-white">
                                  {tr.added_cart_prefix}{cartQty}{tr.added_cart_suffix}
                                </span>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>

                    {/* Non-fullscreen Recent Transactions Ledger */}
                    {!isFullscreen && (
                      <div className="pt-4 border-t border-[#2A3447] space-y-2">
                        <h4 className="text-xs font-bold text-slate-400">{tr.recent_ledger}</h4>
                        <div className="max-h-52 overflow-y-auto border border-[#2A3447] rounded-xl bg-[#0B0F17]">
                          <table className="w-full text-left text-xs">
                            <thead>
                              <tr className="border-b border-[#2A3447] text-slate-400 bg-[#131924]">
                                <th className="py-1.5 px-2">{tr.order_no}</th>
                                <th className="py-1.5 px-2">{tr.order_date}</th>
                                <th className="py-1.5 px-2">{tr.items_detail}</th>
                                <th className="py-1.5 px-2 text-right">{tr.original_subtotal}</th>
                                <th className="py-1.5 px-2 text-right">{tr.net_received}</th>
                                <th className="py-1.5 px-2 text-center">{tr.action}</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-[#2A3447]/50 text-slate-200 font-mono text-[11px]">
                              {(posOrders || []).slice(0, 10).map((o: any) => (
                                <tr key={o.id} className="hover:bg-[#18202F]">
                                  <td className="py-2 px-2 font-bold text-violet-300">{o.order_no}</td>
                                  <td className="py-2 px-2 text-slate-400 font-sans">{o.created_at ? o.created_at.slice(0, 10) : '-'}</td>
                                  <td className="py-2 px-2 font-sans truncate max-w-[150px]">
                                    {(o.items || []).map((i: any) => `${i.product_name || '商品'} x${i.quantity}`).join(', ')}
                                  </td>
                                  <td className="py-2 px-2 text-right">{currSymbol}{Number(o.total_amount || 0).toFixed(2)}</td>
                                  <td className="py-2 px-2 text-right font-bold text-emerald-400">
                                    {currSymbol}{Number(o.total_amount || 0).toFixed(2)}
                                  </td>
                                  <td className="py-2 px-2 text-center">
                                    <button
                                      onClick={() => setRevokeOrderNo(o.order_no)}
                                      className="px-2 py-0.5 bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 text-[10px] rounded transition"
                                    >
                                      {tr.revoke}
                                    </button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Right Column: POS Cart & Checkout */}
                  <div className="p-5 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] flex flex-col justify-between space-y-4">
                    <div className="space-y-4">
                      <div className="flex items-center justify-between border-b border-[#2A3447] pb-3">
                        <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                          <span>🧾</span> {tr.cart_title} ({cart.length})
                        </h3>
                        {cart.length > 0 && (
                          <button
                            onClick={() => setCart([])}
                            className="text-[11px] text-slate-400 hover:text-rose-400 transition"
                          >
                            {tr.clear_cart}
                          </button>
                        )}
                      </div>

                      {/* Cart Items List */}
                      <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                        {cart.length === 0 ? (
                          <div className="text-center py-8 text-slate-500 text-xs">
                            {tr.cart_empty}
                          </div>
                        ) : (
                          cart.map((item) => (
                            <div
                              key={item.product_color}
                              className="p-2.5 bg-[#0B0F17] rounded-xl border border-[#2A3447] flex items-center justify-between text-xs gap-2"
                            >
                              {/* Cart Item Thumbnail */}
                              {item.image_data ? (
                                <img
                                  src={getImageUrl(item.image_data)}
                                  alt={item.product_name}
                                  className="w-8 h-8 object-cover rounded flex-shrink-0"
                                />
                              ) : (
                                <div className="w-8 h-8 rounded bg-slate-800 flex items-center justify-center flex-shrink-0">
                                  <ShoppingBag className="w-4 h-4 text-violet-400" />
                                </div>
                              )}

                              <div className="flex-1 min-w-0">
                                <div className="font-bold text-slate-200 truncate">{item.product_name}</div>
                                <div className="text-[10px] text-slate-400 truncate">{item.variant}</div>
                              </div>

                              <div className="flex items-center gap-2 font-mono">
                                <span className="text-slate-300 font-bold">{currSymbol}{(item.unit_price * item.qty).toFixed(2)}</span>
                                <div className="flex items-center gap-1 bg-[#18202F] rounded-lg p-0.5 border border-[#2A3447]">
                                  <button onClick={() => removeFromCart(item.product_color)} className="p-1 text-slate-400 hover:text-rose-400 transition">
                                    <Minus className="w-3 h-3" />
                                  </button>
                                  <span className="px-1 text-white font-bold">{item.qty}</span>
                                  <button onClick={() => addToCart({ ...item, preset_price: item.unit_price })} className="p-1 text-slate-400 hover:text-emerald-400 transition">
                                    <Plus className="w-3 h-3" />
                                  </button>
                                </div>
                              </div>
                            </div>
                          ))
                        )}
                      </div>

                      {/* Payment Method Selector */}
                      <div className="space-y-2 pt-2 border-t border-[#2A3447] text-xs">
                        <label className="block text-slate-400 font-bold">{tr.select_payment}</label>
                        <div className="grid grid-cols-2 gap-2">
                          <button
                            onClick={() => handlePayMethodChange('现金')}
                            className={`py-2 px-3 rounded-xl border font-bold transition text-xs ${
                              payMethod === '现金'
                                ? 'bg-violet-600 border-violet-500 text-white'
                                : 'bg-[#0B0F17] border-[#2A3447] text-slate-300'
                            }`}
                          >
                            {tr.pay_cash}
                          </button>
                          <button
                            onClick={() => handlePayMethodChange('PayPay')}
                            className={`py-2 px-3 rounded-xl border font-bold transition text-xs ${
                              payMethod === 'PayPay'
                                ? 'bg-violet-600 border-violet-500 text-white'
                                : 'bg-[#0B0F17] border-[#2A3447] text-slate-300'
                            }`}
                          >
                            {tr.pay_paypay}
                          </button>
                        </div>

                        {/* PayPay Fee Breakdown */}
                        {payMethod === 'PayPay' && (
                          <div className="p-2.5 bg-rose-500/10 rounded-xl border border-rose-500/20 space-y-1 text-[11px] font-mono">
                            <div className="flex justify-between text-slate-400">
                              <span>{tr.paypay_fee_label}</span>
                              <span className="text-rose-400 font-bold">-{currSymbol}{paypayFee.toFixed(2)}</span>
                            </div>
                            <div className="flex justify-between text-slate-200 font-bold border-t border-rose-500/20 pt-1">
                              <span>{tr.net_receive_label}</span>
                              <span className="text-emerald-400">{currSymbol}{paypayEstimatedReceive.toFixed(2)}</span>
                            </div>
                          </div>
                        )}

                        {/* Deposit Account */}
                        <div>
                          <label className="block text-slate-400 mb-1 font-bold">{tr.deposit_account}</label>
                          <select
                            value={depositAccount}
                            onChange={(e) => setDepositAccount(e.target.value)}
                            className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-1.5 text-slate-200 text-xs"
                          >
                            {filteredCashAccounts.map((acc: any) => (
                              <option key={acc.id} value={acc.name}>{acc.name} [{acc.currency}]</option>
                            ))}
                          </select>
                        </div>
                      </div>
                    </div>

                    {/* Checkout Total & Submit */}
                    <div className="space-y-3 pt-4 border-t border-[#2A3447]">
                      <div className="flex justify-between items-center text-sm">
                        <span className="font-bold text-slate-300">{tr.total_due}</span>
                        <span className="text-2xl font-bold font-mono text-emerald-400">
                          {currSymbol}{cartTotal.toFixed(2)}
                        </span>
                      </div>

                      <button
                        onClick={() => checkoutMutation.mutate()}
                        disabled={cart.length === 0 || checkoutMutation.isPending}
                        className="w-full h-16 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm font-bold rounded-xl shadow-lg shadow-emerald-500/20 transition flex items-center justify-center gap-2"
                      >
                        {checkoutMutation.isPending ? (
                          <>
                            <Loader2 className="w-5 h-5 animate-spin" />
                            <span>{tr.submitting_btn}</span>
                          </>
                        ) : (
                          <>
                            <CheckCircle2 className="w-5 h-5" />
                            <span>{tr.checkout_btn}</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}

          {/* Language Switcher Footer */}
          {!isFullscreen && (
            <div className="flex items-center gap-2 text-xs text-slate-400 pt-2 border-t border-[#2A3447]/50">
              <Languages className="w-4 h-4 text-violet-400" />
              <span>多语言 UI / Language:</span>
              <div className="flex gap-1">
                {(['zh', 'en', 'ja'] as const).map((lang) => (
                  <button
                    key={lang}
                    onClick={() => setPosLang(lang)}
                    className={`px-2 py-0.5 rounded text-[10px] uppercase font-bold transition ${
                      posLang === lang ? 'bg-violet-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {lang}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: TEMPLATE CONFIGURATION */}
      {activeTab === 'template' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column: Template Form */}
          <div className="space-y-4 p-5 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447]">
            <div className="flex border-b border-[#2A3447] pb-3 text-xs">
              <button
                onClick={() => {
                  setTplMode('create');
                  setTplId(null);
                  setTplName('');
                  setTplCode('');
                  setTplCurrency('CNY');
                  setTplWarehouseName('未分配');
                  setTplPlatform('国内线下');
                  if (assignableData) {
                    setAssignableList(applyTemplateToAssignableList(null, assignableData));
                  }
                }}
                className={`flex-1 py-1.5 font-bold rounded-lg transition ${
                  tplMode === 'create' ? 'bg-violet-600 text-white' : 'text-slate-400'
                }`}
              >
                ➕ 新建收银场景模板
              </button>
              <button
                onClick={() => {
                  setTplMode('edit');
                  const target = templates?.find(t => t.id === tplId) || templates?.[0];
                  if (target) {
                    setTplId(target.id);
                    setTplName(target.name);
                    setTplCode(target.code);
                    setTplCurrency(target.currency);
                    setTplWarehouseName(target.warehouse_name || '未分配');
                    setTplPlatform(target.platform || '国内线下');
                    if (assignableData) {
                      setAssignableList(applyTemplateToAssignableList(target, assignableData));
                    }
                  }
                }}
                className={`flex-1 py-1.5 font-bold rounded-lg transition ${
                  tplMode === 'edit' ? 'bg-violet-600 text-white' : 'text-slate-400'
                }`}
              >
                ✏️ 编辑/注销现有模板
              </button>
            </div>

            {tplMode === 'edit' && (
              <FormField label="选择待配置模板">
                <select
                  value={tplId || ''}
                  onChange={(e) => {
                    const id = Number(e.target.value);
                    setTplId(id);
                    const found = templates?.find(t => t.id === id);
                    if (found) {
                      setTplName(found.name);
                      setTplCode(found.code);
                      setTplCurrency(found.currency);
                      setTplWarehouseName(found.warehouse_name || '未分配');
                      setTplPlatform(found.platform || '国内线下');
                      if (assignableData) {
                        setAssignableList(applyTemplateToAssignableList(found, assignableData));
                      }
                    }
                  }}
                  className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 text-xs"
                >
                  <option value="">请选择模板...</option>
                  {(templates || []).map(t => (
                    <option key={t.id} value={t.id}>{t.name} ({t.code})</option>
                  ))}
                </select>
              </FormField>
            )}

            <FormField label="模板场景名称" required>
              <input
                type="text"
                required
                placeholder="如: 2026年广州CP展会"
                value={tplName}
                onChange={(e) => setTplName(e.target.value)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 text-xs"
              />
            </FormField>

            <FormField label="代号/单号前缀" required>
              <input
                type="text"
                required
                placeholder="如: GZCP26"
                value={tplCode}
                onChange={(e) => setTplCode(e.target.value)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 text-xs font-mono"
              />
            </FormField>

            <FormField label="物理结算币种">
              <select
                value={tplCurrency}
                onChange={(e) => setTplCurrency(e.target.value)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 text-xs font-mono"
              >
                <option value="CNY">CNY</option>
                <option value="JPY">JPY</option>
                <option value="USD">USD</option>
              </select>
            </FormField>

            <FormField label="物理出货指定大货仓库">
              <select
                value={tplWarehouseName}
                onChange={(e) => setTplWarehouseName(e.target.value)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 text-xs"
              >
                <option value="未分配">未分配</option>
                <option value="广州1仓">广州1仓</option>
                <option value="东京中转仓">东京中转仓</option>
              </select>
            </FormField>

            <FormField label="销售平台">
              <select
                value={tplPlatform}
                onChange={(e) => setTplPlatform(e.target.value)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 text-xs"
              >
                <option value="国内线下">国内线下</option>
                <option value="日本线下">日本线下</option>
                <option value="线下展会">线下展会</option>
              </select>
            </FormField>

            <div className="flex gap-3 pt-2">
              <button
                onClick={() => saveTemplateMutation.mutate()}
                disabled={saveTemplateMutation.isPending}
                className="flex-1 py-2.5 bg-emerald-600 hover:bg-emerald-500 font-bold text-white text-xs rounded-xl shadow-lg transition"
              >
                💾 保存模板配置
              </button>
              {tplMode === 'edit' && tplId && (
                <button
                  onClick={() => {
                    if (confirm(`确定要注销此模板配置吗？`)) {
                      deleteTemplateMutation.mutate(tplId);
                    }
                  }}
                  disabled={deleteTemplateMutation.isPending}
                  className="flex-1 py-2.5 bg-rose-600 hover:bg-rose-500 font-bold text-white text-xs rounded-xl shadow-lg transition"
                >
                  🗑️ 注销此模板
                </button>
              )}
            </div>
          </div>

          {/* Right Column: Product Assignment List */}
          <div className="lg:col-span-2 p-5 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] space-y-4">
            <h3 className="text-xs font-bold text-slate-200 flex items-center justify-between">
              <span className="flex items-center gap-2">
                <span>🧩</span> 配置该模板分配的货品清单 (实时木桶配装上限校验)
              </span>
              <span className="text-[10px] text-violet-400 font-mono">
                已选 {assignableList.filter(i => i.is_selected).length} / {assignableList.length} 项
              </span>
            </h3>

            {isAssignableLoading ? (
              <div className="flex items-center justify-center p-12 text-slate-400 text-xs gap-2">
                <Loader2 className="w-4 h-4 animate-spin text-violet-400" />
                <span>正在加载全库可分派商品清单...</span>
              </div>
            ) : assignableList.length === 0 ? (
              <div className="flex flex-col items-center justify-center p-12 text-slate-400 text-xs space-y-2 border border-dashed border-[#2A3447] rounded-xl">
                <ShoppingBag className="w-8 h-8 text-slate-500" />
                <p>暂无可分配的商品款色，请先在“商品管理”中录入商品与款式数据。</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[600px] overflow-y-auto pr-1">
                {assignableList.map((item, idx) => (
                <div
                  key={item.product_color}
                  className={`p-3 rounded-xl border text-xs space-y-2 transition ${
                    item.is_selected ? 'bg-violet-600/10 border-violet-500/50' : 'bg-[#0B0F17] border-[#2A3447]'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={item.is_selected}
                      onChange={(e) => {
                        const checked = e.target.checked;
                        setAssignableList(prev => prev.map((it, i) => i === idx ? { ...it, is_selected: checked } : it));
                      }}
                      className="rounded border-[#2A3447]"
                    />
                    {item.img_data ? (
                      <img
                        src={getImageUrl(item.img_data)}
                        alt={item.product_name}
                        className="w-6 h-6 object-cover rounded flex-shrink-0"
                      />
                    ) : (
                      <div className="w-6 h-6 rounded bg-slate-800 flex items-center justify-center flex-shrink-0">
                        <ShoppingBag className="w-3 h-3 text-slate-400" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-slate-100 truncate">{item.product_name}</div>
                      <div className="text-[10px] text-slate-400 truncate">
                        {item.variant} {item.sku_code ? `(SKU: ${item.sku_code})` : ''} (大货整套上限: {item.max_stock})
                      </div>
                    </div>
                  </div>

                  {item.is_selected && (
                    <div className="grid grid-cols-2 gap-2 pt-2 border-t border-[#2A3447]/50 text-[11px]">
                      <div>
                        <label className="block text-slate-400">预设售价</label>
                        <input
                          type="number"
                          value={item.preset_price}
                          onChange={(e) => {
                            const val = parseFloat(e.target.value) || 0;
                            setAssignableList(prev => prev.map((it, i) => i === idx ? { ...it, preset_price: val } : it));
                          }}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded px-2 py-1 text-slate-100 font-mono"
                        />
                      </div>
                      <div>
                        <label className="block text-slate-400">分配数量</label>
                        <input
                          type="number"
                          value={item.quantity}
                          onChange={(e) => {
                            const val = parseInt(e.target.value) || 0;
                            setAssignableList(prev => prev.map((it, i) => i === idx ? { ...it, quantity: val } : it));
                          }}
                          className="w-full bg-[#131924] border border-[#2A3447] rounded px-2 py-1 text-slate-100 font-mono"
                        />
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default OfflineSalesPage;
