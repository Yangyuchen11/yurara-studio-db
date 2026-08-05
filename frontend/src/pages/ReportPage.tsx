// frontend/src/pages/ReportPage.tsx
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { StatCard } from '../components/ui/StatCard';
import { DataCard } from '../components/ui/DataCard';
import { PageHeader } from '../components/ui/PageHeader';
import {
  Landmark,
  ArrowLeftRight,
  Wallet,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  Calendar,
  CalendarRange,
  ShoppingBag,
  TrendingUp,
  Box
} from 'lucide-react';

interface BalanceChangeRow {
  item_name: string;
  opening_balance: number;
  change: number;
  closing_balance: number;
  opening_str: string;
  change_str: string;
  closing_str: string;
}

interface AccountPeriodRow {
  account_name: string;
  currency: string;
  opening_balance: number;
  inflow: number;
  outflow: number;
  net_change: number;
  closing_balance: number;
  opening_str: string;
  inflow_str: string;
  outflow_str: string;
  net_str: string;
  closing_str: string;
}

interface NonCashDetailRow {
  item_name: string;
  opening_balance: number;
  change: number;
  closing_balance: number;
  opening_str: string;
  change_str: string;
  closing_str: string;
}

interface NonCashCategoryRow {
  item_name: string;
  opening_balance: number;
  change: number;
  closing_balance: number;
  opening_str: string;
  change_str: string;
  closing_str: string;
  details: NonCashDetailRow[];
}

interface AssetLiabPeriodRow {
  category: string;
  cny_amount: number;
  jpy_amount: number;
  total_cny_equiv: number;
  cny_str: string;
  jpy_str: string;
  equiv_str: string;
}

interface FlowSummaryRow {
  category: string;
  direction: string;
  cny_amount: number;
  jpy_amount: number;
  total_cny_equiv: number;
  cny_str: string;
  jpy_str: string;
  equiv_str: string;
}

interface ChartBarData {
  name: string;
  amount: number;
  amount_str: string;
  width_pct: string;
}

interface TrendChartData {
  month: string;
  net_profit: number;
  profit_str: string;
  height_str: string;
  is_positive: boolean;
}

interface ReportData {
  has_data: boolean;
  active_report_type: 'month' | 'year';
  selected_year: string;
  selected_month: string;
  available_years: string[];
  available_months: string[];
  balance_change_summary: BalanceChangeRow[];
  past_cash_total_str: string;
  net_cash_total_str: string;
  closing_cash_total_str: string;
  month_asset_add_str: string;
  month_asset_sub_str: string;
  net_asset_change_str: string;
  profit_in_str: string;
  profit_out_str: string;
  net_profit_str: string;
  stock_cny_str: string;
  wip_cny_str: string;
  inventory_total_cny_str: string;
  acc_summary: AccountPeriodRow[];
  non_cash_asset_summary: NonCashCategoryRow[];
  asset_purchase_rows: AssetLiabPeriodRow[];
  liab_equity_rows: AssetLiabPeriodRow[];
  flow_summary: FlowSummaryRow[];
  chart_bar_data: ChartBarData[];
  trend_chart_data: TrendChartData[];
}

