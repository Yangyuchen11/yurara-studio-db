// frontend/src/pages/PlatformsPage.tsx
import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { Globe, Plus, Trash2, Edit2, RefreshCw } from 'lucide-react';
import { Modal } from '../components/ui/Modal';

interface SalesPlatform {
  id: number;
  name: string;
  code: string;
  currency: string;
  fee_rate: number;
  fee_fixed: number;
}

export const PlatformsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingPlatform, setEditingPlatform] = useState<SalesPlatform | null>(null);

  // Form State (Right Panel Inline Creation & Modal Editing)
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [currency, setCurrency] = useState('CNY');
  const [feeRatePct, setFeeRatePct] = useState<number>(0);
  const [feeFixed, setFeeFixed] = useState<number>(0);

  // Fetch Registered Exchange Rates for Currency Options
  const { data: ratesData } = useQuery<Record<string, number>>({
    queryKey: ['rates'],
    queryFn: async () => {
      const res = await apiClient.get('/rates/');
      return res.data.rates || { JPY: 0.048 };
    },
  });

  const currencyOptions = React.useMemo(() => {
    const keys = Object.keys(ratesData || {});
    return Array.from(new Set(['CNY', ...keys]));
  }, [ratesData]);

  // Fetch Platforms
  const { data: platformsData, isLoading, refetch } = useQuery<SalesPlatform[]>({
    queryKey: ['salesPlatforms'],
    queryFn: async () => {
      const res = await apiClient.get('/platforms/');
      const raw = res.data;
      if (Array.isArray(raw)) return raw;
      if (raw && Array.isArray(raw.results)) return raw.results;
      return [];
    },
  });

  // Mutation: Save Platform (Create or Update)
  const saveMutation = useMutation({
    mutationFn: async (isEdit: boolean) => {
      const payload = {
        code: code.trim().toLowerCase(),
        name: name.trim(),
        currency,
        fee_rate: (feeRatePct || 0) / 100.0,
        fee_fixed: feeFixed || 0.0,
      };
      if (isEdit && editingPlatform) {
        await apiClient.put(`/platforms/${editingPlatform.id}/`, payload);
      } else {
        await apiClient.post('/platforms/', payload);
      }
    },
    onSuccess: (_, isEdit) => {
      queryClient.invalidateQueries({ queryKey: ['salesPlatforms'] });
      resetInlineForm();
      if (isEdit) closeModal();
      alert('🎉 销售平台配置已成功保存！');
    },
    onError: (err: any) => {
      alert(`保存失败: ${err.response?.data?.error || err.message || '未知错误'}`);
    }
  });

  // Mutation: Delete Platform
  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/platforms/${id}/`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['salesPlatforms'] });
      alert('🗑️ 销售平台已成功删除！');
    },
  });

  const resetInlineForm = () => {
    setCode('');
    setName('');
    setCurrency('CNY');
    setFeeRatePct(0);
    setFeeFixed(0);
  };

  const openEditModal = (p: SalesPlatform) => {
    setEditingPlatform(p);
    setCode(p.code);
    setName(p.name);
    setCurrency(p.currency || 'CNY');
    setFeeRatePct(Number(((p.fee_rate || 0) * 100).toFixed(2)));
    setFeeFixed(p.fee_fixed || 0);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingPlatform(null);
  };

  const items = Array.isArray(platformsData) ? platformsData : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
            <span className="p-2 bg-blue-500/10 text-blue-400 rounded-xl border border-blue-500/20">🌐</span>
            销售平台管理
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            配置与维护线上线下渠道（淘宝、Mercari、展会等）的手续费率与结算币种
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="px-3 py-1.5 bg-[#18202F] hover:bg-[#222C3E] text-slate-200 text-xs font-medium rounded-lg border border-[#2A3447] transition flex items-center gap-1.5"
        >
          <RefreshCw className="w-3.5 h-3.5 text-blue-400" />
          刷新平台列表
        </button>
      </div>

      {/* Main 2-Column Grid Layout (Matching Reflex Parity) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left 7 Columns: Existing Platforms List Table */}
        <div className="lg:col-span-7 p-5 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] space-y-4">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <Globe className="w-4 h-4 text-blue-400" />
            📋 现有销售平台清单
          </h3>

          {isLoading ? (
            <div className="text-center py-8 text-slate-400 text-xs">加载中...</div>
          ) : items.length === 0 ? (
            <div className="text-center py-12 text-slate-400 text-xs">暂无销售平台。</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-[#2A3447] text-slate-400 uppercase font-medium">
                    <th className="pb-3 px-2">平台代号</th>
                    <th className="pb-3 px-2">平台名称</th>
                    <th className="pb-3 px-2 text-center">结算币种</th>
                    <th className="pb-3 px-2 text-right">手续费扣率</th>
                    <th className="pb-3 px-2 text-right">单笔固定费 (原币)</th>
                    <th className="pb-3 px-2 text-center">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#2A3447]/50 text-slate-300">
                  {items.map((p) => (
                    <tr key={p.id} className="hover:bg-[#18202F]">
                      <td className="py-3 px-2 font-mono font-bold text-violet-400">{p.code}</td>
                      <td className="py-3 px-2 font-medium text-slate-100">{p.name}</td>
                      <td className="py-3 px-2 text-center">
                        <span className="px-2 py-0.5 rounded text-[10px] bg-blue-500/10 text-blue-400 border border-blue-500/20 font-mono font-bold">
                          {p.currency || 'CNY'}
                        </span>
                      </td>
                      <td className="py-3 px-2 text-right font-mono text-slate-200">
                        {((Number(p.fee_rate) || 0) * 100).toFixed(2)}%
                      </td>
                      <td className="py-3 px-2 text-right font-mono text-slate-200">
                        {(Number(p.fee_fixed) || 0).toFixed(2)}
                      </td>
                      <td className="py-3 px-2 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <button
                            onClick={() => openEditModal(p)}
                            title="编辑"
                            className="p-1 text-slate-400 hover:text-blue-400 transition"
                          >
                            <Edit2 className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => {
                              if (confirm(`确认要删除销售平台【${p.name}】吗？删除后已保存的历史数据不受影响。`)) {
                                deleteMutation.mutate(p.id);
                              }
                            }}
                            title="删除"
                            className="p-1 text-slate-400 hover:text-rose-400 transition"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Right 5 Columns: Add New Platform Card Form */}
        <div className="lg:col-span-5 p-5 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] space-y-4">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Plus className="w-4 h-4 text-violet-400" />
              ➕ 追加销售平台
            </h3>
            <p className="text-xs text-slate-400 mt-1">
              在此为系统追加新的线上/线下销售渠道并配置其扣率和币种参数。
            </p>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              saveMutation.mutate(false);
            }}
            className="space-y-4 text-xs"
          >
            <div>
              <label className="block text-slate-300 font-medium mb-1">
                平台英文代号 (唯一标识，如: ebay) <span className="text-rose-400">*</span>
              </label>
              <input
                type="text"
                required
                placeholder="请输入拼音或英文小写代号"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono focus:outline-none focus:border-violet-500"
              />
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">
                平台显示名称 (如: eBay 商店) <span className="text-rose-400">*</span>
              </label>
              <input
                type="text"
                required
                placeholder="显示在列表与下拉菜单中的名称"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 focus:outline-none focus:border-violet-500"
              />
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-slate-300 font-medium mb-1">结算币种</label>
                <select
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-2 text-slate-100 font-mono focus:outline-none focus:border-violet-500"
                >
                  {currencyOptions.map(c => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">手续费率 (%)</label>
                <input
                  type="number"
                  step="0.01"
                  placeholder="如: 0.6 或 5.6"
                  value={feeRatePct || ''}
                  onChange={(e) => setFeeRatePct(parseFloat(e.target.value) || 0)}
                  className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-2 text-slate-100 font-mono focus:outline-none focus:border-violet-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">单笔固定费(原币)</label>
                <input
                  type="number"
                  step="0.01"
                  placeholder="例如: 22"
                  value={feeFixed || ''}
                  onChange={(e) => setFeeFixed(parseFloat(e.target.value) || 0)}
                  className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-2 text-slate-100 font-mono focus:outline-none focus:border-violet-500"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={saveMutation.isPending}
              className="w-full py-2.5 bg-violet-600 hover:bg-violet-500 text-white font-bold rounded-xl shadow-lg transition flex items-center justify-center gap-2"
            >
              <Plus className="w-4 h-4" />
              {saveMutation.isPending ? '添加中...' : '添加销售平台'}
            </button>
          </form>
        </div>
      </div>

      {/* Modal for Editing Platform */}
      <Modal
        isOpen={isModalOpen}
        onClose={closeModal}
        title="✏️ 编辑销售平台"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            saveMutation.mutate(true);
          }}
          className="space-y-4 text-xs"
        >
          <div>
            <label className="block text-slate-300 font-medium mb-1">平台英文代号</label>
            <input
              type="text"
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
            />
          </div>

          <div>
            <label className="block text-slate-300 font-medium mb-1">平台显示名称</label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-slate-300 font-medium mb-1">结算币种</label>
              <select
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-2 text-slate-100 font-mono"
              >
                {currencyOptions.map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-slate-300 font-medium mb-1">手续费率 (%)</label>
              <input
                type="number"
                step="0.01"
                value={feeRatePct}
                onChange={(e) => setFeeRatePct(parseFloat(e.target.value) || 0)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-2 text-slate-100 font-mono"
              />
            </div>
            <div>
              <label className="block text-slate-300 font-medium mb-1">单笔固定费</label>
              <input
                type="number"
                step="0.01"
                value={feeFixed}
                onChange={(e) => setFeeFixed(parseFloat(e.target.value) || 0)}
                className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-2.5 py-2 text-slate-100 font-mono"
              />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={closeModal}
              className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg font-medium"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={saveMutation.isPending}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white font-medium rounded-lg shadow-lg"
            >
              {saveMutation.isPending ? '保存中...' : '💾 保存修改'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

export default PlatformsPage;
