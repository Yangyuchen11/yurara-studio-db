from sqlalchemy.orm import Session, joinedload
from models import Product, ProductColor, ProductPrice, ProductPart
from constants import PLATFORM_CURRENCY_MAP, PLATFORM_CODES

class ProductService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_products(self):
        """
        获取所有产品，按ID倒序排列
        级联加载路径：Product -> ProductColor -> ProductPrice / ProductPart
        """
        return self.db.query(Product)\
            .options(
                joinedload(Product.colors).joinedload(ProductColor.prices),
                joinedload(Product.colors).joinedload(ProductColor.parts)
            )\
            .order_by(Product.id.desc()).all()

    def get_product_by_id(self, product_id):
        """根据ID获取单个产品"""
        return self.db.query(Product)\
            .options(
                joinedload(Product.colors).joinedload(ProductColor.prices),
                joinedload(Product.colors).joinedload(ProductColor.parts)
            )\
            .filter(Product.id == product_id).first()

    def get_product_colors(self, product_id):
        """获取指定产品的所有颜色规格"""
        return self.db.query(ProductColor)\
            .options(joinedload(ProductColor.prices), joinedload(ProductColor.parts))\
            .filter(ProductColor.product_id == product_id).all()

    def _update_color_prices(self, color_id, prices_dict):
        """内部辅助函数：更新特定颜色规格的价格"""
        # 1. 删除该颜色旧价格
        self.db.query(ProductPrice).filter(ProductPrice.color_id == color_id).delete()

        # 2. 写入新价格
        for pf_key, price_val in prices_dict.items():
            if price_val and float(price_val) > 0:
                currency = PLATFORM_CURRENCY_MAP.get(pf_key)
                if currency:
                    new_price = ProductPrice(
                        color_id=color_id,
                        platform=pf_key,
                        currency=currency,
                        price=float(price_val)
                    )
                    self.db.add(new_price)

    def create_product(self, name, platform, colors_with_prices, parts_df=None):
        """创建新产品及其规格和部件"""
        # 1. 计算总数量
        total_q = sum([item['qty'] for item in colors_with_prices])

        # 2. 创建主表对象
        new_prod = Product(
            name=name,
            target_platform=platform,
            total_quantity=total_q,
            marketable_quantity=total_q 
        )
        self.db.add(new_prod)
        self.db.flush() # 获取 ID
        
        # 3. 插入颜色规格并保存价格
        for item in colors_with_prices:
            new_color = ProductColor(
                product_id=new_prod.id, 
                color_name=item['name'],
                quantity=item['qty'],
                image_data=item.get('image_data')
            )
            self.db.add(new_color)
            self.db.flush() # 获取 Color ID
            
            # 保存该颜色的价格
            if 'prices' in item:
                self._update_color_prices(new_color.id, item['prices'])

            # 保存该颜色的部件
            if parts_df is not None and not parts_df.empty:
                color_parts = parts_df[parts_df["颜色名称"] == item['name']]
                for _, prow in color_parts.iterrows():
                    p_name = str(prow.get("部件名称", "")).strip()
                    p_qty = int(prow.get("数量", 1))
                    if p_name and p_qty > 0:
                        self.db.add(ProductPart(
                            color_id=new_color.id, 
                            part_name=p_name, 
                            quantity=p_qty
                        ))
        
        self.db.commit()
        return new_prod

    def update_product(self, product_id, name, platform, color_matrix_data, parts_df=None, image_map=None):
        """更新产品信息"""
        target_prod = self.get_product_by_id(product_id)
        if not target_prod:
            raise ValueError("产品不存在")

        # 1. 更新主表基础信息
        target_prod.name = name
        target_prod.target_platform = platform
        
        # 2. 更新颜色规格
        # 删除旧颜色前，如果没传入新图片，可以考虑保留原图片逻辑（此处简化为覆盖）
        self.db.query(ProductColor).filter(ProductColor.product_id == target_prod.id).delete()
        new_total_qty = 0
        for index, row in color_matrix_data.iterrows():
            c_name = row.get("颜色名称")
            # ✨ 从传入的 map 中获取该颜色对应的图片
            img_data = image_map.get(c_name) if image_map else None
            c_qty = int(row.get("库存/预计数量", 0))
            
            if c_name: 
                new_color = ProductColor(
                    product_id=target_prod.id, 
                    color_name=str(c_name), 
                    quantity=c_qty,
                    image_data=img_data
                )
                self.db.add(new_color)
                self.db.flush() # 获取 Color ID
                new_total_qty += c_qty
                
                # 3. 提取并更新价格
                row_prices = {}
                for pf_key in PLATFORM_CODES.keys():
                    if pf_key in row:
                        row_prices[pf_key] = row[pf_key]
                
                self._update_color_prices(new_color.id, row_prices)

                # 4. 提取并更新部件
                if parts_df is not None and not parts_df.empty:
                    color_parts = parts_df[parts_df["颜色名称"] == str(c_name)]
                    for _, prow in color_parts.iterrows():
                        p_name = str(prow.get("部件名称", "")).strip()
                        p_qty = int(prow.get("数量", 1))
                        if p_name and p_qty > 0:
                            self.db.add(ProductPart(
                                color_id=new_color.id, 
                                part_name=p_name, 
                                quantity=p_qty
                            ))
        
        # 更新主表的总数量
        target_prod.total_quantity = new_total_qty

        self.db.commit()
        return target_prod

    def delete_product(self, product_id):
        """删除产品"""
        target_prod = self.get_product_by_id(product_id)
        if target_prod:
            self.db.delete(target_prod)
            self.db.commit()