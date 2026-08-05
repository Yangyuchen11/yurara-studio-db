// frontend/src/pages/BalancePage.tsx
import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { CompanyBalanceItem } from '../types';
import { DataCard } from '../components/ui/DataCard';
import { FormField } from '../components/ui/FormField';
import { PageHeader } from '../components/ui/PageHeader';
import { Modal } from '../components/ui/Modal';
import {
  Wallet,
  ShoppingBag,
  CreditCard,
  PieChart,
  Plus,
  Trash2,
  Edit2,
  RefreshCw,
  ChevronDown,
  ChevronUp
} from 'lucide-react';

interface CurrencyKpiItem {
  currency: string;
  amount: number;
  amount_str: string;
  amount_cny_equiv: number;
  amount_cny_str: string;
}

interface DisplayRow {
  item_name: string;
  amounts_by_currency: Record<string, string>;
  total_cny_str: string;
}

interface FinancialSummary {
  cash_items: CompanyBalanceItem[];
  manual_assets: CompanyBalanceItem[];
  liabilities: CompanyBalanceItem[];
  equities: CompanyBalanceItem[];
  summary_currencies: string[];
  display_currencies: string[];
  cash_by_currency: CurrencyKpiItem[];
  pure_asset_by_currency: CurrencyKpiItem[];
  total_asset_by_currency: CurrencyKpiItem[];
  liability_by_currency: CurrencyKpiItem[];
  equity_by_currency: CurrencyKpiItem[];
  net_by_currency: CurrencyKpiItem[];
  cash_total_str: string;
  pure_asset_total_str: string;
  total_asset_total_str: string;
  liability_total_str: string;
  equity_total_str: string;
  net_total_str: string;
  assets_rows: DisplayRow[];
  liabilities_rows: DisplayRow[];
  equities_rows: DisplayRow[];
  all_currencies: string[];
}

