"""
End-to-end tests for the Consignment Management overhaul (Sales Management module):
- Shop CRUD & constraints
- Dispatch from physical warehouse -> stock deduction & stock_value sync
- Return to warehouse -> stock restoration & StockLogReason.CONSIGNMENT_RETURN
- Revoke return -> negative stock guard & state restoration
- Single & Batch settlement -> fee/net math, cash account credit, FinanceRecord, SalesOrder, SalesService analytics
- Settlement deletion rollback
- Inventory log cascade guard
- REST API endpoints under /api/v1/consignments*
"""
import os
import sys
from datetime import date
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import (
    Base,
    Product,
    ProductColor,
    ProductPart,
    ProductPrice,
    Warehouse,
    InventoryLog,
    CompanyBalanceItem,
    FinanceRecord,
    SalesOrder,
    SalesOrderItem,
    ConsignmentShop,
    ConsignmentItem,
    ConsignmentSettlement,
    ConsignmentSettlementItem,
    ConsignmentReturn,
)
from constants import BalanceCategory, FinanceCategory, StockLogReason, OrderStatus
from services.inventory_service import InventoryService
from services.consignment_service import ConsignmentService
from services.sales_service import SalesService
from api import create_mobile_api_app
from api.deps import get_db_session, verify_auth_token


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_catalog_and_stock(db):
    wh_a = Warehouse(name="主仓库A")
    wh_b = Warehouse(name="分仓B")
    db.add_all([wh_a, wh_b])

    cash_acc = CompanyBalanceItem(
        category=BalanceCategory.ASSET,
        name="微信对公户",
        asset_type="现金",
        amount=1000.0,
        currency="CNY",
    )
    jpy_acc = CompanyBalanceItem(
        category=BalanceCategory.ASSET,
        name="日元现金账户",
        asset_type="现金",
        amount=50000.0,
        currency="JPY",
    )
    db.add_all([cash_acc, jpy_acc])

    prod = Product(
        name="星夜连衣裙",
        total_quantity=20,
        marketable_quantity=20,
    )
    db.add(prod)
    db.flush()

    c_blue = ProductColor(product_id=prod.id, color_name="绀蓝", quantity=10)
    c_pink = ProductColor(product_id=prod.id, color_name="樱粉", quantity=10)
    db.add_all([c_blue, c_pink])
    db.flush()

    db.add_all([
        ProductPart(color_id=c_blue.id, part_name="OP本体", quantity=1),
        ProductPart(color_id=c_pink.id, part_name="OP本体", quantity=1),
        ProductPrice(color_id=c_blue.id, platform="通用", currency="CNY", price=400.0),
        ProductPrice(color_id=c_pink.id, platform="通用", currency="CNY", price=420.0),
    ])
    db.flush()

    inv = InventoryService(db)
    for var_name, qty in [("绀蓝", 10), ("樱粉", 6)]:
        inv.add_inventory_movement(
            product_id=prod.id,
            product_name=prod.name,
            variant=var_name,
            quantity=qty,
            move_type="入库验收",
            date_obj=date(2026, 3, 1),
            remark="送检入库",
            warehouse_id=wh_a.id,
            is_set=False,
            part_name="OP本体",
        )
        inv.add_inventory_movement(
            product_id=prod.id,
            product_name=prod.name,
            variant=var_name,
            quantity=qty,
            move_type="验收完成入库",
            date_obj=date(2026, 3, 1),
            remark="合格入库",
            warehouse_id=wh_a.id,
            is_set=False,
            part_name="OP本体",
        )
    db.commit()
    return wh_a, wh_b, cash_acc, jpy_acc, prod


