from sqlalchemy.orm import Session, joinedload
from models import Product, ProductColor, ProductPrice

class ProductService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_products(self):
        """
        获取所有产品，按ID倒序排列
        使用 joinedload 预加载价格和颜色，防止 N+1 查询问题
        """
        return self.db.query(Product)\
            .options(joinedload(Product.colors), joinedload(Product.prices))\
            .order_by(Product.id.desc()).all()

    def get_product_by_id(self, product_id):
        """根据ID获取单个产品"""
        return self.db.query(Product)\
            .options(joinedload(Product.colors), joinedload(Product.prices))\
            .filter(Product.id == product_id).first()

    def get_product_colors(self, product_id):
        """获取指定产品的所有颜色规格"""
        return self.db.query(ProductColor).filter(ProductColor.product_id == product_id).all()

    def _update_prices(self, product_id, prices_dict):
        """
        内部辅助函数：更新产品的价格列表
        策略：删除旧价格 -> 写入新价格
        prices_dict: {'weidian': 100, 'booth': 200, ...}
        """
        # 1. 定义平台与币种的映射关系
        # (平台代码, 币种)
        platform_map = {
            "weidian": "CNY",
            "offline_cn": "CNY",
            "other": "CNY",
            "booth": "JPY",
            "instagram": "JPY",
            "offline_jp": "JPY",
            "other_jpy": "JPY"
        }

        # 2. 删除旧价格
        self.db.query(ProductPrice).filter(ProductPrice.product_id == product_id).delete()

        # 3. 写入新价格
        for pf_key, price_val in prices_dict.items():
            # 只有金额 > 0 才存入数据库 (节省空间)
            if price_val and float(price_val) > 0:
                currency = platform_map.get(pf_key, "CNY")
                new_price = ProductPrice(
                    product_id=product_id,
                    platform=pf_key,
                    currency=currency,
                    price=float(price_val)
                )
                self.db.add(new_price)

    def create_product(self, name, platform, prices, colors):
        """
        创建新产品及其规格
        :param prices: 价格字典 {'weidian': 100, ...}
        """
        # 1. 计算总数量
        total_q = sum([item['qty'] for item in colors])

        # 2. 创建主表对象 (不再包含价格字段)
        new_prod = Product(
            name=name,
            target_platform=platform,
            total_quantity=total_q,
            marketable_quantity=total_q 
        )
        self.db.add(new_prod)
        self.db.flush() # 获取 ID
        
        # 3. 处理价格 (写入 ProductPrice 表)
        self._update_prices(new_prod.id, prices)
        
        # 4. 插入颜色规格
        for item in colors:
            self.db.add(ProductColor(
                product_id=new_prod.id, 
                color_name=item['name'],
                quantity=item['qty']
            ))
        
        self.db.commit()
        return new_prod

    def update_product(self, product_id, name, platform, prices, colors_df):
        """
        更新产品信息
        """
        target_prod = self.get_product_by_id(product_id)
        if not target_prod:
            raise ValueError("产品不存在")

        # 1. 更新主表基础信息
        target_prod.name = name
        target_prod.target_platform = platform
        
        # 2. 更新价格 (使用辅助函数)
        self._update_prices(target_prod.id, prices)
        
        # 3. 更新颜色规格 (策略：清空旧的 -> 写入新的)
        self.db.query(ProductColor).filter(ProductColor.product_id == target_prod.id).delete()
        
        new_total_qty = 0
        for index, row in colors_df.iterrows():
            c_name = row["颜色名称"]
            c_qty = int(row["库存/预计数量"])
            if c_name: 
                self.db.add(ProductColor(
                    product_id=target_prod.id, 
                    color_name=str(c_name), 
                    quantity=c_qty
                ))
                new_total_qty += c_qty
        
        # 4. 更新主表的总数量
        target_prod.total_quantity = new_total_qty

        self.db.commit()
        return target_prod

    def delete_product(self, product_id):
        """删除产品 (级联删除现在由数据库 CASCADE 保证)"""
        target_prod = self.get_product_by_id(product_id)
        if target_prod:
            self.db.delete(target_prod)
            self.db.commit()