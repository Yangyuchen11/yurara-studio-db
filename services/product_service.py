from sqlalchemy.orm import Session
from models import Product, ProductColor

class ProductService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_products(self):
        """获取所有产品，按ID倒序排列"""
        return self.db.query(Product).order_by(Product.id.desc()).all()

    def get_product_by_id(self, product_id):
        """根据ID获取单个产品"""
        return self.db.query(Product).filter(Product.id == product_id).first()

    def get_product_colors(self, product_id):
        """获取指定产品的所有颜色规格"""
        return self.db.query(ProductColor).filter(ProductColor.product_id == product_id).all()

    def create_product(self, name, platform, prices, colors):
        """
        创建新产品及其规格
        :param name: 产品名称
        :param platform: 首发平台
        :param prices: 价格字典 {'weidian': 100, ...}
        :param colors: 颜色列表 [{'name': '蓝色', 'qty': 10}, ...]
        """
        # 1. 计算总数量
        total_q = sum([item['qty'] for item in colors])

        # 2. 创建主表对象
        new_prod = Product(
            name=name,
            target_platform=platform,
            price_weidian=prices.get('weidian', 0.0),
            price_booth=prices.get('booth', 0.0),
            price_offline_jp=prices.get('offline_jp', 0.0),
            price_offline_cn=prices.get('offline_cn', 0.0),
            price_other=prices.get('other', 0.0),
            price_instagram=prices.get('instagram', 0.0),
            price_other_jpy=prices.get('other_jpy', 0.0),
            total_quantity=total_q,
            marketable_quantity=total_q # 初始化可售数量
        )
        self.db.add(new_prod)
        self.db.flush() # 获取 ID
        
        # 3. 插入颜色规格
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
        :param colors_df: 包含 "颜色名称" 和 "库存/预计数量" 列的 Pandas DataFrame
        """
        target_prod = self.get_product_by_id(product_id)
        if not target_prod:
            raise ValueError("产品不存在")

        # 1. 更新主表基础信息
        target_prod.name = name
        target_prod.target_platform = platform
        
        target_prod.price_weidian = prices.get('weidian', 0.0)
        target_prod.price_booth = prices.get('booth', 0.0)
        target_prod.price_offline_jp = prices.get('offline_jp', 0.0)
        target_prod.price_offline_cn = prices.get('offline_cn', 0.0)
        target_prod.price_other = prices.get('other', 0.0)
        target_prod.price_instagram = prices.get('instagram', 0.0)
        target_prod.price_other_jpy = prices.get('other_jpy', 0.0)
        
        # 2. 更新颜色规格 (策略：清空旧的 -> 写入新的)
        # 注意：这里直接删除重建颜色表，如果有 InventoryLog 关联，需要确保外键约束正确或逻辑自洽
        self.db.query(ProductColor).filter(ProductColor.product_id == target_prod.id).delete()
        
        new_total_qty = 0
        # 遍历 DataFrame 写入新规格
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
        
        # 3. 更新主表的总数量
        target_prod.total_quantity = new_total_qty

        self.db.commit()
        return target_prod

    def delete_product(self, product_id):
        """删除产品 (级联删除颜色在数据库模型中定义)"""
        target_prod = self.get_product_by_id(product_id)
        if target_prod:
            self.db.delete(target_prod)
            self.db.commit()