# yurara_app/state/product_state.py
"""
商品管理 State。
负责：商品列表、创建/编辑/删除商品、颜色规格、定价矩阵、款式图片。

Reflex 0.9.x 兼容：使用 Pydantic BaseModel 作为状态的数据类型，以提供强类型支持，
从而允许 rx.foreach 成功编译嵌套的列表与属性访问。
"""
import base64
import reflex as rx
from pydantic import BaseModel
from ..state.app_state import AppState
from constants import PLATFORM_CODES

PLATFORMS = list(PLATFORM_CODES.keys())
PLATFORM_OPTIONS = [{"key": k, "label": v} for k, v in PLATFORM_CODES.items()]
PLATFORM_LAUNCH_OPTIONS = ["微店", "Booth", "Instagram", "日本线下", "中国线下", "其他"]

# ===================== Pydantic 强类型声明 =====================

class ColorRow(BaseModel):
    key: str = ""
    name: str = ""
    quantity: int = 0
    image_data: str = ""
    price_weidian: float = 0.0
    price_booth: float = 0.0
    price_offline_cn: float = 0.0
    price_offline_jp: float = 0.0
    price_instagram: float = 0.0
    price_other: float = 0.0
    price_other_jpy: float = 0.0

class PartRow(BaseModel):
    key: str = ""
    part_name: str = ""
    quantity: int = 1

class ProductItem(BaseModel):
    id: int = 0
    name: str = ""
    platform: str = ""
    total_quantity: int = 0
    is_completed: bool = False
    color_summary: str = ""
    color_rows: list[ColorRow] = []

# ---- 空行模板 ----
def _new_color_row(idx: int) -> ColorRow:
    prices = {f"price_{k}": 0.0 for k in PLATFORMS}
    return ColorRow(key=f"row_{idx}", name="", quantity=0, image_data="", **prices)

def _new_part_row(idx: int) -> PartRow:
    return PartRow(key=f"part_{idx}", part_name="", quantity=1)


