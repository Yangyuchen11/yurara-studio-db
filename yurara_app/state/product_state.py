# yurara_app/state/product_state.py
"""
商品管理 State。
负责：商品列表、创建/编辑/删除商品、颜色规格、定价矩阵、款式图片。
"""
import base64
import reflex as rx
from typing import Optional
from ..state.app_state import AppState
from constants import PLATFORM_CODES


# ---- 数据传输对象（用于 rx.State 序列化）----

class PriceEntry(rx.Base):
    platform: str = ""
    platform_label: str = ""
    price: float = 0.0


class ColorEntry(rx.Base):
    id: int = 0
    name: str = ""
    quantity: int = 0
    image_data: str = ""  # base64 data URL，空字符串表示无图
    prices: list[PriceEntry] = []


class PartEntry(rx.Base):
    part_name: str = ""
    quantity: int = 1


class ProductEntry(rx.Base):
    id: int = 0
    name: str = ""
    platform: str = ""
    total_quantity: int = 0
    is_completed: bool = False
    colors: list[ColorEntry] = []


# ---- 新建/编辑表单用的临时行数据 ----

class ColorRow(rx.Base):
    """用于新建/编辑表单中的颜色规格行。"""
    key: str = ""   # 前端唯一 key，用 uuid 或 index
    name: str = ""
    quantity: int = 0
    prices: dict[str, float] = {}  # {platform_key: price}
    image_data: str = ""


class PartRow(rx.Base):
    key: str = ""
    part_name: str = ""
    quantity: int = 1


PLATFORMS = list(PLATFORM_CODES.keys())
PLATFORM_OPTIONS = [{"key": k, "label": v} for k, v in PLATFORM_CODES.items()]
PLATFORM_LAUNCH_OPTIONS = ["微店", "Booth", "Instagram", "日本线下", "中国线下", "其他"]


