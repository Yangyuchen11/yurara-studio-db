// frontend/src/pages/ProductsPage.tsx
import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import type { Product, ProductColor, SalesPlatform } from '../types';
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
  Layers,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Image as ImageIcon,
  Puzzle,
  Tag,
  Upload
} from 'lucide-react';

const getImageUrl = (imgData?: string | null, imgUrl?: string | null): string | null => {
  if (imgData && imgData.trim().length > 0) return imgData;
  if (imgUrl && imgUrl.trim().length > 0) {
    if (imgUrl.startsWith('http://') || imgUrl.startsWith('https://')) return imgUrl;
    return imgUrl.startsWith('/') ? imgUrl : `/${imgUrl}`;
  }
  return null;
};

const ColorThumbnail: React.FC<{ src: string | null; name: string; size?: string }> = ({
  src,
  name,
  size = 'w-10 h-10',
}) => {
  const [hasError, setHasError] = useState(false);

  if (!src || hasError) {
    return (
      <div
        className={`${size} rounded-xl bg-slate-800/90 border border-slate-700/80 flex items-center justify-center text-slate-400 inline-flex shadow-sm`}
        title={`规格 ${name}`}
      >
        <ImageIcon className="w-4 h-4 text-slate-400" />
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={name}
      onError={() => setHasError(true)}
      className={`${size} object-cover rounded-xl border border-slate-700/80 shadow-sm inline-block bg-slate-800`}
    />
  );
};

export const ProductsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);

  // SPU Form
  const [name, setName] = useState('');
  const [targetPlatform, setTargetPlatform] = useState('通用');
  const [formError, setFormError] = useState('');

  // SKU Management Modal State
  const [selectedProductForSku, setSelectedProductForSku] = useState<Product | null>(null);
  const [colorName, setColorName] = useState('');
  const [colorQty, setColorQty] = useState<number | ''>(0);
  const [colorImageData, setColorImageData] = useState('');

  // Price Sub-form
  const [activeColorForPrice, setActiveColorForPrice] = useState<number | null>(null);
  const [pricePlatform, setPricePlatform] = useState('');
  const [priceCurrency, setPriceCurrency] = useState('CNY');
  const [priceVal, setPriceVal] = useState<number | ''>('');

  // Part Sub-form
  const [activeColorForPart, setActiveColorForPart] = useState<number | null>(null);
  const [partName, setPartName] = useState('');
  const [partQty, setPartQty] = useState<number | ''>(1);

  // Expandable Parts state for Product Cards
  const [expandedColorIds, setExpandedColorIds] = useState<number[]>([]);

  const toggleExpandColor = (colorId: number) => {
    setExpandedColorIds(prev =>
      prev.includes(colorId) ? prev.filter(id => id !== colorId) : [...prev, colorId]
    );
  };

  // Fetch Sales Platforms dynamically from API (no hardcoding)
  const { data: platforms = [] } = useQuery<SalesPlatform[]>({
    queryKey: ['platforms'],
    queryFn: async () => {
      const res = await apiClient.get('/platforms/');
      return res.data.results || res.data || [];
    },
  });

  const getPlatformDisplayName = (codeOrName: string): string => {
    if (!codeOrName) return '-';
    const matched = platforms.find(
      (p) => p.code === codeOrName || p.name === codeOrName
    );
    return matched ? matched.name : codeOrName;
  };

  const { data: products, isLoading, refetch } = useQuery<Product[]>({
    queryKey: ['products'],
    queryFn: async () => {
      const res = await apiClient.get('/products/');
      return res.data.results || res.data;
    },
  });

  const saveProductMutation = useMutation({
    mutationFn: async (data: any) => {
      if (editingProduct) {
        const res = await apiClient.put(`/products/${editingProduct.id}/`, data);
        return res.data;
      } else {
        const res = await apiClient.post('/products/', data);
        return res.data;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      closeProductModal();
    },
    onError: (err: any) => {
      setFormError(err.response?.data?.error || '保存商品失败');
    },
  });

  const addColorMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await apiClient.post('/product-colors/', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      setColorName('');
      setColorQty(0);
      setColorImageData('');
      refetchSkuProduct();
    },
    onError: (err: any) => {
      alert(err.response?.data?.error || '添加颜色规格失败');
    },
  });

  const deleteColorMutation = useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/product-colors/${id}/`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      refetchSkuProduct();
    },
  });

  const addPriceMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await apiClient.post('/product-prices/', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      setPriceVal('');
      refetchSkuProduct();
    },
    onError: (err: any) => {
      alert(err.response?.data?.error || '添加定价失败');
    },
  });

  const deletePriceMutation = useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/product-prices/${id}/`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      refetchSkuProduct();
    },
  });

  const addPartMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await apiClient.post('/product-parts/', data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      setPartName('');
      setPartQty(1);
      refetchSkuProduct();
    },
    onError: (err: any) => {
      alert(err.response?.data?.error || '添加部件失败');
    },
  });

  const deletePartMutation = useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/product-parts/${id}/`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
      refetchSkuProduct();
    },
  });

  const deleteProductMutation = useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/products/${id}/`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] });
    },
  });

  const refetchSkuProduct = async () => {
    if (!selectedProductForSku) return;
    try {
      const res = await apiClient.get(`/products/${selectedProductForSku.id}/`);
      setSelectedProductForSku(res.data);
    } catch (e) {
      console.error(e);
    }
  };

  const openCreateModal = () => {
    setEditingProduct(null);
    setName('');
    setTargetPlatform(platforms[0]?.name || '通用');
    setFormError('');
    setIsAddModalOpen(true);
  };

  const openEditModal = (p: Product) => {
    setEditingProduct(p);
    setName(p.name);
    setTargetPlatform(p.target_platform || '通用');
    setFormError('');
    setIsAddModalOpen(true);
  };

  const closeProductModal = () => {
    setIsAddModalOpen(false);
    setEditingProduct(null);
    setFormError('');
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    if (!name.trim()) {
      setFormError('请输入商品名称');
      return;
    }

    saveProductMutation.mutate({
      name,
      target_platform: targetPlatform,
    });
  };

  const handleAddColor = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProductForSku || !colorName.trim()) return;
    addColorMutation.mutate({
      product: selectedProductForSku.id,
      color_name: colorName,
      quantity: Number(colorQty) || 0,
      image_data: colorImageData,
    });
  };

  const handleImageFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setColorImageData(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleAddPrice = (colorId: number) => {
    if (!priceVal || Number(priceVal) <= 0) return;
    const selectedPlat = pricePlatform || (platforms[0]?.code || platforms[0]?.name || 'weidian');
    addPriceMutation.mutate({
      color: colorId,
      platform: selectedPlat,
      currency: priceCurrency,
      price: Number(priceVal),
    });
  };

  const handleAddPart = (colorId: number) => {
    if (!partName.trim()) return;
    addPartMutation.mutate({
      color: colorId,
      part_name: partName,
      quantity: Number(partQty) || 1,
    });
  };

  const productList = Array.isArray(products) ? products : [];
  const totalColorsCount = productList.reduce((sum, p) => sum + (p.colors?.length || 0), 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="📦 商品管理与款号配置"
        subtitle="管理核心商品 SPU、规格颜色 SKU 缩略图、多平台定价与款式部件明细"
        action={
          <div className="flex items-center gap-2">
            <button
              onClick={() => refetch()}
              className="px-3 py-1.5 bg-[#18202F] hover:bg-[#222C3E] text-slate-200 text-xs font-medium rounded-lg border border-[#2A3447] transition flex items-center gap-1.5"
            >
              <RefreshCw className="w-3.5 h-3.5 text-violet-400" />
              刷新
            </button>
            <button
              onClick={openCreateModal}
              className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white text-xs font-semibold rounded-xl shadow-lg shadow-violet-500/20 transition flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              新建商品 SPU
            </button>
          </div>
        }
      />

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <StatCard
          label="在售商品 SPU 总数"
          value={productList.length}
          unit="个"
          icon={Package}
          colorScheme="violet"
          borderLeft
        />
        <StatCard
          label="规格 SKU 总数"
          value={totalColorsCount}
          unit="款"
          icon={Layers}
          colorScheme="indigo"
          borderLeft
        />
      </div>

      {/* Product Cards List */}
      <DataCard title="🛍️ 全量商品卡片列表">
        {isLoading ? (
          <div className="text-center py-8 text-slate-400 text-xs">加载商品数据中...</div>
        ) : productList.length === 0 ? (
          <div className="text-center py-12 text-slate-400 text-xs">暂无商品，请点击右上角新建商品</div>
        ) : (
          <div className="space-y-5">
            {productList.map((p) => {
              const colors = p.colors || [];
              const totalQuantity = colors.reduce((sum, c) => sum + (c.quantity || 0), 0);

              return (
                <div
                  key={p.id}
                  className="p-5 bg-[#0B0F17] rounded-2xl border border-[#2A3447] hover:border-violet-500/40 transition shadow-xl space-y-4"
                >
                  {/* Card Header */}
                  <div className="flex justify-between items-start pb-3 border-b border-[#2A3447]/60">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2.5">
                        <h3 className="font-bold text-base text-slate-100">{p.name}</h3>
                        <span className="px-2 py-0.5 rounded-full text-[10px] bg-violet-500/10 text-violet-300 border border-violet-500/20 font-mono">
                          SPU ID: #{p.id}
                        </span>
                      </div>
                      <div className="text-xs text-slate-400 flex items-center gap-4">
                        <span>主渠道: <strong className="text-slate-200">{getPlatformDisplayName(p.target_platform || '通用')}</strong></span>
                        <span>已配置规格总量: <strong className="text-violet-400">{totalQuantity} 件</strong></span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setSelectedProductForSku(p)}
                        className="px-3 py-1.5 bg-violet-600/20 hover:bg-violet-600/30 text-violet-300 border border-violet-500/30 text-xs font-semibold rounded-xl transition flex items-center gap-1.5"
                      >
                        <Plus className="w-3.5 h-3.5" />
                        SKU/定价/部件配置
                      </button>
                      <button
                        onClick={() => openEditModal(p)}
                        className="p-1.5 text-slate-400 hover:text-violet-400 hover:bg-[#18202F] rounded-lg transition"
                        title="编辑商品"
                      >
                        <Edit2 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => {
                          if (confirm(`确认删除商品 [${p.name}] ？`)) {
                            deleteProductMutation.mutate(p.id);
                          }
                        }}
                        className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition"
                        title="删除商品"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {/* Color & Variant Specs Table with Fixed Column Widths */}
                  {colors.length === 0 ? (
                    <div className="p-4 bg-[#131924]/60 rounded-xl border border-dashed border-[#2A3447] text-center text-slate-500 text-xs">
                      暂未添加颜色规格 SKU，请点击上方「SKU/定价/部件配置」添加
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs border-collapse table-fixed min-w-[700px]">
                        <thead>
                          <tr className="border-b border-[#2A3447] text-slate-400 uppercase text-[11px]">
                            <th className="pb-2 px-3 w-16 text-center">缩略图</th>
                            <th className="pb-2 px-3 w-44">规格/颜色名称</th>
                            <th className="pb-2 px-3 w-28">库存数量</th>
                            <th className="pb-2 px-3">多平台定价</th>
                            <th className="pb-2 px-3 w-36 text-right">款式部件信息</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#2A3447]/40">
                          {colors.map((c) => {
                            const isPartsExpanded = expandedColorIds.includes(c.id);
                            const parts = c.parts || [];
                            const prices = c.prices || [];
                            const imgSrc = getImageUrl(c.image_data, c.image);

                            return (
                              <React.Fragment key={c.id}>
                                <tr className="hover:bg-[#131924]/40 transition group">
                                  {/* Fixed Width Thumbnail Column */}
                                  <td className="py-2.5 px-3 w-16 text-center">
                                    <ColorThumbnail src={imgSrc} name={c.color_name} />
                                  </td>

                                  {/* Color Spec Name */}
                                  <td className="py-2.5 px-3 w-44 truncate">
                                    <span className="font-bold text-slate-100 text-xs truncate">{c.color_name}</span>
                                  </td>

                                  {/* Quantity */}
                                  <td className="py-2.5 px-3 w-28">
                                    <span className="px-2.5 py-1 rounded-lg bg-slate-800 text-slate-200 font-mono font-semibold text-xs border border-slate-700 inline-block">
                                      {c.quantity || 0} 件
                                    </span>
                                  </td>

                                  {/* Platform Pricing */}
                                  <td className="py-2.5 px-3">
                                    {prices.length === 0 ? (
                                      <span className="text-slate-500 text-[11px] italic">未设置定价</span>
                                    ) : (
                                      <div className="flex flex-wrap gap-1.5">
                                        {prices.map((pr, prIdx) => (
                                          <span
                                            key={prIdx}
                                            className="px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-mono text-[11px] flex items-center gap-1"
                                          >
                                            <Tag className="w-3 h-3 text-emerald-400" />
                                            <span className="font-bold">{getPlatformDisplayName(pr.platform)}:</span>
                                            <span>
                                              {pr.currency === 'JPY'
                                                ? `${pr.price.toLocaleString()} JPY`
                                                : `¥${pr.price.toFixed(2)}`}
                                            </span>
                                          </span>
                                        ))}
                                      </div>
                                    )}
                                  </td>

                                  {/* Expandable Parts Action Button */}
                                  <td className="py-2.5 px-3 w-36 text-right">
                                    <button
                                      onClick={() => toggleExpandColor(c.id)}
                                      className={`px-2.5 py-1 text-xs font-medium rounded-lg border transition inline-flex items-center gap-1.5 ${
                                        isPartsExpanded
                                          ? 'bg-violet-600/30 text-violet-200 border-violet-500/50'
                                          : 'bg-[#18202F] hover:bg-[#222C3E] text-slate-300 border-[#2A3447]'
                                      }`}
                                    >
                                      <Puzzle className="w-3.5 h-3.5 text-violet-400" />
                                      <span>部件 ({parts.length})</span>
                                      {isPartsExpanded ? (
                                        <ChevronUp className="w-3.5 h-3.5 text-violet-400" />
                                      ) : (
                                        <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                                      )}
                                    </button>
                                  </td>
                                </tr>

                                {/* Expandable Parts Sub-row */}
                                {isPartsExpanded && (
                                  <tr className="bg-[#0B0F17]/90">
                                    <td colSpan={5} className="p-3 bg-[#131924]/60 rounded-xl border border-violet-500/20 my-1">
                                      <div className="space-y-2">
                                        <div className="flex items-center justify-between text-xs font-bold text-violet-300">
                                          <span className="flex items-center gap-1.5">
                                            <Puzzle className="w-3.5 h-3.5 text-violet-400" />
                                            规格 [{c.color_name}] 的零件/部件组成构成:
                                          </span>
                                          <span className="text-[10px] text-slate-400 font-normal">
                                            共 {parts.length} 个独立构成部件
                                          </span>
                                        </div>

                                        {parts.length === 0 ? (
                                          <p className="text-slate-500 text-[11px] italic py-1">
                                            此颜色规格尚未绑定成套部件明细（默认为整件出售）
                                          </p>
                                        ) : (
                                          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-1">
                                            {parts.map((pt, ptIdx) => (
                                              <div
                                                key={ptIdx}
                                                className="p-2 bg-[#0B0F17] rounded-lg border border-[#2A3447] flex items-center justify-between text-xs"
                                              >
                                                <span className="font-medium text-slate-200">{pt.part_name}</span>
                                                <span className="px-1.5 py-0.5 rounded bg-violet-500/20 text-violet-300 font-mono text-[10px] font-bold">
                                                  x{pt.quantity}
                                                </span>
                                              </div>
                                            ))}
                                          </div>
                                        )}
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
                  )}
                </div>
              );
            })}
          </div>
        )}
      </DataCard>

      {/* Create / Edit SPU Modal */}
      <Modal
        isOpen={isAddModalOpen}
        onClose={closeProductModal}
        title={editingProduct ? "编辑商品 SPU" : "新建商品 SPU"}
      >
        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          {formError && (
            <div className="p-2.5 bg-rose-500/10 border border-rose-500/30 rounded-lg text-rose-400">
              {formError}
            </div>
          )}

          <FormField label="商品名称" required>
            <input
              type="text"
              required
              placeholder="例如: 2026早春娃娃装连衣长裙"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 focus:outline-none focus:border-violet-500"
            />
          </FormField>

          <FormField label="主销售渠道">
            <select
              value={targetPlatform}
              onChange={(e) => setTargetPlatform(e.target.value)}
              className="w-full bg-[#0B0F17] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
            >
              <option value="通用">通用</option>
              {platforms.map((plat) => (
                <option key={plat.id} value={plat.name}>
                  {plat.name}
                </option>
              ))}
            </select>
          </FormField>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={closeProductModal}
              className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={saveProductMutation.isPending}
              className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white font-medium rounded-lg"
            >
              {saveProductMutation.isPending ? '保存中...' : '提交'}
            </button>
          </div>
        </form>
      </Modal>

      {/* SKU Color / Pricing / Parts Manager Modal */}
      {selectedProductForSku && (
        <Modal
          isOpen={!!selectedProductForSku}
          onClose={() => setSelectedProductForSku(null)}
          title={`🎨 SKU 规格、缩略图、定价与部件配置 - ${selectedProductForSku.name}`}
          maxWidth="4xl"
        >
          <div className="space-y-5 text-xs max-h-[75vh] overflow-y-auto pr-1">
            {/* Add New Color Form */}
            <form onSubmit={handleAddColor} className="p-4 bg-[#0B0F17] rounded-xl border border-[#2A3447] space-y-3">
              <h4 className="font-bold text-slate-200 text-xs flex items-center gap-1.5">
                <Plus className="w-4 h-4 text-violet-400" />
                <span>添加新规格颜色 SKU</span>
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-center">
                <input
                  type="text"
                  required
                  placeholder="颜色规格 (如: 樱花粉 / XL)"
                  value={colorName}
                  onChange={(e) => setColorName(e.target.value)}
                  className="bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100"
                />
                <input
                  type="number"
                  placeholder="生产/预估数量 (件)"
                  value={colorQty}
                  onChange={(e) => setColorQty(e.target.value ? parseInt(e.target.value) : '')}
                  className="bg-[#131924] border border-[#2A3447] rounded-lg px-3 py-2 text-slate-100 font-mono"
                />
                <div className="flex items-center gap-2">
                  <label className="px-3 py-2 bg-[#18202F] hover:bg-[#222C3E] text-slate-300 rounded-lg border border-[#2A3447] cursor-pointer text-xs flex items-center gap-1.5 flex-1 truncate">
                    <Upload className="w-3.5 h-3.5 text-violet-400" />
                    <span className="truncate">{colorImageData ? '已选缩略图' : '选择图片...'}</span>
                    <input type="file" accept="image/*" onChange={handleImageFileChange} className="hidden" />
                  </label>
                  {colorImageData && (
                    <img src={colorImageData} alt="Preview" className="w-8 h-8 object-cover rounded-lg border border-violet-500/50" />
                  )}
                </div>
              </div>
              <button
                type="submit"
                disabled={addColorMutation.isPending}
                className="w-full py-2 bg-violet-600 hover:bg-violet-500 text-white font-bold rounded-xl transition shadow-lg shadow-violet-500/20"
              >
                + 确认保存新规格 SKU
              </button>
            </form>

            {/* Color SKU List & Nested Sub-forms */}
            <div className="space-y-3">
              <h4 className="font-bold text-slate-300 text-xs">已配置规格及子项目 (定价/部件)</h4>
              {(selectedProductForSku.colors || []).length === 0 ? (
                <div className="text-slate-400 py-6 text-center bg-[#0B0F17] rounded-xl border border-[#2A3447]">
                  暂无颜色规格，请上方输入添加
                </div>
              ) : (
                <div className="space-y-3">
                  {(selectedProductForSku.colors || []).map((c) => {
                    const cImgSrc = getImageUrl(c.image_data, c.image);

                    return (
                      <div key={c.id} className="p-4 bg-[#0B0F17] border border-[#2A3447] rounded-xl space-y-3">
                        {/* Color Bar Header */}
                        <div className="flex items-center justify-between pb-2 border-b border-[#2A3447]/60">
                          <div className="flex items-center gap-3">
                            <ColorThumbnail src={cImgSrc} name={c.color_name} size="w-8 h-8" />
                            <div>
                              <span className="font-bold text-slate-100 text-xs">{c.color_name}</span>
                              <span className="text-slate-400 text-[11px] ml-2 font-mono">({c.quantity || 0} 件)</span>
                            </div>
                          </div>
                          <button
                            onClick={() => deleteColorMutation.mutate(c.id)}
                            className="p-1 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition"
                            title="删除此规格"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>

                        {/* Pricing Section */}
                        <div className="space-y-1.5">
                          <div className="flex items-center justify-between text-[11px] font-bold text-emerald-400">
                            <span className="flex items-center gap-1">
                              <Tag className="w-3 h-3" /> 各平台定价列表:
                            </span>
                          </div>
                          <div className="flex flex-wrap gap-2 items-center">
                            {(c.prices || []).map((pr) => (
                              <span key={pr.id} className="px-2.5 py-1 bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 rounded-lg text-xs font-mono flex items-center gap-1.5">
                                <span>{getPlatformDisplayName(pr.platform)}:</span>
                                <strong className="text-slate-100">
                                  {pr.currency === 'JPY' ? `${pr.price.toLocaleString()} JPY` : `¥${pr.price}`}
                                </strong>
                                <button
                                  onClick={() => pr.id && deletePriceMutation.mutate(pr.id)}
                                  className="text-slate-400 hover:text-rose-400 ml-1"
                                >
                                  &times;
                                </button>
                              </span>
                            ))}

                            {/* Quick Add Price with Dynamic Platforms from API */}
                            {activeColorForPrice === c.id ? (
                              <div className="flex items-center gap-1 bg-[#131924] p-1 rounded-lg border border-emerald-500/30">
                                <select
                                  value={pricePlatform || (platforms[0]?.code || platforms[0]?.name || '')}
                                  onChange={(e) => {
                                    const val = e.target.value;
                                    setPricePlatform(val);
                                    const matched = platforms.find((p) => (p.code || p.name) === val);
                                    if (matched && matched.currency) {
                                      setPriceCurrency(matched.currency);
                                    }
                                  }}
                                  className="bg-[#0B0F17] border border-[#2A3447] rounded px-1.5 py-0.5 text-[11px] text-slate-100"
                                >
                                  {platforms.map((plat) => (
                                    <option key={plat.id} value={plat.code || plat.name}>
                                      {plat.name} ({plat.currency || 'CNY'})
                                    </option>
                                  ))}
                                </select>
                                <select
                                  value={priceCurrency}
                                  onChange={(e) => setPriceCurrency(e.target.value)}
                                  className="bg-[#0B0F17] border border-[#2A3447] rounded px-1.5 py-0.5 text-[11px] text-slate-100"
                                >
                                  <option value="CNY">CNY</option>
                                  <option value="JPY">JPY</option>
                                </select>
                                <input
                                  type="number"
                                  placeholder="价格"
                                  value={priceVal}
                                  onChange={(e) => setPriceVal(e.target.value ? parseFloat(e.target.value) : '')}
                                  className="w-16 bg-[#0B0F17] border border-[#2A3447] rounded px-1.5 py-0.5 text-[11px] text-slate-100 font-mono"
                                />
                                <button
                                  onClick={() => handleAddPrice(c.id)}
                                  className="px-2 py-0.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-[10px] font-bold"
                                >
                                  保存
                                </button>
                                <button
                                  onClick={() => setActiveColorForPrice(null)}
                                  className="px-1.5 py-0.5 text-slate-400 hover:text-slate-200 text-[11px]"
                                >
                                  取消
                                </button>
                              </div>
                            ) : (
                              <button
                                onClick={() => {
                                  setActiveColorForPrice(c.id);
                                  if (platforms.length > 0) {
                                    setPricePlatform(platforms[0].code || platforms[0].name);
                                    setPriceCurrency(platforms[0].currency || 'CNY');
                                  }
                                }}
                                className="px-2 py-0.5 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-lg text-[11px] font-medium flex items-center gap-1 transition"
                              >
                                <Plus className="w-3.5 h-3.5" /> 添加定价
                              </button>
                            )}
                          </div>
                        </div>

                        {/* Parts Section */}
                        <div className="space-y-1.5 pt-1 border-t border-[#2A3447]/40">
                          <div className="flex items-center justify-between text-[11px] font-bold text-violet-400">
                            <span className="flex items-center gap-1">
                              <Puzzle className="w-3 h-3" /> 部件组成列表:
                            </span>
                          </div>
                          <div className="flex flex-wrap gap-2 items-center">
                            {(c.parts || []).map((pt) => (
                              <span key={pt.id} className="px-2.5 py-1 bg-violet-500/10 text-violet-300 border border-violet-500/20 rounded-lg text-xs font-mono flex items-center gap-1.5">
                                <span>{pt.part_name}</span>
                                <strong className="text-violet-400">x{pt.quantity}</strong>
                                <button
                                  onClick={() => pt.id && deletePartMutation.mutate(pt.id)}
                                  className="text-slate-400 hover:text-rose-400 ml-1"
                                >
                                  &times;
                                </button>
                              </span>
                            ))}

                            {/* Quick Add Part */}
                            {activeColorForPart === c.id ? (
                              <div className="flex items-center gap-1 bg-[#131924] p-1 rounded-lg border border-violet-500/30">
                                <input
                                  type="text"
                                  placeholder="部件名称 (如: 外套)"
                                  value={partName}
                                  onChange={(e) => setPartName(e.target.value)}
                                  className="w-24 bg-[#0B0F17] border border-[#2A3447] rounded px-1.5 py-0.5 text-[11px] text-slate-100"
                                />
                                <input
                                  type="number"
                                  min="1"
                                  placeholder="数量"
                                  value={partQty}
                                  onChange={(e) => setPartQty(e.target.value ? parseInt(e.target.value) : '')}
                                  className="w-12 bg-[#0B0F17] border border-[#2A3447] rounded px-1.5 py-0.5 text-[11px] text-slate-100 font-mono"
                                />
                                <button
                                  onClick={() => handleAddPart(c.id)}
                                  className="px-2 py-0.5 bg-violet-600 hover:bg-violet-500 text-white rounded text-[10px] font-bold"
                                >
                                  保存
                                </button>
                                <button
                                  onClick={() => setActiveColorForPart(null)}
                                  className="px-1.5 py-0.5 text-slate-400 hover:text-slate-200 text-[11px]"
                                >
                                  取消
                                </button>
                              </div>
                            ) : (
                              <button
                                onClick={() => setActiveColorForPart(c.id)}
                                className="px-2 py-0.5 bg-violet-500/10 hover:bg-violet-500/20 text-violet-400 border border-violet-500/30 rounded-lg text-[11px] font-medium flex items-center gap-1 transition"
                              >
                                <Plus className="w-3.5 h-3.5" /> 添加部件
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};

export default ProductsPage;