def test_consignment_full_lifecycle(db_session):
    wh_a, wh_b, cash_acc, _, prod = _seed_catalog_and_stock(db_session)
    cs = ConsignmentService(db_session)
    inv = InventoryService(db_session)

    # 1. Create Shop Profile
    shop = cs.create_shop(
        name="秋叶原委托店",
        currency="CNY",
        default_fee_rate=0.20,
        default_fee_fixed=0.0,
        default_account_name="微信对公户",
        contact_info="月结",
    )
    db_session.commit()
    assert shop.id > 0

    # Verify initial stock in wh_a (10 + 6 = 16)
    wh_a_stock_before = inv.get_warehouse_inventory_details().get(wh_a.id, {}).get("stock", {}).get(prod.name, {})
    assert wh_a_stock_before["绀蓝"]["OP本体"] == 10
    assert wh_a_stock_before["樱粉"]["OP本体"] == 6

    # 2. Dispatch from Warehouse to Consignment Shop
    cs.dispatch_from_warehouse(
        shop_id=shop.id,
        shop_name=shop.name,
        warehouse_id=wh_a.id,
        product_name=prod.name,
        entries=[
            {"variant": "绀蓝", "part_name": "OP本体", "quantity": 4},
            {"variant": "樱粉", "part_name": "OP本体", "quantity": 2},
        ],
        dispatch_date=date(2026, 3, 5),
        remarks="春季寄售首批次",
    )
    db_session.commit()
    created_items = cs.get_all_consignments(shop_id=shop.id)
    assert len(created_items) == 2
    item_blue = next(i for i in created_items if i.variant == "绀蓝")
    item_pink = next(i for i in created_items if i.variant == "樱粉")
    assert item_blue.remaining_qty == 4
    assert item_blue.status == "寄售中"
    assert item_blue.warehouse_id == wh_a.id

    # Warehouse stock decreased: 10-4=6 blue, 6-2=4 pink
    wh_a_stock_after = inv.get_warehouse_inventory_details().get(wh_a.id, {}).get("stock", {}).get(prod.name, {})
    assert wh_a_stock_after["绀蓝"]["OP本体"] == 6
    assert wh_a_stock_after["樱粉"]["OP本体"] == 4

    # 3. Return 1 pink item back to wh_b
    returns = cs.return_to_warehouse(
        entries=[{"consignment_item_id": item_pink.id, "return_qty": 1}],
        warehouse_id=wh_b.id,
        return_date=date(2026, 3, 10),
        notes="调回分仓",
    )
    db_session.commit()
    assert len(returns) == 1
    db_session.refresh(item_pink)
    assert item_pink.returned_qty == 1
    assert item_pink.remaining_qty == 1
    assert item_pink.status == "部分结算"

    wh_b_stock = inv.get_warehouse_inventory_details().get(wh_b.id, {}).get("stock", {}).get(prod.name, {})
    assert wh_b_stock["樱粉"]["OP本体"] == 1

    # Guard: cannot delete outbound InventoryLog once consignment has return/sale
    with pytest.raises(ValueError, match="已发生销售结算"):
        inv.delete_log_cascade(item_pink.inventory_log_id)
    with pytest.raises(ValueError, match="寄售管理"):
        inv.delete_log_cascade(returns[0].inventory_log_id)

    # 4. Batch Settlement: 3 blue @ 400 + 1 pink @ 420 = 1620 gross
    # Fee 20% = 324 -> Net = 1296
    st = cs.create_settlement(
        shop_id=shop.id,
        shop_name=shop.name,
        items=[
            {"consignment_item_id": item_blue.id, "sold_qty": 3, "unit_price": 400.0},
            {"consignment_item_id": item_pink.id, "sold_qty": 1, "unit_price": 420.0},
        ],
        account_id=cash_acc.id,
        settlement_date=date(2026, 3, 15),
        currency="CNY",
        fee_rate=0.20,
        notes="3月上半月对账单",
    )
    db_session.commit()

    assert st.gross_amount == pytest.approx(1620.0)
    assert st.fee_amount == pytest.approx(324.0)
    assert st.net_amount == pytest.approx(1296.0)
    assert len(st.items) == 2

    db_session.refresh(item_blue)
    db_session.refresh(item_pink)
    db_session.refresh(cash_acc)
    assert item_blue.sold_qty == 3
    assert item_blue.remaining_qty == 1
    assert item_blue.status == "部分结算"
    assert item_pink.sold_qty == 1
    assert item_pink.remaining_qty == 0
    assert item_pink.status == "已结清"

    # Cash account increased by net_amount (1000 + 1296 = 2296)
    assert cash_acc.amount == pytest.approx(2296.0)

    # FinanceRecord & SalesOrder linked
    fin = db_session.query(FinanceRecord).filter(FinanceRecord.id == st.finance_record_id).first()
    so = db_session.query(SalesOrder).filter(SalesOrder.id == st.sales_order_id).first()
    assert fin is not None
    assert fin.category == FinanceCategory.SALES_INCOME
    assert fin.amount == pytest.approx(1296.0)
    assert so is not None
    assert so.order_type == "寄售"
    assert so.status == OrderStatus.COMPLETED
    assert so.total_amount == pytest.approx(1296.0)
    assert sum(si.subtotal for si in so.items) == pytest.approx(1296.0)

    # SalesService revenue attribution picks up consignment SalesOrder
    df_sales = SalesService.process_sales_data_v2(db_session)
    assert not df_sales.empty
    cons_rows = df_sales[df_sales["platform"].str.contains(shop.name, na=False)]
    assert not cons_rows.empty
    assert float(cons_rows["amount"].sum()) == pytest.approx(1296.0)
    assert int(cons_rows["qty"].sum()) == 4

    # Return remaining 1 blue item -> should transition to 已清账
    cs.return_to_warehouse(
        entries=[{"consignment_item_id": item_blue.id, "return_qty": 1}],
        warehouse_id=wh_a.id,
        return_date=date(2026, 3, 20),
    )
    db_session.commit()
    db_session.refresh(item_blue)
    assert item_blue.remaining_qty == 0
    assert item_blue.status == "已结清"  # sold_qty=3, returned_qty=1, remaining=0

    # 5. Revoke settlement -> restores sold_qty, remaining_qty, status, cash_acc, deletes SalesOrder & FinanceRecord
    cs.delete_settlement(st.id)
    db_session.commit()

    db_session.refresh(item_blue)
    db_session.refresh(item_pink)
    db_session.refresh(cash_acc)
    assert item_blue.sold_qty == 0
    assert item_blue.remaining_qty == 3
    assert item_blue.status == "部分结算"  # 1 unit still marked returned
    assert item_pink.sold_qty == 0
    assert item_pink.remaining_qty == 1
    assert item_pink.status == "部分结算"  # 1 unit still marked returned
    assert cash_acc.amount == pytest.approx(1000.0)
    assert db_session.query(SalesOrder).filter(SalesOrder.id == so.id).first() is None
    assert db_session.query(FinanceRecord).filter(FinanceRecord.id == fin.id).first() is None

    # 6. Revoke return -> restores pink remaining_qty=2, removes stock from wh_b
    cs.revoke_return(returns[0].id)
    db_session.commit()
    db_session.refresh(item_pink)
    assert item_pink.returned_qty == 0
    assert item_pink.remaining_qty == 2
    wh_b_stock_after = inv.get_warehouse_inventory_details().get(wh_b.id, {}).get("stock", {}).get(prod.name, {})
    assert wh_b_stock_after.get("樱粉", {}).get("OP本体", 0) == 0