class ProductState(AppState):
    """商品管理页状态。"""

    # --- 商品列表 ---
    products: list[ProductEntry] = []
    is_loading: bool = False

    # --- 当前激活的 Tab ---
    active_tab: str = "list"  # "list" | "create" | "edit"

    # === 新建表单状态 ===
    create_name: str = ""
    create_platform: str = "微店"
    create_color_rows: list[ColorRow] = []
    create_part_rows: list[PartRow] = []
    create_error: str = ""

    # === 编辑表单状态 ===
    edit_product_id: int = 0
    edit_name: str = ""
    edit_platform: str = "微店"
    edit_color_rows: list[ColorRow] = []
    edit_part_rows: list[PartRow] = []
    edit_error: str = ""

    # === 删除确认 ===
    delete_confirm_id: int = 0

    # ===================== 属性计算 =====================

    @rx.var
    def platform_codes(self) -> list[dict]:
        return PLATFORM_OPTIONS

    @rx.var
    def platform_launch_options(self) -> list[str]:
        return PLATFORM_LAUNCH_OPTIONS

    @rx.var
    def has_products(self) -> bool:
        return len(self.products) > 0

    # ===================== 加载数据 =====================

    @rx.event
    def load_products(self):
        """从数据库加载所有商品。"""
        self.is_loading = True
        yield
        db = self.get_db()
        try:
            from services.product_service import ProductService
            service = ProductService(db)
            prods = service.get_all_products()
            result = []
            for p in prods:
                colors = []
                for c in p.colors:
                    prices = []
                    for pf_key, pf_label in PLATFORM_CODES.items():
                        price_val = 0.0
                        for pr in c.prices:
                            if pr.platform == pf_key:
                                price_val = pr.price
                                break
                        prices.append(PriceEntry(
                            platform=pf_key,
                            platform_label=pf_label,
                            price=price_val,
                        ))
                    colors.append(ColorEntry(
                        id=c.id,
                        name=c.color_name,
                        quantity=c.quantity,
                        image_data=getattr(c, "image_data", "") or "",
                        prices=prices,
                    ))
                result.append(ProductEntry(
                    id=p.id,
                    name=p.name,
                    platform=p.target_platform or "",
                    total_quantity=p.total_quantity or 0,
                    is_completed=p.is_production_completed or False,
                    colors=colors,
                ))
            self.products = result
        except Exception as e:
            print(f"[ProductState] load_products error: {e}")
        finally:
            db.close()
            self.is_loading = False

    # ===================== 新建表单 =====================

    @rx.event
    def init_create_form(self):
        """初始化新建表单（重置状态）。"""
        self.create_name = ""
        self.create_platform = "微店"
        self.create_color_rows = [
            ColorRow(
                key="row_0",
                name="",
                quantity=0,
                prices={k: 0.0 for k in PLATFORMS},
            )
        ]
        self.create_part_rows = [PartRow(key="part_0", part_name="", quantity=1)]
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
        idx = len(self.create_color_rows)
        self.create_color_rows.append(
            ColorRow(
                key=f"row_{idx}",
                name="",
                quantity=0,
                prices={k: 0.0 for k in PLATFORMS},
            )
        )

    @rx.event
    def remove_create_color_row(self, key: str):
        self.create_color_rows = [r for r in self.create_color_rows if r.key != key]

    @rx.event
    def update_create_color_field(self, key: str, field: str, value):
        """更新颜色行的某个字段。"""
        for row in self.create_color_rows:
            if row.key == key:
                if field == "name":
                    row.name = str(value)
                elif field == "quantity":
                    row.quantity = int(value or 0)
                elif field.startswith("price_"):
                    pf_key = field[6:]  # 去掉 "price_" 前缀
                    row.prices[pf_key] = float(value or 0)
                break

    @rx.event
    def add_create_part_row(self):
        idx = len(self.create_part_rows)
        self.create_part_rows.append(PartRow(key=f"part_{idx}", part_name="", quantity=1))

    @rx.event
    def remove_create_part_row(self, key: str):
        self.create_part_rows = [r for r in self.create_part_rows if r.key != key]

    @rx.event
    def update_create_part_field(self, key: str, field: str, value):
        for row in self.create_part_rows:
            if row.key == key:
                if field == "part_name":
                    row.part_name = str(value)
                elif field == "quantity":
                    row.quantity = int(value or 1)
                break

    @rx.event
    async def upload_create_color_image(self, key: str, files: list[rx.UploadFile]):
        """上传颜色缩略图并转为 base64 存储。"""
        if not files:
            return
        file = files[0]
        data = await file.read()
        # 压缩图片至 100x100
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

    @rx.event
    def save_create_product(self):
        """提交新建商品表单。"""
        # 验证
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
                colors_with_prices.append({
                    "name": row.name.strip(),
                    "qty": row.quantity,
                    "prices": dict(row.prices),
                    "image_data": row.image_data or None,
                })

            # 部件（所有颜色共用）
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

        # 成功：重置表单并刷新列表
        self.init_create_form()
        self.active_tab = "list"
        yield ProductState.load_products()

    # ===================== 编辑表单 =====================

    @rx.event
    def load_edit_product(self, product_id: int):
        """加载指定商品进入编辑表单。"""
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
                prices = {k: 0.0 for k in PLATFORMS}
                for pr in c.prices:
                    if pr.platform in prices:
                        prices[pr.platform] = pr.price
                color_rows.append(ColorRow(
                    key=f"edit_row_{i}",
                    name=c.color_name,
                    quantity=c.quantity,
                    prices=prices,
                    image_data=getattr(c, "image_data", "") or "",
                ))
            self.edit_color_rows = color_rows

            # 部件（取第一个颜色的部件列表作为模板）
            part_rows = []
            if p.colors and p.colors[0].parts:
                for i, pt in enumerate(p.colors[0].parts):
                    part_rows.append(PartRow(
                        key=f"edit_part_{i}",
                        part_name=pt.part_name,
                        quantity=pt.quantity,
                    ))
            if not part_rows:
                part_rows = [PartRow(key="edit_part_0", part_name="", quantity=1)]
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
        idx = len(self.edit_color_rows)
        self.edit_color_rows.append(
            ColorRow(
                key=f"edit_row_{idx}",
                name="",
                quantity=0,
                prices={k: 0.0 for k in PLATFORMS},
            )
        )

    @rx.event
    def remove_edit_color_row(self, key: str):
        self.edit_color_rows = [r for r in self.edit_color_rows if r.key != key]

    @rx.event
    def update_edit_color_field(self, key: str, field: str, value):
        for row in self.edit_color_rows:
            if row.key == key:
                if field == "name":
                    row.name = str(value)
                elif field == "quantity":
                    row.quantity = int(value or 0)
                elif field.startswith("price_"):
                    pf_key = field[6:]
                    row.prices[pf_key] = float(value or 0)
                break

    @rx.event
    def save_edit_product(self):
        """提交编辑商品。"""
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

            import pandas as pd
            color_rows_data = []
            for row in valid_colors:
                r = {"颜色名称": row.name.strip(), "库存/预计数量": row.quantity}
                for pf_key in PLATFORMS:
                    r[pf_key] = row.prices.get(pf_key, 0.0)
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
