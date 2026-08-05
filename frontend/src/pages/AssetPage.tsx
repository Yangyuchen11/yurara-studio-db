// frontend/src/pages/AssetPage.tsx
import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { FixedAsset } from '../types';
import { Modal } from '../components/ui/Modal';
import { StatCard } from '../components/ui/StatCard';
import { DataCard } from '../components/ui/DataCard';
import { FormField } from '../components/ui/FormField';
import { PageHeader } from '../components/ui/PageHeader';
import {
  Banknote,
  TrendingUp,
  Search,
  X,
  Pencil,
  Link as LinkIcon,
  CheckCheck,
  RefreshCw
} from 'lucide-react';

interface FixedAssetLog {
  id: number;
  asset_name: string;
  decrease_qty: number;
  reason: string;
  date: string;
}

export const AssetPage: React.FC = () => {
  const queryClient = useQueryClient();

  // Search & Edit States
  const [searchQuery, setSearchQuery] = useState('');
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [editingAsset, setEditingAsset] = useState<FixedAsset | null>(null);
  const [editShopName, setEditShopName] = useState('');
  const [editUrl, setEditUrl] = useState('');
  const [editRemarks, setEditRemarks] = useState('');

  // Write-off Form State
  const [writeOffAssetId, setWriteOffAssetId] = useState<number | ''>('');
  const [writeOffQty, setWriteOffQty] = useState<number>(1);
  const [writeOffReason, setWriteOffReason] = useState<string>('');
  const [writeOffError, setWriteOffError] = useState<string>('');

  // Fetch Fixed Assets
  const { data: assets, isLoading: loadingAssets, refetch: refetchAssets } = useQuery<FixedAsset[]>({
    queryKey: ['fixedAssets'],
    queryFn: async () => {
      const res = await apiClient.get('/assets/fixed/');
      return res.data.results || res.data || [];
    },
  });

  // Fetch Asset Totals
  const { data: totalsData } = useQuery({
    queryKey: ['fixedAssetTotals'],
    queryFn: async () => {
      const res = await apiClient.get('/assets/fixed/totals/');
      return res.data;
    },
  });

  // Fetch Fixed Asset Logs
  const { data: assetLogs, isLoading: loadingLogs, refetch: refetchLogs } = useQuery<FixedAssetLog[]>({
    queryKey: ['fixedAssetLogs'],
    queryFn: async () => {
      const res = await apiClient.get('/assets/fixed-logs/');
      return res.data.results || res.data || [];
    },
  });

  // Active Assets (Remaining Qty > 0)
  const activeAssets = useMemo(() => {
    return (assets || []).filter((a) => (a.remaining_qty ?? 0) > 0);
  }, [assets]);

  // Filtered Assets by Search Query
  const filteredAssets = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return assets || [];
    return (assets || []).filter((a) => {
      return (
        (a.name || '').toLowerCase().includes(q) ||
        (a.shop_name || '').toLowerCase().includes(q) ||
        (a.remarks || '').toLowerCase().includes(q) ||
        (a.currency || '').toLowerCase().includes(q)
      );
    });
  }, [assets, searchQuery]);

  // Mutations
  const updateAssetMutation = useMutation({
    mutationFn: async ({ id, data }: { id: number; data: any }) => {
      const res = await apiClient.patch(`/assets/fixed/${id}/`, data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fixedAssets'] });
      queryClient.invalidateQueries({ queryKey: ['fixedAssetTotals'] });
      setIsEditOpen(false);
      setEditingAsset(null);
    },
  });

  const writeOffMutation = useMutation({
    mutationFn: async ({ assetId, qty, reason }: { assetId: number; qty: number; reason: string }) => {
      const res = await apiClient.post(`/assets/fixed/${assetId}/write_off/`, {
        decrease_qty: qty,
        reason,
      });
      return res.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['fixedAssets'] });
      queryClient.invalidateQueries({ queryKey: ['fixedAssetTotals'] });
      queryClient.invalidateQueries({ queryKey: ['fixedAssetLogs'] });
      setWriteOffAssetId('');
      setWriteOffQty(1);
      setWriteOffReason('');
      setWriteOffError('');
      alert(data.message || '核销处理成功！');
    },
    onError: (err: any) => {
      setWriteOffError(err.response?.data?.error || '核销操作失败');
    },
  });

  // Handlers
  const handleOpenEdit = (asset: FixedAsset) => {
    setEditingAsset(asset);
    setEditShopName(asset.shop_name || '');
    setEditUrl(asset.url || '');
    setEditRemarks(asset.remarks || '');
    setIsEditOpen(true);
  };

  const handleSaveEdit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingAsset) return;
    updateAssetMutation.mutate({
      id: editingAsset.id,
      data: {
        shop_name: editShopName.trim(),
        url: editUrl.trim(),
        remarks: editRemarks.trim(),
      },
    });
  };

  const handleSubmitWriteOff = (e: React.FormEvent) => {
    e.preventDefault();
    setWriteOffError('');

    if (!writeOffAssetId) {
      setWriteOffError('请选择要核销的资产');
      return;
    }
    if (writeOffQty <= 0) {
      setWriteOffError('核销数量必须大于 0');
      return;
    }
    if (!writeOffReason.trim()) {
      setWriteOffError('请填写核销原因说明');
      return;
    }

    writeOffMutation.mutate({
      assetId: Number(writeOffAssetId),
      qty: Number(writeOffQty),
      reason: writeOffReason.trim(),
    });
  };

  const logList = Array.isArray(assetLogs) ? assetLogs : [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="🏢 固定资产管理"
        subtitle="摄影器材、办公设备等固定资产采购原值、实时账面残值及核销/报废追溯"
        action={
          <button
            onClick={() => {
              refetchAssets();
              refetchLogs();
            }}
            className="px-3.5 py-2 bg-[#18202F] hover:bg-[#222C3E] text-slate-200 text-xs font-medium rounded-xl border border-[#2A3447] transition flex items-center gap-1.5 shadow"
          >
            <RefreshCw className="w-3.5 h-3.5 text-violet-400" />
            刷新数据
          </button>
        }
      />

      {/* Top 2 Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <StatCard
          label="资产采购历史总值 (折合)"
          value={totalsData?.total_cny_str || '¥ 0.00'}
          unit=""
          icon={Banknote}
          colorScheme="violet"
          borderLeft
        />
        <StatCard
          label="当前剩余价值 (折合)"
          value={totalsData?.remain_cny_str || '¥ 0.00'}
          unit=""
          icon={TrendingUp}
          colorScheme="emerald"
          borderLeft
        />
      </div>

      {/* Main Data Card: Fixed Asset List */}
      <DataCard title="📋 固定资产清单">
        <div className="space-y-4">
          {/* Search Bar */}
          <div className="flex items-center gap-2 text-xs">
            <div className="relative flex-1 max-w-xs">
              <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="搜索项目名称、店铺、备注、币种..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-xl pl-9 pr-3 py-2 text-slate-100 focus:outline-none focus:border-violet-500"
              />
            </div>
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition flex items-center gap-1"
              >
                <X className="w-3.5 h-3.5" />
                <span>清除</span>
              </button>
            )}
          </div>

          {/* Table */}
          {loadingAssets ? (
            <div className="text-xs text-slate-400 py-8 text-center">加载固定资产列表中...</div>
          ) : filteredAssets.length === 0 ? (
            <div className="text-xs text-slate-400 py-8 text-center bg-[#0B0F17] rounded-xl border border-[#2A3447]">
              {searchQuery ? '未找到匹配的固定资产记录' : '暂无固定资产数据。请在【财务流水账】中录入‘固定资产购入’。'}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#2A3447] text-slate-400 font-medium uppercase">
                    <th className="pb-2.5 px-2">项目</th>
                    <th className="pb-2.5 px-2">币种</th>
                    <th className="pb-2.5 px-2 text-right">单价(原币)</th>
                    <th className="pb-2.5 px-2 text-right">初始数量</th>
                    <th className="pb-2.5 px-2 text-right">剩余数量</th>
                    <th className="pb-2.5 px-2 text-right">总价(原币)</th>
                    <th className="pb-2.5 px-2 text-right">剩余价值(CNY)</th>
                    <th className="pb-2.5 px-2 text-right">剩余价值(原币)</th>
                    <th className="pb-2.5 px-2">店铺</th>
                    <th className="pb-2.5 px-2 text-center">链接</th>
                    <th className="pb-2.5 px-2">备注</th>
                    <th className="pb-2.5 px-2 text-center">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#2A3447]/50 text-slate-300">
                  {filteredAssets.map((a) => {
                    const origQty = Number(a.quantity) || 0;
                    const remainQty = Number(a.remaining_qty) || 0;
                    const unitP = Number(a.unit_price) || 0;
                    const totalPrice = unitP * origQty;
                    const remainOrig = unitP * remainQty;

                    return (
                      <tr key={a.id} className="hover:bg-[#18202F]">
                        <td className="py-2.5 px-2 font-bold text-slate-100">{a.name}</td>
                        <td className="py-2.5 px-2 font-mono text-slate-400">{a.currency}</td>
                        <td className="py-2.5 px-2 text-right font-mono">{unitP.toFixed(2)}</td>
                        <td className="py-2.5 px-2 text-right font-mono">{origQty}</td>
                        <td className="py-2.5 px-2 text-right font-mono">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              remainQty > 0
                                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                : 'bg-slate-800 text-slate-500'
                            }`}
                          >
                            {remainQty}
                          </span>
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono font-bold text-slate-200">
                          {totalPrice.toFixed(2)}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono font-bold text-violet-300">
                          ¥ {(a.remaining_cny || 0).toFixed(2)}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-slate-400">
                          {remainOrig > 0.001 ? `${remainOrig.toFixed(2)} ${a.currency}` : '-'}
                        </td>
                        <td className="py-2.5 px-2 text-slate-300 truncate max-w-xs">{a.shop_name || '-'}</td>
                        <td className="py-2.5 px-2 text-center">
                          {a.url ? (
                            <a
                              href={a.url}
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
                        <td className="py-2.5 px-2 text-slate-400 truncate max-w-xs">{a.remarks || '-'}</td>
                        <td className="py-2.5 px-2 text-center">
                          <button
                            onClick={() => handleOpenEdit(a)}
                            title="修改店名、链接与备注"
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

      {/* Bottom Section: Write-off Form & Write-off Logs */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        {/* Left Column: Write-off Form */}
        <div className="p-4 bg-[#131924] rounded-2xl border border-[#2A3447] space-y-4 text-xs">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-rose-400" />
              📉 资产核销/报废
            </h3>
            <p className="text-slate-400 mt-1">
              对已损坏、丢失或产生物理折旧的固定资产进行核销处理。
            </p>
          </div>

          {writeOffError && (
            <div className="p-2.5 bg-rose-500/10 border border-rose-500/30 rounded-lg text-rose-400">
              {writeOffError}
            </div>
          )}

          {activeAssets.length === 0 ? (
            <div className="p-3 bg-blue-500/10 border border-blue-500/30 rounded-xl text-blue-300 text-xs">
              ℹ️ 当前没有可核销的资产 (剩余数量均为 0)
            </div>
          ) : (
            <form onSubmit={handleSubmitWriteOff} className="space-y-3">
              <FormField label="选择要核销的资产" required>
                <select
                  value={writeOffAssetId}
                  onChange={(e) => setWriteOffAssetId(e.target.value ? Number(e.target.value) : '')}
                  className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                >
                  <option value="">-- 选择要核销的资产 --</option>
                  {activeAssets.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} (剩余: {a.remaining_qty})
                    </option>
                  ))}
                </select>
              </FormField>

              <div className="grid grid-cols-2 gap-3">
                <FormField label="核销数量" required>
                  <input
                    type="number"
                    value={writeOffQty}
                    onChange={(e) => setWriteOffQty(parseInt(e.target.value) || 1)}
                    className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                  />
                </FormField>

                <FormField label="核销原因 (必填)" required>
                  <input
                    type="text"
                    placeholder="如: 损坏、丢失、过时报废"
                    value={writeOffReason}
                    onChange={(e) => setWriteOffReason(e.target.value)}
                    className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                  />
                </FormField>
              </div>

              <button
                type="submit"
                disabled={writeOffMutation.isPending}
                className="w-full py-2.5 bg-rose-600 hover:bg-rose-500 font-bold text-white rounded-xl transition shadow-lg shadow-rose-500/20 flex items-center justify-center gap-1.5"
              >
                <CheckCheck className="w-4 h-4" />
                <span>{writeOffMutation.isPending ? '提交中...' : '确认执行核销'}</span>
              </button>
            </form>
          )}
        </div>

        {/* Right Column: Fixed Asset Logs Table */}
        <DataCard title="📜 固定资产核销记录">
          {loadingLogs ? (
            <div className="text-xs text-slate-400 py-6 text-center">加载核销记录中...</div>
          ) : logList.length === 0 ? (
            <div className="text-xs text-slate-400 py-6 text-center">暂无相关固定资产核销或折旧流水记录</div>
          ) : (
            <div className="overflow-x-auto max-h-80 overflow-y-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#2A3447] text-slate-400 uppercase font-medium">
                    <th className="pb-2 px-2">日期</th>
                    <th className="pb-2 px-2">资产名称</th>
                    <th className="pb-2 px-2 text-center">核销数量</th>
                    <th className="pb-2 px-2">原因说明</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#2A3447]/50 text-slate-300">
                  {logList.map((log) => (
                    <tr key={log.id} className="hover:bg-[#18202F]">
                      <td className="py-2 px-2 font-mono text-slate-400">{log.date}</td>
                      <td className="py-2 px-2 font-bold text-slate-200">{log.asset_name}</td>
                      <td className="py-2 px-2 text-center">
                        <span className="px-2 py-0.5 bg-rose-500/10 text-rose-400 border border-rose-500/20 rounded font-mono font-bold">
                          -{log.decrease_qty}
                        </span>
                      </td>
                      <td className="py-2 px-2 text-slate-400">{log.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DataCard>
      </div>

      {/* Edit Asset Modal */}
      <Modal isOpen={isEditOpen} onClose={() => setIsEditOpen(false)} title={`⚙️ 编辑资产: ${editingAsset?.name || ''}`}>
        <form onSubmit={handleSaveEdit} className="space-y-4 text-xs">
          <p className="text-slate-400">在此修改该项固定资产的采购店铺来源、网址链接或补充备注。</p>

          <FormField label="店名 / 来源 (必填)">
            <input
              type="text"
              required
              value={editShopName}
              onChange={(e) => setEditShopName(e.target.value)}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
            />
          </FormField>

          <FormField label="相关链接 / 网址">
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
              disabled={updateAssetMutation.isPending}
              className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white font-bold rounded-lg shadow"
            >
              保存修改
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default AssetPage;