def test_consignment_negative_guards(db_session):
    wh_a, wh_b, cash_acc, _, prod = _seed_catalog_and_stock(db_session)
    cs = ConsignmentService(db_session)
    inv = InventoryService(db_session)

    cs.dispatch_from_warehouse(
        shop_id=None,
        shop_name="新店铺X",
        warehouse_id=wh_a.id,
        product_name=prod.name,
        entries=[{"variant": "绀蓝", "part_name": "OP本体", "quantity": 2}],
    )
    db_session.commit()
    item = cs.get_all_consignments(search="新店铺X")[0]

    # Return 2 to wh_b -> status becomes 已结清
    ret = cs.return_to_warehouse(
        entries=[{"consignment_item_id": item.id, "return_qty": 2}],
        warehouse_id=wh_b.id,
    )[0]
    db_session.commit()
    db_session.refresh(item)
    assert item.status == "已结清"
    assert item.remaining_qty == 0

    # Consume 1 from wh_b so wh_b only has 1 left, then revoking return(2) must fail
    inv.add_inventory_movement(
        product_id=prod.id,
        product_name=prod.name,
        variant="绀蓝",
        quantity=1,
        move_type="出库",
        date_obj=date(2026, 3, 21),
        remark="领用出库",
        warehouse_id=wh_b.id,
        is_set=False,
        part_name="OP本体",
        out_type="其他",
    )
    db_session.commit()
    with pytest.raises(ValueError, match="不足"):
        cs.revoke_return(ret.id)

    # Shop deletion guard while items exist
    shop = db_session.query(ConsignmentShop).filter(ConsignmentShop.name == "新店铺X").first()
    with pytest.raises(ValueError, match="关联寄售库存"):
        cs.delete_shop(shop.id)


