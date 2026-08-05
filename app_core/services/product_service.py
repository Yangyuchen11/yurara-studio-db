# app_core/services/product_service.py
from django.db import transaction
from app_core.models import Product, ProductColor, ProductPrice, ProductPart, SalesPlatform

class ProductService:
    @staticmethod
    def get_all_products():
        """
        全商品を取得（ID降順）。関連するカラー、価格、パーツをあらかじめロード。
        """
        return Product.objects.prefetch_related('colors__prices', 'colors__parts').order_by('-id')

    @staticmethod
    def get_product_by_id(product_id: int):
        """
        ID指定で単一商品を取得。
        """
        return Product.objects.prefetch_related('colors__prices', 'colors__parts').filter(id=product_id).first()

    @staticmethod
    def get_product_colors(product_id: int):
        """
        指定商品のカラーバリエーション一覧を取得。
        """
        return ProductColor.objects.prefetch_related('prices', 'parts').filter(product_id=product_id)

    @staticmethod
    def _update_color_prices(color_id: int, prices_dict: dict):
        """
        内部ヘルパー: 特定カラーの価格情報を更新。
        """
        ProductPrice.objects.filter(color_id=color_id).delete()

        platforms = SalesPlatform.objects.all()
        platform_currency_map = {}
        for p in platforms:
            platform_currency_map[p.code] = p.currency
            platform_currency_map[p.name] = p.currency

        new_prices = []
        for pf_key, price_val in prices_dict.items():
            if price_val and float(price_val) > 0:
                currency = platform_currency_map.get(pf_key, "CNY")
                new_prices.append(
                    ProductPrice(
                        color_id=color_id,
                        platform=pf_key,
                        currency=currency,
                        price=float(price_val)
                    )
                )
        if new_prices:
            ProductPrice.objects.bulk_create(new_prices)

    @classmethod
    @transaction.atomic
    def create_product(cls, name: str, platform: str, colors_with_prices: list, parts_df=None):
        """
        新商品・カラー・価格・パーツを一括作成。
        """
        total_q = sum([item['qty'] for item in colors_with_prices])

        new_prod = Product.objects.create(
            name=name,
            target_platform=platform,
            total_quantity=total_q,
            marketable_quantity=total_q
        )

        for item in colors_with_prices:
            new_color = ProductColor.objects.create(
                product=new_prod,
                color_name=item['name'],
                quantity=item['qty'],
                image_data=item.get('image_data')
            )

            if 'prices' in item:
                cls._update_color_prices(new_color.id, item['prices'])

            if parts_df is not None and not parts_df.empty:
                color_parts = parts_df[parts_df["颜色名称"] == item['name']]
                parts_to_create = []
                for _, prow in color_parts.iterrows():
                    p_name = str(prow.get("部件名称", "")).strip()
                    p_qty = int(prow.get("数量", 1))
                    if p_name and p_qty > 0:
                        parts_to_create.append(
                            ProductPart(
                                color=new_color,
                                part_name=p_name,
                                quantity=p_qty
                            )
                        )
                if parts_to_create:
                    ProductPart.objects.bulk_create(parts_to_create)

        return new_prod

    @classmethod
    @transaction.atomic
    def update_product(cls, product_id: int, name: str, platform: str, color_matrix_data, parts_df=None, image_map=None):
        """
        商品情報の更新。
        """
        target_prod = cls.get_product_by_id(product_id)
        if not target_prod:
            raise ValueError("商品が存在しません。")

        target_prod.name = name
        target_prod.target_platform = platform

        ProductColor.objects.filter(product_id=target_prod.id).delete()
        new_total_qty = 0

        plats = SalesPlatform.objects.all()
        platform_codes = [p.code for p in plats]

        for index, row in color_matrix_data.iterrows():
            c_name = row.get("颜色名称")
            img_data = image_map.get(c_name) if image_map else None
            c_qty = int(row.get("库存/预计数量", 0))

            if c_name:
                new_color = ProductColor.objects.create(
                    product=target_prod,
                    color_name=str(c_name),
                    quantity=c_qty,
                    image_data=img_data
                )
                new_total_qty += c_qty

                row_prices = {}
                for pf_code in platform_codes:
                    if pf_code in row:
                        row_prices[pf_code] = row[pf_code]

                cls._update_color_prices(new_color.id, row_prices)

                if parts_df is not None and not parts_df.empty:
                    color_parts = parts_df[parts_df["颜色名称"] == str(c_name)]
                    parts_to_create = []
                    for _, prow in color_parts.iterrows():
                        p_name = str(prow.get("部件名称", "")).strip()
                        p_qty = int(prow.get("数量", 1))
                        if p_name and p_qty > 0:
                            parts_to_create.append(
                                ProductPart(
                                    color=new_color,
                                    part_name=p_name,
                                    quantity=p_qty
                                )
                            )
                    if parts_to_create:
                        ProductPart.objects.bulk_create(parts_to_create)

        target_prod.total_quantity = new_total_qty
        target_prod.save()
        return target_prod

    @classmethod
    @transaction.atomic
    def delete_product(cls, product_id: int):
        """
        商品を削除。
        """
        Product.objects.filter(id=product_id).delete()
