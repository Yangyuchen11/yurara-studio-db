// frontend/src/types/index.ts

export interface ProductPrice {
  id?: number;
  color: number;
  platform: string;
  currency: string;
  price: number;
}

export interface ProductPart {
  id?: number;
  color: number;
  part_name: string;
  quantity: number;
}

export interface ProductColor {
  id: number;
  product: number;
  color_name: string;
  sku_code?: string;
  quantity?: number;
  produced_quantity?: number;
  image_data?: string;
  image?: string;
  prices?: ProductPrice[];
  parts?: ProductPart[];
}

export interface CostItem {
  id: number;
  product: number;
  item_name?: string;
  actual_cost?: number;
  supplier?: string;
  category?: string;
  unit_price?: number;
  quantity?: number;
  unit?: string;
  remarks?: string;
  url?: string;
  currency?: string;
  is_budget?: boolean;
  actual_qty?: number;
  actual_unit_price?: number;
  material_cost?: number;
  labor_cost?: number;
  shipping_cost?: number;
  other_cost?: number;
  total_cost?: number;
  notes?: string;
}

export interface Product {
  id: number;
  name: string;
  spu_code?: string;
  total_quantity?: number;
  marketable_quantity?: number;
  is_production_completed?: boolean;
  target_platform?: string;
  colors?: ProductColor[];
  costs?: CostItem[];
}

export interface Warehouse {
  id: number;
  name: string;
  remarks?: string;
}

export interface FinanceRecord {
  id: number;
  date: string;
  direction?: string;
  type?: string;
  amount: number;
  currency: string;
  category: string;
  description?: string;
  account_name?: string;
  account_id?: number;
  account?: string;
  url?: string;
  order_id?: number;
  related_cost_id?: number;
  child_items?: Array<{
    id?: number;
    name: string;
    amount: number;
    qty: number;
    desc?: string;
    url?: string;
    category?: string;
  }>;
}

export interface CompanyBalanceItem {
  id: number;
  item_type?: string;
  category?: string;
  name: string;
  amount: number;
  currency: string;
  asset_type?: string;
  product_id?: number;
  notes?: string;
}

export interface InventoryLog {
  id: number;
  product_name: string;
  variant?: string;
  move_type?: string;
  quantity?: number;
  change_amount?: number;
  reason?: string;
  remark?: string;
  date: string;
  note?: string;
  is_sold?: boolean;
  sale_amount?: number;
  currency?: string;
  platform?: string;
  warehouse_id?: number;
  part_name?: string;
}

export interface SalesOrderItem {
  id?: number;
  order?: number;
  product_name: string;
  variant?: string;
  quantity: number;
  unit_price: number;
  subtotal?: number;
  warehouse_id?: number;
}

export interface OrderRefund {
  id: number;
  order: number;
  refund_amount: number;
  refund_reason?: string;
  refund_date: string;
  is_returned: boolean;
  returned_quantity: number;
}

export interface SalesOrder {
  id: number;
  order_no: string;
  order_type?: string;
  final_order_no?: string;
  deposit_amount?: number;
  final_amount?: number;
  status?: string;
  total_amount: number;
  currency: string;
  platform?: string;
  target_account_name?: string;
  created_date?: string;
  shipped_date?: string;
  completed_date?: string;
  notes?: string;
  discount_note?: string;
  items?: SalesOrderItem[];
  refunds?: OrderRefund[];
}

export interface FixedAsset {
  id: number;
  name: string;
  category?: string;
  unit_price?: number;
  quantity?: number;
  remaining_qty?: number;
  shop_name?: string;
  remarks?: string;
  purchase_date?: string;
  currency?: string;
  original_value?: number;
  current_value?: number;
  useful_life_years?: number;
  status?: string;
  notes?: string;
}

export interface ConsumableItem {
  id: number;
  name: string;
  category?: string;
  stock_quantity?: number;
  unit?: string;
  safety_stock?: number;
  unit_price?: number;
  initial_quantity?: number;
  remaining_qty?: number;
  shop_name?: string;
  remarks?: string;
  purchase_date?: string;
  currency?: string;
  notes?: string;
}

export interface MemoNote {
  id: number;
  date: string;
  content: string;
  created_at: string;
}

export interface SalesPlatform {
  id: number;
  name: string;
  code: string;
  fee_rate?: number;
  currency?: string;
  is_active?: boolean;
  notes?: string;
}