export const ReportPage: React.FC = () => {
  const [activeReportType, setActiveReportType] = useState<'month' | 'year'>('month');
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear().toString());
  const [selectedMonth, setSelectedMonth] = useState(
    `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}`
  );
  const [openAccordions, setOpenAccordions] = useState<Record<string, boolean>>({});

  const toggleAccordion = (key: string) => {
    setOpenAccordions(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const { data: report, isLoading, refetch } = useQuery<ReportData>({
    queryKey: ['financialReport', activeReportType, selectedYear, selectedMonth],
    queryFn: async () => {
      const res = await apiClient.get('/finance/report-data/', {
        params: {
          report_type: activeReportType,
          year: selectedYear,
          month: selectedMonth,
        },
      });
      return res.data;
    },
  });

  const availableYears = report?.available_years || [new Date().getFullYear().toString()];
  const availableMonths = report?.available_months || [
    `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}`
  ];

  React.useEffect(() => {
    if (report?.available_months && report.available_months.length > 0) {
      if (!selectedMonth || !report.available_months.includes(selectedMonth)) {
        setSelectedMonth(report.available_months[0]);
      }
    }
    if (report?.available_years && report.available_years.length > 0) {
      if (!selectedYear || !report.available_years.includes(selectedYear)) {
        setSelectedYear(report.available_years[0]);
      }
    }
  }, [report]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="📊 财务报表与分析看板"
        subtitle="期初/期末家底、资产负债、资本变动及主营盈亏整体8大对账单分析"
        action={
          <button
            onClick={() => refetch()}
            className="px-3 py-1.5 bg-[#18202F] hover:bg-[#222C3E] text-slate-200 text-xs font-medium rounded-lg border border-[#2A3447] transition flex items-center gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5 text-violet-400" />
            刷新数据
          </button>
        }
      />

      {/* Report Mode Tabs */}
      <div className="flex border-b border-[#2A3447]">
        <button
          onClick={() => setActiveReportType('month')}
          className={`px-4 py-2.5 text-xs font-bold transition flex items-center gap-2 border-b-2 ${
            activeReportType === 'month'
              ? 'border-violet-500 text-violet-300 bg-violet-500/10'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Calendar className="w-4 h-4" />
          公司资本月报看板
        </button>
        <button
          onClick={() => setActiveReportType('year')}
          className={`px-4 py-2.5 text-xs font-bold transition flex items-center gap-2 border-b-2 ${
            activeReportType === 'year'
              ? 'border-violet-500 text-violet-300 bg-violet-500/10'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <CalendarRange className="w-4 h-4" />
          公司资本年报看板
        </button>
      </div>

      {/* Period Filter Card */}
      <div className="p-4 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] flex items-center gap-3 text-xs">
        <span className="font-bold text-slate-200">
          🔍 请选择要查询的结算{activeReportType === 'month' ? '月份' : '年份'}:
        </span>
        {activeReportType === 'month' ? (
          <select
            value={selectedMonth}
            onChange={(e) => setSelectedMonth(e.target.value)}
            className="bg-[#0B0F17] border border-[#2A3447] text-slate-100 rounded-lg px-3 py-1.5 font-mono focus:outline-none focus:border-violet-500"
          >
            {availableMonths.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        ) : (
          <select
            value={selectedYear}
            onChange={(e) => setSelectedYear(e.target.value)}
            className="bg-[#0B0F17] border border-[#2A3447] text-slate-100 rounded-lg px-3 py-1.5 font-mono focus:outline-none focus:border-violet-500"
          >
            {availableYears.map((y) => (
              <option key={y} value={y}>{y} 年</option>
            ))}
          </select>
        )}
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-slate-400 text-xs">正在加载财务报表数据...</div>
      ) : !report?.has_data ? (
        <div className="text-center py-12 text-slate-400 text-xs">暂无流水数据</div>
      ) : (
        <div className="space-y-6">
          {/* 一、 期初与期末资产、负债及资本变动表 */}
          <div className="space-y-3">
            <h2 className="text-xs font-bold text-violet-400 uppercase tracking-wider flex items-center gap-2">
              <span>🏢</span> 一、 期初与期末资产、负债及资本变动表 (折算 CNY 总计)
            </h2>
            <DataCard title="期初与期末整体财务家底账目表">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[#2A3447] text-slate-400 uppercase">
                      <th className="pb-2 px-2">财务科目项目</th>
                      <th className="pb-2 px-2 text-right">期初余额 (变动前)</th>
                      <th className="pb-2 px-2 text-right">本期净变动额</th>
                      <th className="pb-2 px-2 text-right">期末余额 (变动后)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#2A3447]/50 text-slate-200 font-mono">
                    {(report.balance_change_summary || []).map((row, idx) => (
                      <tr key={idx} className="hover:bg-[#18202F]">
                        <td className="py-2.5 px-2 font-sans font-bold text-slate-100">{row.item_name}</td>
                        <td className="py-2.5 px-2 text-right">{row.opening_str}</td>
                        <td className={`py-2.5 px-2 text-right font-bold ${row.change >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {row.change_str}
                        </td>
                        <td className="py-2.5 px-2 text-right font-bold text-violet-300">{row.closing_str}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </DataCard>
          </div>

          {/* 二、 期初与期末现金流汇总 */}
          <div className="space-y-3">
            <h2 className="text-xs font-bold text-violet-400 uppercase tracking-wider flex items-center gap-2">
              <span>💵</span> 二、 期初与期末现金流汇总 (折算 CNY 总计)
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <StatCard
                label="期初总资金 (变动前)"
                value={report.past_cash_total_str || '¥ 0.00'}
                unit="CNY"
                icon={Landmark}
                colorScheme="slate"
                borderLeft
              />
              <StatCard
                label="本期净现金流 (变动额)"
                value={report.net_cash_total_str || '¥ 0.00'}
                unit="CNY"
                icon={ArrowLeftRight}
                colorScheme="violet"
                borderLeft
              />
              <StatCard
                label="期末总资金 (变动后)"
                value={report.closing_cash_total_str || '¥ 0.00'}
                unit="CNY"
                icon={Wallet}
                colorScheme="emerald"
                borderLeft
              />
            </div>
          </div>

          {/* 三、 实体资产与经营盈亏结算 */}
          <div className="space-y-3">
            <h2 className="text-xs font-bold text-violet-400 uppercase tracking-wider flex items-center gap-2">
              <span>🏢</span> 三、 实体资产与经营盈亏结算 (经营利润与存货大盘)
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* 设备物料资产 */}
              <div className="p-4 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] space-y-2 text-xs">
                <div className="flex items-center gap-1.5 text-slate-400 font-medium">
                  <ShoppingBag className="w-4 h-4 text-blue-400" />
                  <span>实体设备与物料资产投入</span>
                </div>
                <div className="flex justify-between text-slate-300">
                  <span>本期新增投入:</span>
                  <span className="font-mono">{report.month_asset_add_str}</span>
                </div>
                <div className="flex justify-between text-slate-300">
                  <span>本期资产变现:</span>
                  <span className="font-mono">{report.month_asset_sub_str}</span>
                </div>
                <div className="border-t border-[#2A3447] pt-2 flex justify-between font-bold text-slate-100">
                  <span>资产净变动:</span>
                  <span className="font-mono text-blue-400">{report.net_asset_change_str}</span>
                </div>
              </div>

              {/* 主营盈亏大盘 */}
              <div className="p-4 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] space-y-2 text-xs">
                <div className="flex items-center gap-1.5 text-slate-400 font-medium">
                  <TrendingUp className="w-4 h-4 text-emerald-400" />
                  <span>主营盈亏净利润大盘</span>
                </div>
                <div className="flex justify-between text-slate-300">
                  <span>营业总收入:</span>
                  <span className="font-mono text-emerald-400">{report.profit_in_str}</span>
                </div>
                <div className="flex justify-between text-slate-300">
                  <span>营业总成本:</span>
                  <span className="font-mono text-rose-400">{report.profit_out_str}</span>
                </div>
                <div className="border-t border-[#2A3447] pt-2 flex justify-between font-bold text-slate-100">
                  <span>本期净利润:</span>
                  <span className="font-mono text-violet-400">{report.net_profit_str}</span>
                </div>
              </div>

              {/* 实时存货家底 */}
              <div className="p-4 bg-[#131924]/90 backdrop-blur-xl rounded-2xl border border-[#2A3447] space-y-2 text-xs">
                <div className="flex items-center gap-1.5 text-slate-400 font-medium">
                  <Box className="w-4 h-4 text-purple-400" />
                  <span>实时存货资产估值 (家底)</span>
                </div>
                <div className="flex justify-between text-slate-300">
                  <span>大货商品资产:</span>
                  <span className="font-mono">{report.stock_cny_str}</span>
                </div>
                <div className="flex justify-between text-slate-300">
                  <span>在制在研资产:</span>
                  <span className="font-mono">{report.wip_cny_str}</span>
                </div>
                <div className="border-t border-[#2A3447] pt-2 flex justify-between font-bold text-slate-100">
                  <span>存货合计(实时):</span>
                  <span className="font-mono text-emerald-400">{report.inventory_total_cny_str}</span>
                </div>
              </div>
            </div>
          </div>

          {/* 四、 各流动资金账户变动明细 */}
          <div className="space-y-3">
            <h2 className="text-xs font-bold text-violet-400 uppercase tracking-wider flex items-center gap-2">
              <span>💵</span> 四、 各流动资金账户变动明细
            </h2>
            <DataCard title="资金账户对账单">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-[#2A3447] text-slate-400 uppercase">
                      <th className="pb-2 px-2">资金账户</th>
                      <th className="pb-2 px-2 text-center">币种</th>
                      <th className="pb-2 px-2 text-right">期初余额(前)</th>
                      <th className="pb-2 px-2 text-right">本期流入</th>
                      <th className="pb-2 px-2 text-right">本期流出</th>
                      <th className="pb-2 px-2 text-right">净变动额</th>
                      <th className="pb-2 px-2 text-right">期末余额(后)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#2A3447]/50 text-slate-200 font-mono">
                    {(report.acc_summary || []).map((acc, idx) => (
                      <tr key={idx} className="hover:bg-[#18202F]">
                        <td className="py-2.5 px-2 font-sans font-medium text-slate-100">{acc.account_name}</td>
                        <td className="py-2.5 px-2 text-center">
                          <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300">
                            {acc.currency}
                          </span>
                        </td>
                        <td className="py-2.5 px-2 text-right">{acc.opening_str}</td>
                        <td className="py-2.5 px-2 text-right text-emerald-400 font-bold">{acc.inflow_str}</td>
                        <td className="py-2.5 px-2 text-right text-rose-400">{acc.outflow_str}</td>
                        <td className={`py-2.5 px-2 text-right font-bold ${acc.net_change >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {acc.net_str}
                        </td>
                        <td className="py-2.5 px-2 text-right font-bold text-violet-300">{acc.closing_str}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </DataCard>
          </div>

          {/* 五、 各非现金资产变动明细 (Accordion) */}
          <div className="space-y-3">
            <h2 className="text-xs font-bold text-violet-400 uppercase tracking-wider flex items-center gap-2">
              <span>🏢</span> 五、 各非现金资产变动明细 (点击项目可展开查看明细)
            </h2>
            <DataCard title="非现金资产对账单">
              <div className="space-y-2 text-xs">
                {(report.non_cash_asset_summary || []).map((cat, idx) => {
                  const isOpen = openAccordions[cat.item_name];
                  return (
                    <div key={idx} className="border border-[#2A3447] rounded-xl overflow-hidden bg-[#0B0F17]">
                      <button
                        onClick={() => toggleAccordion(cat.item_name)}
                        className="w-full px-4 py-3 flex items-center justify-between hover:bg-[#18202F] transition text-left"
                      >
                        <span className="font-bold text-slate-200 flex items-center gap-2">
                          {isOpen ? <ChevronDown className="w-4 h-4 text-violet-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
                          {cat.item_name}
                        </span>
                        <div className="flex gap-6 font-mono text-slate-300">
                          <span>期初: {cat.opening_str}</span>
                          <span className={`font-bold ${cat.change >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            变动: {cat.change_str}
                          </span>
                          <span className="font-bold text-violet-400">期末: {cat.closing_str}</span>
                        </div>
                      </button>

                      {isOpen && cat.details && cat.details.length > 0 && (
                        <div className="p-3 bg-[#131924] border-t border-[#2A3447] space-y-1.5 text-slate-300">
                          {cat.details.map((sub, sIdx) => (
                            <div key={sIdx} className="flex justify-between py-1 border-b border-slate-800/50 font-mono">
                              <span className="font-sans text-slate-400">{sub.item_name}</span>
                              <div className="flex gap-6">
                                <span>期初: {sub.opening_str}</span>
                                <span className={sub.change >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                                  变动: {sub.change_str}
                                </span>
                                <span className="font-bold text-slate-100">期末: {sub.closing_str}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </DataCard>
          </div>

          {/* 六、 物料采购 vs 负债资本 */}
          <div className="space-y-3">
            <h2 className="text-xs font-bold text-violet-400 uppercase tracking-wider flex items-center gap-2">
              <span>🏢</span> 六、 固定及其他资产采购 / 负债与外部资本变动
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <DataCard title="🛒 实体设备与物料采购汇总">
                {(report.asset_purchase_rows || []).length === 0 ? (
                  <div className="text-slate-400 text-xs py-4 text-center">本期无固定设备或耗材采购记录。</div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-[#2A3447] text-slate-400">
                          <th className="pb-2 px-2">资产分类</th>
                          <th className="pb-2 px-2 text-right">CNY 变动</th>
                          <th className="pb-2 px-2 text-right">原币变动</th>
                          <th className="pb-2 px-2 text-right">折合 CNY</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#2A3447]/50 text-slate-300 font-mono">
                        {(report.asset_purchase_rows || []).map((row, idx) => (
                          <tr key={idx} className="hover:bg-[#18202F]">
                            <td className="py-2.5 px-2 font-sans font-medium text-slate-100">{row.category}</td>
                            <td className="py-2.5 px-2 text-right">{row.cny_str}</td>
                            <td className="py-2.5 px-2 text-right">{row.jpy_str}</td>
                            <td className="py-2.5 px-2 text-right font-bold text-violet-300">{row.equiv_str}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </DataCard>

              <DataCard title="📉 负债与外部投资资本变动汇总">
                {(report.liab_equity_rows || []).length === 0 ? (
                  <div className="text-slate-400 text-xs py-4 text-center">本期无外部借贷、还款或投资注资变动。</div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-[#2A3447] text-slate-400">
                          <th className="pb-2 px-2">资本分类</th>
                          <th className="pb-2 px-2 text-right">CNY 变动</th>
                          <th className="pb-2 px-2 text-right">原币变动</th>
                          <th className="pb-2 px-2 text-right">折合 CNY</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#2A3447]/50 text-slate-300 font-mono">
                        {(report.liab_equity_rows || []).map((row, idx) => (
                          <tr key={idx} className="hover:bg-[#18202F]">
                            <td className="py-2.5 px-2 font-sans font-medium text-slate-100">{row.category}</td>
                            <td className="py-2.5 px-2 text-right">{row.cny_str}</td>
                            <td className="py-2.5 px-2 text-right">{row.jpy_str}</td>
                            <td className="py-2.5 px-2 text-right font-bold text-rose-300">{row.equiv_str}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </DataCard>
            </div>
          </div>

          {/* 七、 经营性现金流收支流向构成分析 */}
          <div className="space-y-3">
            <h2 className="text-xs font-bold text-violet-400 uppercase tracking-wider flex items-center gap-2">
              <span>📊</span> 七、 经营性现金流收支流向构成分析
            </h2>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Histogram */}
              <DataCard title="收支流向绝对金额排行 (元)">
                <div className="space-y-3 py-2 text-xs">
                  {(report.chart_bar_data || []).length === 0 ? (
                    <div className="text-slate-400 text-center py-6">暂无流水流向数据</div>
                  ) : (
                    (report.chart_bar_data || []).map((item, idx) => (
                      <div key={idx} className="space-y-1">
                        <div className="flex justify-between text-slate-300">
                          <span className="font-medium">{item.name}</span>
                          <span className="font-mono font-bold text-violet-300">{item.amount_str}</span>
                        </div>
                        <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-violet-600 to-fuchsia-500 transition-all duration-500"
                            style={{ width: item.width_pct }}
                          />
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </DataCard>

              {/* Detail Table */}
              <DataCard title="收支流水大类折合账表">
                <div className="overflow-x-auto max-h-72 overflow-y-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-[#2A3447] text-slate-400 uppercase">
                        <th className="pb-2 px-2">大类分类</th>
                        <th className="pb-2 px-2 text-center">流向</th>
                        <th className="pb-2 px-2 text-right">CNY 变动</th>
                        <th className="pb-2 px-2 text-right">原币变动</th>
                        <th className="pb-2 px-2 text-right">折合 CNY</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#2A3447]/50 text-slate-300 font-mono">
                      {(report.flow_summary || []).map((row, idx) => (
                        <tr key={idx} className="hover:bg-[#18202F]">
                          <td className="py-2.5 px-2 font-sans font-medium text-slate-100">{row.category}</td>
                          <td className="py-2.5 px-2 text-center font-sans">
                            <span className={`px-2 py-0.5 rounded text-[10px] ${
                              row.direction === '流入' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
                            }`}>
                              {row.direction}
                            </span>
                          </td>
                          <td className="py-2.5 px-2 text-right">{row.cny_str}</td>
                          <td className="py-2.5 px-2 text-right">{row.jpy_str}</td>
                          <td className="py-2.5 px-2 text-right font-bold text-violet-300">{row.equiv_str}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </DataCard>
            </div>
          </div>

          {/* 八、 年度走势 (仅在年报模式下渲染) */}
          {activeReportType === 'year' && (
            <div className="space-y-3">
              <h2 className="text-xs font-bold text-violet-400 uppercase tracking-wider flex items-center gap-2">
                <span>📈</span> 八、 年度内按月份经营盈亏走势分析
              </h2>
              <DataCard title="按月份净利润走势图 (CNY)">
                <div className="flex items-end justify-between gap-2 h-44 pt-6 px-4">
                  {(report.trend_chart_data || []).map((item, idx) => (
                    <div key={idx} className="flex flex-col items-center gap-2 flex-1 group">
                      <div className="text-[10px] font-mono text-slate-400 opacity-0 group-hover:opacity-100 transition">
                        {item.profit_str}
                      </div>
                      <div
                        className={`w-4 sm:w-6 rounded-t-md transition-all duration-300 ${
                          item.is_positive
                            ? 'bg-gradient-to-t from-emerald-600 to-emerald-400'
                            : 'bg-gradient-to-t from-rose-600 to-rose-400'
                        }`}
                        style={{ height: item.height_str }}
                      />
                      <span className="text-[10px] text-slate-400 font-medium">{item.month}</span>
                    </div>
                  ))}
                </div>
              </DataCard>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ReportPage;