class ProductState(AppState):
    """商品管理页状态。"""

    # --- 商品列表（list of ProductItem） ---
    products: list[ProductItem] = []
    is_loading: bool = False

    # --- 当前激活的 Tab ---
    active_tab: str = "list"

    # === 新建表单 ===
    create_name: str = ""
    create_platform: str = "微店"
    create_color_rows: list[ColorRow] = []
    create_part_rows: list[PartRow] = []
    create_error: str = ""

    # === 编辑表单 ===
    edit_product_id: int = 0
    edit_name: str = ""
    edit_platform: str = "微店"
    edit_color_rows: list[ColorRow] = []
    edit_part_rows: list[PartRow] = []
    edit_error: str = ""

    # ===================== 计算属性 =====================

    @rx.var
    def platform_launch_options(self) -> list[str]:
        return PLATFORM_LAUNCH_OPTIONS

    @rx.var
    def platform_keys(self) -> list[str]:
        return PLATFORMS

    @rx.var
    def has_products(self) -> bool:
        return len(self.products) > 0

    # ===================== 加载数据 =====================

    @rx.event
    def load_products(self):
        self.is_loading = True
        yield
        db = self.get_db()
        try:
            from services.product_service import ProductService
            service = ProductService(db)
            prods = service.get_all_products()
            result = []
            for p in prods:
                # 构建展平的颜色行（用于列表展示的定价表格）
                color_rows = []
                color_names = []
                for c in p.colors:
                    color_names.append(c.color_name)
                    prices = {
                        "price_weidian": 0.0,
                        "price_booth": 0.0,
                        "price_offline_cn": 0.0,
                        "price_offline_jp": 0.0,
                        "price_instagram": 0.0,
                        "price_other": 0.0,
                        "price_other_jpy": 0.0,
                    }
                    for pr in c.prices:
                        field_key = f"price_{pr.platform}"
                        if field_key in prices:
                            prices[field_key] = pr.price
                    
                    color_rows.append(
                        ColorRow(
                            key=f"row_{len(color_rows)}",
                            name=c.color_name,
                            quantity=c.quantity,
                            image_data=getattr(c, "image_data", "") or "",
                            **prices
                        )
                    )

                result.append(
                    ProductItem(
                        id=p.id,
                        name=p.name,
                        platform=p.target_platform or "",
                        total_quantity=p.total_quantity or 0,
                        is_completed=p.is_production_completed or False,
                        # 颜色名称摘要字符串
                        color_summary="规格: " + "、".join(color_names) if color_names else "暂无规格",
                        # 展平的颜色行，供产品卡片列表中的定价表使用
                        color_rows=color_rows,
                    )
                )

            self.products = result
        except Exception as e:
            print(f"[ProductState] load_products error: {e}")
        finally:
            db.close()
            self.is_loading = False

    # ===================== 新建表单 =====================

    @rx.event
    def init_create_form(self):
        self.create_name = ""
        self.create_platform = "微店"
        self.create_color_rows = [_new_color_row(0)]
        self.create_part_rows = [_new_part_row(0)]
        self.create_error = ""
        self.active_tab = "create"

    @rx.event
    def set_create_name(self, value: str):
        self.create_name = value

    @rx.event
    def set_create_platform(self, value: str):
        self.create_platform = value

    @rx.event
    def add_create_color_row(self):
        self.create_color_rows.append(_new_color_row(len(self.create_color_rows)))

    @rx.event
    def remove_create_color_row(self, key: str):
        self.create_color_rows = [r for r in self.create_color_rows if r.key != key]

    @rx.event
    def update_create_color_field(self, key: str, field: str, value: str):
        for row in self.create_color_rows:
            if row.key == key:
                if field == "name":
                    row.name = value
                elif field == "quantity":
                    try:
                        row.quantity = int(value)
                    except ValueError:
                        row.quantity = 0
                elif field.startswith("price_"):
                    try:
                        setattr(row, field, float(value))
                    except ValueError:
                        setattr(row, field, 0.0)
                break
        self.create_color_rows = list(self.create_color_rows)

    @rx.event
    def add_create_part_row(self):
        self.create_part_rows.append(_new_part_row(len(self.create_part_rows)))

    @rx.event
    def remove_create_part_row(self, key: str):
        self.create_part_rows = [r for r in self.create_part_rows if r.key != key]

    @rx.event
    def update_create_part_field(self, key: str, field: str, value: str):
        for row in self.create_part_rows:
            if row.key == key:
                if field == "part_name":
                    row.part_name = value
                elif field == "quantity":
                    try:
                        row.quantity = int(value)
                    except ValueError:
                        row.quantity = 1
                break
        self.create_part_rows = list(self.create_part_rows)

    @rx.event
    async def upload_create_color_image(self, key: str, files: list[rx.UploadFile]):
        if not files:
            return
        file = files[0]
        data = await file.read()
        try:
            from PIL import Image
            from io import BytesIO
            img = Image.open(BytesIO(data))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail((100, 100))
            buf = BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            data_url = f"data:image/png;base64,{b64}"
        except Exception:
            data_url = ""

        for row in self.create_color_rows:
            if row.key == key:
                row.image_data = data_url
                break
        self.create_color_rows = list(self.create_color_rows)

    @rx.event
    def save_create_product(self):
        if not self.create_name.strip():
            self.create_error = "产品名称不能为空"
            return
        valid_colors = [r for r in self.create_color_rows if r.name.strip()]
        if not valid_colors:
            self.create_error = "请至少添加一个颜色规格"
            return

        self.create_error = ""
        db = self.get_db()
        try:
            from services.product_service import ProductService
            import pandas as pd
            service = ProductService(db)

            colors_with_prices = []
            for row in valid_colors:
                prices = {k: getattr(row, f"price_{k}", 0.0) for k in PLATFORMS}
                colors_with_prices.append({
                    "name": row.name.strip(),
                    "qty": row.quantity,
                    "prices": prices,
                    "image_data": row.image_data or None,
                })

            valid_parts = [r for r in self.create_part_rows if r.part_name.strip()]
            all_color_names = [r.name.strip() for r in valid_colors]
            parts_rows = []
            for c_name in all_color_names:
                for p_row in valid_parts:
                    parts_rows.append({
                        "颜色名称": c_name,
                        "部件名称": p_row.part_name,
                        "数量": p_row.quantity,
                    })
            parts_df = pd.DataFrame(parts_rows) if parts_rows else pd.DataFrame(
                columns=["颜色名称", "部件名称", "数量"]
            )

            service.create_product(
                name=self.create_name.strip(),
                platform=self.create_platform,
                colors_with_prices=colors_with_prices,
                parts_df=parts_df,
            )
            db.commit()
        except Exception as e:
            db.rollback()
            self.create_error = f"创建失败: {e}"
            return
        finally:
            db.close()

        self.active_tab = "list"
        yield ProductState.load_products()

    # ===================== 编辑表单 =====================

    @rx.event
    def load_edit_product(self, product_id: int):
        db = self.get_db()
        try:
            from services.product_service import ProductService
            service = ProductService(db)
            p = service.get_product_by_id(product_id)
            if not p:
                return

            self.edit_product_id = p.id
            self.edit_name = p.name
            self.edit_platform = p.target_platform or "微店"

            color_rows = []
            for i, c in enumerate(p.colors):
                prices = {f"price_{k}": 0.0 for k in PLATFORMS}
                for pr in c.prices:
                    if pr.platform in PLATFORMS:
                        prices[f"price_{pr.platform}"] = pr.price
                
                row = ColorRow(
                    key=f"edit_row_{i}",
                    name=c.color_name,
                    quantity=c.quantity,
                    image_data=getattr(c, "image_data", "") or "",
                    **prices
                )
                color_rows.append(row)
            self.edit_color_rows = color_rows

            part_rows = []
            if p.colors and p.colors[0].parts:
                for i, pt in enumerate(p.colors[0].parts):
                    part_rows.append(
                        PartRow(
                            key=f"edit_part_{i}",
                            part_name=pt.part_name,
                            quantity=pt.quantity,
                        )
                    )
            if not part_rows:
                part_rows = [_new_part_row(0)]
            self.edit_part_rows = part_rows
            self.edit_error = ""
            self.active_tab = "edit"
        finally:
            db.close()

    @rx.event
    def set_edit_name(self, value: str):
        self.edit_name = value

    @rx.event
    def set_edit_platform(self, value: str):
        self.edit_platform = value

    @rx.event
    def add_edit_color_row(self):
        self.edit_color_rows.append(_new_color_row(len(self.edit_color_rows)))

    @rx.event
    def remove_edit_color_row(self, key: str):
        self.edit_color_rows = [r for r in self.edit_color_rows if r.key != key]

    @rx.event
    def update_edit_color_field(self, key: str, field: str, value: str):
        for row in self.edit_color_rows:
            if row.key == key:
                if field == "name":
                    row.name = value
                elif field == "quantity":
                    try:
                        row.quantity = int(value)
                    except ValueError:
                        row.quantity = 0
                elif field.startswith("price_"):
                    try:
                        setattr(row, field, float(value))
                    except ValueError:
                        setattr(row, field, 0.0)
                break
        self.edit_color_rows = list(self.edit_color_rows)

    @rx.event
    def save_edit_product(self):
        if not self.edit_name.strip():
            self.edit_error = "产品名称不能为空"
            return
        valid_colors = [r for r in self.edit_color_rows if r.name.strip()]
        if not valid_colors:
            self.edit_error = "请至少保留一个规格"
            return

        self.edit_error = ""
        db = self.get_db()
        try:
            from services.product_service import ProductService
            import pandas as pd
            service = ProductService(db)

            color_rows_data = []
            for row in valid_colors:
                r = {"颜色名称": row.name.strip(), "库存/预计数量": row.quantity}
                for pf_key in PLATFORMS:
                    r[pf_key] = getattr(row, f"price_{pf_key}", 0.0)
                color_rows_data.append(r)
            color_df = pd.DataFrame(color_rows_data)

            valid_parts = [r for r in self.edit_part_rows if r.part_name.strip()]
            all_color_names = [r.name.strip() for r in valid_colors]
            parts_rows = []
            for c_name in all_color_names:
                for p_row in valid_parts:
                    parts_rows.append({
                        "颜色名称": c_name,
                        "部件名称": p_row.part_name,
                        "数量": p_row.quantity,
                    })
            parts_df = pd.DataFrame(parts_rows) if parts_rows else pd.DataFrame(
                columns=["颜色名称", "部件名称", "数量"]
            )

            image_map = {row.name.strip(): row.image_data or None for row in valid_colors}

            service.update_product(
                product_id=self.edit_product_id,
                name=self.edit_name.strip(),
                platform=self.edit_platform,
                color_matrix_data=color_df,
                parts_df=parts_df,
                image_map=image_map,
            )
            db.commit()
        except Exception as e:
            db.rollback()
            self.edit_error = f"修改失败: {e}"
            return
        finally:
            db.close()

        self.active_tab = "list"
        yield ProductState.load_products()

    # ===================== 删除 =====================

    @rx.event
    def delete_product(self, product_id: int):
        db = self.get_db()
        try:
            from services.product_service import ProductService
            service = ProductService(db)
            service.delete_product(product_id)
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[ProductState] delete_product error: {e}")
        finally:
            db.close()
        yield ProductState.load_products()

    @rx.event
    def switch_tab(self, tab: str):
        self.active_tab = tab