def test_consignment_api_endpoints(db_session):
    wh_a, wh_b, cash_acc, _, prod = _seed_catalog_and_stock(db_session)

    def _override_db():
        yield db_session

    api_app = create_mobile_api_app()
    api_app.dependency_overrides[get_db_session] = _override_db
    api_app.dependency_overrides[verify_auth_token] = lambda: "tester"
    try:
        client = TestClient(api_app)

        # Create shop
        r = client.post("/consignments/shops", json={
            "name": "池袋店",
            "currency": "CNY",
            "default_fee_rate": 0.15,
            "default_account_name": "微信对公户",
        })
        assert r.status_code == 200, r.text

        # Dispatch via API
        r = client.post("/consignments/dispatch", json={
            "shop_name": "池袋店",
            "warehouse_id": wh_a.id,
            "product_name": prod.name,
            "date": "2026-04-01",
            "entries": [{"variant": "绀蓝", "part_name": "OP本体", "quantity": 3}],
        })
        assert r.status_code == 200, r.text

        # Fetch page data
        r = client.get("/consignments")
        assert r.status_code == 200
        payload = r.json()
        assert len(payload["shops"]) == 1
        assert len(payload["items"]) == 1
        cid = payload["items"][0]["id"]
        assert payload["summary"]["total_remaining_qty"] == 3

        # Settle 2 units via API (2 * 400 = 800, 15% fee = 120, net = 680)
        r = client.post("/consignments/settlements", json={
            "shop_name": "池袋店",
            "account_id": cash_acc.id,
            "settlement_date": "2026-04-10",
            "currency": "CNY",
            "fee_rate": 0.15,
            "items": [{"consignment_item_id": cid, "sold_qty": 2, "unit_price": 400.0}],
        })
        assert r.status_code == 200, r.text
        sdata = r.json()
        assert sdata["gross_amount"] == pytest.approx(800.0)
        assert sdata["fee_amount"] == pytest.approx(120.0)
        assert sdata["net_amount"] == pytest.approx(680.0)

        # Return remaining 1 via API
        r = client.post("/consignments/return", json={
            "warehouse_id": wh_b.id,
            "return_date": "2026-04-12",
            "entries": [{"consignment_item_id": cid, "return_qty": 1}],
        })
        assert r.status_code == 200, r.text

        # Verify updated overview
        r = client.get("/consignments")
        assert r.status_code == 200
        overview = r.json()
        assert overview["summary"]["total_remaining_qty"] == 0
        assert overview["summary"]["total_sold_qty"] == 2
        assert overview["summary"]["total_returned_qty"] == 1
        assert len(overview["settlements"]) == 1
        assert len(overview["returns"]) == 1

        # Inventory GET includes consignment_shops & cost_categories
        r_inv = client.get("/inventory/page")
        assert r_inv.status_code == 200
        inv_json = r_inv.json()
        assert any(s["name"] == "池袋店" for s in inv_json["consignment_shops"])
        assert len(inv_json["cost_categories"]) > 0
    finally:
        api_app.dependency_overrides.clear()