export const BalancePage: React.FC = () => {
  const queryClient = useQueryClient();

  // Create Cash Account Drawer State
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [newAccName, setNewAccName] = useState('');
  const [newAccCurr, setNewAccCurr] = useState('CNY');

  // Generic Balance Item Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<CompanyBalanceItem | null>(null);
  const [itemType, setItemType] = useState<'cash' | 'manual_asset' | 'liability' | 'equity'>('cash');
  const [name, setName] = useState('');
  const [currency, setCurrency] = useState('CNY');
  const [amount, setAmount] = useState<number | ''>('');
  const [notes, setNotes] = useState('');

  const { data: summary, isLoading, refetch } = useQuery<FinancialSummary>({
    queryKey: ['financialSummary'],
    queryFn: async () => {
      const res = await apiClient.get('/finance/summary/');
      return res.data;
    },
  });

  // Add Cash Account Mutation
  const addAccountMutation = useMutation({
    mutationFn: async () => {
      await apiClient.post('/finance/balance-items/add-account/', {
        name: newAccName,
        currency: newAccCurr,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['financialSummary'] });
      setNewAccName('');
      setIsDrawerOpen(false);
    },
    onError: (err: any) => {
      alert(`开设失败: ${err.response?.data?.error || err.message}`);
    }
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        item_type: itemType,
        name,
        currency,
        amount: Number(amount) || 0,
        notes,
      };
      if (editingItem) {
        await apiClient.put(`/finance/balance-items/${editingItem.id}/`, payload);
      } else {
        await apiClient.post('/finance/balance-items/', payload);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['financialSummary'] });
      closeModal();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/finance/balance-items/${id}/`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['financialSummary'] });
    },
  });

  const openCreateModal = (type: 'cash' | 'manual_asset' | 'liability' | 'equity') => {
    setEditingItem(null);
    setItemType(type);
    setName('');
    setCurrency('CNY');
    setAmount('');
    setNotes('');
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingItem(null);
  };

  const displayCurrencies = summary?.display_currencies || ['CNY', 'JPY'];

  // Helper to render Multi-Currency Breakdown Card (exact Reflex design)
  const renderMultiCurrencyCard = (
    title: string,
    kpis: CurrencyKpiItem[] = [],
    totalStr: string = '¥ 0.00',
    borderColor: string = 'purple'
  ) => {
    return (
      <div className={`p-4 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] border-l-4 border-l-${borderColor}-500 space-y-3`}>
        <div className="text-xs font-bold text-slate-200">{title}</div>
        <div className="space-y-1.5 text-xs">
          {kpis.map((k) => (
            <div key={k.currency} className="flex items-center justify-between font-mono">
              <span className="text-slate-400">{k.currency}:</span>
              <div className="flex items-center gap-2">
                <span className="text-slate-200 font-medium">{k.amount_str}</span>
                {k.currency !== 'CNY' && (
                  <span className="text-slate-500 text-[11px]">≈ {k.amount_cny_str}</span>
                )}
              </div>
            </div>
          ))}
          <div className="border-t border-[#2A3447] pt-2 flex items-center justify-between font-bold">
            <span className="text-slate-300">综合总计(CNY):</span>
            <span className="text-violet-400 font-mono text-sm">{totalStr}</span>
          </div>
        </div>
      </div>
    );
  };

  // Helper to render Simple Total Card
  const renderSimpleCard = (title: string, totalStr: string = '¥ 0.00', borderColor: string = 'emerald') => {
    return (
      <div className={`p-4 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] border-l-4 border-l-${borderColor}-500 space-y-2`}>
        <div className="text-xs font-bold text-slate-200">{title}</div>
        <div className="flex items-center justify-between text-xs font-bold pt-1">
          <span className="text-slate-300">综合总计(CNY):</span>
          <span className="text-violet-400 font-mono text-sm">{totalStr}</span>
        </div>
      </div>
    );
  };

  // Helper to render Dynamic Multi-Currency Columns Table
  const renderDynamicTable = (title: string, rows: DisplayRow[] = [], onCreateAction?: () => void) => {
    return (
      <DataCard
        title={title}
        action={
          onCreateAction && (
            <button
              onClick={onCreateAction}
              className="px-2.5 py-1 bg-violet-600/20 hover:bg-violet-600/30 text-violet-300 border border-violet-500/30 text-xs rounded-lg transition flex items-center gap-1"
            >
              <Plus className="w-3.5 h-3.5" />
              追加科目
            </button>
          )
        }
      >
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-[#2A3447] text-slate-400 font-medium">
                <th className="pb-2 px-2">项目</th>
                {displayCurrencies.map((c) => (
                  <th key={c} className="pb-2 px-2 font-mono">
                    {c}
                  </th>
                ))}
                <th className="pb-2 px-2 text-right font-medium">折合CNY合计</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#2A3447]/50 text-slate-300 font-mono">
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={displayCurrencies.length + 2} className="text-center py-6 text-slate-500 font-sans">
                    暂无资产数据
                  </td>
                </tr>
              ) : (
                rows.map((r, idx) => (
                  <tr key={idx} className="hover:bg-[#18202F]">
                    <td className="py-2.5 px-2 font-sans font-medium text-slate-100">{r.item_name}</td>
                    {displayCurrencies.map((c) => (
                      <td key={c} className="py-2.5 px-2 text-slate-300">
                        {r.amounts_by_currency[c] || '-'}
                      </td>
                    ))}
                    <td className="py-2.5 px-2 text-right font-bold text-violet-400">
                      {r.total_cny_str}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </DataCard>
    );
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="🏢 公司账面概览 (资产负债表与资本)"
        subtitle="多货币动态公司账面资产、固定投入、负债与资本家底"
        action={
          <button
            onClick={() => refetch()}
            className="px-3 py-1.5 bg-[#18202F] hover:bg-[#222C3E] text-slate-200 text-xs font-medium rounded-lg border border-[#2A3447] transition flex items-center gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5 text-violet-400" />
            刷新
          </button>
        }
      />

      {/* Top Drawer: Create Cash Account (matching Reflex create_account_accordion) */}
      <div className="p-4 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447]">
        <button
          onClick={() => setIsDrawerOpen(!isDrawerOpen)}
          className="w-full flex items-center justify-between text-xs font-bold text-slate-200"
        >
          <span className="flex items-center gap-2">
            <Plus className="w-4 h-4 text-emerald-400" />
            追加现金账户 (开设备用金、独立银行卡等专属现金账户)
          </span>
          {isDrawerOpen ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
        </button>

        {isDrawerOpen && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              addAccountMutation.mutate();
            }}
            className="mt-4 pt-4 border-t border-[#2A3447] grid grid-cols-1 sm:grid-cols-3 gap-3 items-end text-xs"
          >
            <div>
              <label className="block text-slate-400 mb-1">账户名称</label>
              <input
                type="text"
                required
                placeholder="如：日常备用金、三井住友银行"
                value={newAccName}
                onChange={(e) => setNewAccName(e.target.value)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">币种 (CNY / JPY / USD ...)</label>
              <input
                type="text"
                required
                placeholder="CNY"
                value={newAccCurr}
                onChange={(e) => setNewAccCurr(e.target.value.toUpperCase())}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
              />
            </div>
            <div>
              <button
                type="submit"
                disabled={addAccountMutation.isPending}
                className="w-full py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-lg transition"
              >
                {addAccountMutation.isPending ? '开设中...' : '确认追加'}
              </button>
            </div>
          </form>
        )}
      </div>

      {/* Dual Column Balance Sheet Grid (matching Reflex balance.py grid layout) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column: Assets */}
        <div className="space-y-4">
          <h2 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <span>🏢</span> 现金与实物资产 (Assets)
          </h2>

          {/* 1. Assets Table */}
          {renderDynamicTable(
            "资产细明",
            summary?.assets_rows,
            () => openCreateModal('manual_asset')
          )}

          {/* 2. Grid of 2 Simple Total Cards */}
          <div className="grid grid-cols-2 gap-3">
            {renderSimpleCard("💵 现金总计", summary?.cash_total_str, "emerald")}
            {renderSimpleCard("🏢 资产总计 (非现金)", summary?.pure_asset_total_str, "blue")}
          </div>

          {/* 3. Total Assets Multi-Currency Card */}
          {renderMultiCurrencyCard(
            "🏛️ 总资产 (现金+资产)",
            summary?.total_asset_by_currency,
            summary?.total_asset_total_str,
            "purple"
          )}

          {/* 4. Net Assets Multi-Currency Card */}
          {renderMultiCurrencyCard(
            "✨ 净资产 (总资产 - 负债)",
            summary?.net_by_currency,
            summary?.net_total_str,
            "amber"
          )}
        </div>

        {/* Right Column: Liabilities & Equities */}
        <div className="space-y-4">
          <h2 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <span>📉</span> 负债与资本 (Liabilities & Equity)
          </h2>

          {/* 1. Liabilities Table */}
          {renderDynamicTable(
            "负债细明",
            summary?.liabilities_rows,
            () => openCreateModal('liability')
          )}

          {/* 2. Liabilities Total Card */}
          {renderMultiCurrencyCard(
            "负债总计",
            summary?.liability_by_currency,
            summary?.liability_total_str,
            "rose"
          )}

          {/* 3. Equities Table */}
          {renderDynamicTable(
            "资本记录",
            summary?.equities_rows,
            () => openCreateModal('equity')
          )}

          {/* 4. Equities Total Card */}
          {renderMultiCurrencyCard(
            "资本总计",
            summary?.equity_by_currency,
            summary?.equity_total_str,
            "emerald"
          )}
        </div>
      </div>

      {/* Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={closeModal}
        title={editingItem ? '编辑账面科目' : '新增账面科目'}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            saveMutation.mutate();
          }}
          className="space-y-4 text-xs"
        >
          <FormField label="科目类别" required>
            <select
              value={itemType}
              onChange={(e) => setItemType(e.target.value as any)}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
            >
              <option value="cash">现金账户 (Cash)</option>
              <option value="manual_asset">固定资产 (Manual Asset)</option>
              <option value="liability">负债 (Liability)</option>
              <option value="equity">资本 / 权益 (Equity)</option>
            </select>
          </FormField>

          <FormField label="科目名称" required>
            <input
              type="text"
              required
              placeholder="例如: 招商银行卡 / 拍摄机材 / 银行贷款"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
            />
          </FormField>

          <div className="grid grid-cols-2 gap-3">
            <FormField label="金额" required>
              <input
                type="number"
                step="0.01"
                required
                placeholder="0.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value ? parseFloat(e.target.value) : '')}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
              />
            </FormField>

            <FormField label="币种" required>
              <select
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
              >
                {(summary?.all_currencies || ['CNY', 'JPY']).map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </FormField>
          </div>

          <FormField label="备注">
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
            />
          </FormField>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={closeModal}
              className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={saveMutation.isPending}
              className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white font-medium rounded-lg"
            >
              {saveMutation.isPending ? '保存中...' : '保存'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default BalancePage;
