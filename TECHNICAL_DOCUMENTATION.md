# Yurara Studio - 移植后系统整体技术文档

> **文档版本**: v1.0.0  
> **更新时间**: 2026-08-06  
> **架构类型**: 前后端分离架构 (Decoupled SPA + RESTful API)  
> **系统目标**: 替代原单体 Reflex (Python+Next.js WebSocket) 架构，提供更高性能、高可用、易扩展的现代 ERP & 销售仓储财务一体化管理系统。

---

## 目录 (Table of Contents)

1. [📌 项目概述 (Project Overview)](#1-项目概述-project-overview)
2. [🏗️ 总体技术架构 (System Architecture)](#2-总体技术架构-system-architecture)
3. [📂 目录结构与模块划分 (Project Directory & Modules)](#3-目录结构与模块划分-project-directory--modules)
4. [⚙️ 核心业务模块与实现细节 (Core Modules & Technical Details)](#4-核心业务模块与实现细节-core-modules--technical-details)
   - [4.1 动态汇率管理系统 (Dynamic Exchange Rates)](#41-动态汇率管理系统-dynamic-exchange-rates)
   - [4.2 预售销售管理系统 (Presale Sales Management)](#42-预售销售管理系统-presale-sales-management)
   - [4.3 仓库库存管理与级联回滚 (Inventory & Cascade Rollback)](#43-仓库库存管理与级联回滚-inventory--cascade-rollback)
   - [4.4 线下展会模式与货品清单配置 (Offline Exhibition Mode)](#44-线下展会模式与货品清单配置-offline-exhibition-mode)
   - [4.5 销售大屏透视与平台管理 (Sales Analytics & Platforms)](#45-销售大屏透视与平台管理-sales-analytics--platforms)
   - [4.6 财务流水与公司账面概览 (Finance & Balance Sheet)](#46-财务流水与公司账面概览-finance--balance-sheet)
   - [4.7 固定资产与其他/消耗品资产 (Assets & Consumable Management)](#47-固定资产与其他消耗品资产-assets--consumable-management)
5. [🎨 前端 UI/UX 设计规范 (Design System & Aesthetic Guidelines)](#5-前端-uiux-设计规范-design-system--aesthetic-guidelines)
6. [🚀 运行、构建与部署指南 (Execution & Deployment Guide)](#6-运行构建与部署指南-execution--deployment-guide)

---

## 1. 📌 项目概述 (Project Overview)

本项目为 **Yurara Studio** 的全新架构重构与移植版本。

### 1.1 背景与移植原因
- **原版 (Reflex 框架)**：采用单体全栈 Python 框架（底层通过 Websocket 双向通信、SQLAlchemy ORM 及 Next.js 自动生成前端），在复杂数据表格、并发操作及大图高频渲染时存在性能瓶颈与交互延迟。
- **移植版 (Django REST Framework + React TypeScript)**：将后端重构成高并发、标准 RESTful 规范的 DRF 服务，前端采用 Vite + React 19 + TypeScript + TanStack Query 搭建极速单页应用 (SPA)。

### 1.2 代码保留说明
- 为保证业务逻辑与数据的 100% 对照校验，**Reflex 原版代码完整保留在根目录下的 `yurara_app/`** 文件夹中，未做任何删改。
- 移植后的核心后端位于 `app_core/`, `app_sales/`, `app_inventory/`, `app_finance/`, `app_assets/` 等 Django 应用包中；前端全量位于 `frontend/` 目录中。

---

## 2. 🏗️ 总体技术架构 (System Architecture)

```
+-----------------------------------------------------------------------+
|                         React 19 + TypeScript SPA                     |
|            (Vite / Tailwind CSS / TanStack Query v5 / Lucide)         |
+-----------------------------------------------------------------------+
                                   |
                           HTTP REST API (JSON)
                                   |
+-----------------------------------------------------------------------+
|                    Django REST Framework (DRF) Backend                |
|  +--------------+  +--------------+  +---------------+  +----------+  |
|  |   app_core   |  |  app_sales   |  | app_inventory |  | app_...  |  |
|  +--------------+  +--------------+  +---------------+  +----------+  |
|     (Rates/SPU)      (Presale/Exh)      (WIP/Rollback)   (Finance)    |
+-----------------------------------------------------------------------+
                                   |
                          Django ORM & Database
                        (SQLite / PostgreSQL)
```

### 2.1 架构分层明细与语言/框架映射 (Detailed Architecture Matrix)

| 分层维度 (Layer) | 业务功能模块 (Sub-Module) | 编程语言 (Language) | 核心框架/依赖库 (Framework / Library) | 详细实现职责与机制 (Technical Description) |
| :--- | :--- | :--- | :--- | :--- |
| **前端展现层 (Presentation Layer)** | 单页应用主体 (SPA Shell) | TypeScript 5.x, TSX | React 19, Vite 8, React Router v7 | 组件化渲染、组件生命周期管理、路由跳转分发与打包构建 |
| **前端展现层 (Presentation Layer)** | 样式与暗黑主题系统 (Design System) | CSS3 / PostCSS | Tailwind CSS v4, Lucide React Icons | Glassmorphism 暗黑主题、网格布局、微动画与矢量图标渲染 |
| **前端数据层 (Client Data Layer)** | 异步状态与请求缓存 (State Management) | TypeScript 5.x | TanStack Query v5, Axios 1.x | API 接口统一拦截、查询缓存 (Stale-While-Revalidate)、静默轮询与失效重发 |
| **前端工具层 (Client Utility)** | 客户端 Excel 导入解析 (Bulk Import) | TypeScript 5.x, JS | SheetJS XLSX 0.18 | 在浏览器端即时解析预售 `.xlsx`/`.csv` 文件，处理英文分号 `;` 分割多单号匹配校验 |
| **后端 API 路由层 (API Entry Layer)** | RESTful 接口与鉴权 (Router & Views) | Python 3.10+ | Django 4/5, DRF (Django REST Framework) | 路由分发、请求参数校验、权限校验 (`IsAuthenticated`)、HTTP 响应格式统一序列化 |
| **后端服务逻辑层 (Service Layer)** | 动态汇率系统 (`app_core`) | Python 3.10+ | HTTPX 0.27, Regular Expressions, SystemSetting | 同步/异步请求 Google Finance 抓取实时外币对 CNY 汇率、DB 读写与全站解耦共享 |
| **后端服务逻辑层 (Service Layer)** | 预售与订单流转 (`app_sales`) | Python 3.10+ | Django ORM, `@transaction.atomic` | 处理定金购物车建单、尾款订单多对多绑定、多单发货结单、订单状态自动流转 |
| **后端服务逻辑层 (Service Layer)** | 仓储与 WIP 资产 (`app_inventory`) | Python 3.10+ | Django ORM, Django Signals | 成套/散件拆分出入库、物理调拨、在制资产 (WIP) 计算与生产结单清零、级联回滚删除 |
| **后端服务逻辑层 (Service Layer)** | 数据分析与透视 (`app_sales`) | Python 3.10+ | Pandas 2.x, NumPy | 将销售订单历史数据转换为多维透视表 (Pivot Table)，计算渠道收益与销量排行榜 |
| **后端服务逻辑层 (Service Layer)** | 财务与公司账面 (`app_finance`) | Python 3.10+ | Django ORM, BalanceService | 财务流水记录、多货币现金/资产/负债/资本分类统计、资产负债表动态计算 |
| **后端服务逻辑层 (Service Layer)** | 固定资产与耗材 (`app_assets`) | Python 3.10+ | Django ORM, ConsumableService | 固定资产折旧与报废核销、耗材库存变动 (对外销售流水联动 vs 内部消耗成本分摊) |
| **数据持久化层 (Persistence Layer)** | 关系型数据库 (Database) | SQL | Django ORM, SQLite / PostgreSQL | 关系映射、外键关联、数据索引管理与数据表结构自动迁移 (`migrations`) |

### 2.2 各分层详细工作机制与流转方案 (Layered Implementation Workflow)

1. **前端 Client <-> REST API 通信机制**:
   - 前端采用 `Axios` 构建统一 API 客户端 (`src/api/client.ts`)，自动注入 BaseURL (`/api/v1/`) 与 Bearer/CSRF Token。
   - 使用 `TanStack Query (v5)` 包装 API 调用。组件发起查询时，先命中本地 InMemory 缓存秒开页面，后台并发向 Django DRF 发起 Fetch，获取最新 JSON 后静默更新视图。

2. **后端 ViewSet <-> Service 业务逻辑解耦模式**:
   - 后端严格遵循 **Thin Controller, Thick Service (瘦 View, 厚 Service)** 架构理念。
   - `views.py` 仅负责 HTTP 请求接收入参、DRF Serializer 校验与 HTTP 状态码响应。
   - 所有复杂的业务核算（如预售绑定校验、库存出入库扣扣减、级联撤销成本清理、WIP 资产摊销、公司账面汇总）均封装在 `services/` 目录对应的独立 Service 类静态/类方法中。

3. **数据库事务与并发安全 (`@transaction.atomic`)**:
   - 涉及到“多表联动更新”的操作（例如：消耗模式出库需同时扣减仓库库存、增加 `InventoryLog` 变动日志、在 `CostItem` 中插入分摊记录、更新大货资产与 WIP 资产），全部使用 `@transaction.atomic` 装饰器包裹，一旦任何步骤抛出异常，整个事务自动回滚，确保数据库数据绝对完整。

4. **动态汇率引擎与全站贯通机制**:
   - 汇率服务 `app_core/services/rate_service.py` 在数据库 `SystemSetting` 中以 `rate_CNY_per_<CURRENCY>_100` 保存汇率。
   - 全站所有存在外币换算的地方（公司账面概览、财务分析报表、销售透视大屏、固定资产折合、消耗品估值）均调用 `get_all_rates()` 统一读取数据库最新汇率，消除了硬编码数值带来的歧义。

---

## 3. 📂 目录结构与模块划分 (Project Directory & Modules)

```
yurara-studio-db/
├── app_core/                   # 核心基础应用
│   ├── models.py               # 商品(Product)、成本项(CostItem)、系统配置(SystemSetting)
│   ├── services/
│   │   ├── rate_service.py     # 动态汇率查询、写入与 Google Finance 实时抓取
│   │   ├── cost_service.py     # 预算与实际成本核算、WIP 清零
│   │   └── product_service.py  # 商品数据逻辑
│   └── views.py                # 商品管理与汇率 API 视图
├── app_sales/                  # 销售与预售应用
│   ├── models.py               # 销售订单(SalesOrder)、订单项(SalesOrderItem)、展会模板(OfflineExhibition)
│   ├── services/
│   │   ├── sales_service.py    # 销售建单、尾款绑定、状态流转
│   │   └── exhibition_service.py # 展会模板与货品清单配置
│   └── views.py                # 线上/预售/展会/平台/透视分析 API 视图
├── app_inventory/              # 仓库与库存应用
│   ├── models.py               # 物理仓库(Warehouse)、库存变动日志(InventoryLog)
│   ├── services/
│   │   └── inventory_service.py # 成套/散件拆分出入库、物理调拨、WIP资产核算、级联回滚
│   └── views.py                # 库存盘点与仓库管理 API 视图
├── app_finance/                # 财务应用
│   ├── models.py               # 财务流水(FinanceRecord)、公司账面科目(CompanyBalanceItem)
│   ├── services/
│   │   ├── finance_service.py  # 财务收支流水处理
│   │   └── balance_service.py  # 资产负债表与账面概览核算
│   └── views.py                # 财务流水、公司账面概览、月度/年度报表 API 视图
├── app_assets/                 # 资产管理应用
│   ├── models.py               # 固定资产(FixedAsset/Log)、耗材资产(ConsumableItem/Log)
│   ├── services/
│   │   ├── asset_service.py    # 固定资产折旧与报废核销
│   │   └── consumable_service.py # 耗材快速变动、出库记账/成本分摊
│   └── views.py                # 固定资产与消耗品 API 视图
├── frontend/                   # React 19 + TypeScript SPA 前端工程
│   ├── src/
│   │   ├── api/client.ts       # Axios API 客户端配置
│   │   ├── components/
│   │   │   ├── ui/             # StatCard, DataCard, FormField, Modal, PageHeader 等基础 UI 组件
│   │   │   └── Sidebar.tsx     # 侧边栏导航与汇率管理 Modal
│   │   ├── pages/              # 11 个业务主页面组件
│   │   │   ├── Dashboard.tsx   # 首页大盘
│   │   │   ├── SalesPage.tsx   # 销售大屏透视
│   │   │   ├── SalesOrdersPage.tsx # 线上销售订单
│   │   │   ├── PresalePage.tsx # 预售销售管理
│   │   │   ├── OfflineSalesPage.tsx # 线下展会模式
│   │   │   ├── PlatformsPage.tsx # 销售平台管理
│   │   │   ├── InventoryPage.tsx # 仓库库存管理
│   │   │   ├── FinancePage.tsx # 财务流水账
│   │   │   ├── BalancePage.tsx # 公司账面概览
│   │   │   ├── AssetPage.tsx   # 固定资产管理
│   │   │   └── ConsumablePage.tsx # 其他/消耗品资产管理
│   │   └── types/index.ts      # 全局 TypeScript 类型定义
│   ├── package.json            # 前端依赖配置
│   └── vite.config.ts          # Vite 构建配置
├── manage.py                   # Django 入口脚本
├── requirements.txt            # Python 依赖清单
└── yurara_app/                 # Reflex 原版代码 (完整保留备查)
```

---

## 4. ⚙️ 核心业务模块与实现细节 (Core Modules & Technical Details)

### 4.1 动态汇率管理系统 (Dynamic Exchange Rates)
- **后端设计 (`app_core/services/rate_service.py`)**:
  - 存储：在 `SystemSetting` 中保存各外币对 CNY 的汇率（以 100 外币 = X CNY 格式保存，如 `rate_CNY_per_JPY_100` = `4.28`）。
  - 读取：`get_all_rates()` 方法统一从数据库抓取所有已登记汇率，转换为 1 单位外货的标准比例（如 `{"JPY": 0.0428, "USD": 7.25}`）。
  - 实时抓取：`fetch_live_rates_sync()` 使用 `HTTPX` 搭配正则表达式访问 Google Finance (`https://www.google.com/finance/quote/JPY-CNY`) 解析最新实时汇率并更新 DB。
  - **彻底解决汇率不一致**: 后端所有模块（账面概览、财务报表、销售透视、资产折算）统一调用 `get_all_rates()`，杜绝硬编码。
- **前端联动 (`Sidebar.tsx` & `FinancePage.tsx`)**:
  - `Sidebar.tsx` 模态框提供全系统汇率查看、手动修改编辑、一键刷新抓取与交叉汇率换算计算器。

---

### 4.2 预售销售管理系统 (Presale Sales Management)
- **功能特性与技术实现 (`PresalePage.tsx` & `app_sales/`)**:
  1. **手动建单与尾款绑定**:
     - **模式 1 (主定金订单创建)**：定金购物车支持多 SPU/SKU、自选出货仓库暂存，一键创建 `order_type='预售'` 的定金订单。
     - **模式 2 (尾款订单绑定)**：支持在输入框搜索并锁定定金单。为了满足复杂的预售场景，已支持 **多对多绑定**：
       - **1 个尾款订单绑定多个定金订单**：发货时可同时完成多个定金订单。
       - **多个尾款订单绑定同一个定金订单**：后端状态校验逻辑规定必须多个尾款订单全部完成时，才触发对应定金订单的最终结单。
  2. **Excel 批量导入解析 (SheetJS / XLSX)**:
     - 允许导入包含 `订单号`、`关联定金单号`、`商品名`、`数量` 等列的 Excel 文件。
     - **支持英文分号 `;` 分割**：在 `关联定金单号` 列中支持用 `;` 分割多个定金单号，解析器会自动切割并批量搜索匹配数据库中的定金记录。
  3. **完整分页支持**:
     - 前端列表配置 `pageIndex` 与 `pageSize` (20/50/100 条/页)。当切换 7 大状态 Tab（待确认定金、待付尾款、待发货、已发货、已完成、售后中、全部）或搜索时自动重置页码。

---

### 4.3 仓库库存管理与级联回滚 (Inventory & Cascade Rollback)
- **功能特性与技术实现 (`InventoryPage.tsx` & `app_inventory/`)**:
  1. **双 Tab 页面结构**:
     - **Tab 1: 库存管理与盘点**：包含款式成套/散件拆分入库进度明细、Excess Parts 散件物理余量折叠面板、WIP 在制资产估值卡片、出入库与调拨录入表单以及仓储物理日志流水。
     - **Tab 2: 物理仓库与明细**：支持开立新仓库、按商品筛选各物理仓库库存明细以及空置仓库注销。
  2. **调拨与物理校验**:
     - 调拨 (TRANSFER) 时需选择源仓库与目的仓库，后端自动生成一进一出两笔日志，且在调拨前执行底层物理可用库存校验。
  3. **级联回滚/撤销 (`cascade_delete`)**:
     - 当选择“消耗”模式出库时，系统会在 `CostItem` 成本表中生成关联描述记录。
     - 当用户在日志表格中撤销/删除该笔出库日志时，后端 `InventoryLogViewSet.cascade_delete` 会自动清理关联的 `CostItem` 成本，并触发大货资产 (`Asset:Stock`) 与 WIP 资产的重新核算，确保数据库彻底回滚无遗留。
  4. **在制资产 (WIP) 核算与结单**:
     - 提供 `get_wip_balance` 与 `clear_wip_for_product`（生产结单清零），在制资产实时根据成套摊销分子分母联动。

---

### 4.4 线下展会模式与货品清单配置 (Offline Exhibition Mode)
- **功能特性与技术实现 (`OfflineSalesPage.tsx` & `app_sales/`)**:
  1. **展会模板创建与编辑**:
     - 支持创建展会模板（设置展会名称、开始/结束日期、场地租金、预期销售额、结算币种等）。
  2. **右侧货品清单配置面板 (与 Reflex 完全一致)**:
     - 切换或编辑已有模板时，右侧自动加载系统内所有已开户商品。
     - 展会货品配置表格联动商品 SPU/SKU 明细，展示配比数量、参考单价与已配比件数，支持实时配置保存展会货品清单。

---

### 4.5 销售大屏透视与平台管理 (Sales Analytics & Platforms)
- **功能特性与技术实现 (`SalesPage.tsx`, `PlatformsPage.tsx` & `app_sales/`)**:
  1. **销售数据透视分析**:
     - 后端 `SalesAnalyticsView` 利用 **Pandas** 建立数据透视表，按销售渠道（微店、Booth、淘宝、展会、私域等）、款式 Variant 与时间维度统计销售件数、总金额与折合 CNY 收益。
  2. **动态结算币种平台管理**:
     - `PlatformsPage.tsx` 结算币种下拉框动态加载全系统已登记币种（如 `['CNY', ...Object.keys(ratesData)]`），支持配置各平台的固定/百分比手续费扣率。

---

### 4.6 财务流水与公司账面概览 (Finance & Balance Sheet)
- **功能特性与技术实现 (`FinancePage.tsx`, `BalancePage.tsx` & `app_finance/`)**:
  1. **多货币公司账面概览 (资产负债表)**:
     - 分为 *现金与实物资产 (Assets)* 和 *负债与资本 (Liabilities & Equity)* 两栏网格。
     - `FinancialSummaryView` 动态统计流动资金现金账户、非现金实体资产、固定资产残值、耗材在库价值以及 WIP 在制资产，输出多货币指标卡与综合折算 CNY 净资产。
  2. **财务收支流水账**:
     - 支持销售收入、商品成本、退款、固定资产购入、债务偿还等多类流水的录入与批量修改。
     - 接入动态汇率进行实时交叉换算。

---

### 4.7 固定资产与其他/消耗品资产 (Assets & Consumable Management)
- **功能特性与技术实现 (`AssetPage.tsx`, `ConsumablePage.tsx` & `app_assets/`)**:
  1. **固定资产管理**:
     - 展示采购历史总值 (折合 CNY) 与当前账面残值。
     - 包含资产核销/报废操作卡片，核销后自动扣减剩余数量并生成 `FixedAssetLog`。
  2. **其他/消耗品资产管理**:
     - 展示耗材库存总值及各币种实物总值。
     - **快速变动分支**：
       - *出库-对外销售*：自动联动划入选定现金账户并生成销售收入财务流水。
       - *出库-内部消耗*：支持勾选 `🔗 计入商品大货成本`，自动在目标商品下生成成本分摊项。
     - **行内账期更正**：日志表格日期单元格嵌入 Date Picker，失焦自动调用 `/update_date/` 更正历史日志账期。

---

## 5. 🎨 前端 UI/UX 设计规范 (Design System & Aesthetic Guidelines)

前端采用了 **暗黑极光极简风 (Dark Mode Glassmorphism)** 设计规范，提升视觉体验：

- **主色调 Token**:
  - 背景底色: `#0B0F17` (Deep Obsidian)
  - 卡片与面板: `#131924` (Navy Dark) 配合 `backdrop-blur-xl` 玻璃拟态效果
  - 边框颜色: `#2A3447` (Slate Border)
  - 主品牌色: Violet 紫罗兰系列 (`#8B5CF6`, `#7C3AED`)
  - 成功与增益: Emerald 翡翠绿 (`#10B981`)
  - 警告与定金: Amber 琥珀黄 (`#F59E0B`)
  - 危险与退款: Rose 玫瑰红 (`#F43F5E`)
- **交互规范**:
  - 所有按钮与卡片均配置 Hover 渐变与 Subtle 微动画。
  - 所有表格单元格文本溢出时均使用 `text-ellipsis` 结合 `Tooltip` 悬浮提示。

---

## 6. 🚀 运行、构建与部署指南 (Execution & Deployment Guide)

### 6.1 环境要求
- **Python**: 3.10 或更高版本
- **Node.js**: v18.0.0 或更高版本 (推荐 v20+)
- **包管理器**: npm 或 pnpm

### 6.2 后端 (Django) 启动命令
```bash
# 1. 切换到项目根目录
cd e:\yurara-studio\yurara-studio-db

# 2. 执行数据库迁移 (若有改动)
python manage.py makemigrations
python manage.py migrate

# 3. 启动 Django 开发服务器 (默认端口 8000)
python manage.py runserver 0.0.0.0:8000
```

### 6.3 前端 (React Vite) 启动与构建命令
```bash
# 1. 切换到前端工程目录
cd e:\yurara-studio\yurara-studio-db\frontend

# 2. 安装依赖 (初次运行)
npm install

# 3. 启动前端 Vite 开发服务器 (默认端口 5173 / 3000)
npm run dev

# 4. 前端 TypeScript 类型检查
npx tsc --noEmit

# 5. 打包生产环境静态 Bundle
npm run build
```

---

> **总结**: 本系统完成了从单体 Reflex 到 Django DRF + React 19 分离架构的成功移植，在**数据准确性、汇率一致性、库存级联回滚、预售多对多绑定与前端高流畅度 UI** 上均达到了生产级标准。
