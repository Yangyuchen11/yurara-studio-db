"""Tests for backwards-compatible payload optimization query params on YuraraERP API."""
from __future__ import annotations

import os
import sys
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from api import create_mobile_api_app
from api.deps import get_db_session, verify_auth_token
from database import Base
from models import (
    CompanyBalanceItem,
    ConsignmentItem,
    ConsumableItem,
    ConsumableLog,
    CostItem,
    FixedAsset,
    FixedAssetLog,
    InventoryLog,
    Product,
    ProductColor,
    ProductPrice,
    SalesOrder,
    SalesOrderItem,
    SalesPlatform,
    Warehouse,
)


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    with Session(bind=engine) as db:
        db.add_all([
            SalesPlatform(code="weidian", name="微店", currency="CNY", fee_rate=0.006, fee_fixed=0.0),
            SalesPlatform(code="booth", name="Booth", currency="JPY", fee_rate=0.056, fee_fixed=22.0),
        ])
        wh = Warehouse(name="东京仓", remarks="日本发")
        db.add(wh)
        db.flush()

        p1 = Product(name="水母睡裙", total_quantity=100, marketable_quantity=95, target_platform="微店")
        p2 = Product(name="星光斗篷", total_quantity=50, marketable_quantity=50, target_platform="Booth")
        db.add_all([p1, p2])
        db.flush()

        c1 = ProductColor(product_id=p1.id, color_name="海月蓝", quantity=50, produced_quantity=50)
        c2 = ProductColor(product_id=p2.id, color_name="夜空紫", quantity=50, produced_quantity=50)
        db.add_all([c1, c2])
        db.flush()

        db.add_all([
            ProductPrice(color_id=c1.id, platform="weidian", currency="CNY", price=168.0),
            ProductPrice(color_id=c1.id, platform="booth", currency="JPY", price=3600.0),
            ProductPrice(color_id=c2.id, platform="weidian", currency="CNY", price=198.0),
        ])
        db.add(CostItem(product_id=p1.id, item_name="面料", actual_cost=1900.0, supplier="A厂", category="大货材料费"))

        db.add(InventoryLog(
            product_name="水母睡裙", variant="海月蓝", change_amount=30,
            reason="质检合格入库", date=date(2026, 11, 1), warehouse_id=wh.id,
        ))
        db.add(ConsignmentItem(
            shop_name="秋叶原店", product_name="水母睡裙", variant="海月蓝",
            quantity=5, remaining_qty=3, date=date(2026, 11, 2),
        ))

        o1 = SalesOrder(
            order_no="WD001", order_type="线上", status="待发货",
            total_amount=168.0, currency="CNY", platform="微店", created_date=date(2026, 11, 5),
        )
        o2 = SalesOrder(
            order_no="PS001", order_type="预售", status="待付尾款",
            deposit_amount=50.0, final_amount=118.0, total_amount=168.0,
            currency="CNY", platform="微店", created_date=date(2026, 11, 6),
        )
        db.add_all([o1, o2])
        db.flush()
        db.add_all([
            SalesOrderItem(order_id=o1.id, product_name="水母睡裙", variant="海月蓝", quantity=1, unit_price=168.0, subtotal=168.0, warehouse_id=wh.id),
            SalesOrderItem(order_id=o2.id, product_name="水母睡裙", variant="海月蓝", quantity=1, unit_price=168.0, subtotal=168.0, warehouse_id=wh.id),
        ])

        db.add(FixedAsset(name="封口机", unit_price=500.0, quantity=1, remaining_qty=1, shop_name="京东", remarks="", purchase_date=date(2026, 10, 1)))
        db.add(FixedAssetLog(asset_name="封口机", decrease_qty=0, reason="盘点", date=date(2026, 10, 2)))
        db.add(ConsumableItem(name="飞机盒", category="包装", unit_price=2.0, initial_quantity=100, remaining_qty=80, shop_name="纸箱厂", remarks="", purchase_date=date(2026, 10, 1)))
        db.add(ConsumableLog(item_name="飞机盒", change_qty=-20, value_cny=-40.0, date=date(2026, 10, 5), note="发货使用"))
        db.add(CompanyBalanceItem(name="流动资金-支付宝", category="asset", amount=10000.0, currency="CNY", asset_type="现金"))
        db.commit()

    app = create_mobile_api_app()

    def override_db():
        with Session(bind=engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[verify_auth_token] = lambda: "admin"
    return TestClient(app)


def test_products_search_filter(client: TestClient) -> None:
    all_resp = client.get("/products")
    assert all_resp.status_code == 200
    assert len(all_resp.json()["products"]) == 2

    filtered = client.get("/products", params={"search": "水母"})
    assert filtered.status_code == 200
    prods = filtered.json()["products"]
    assert len(prods) == 1
    assert prods[0]["name"] == "水母睡裙"
    assert prods[0]["unit_cost"] == 20.0


def test_inventory_lightweight_flags(client: TestClient) -> None:
    default_resp = client.get("/inventory/page")
    assert default_resp.status_code == 200
    default_data = default_resp.json()
    assert len(default_data["product_cards"]) == 2
    assert len(default_data["consignments"]) == 1
    assert len(default_data["logs"]) == 1

    lite_resp = client.get(
        "/inventory/page",
        params={"include_logs": "false", "include_consignments": "false", "product_search": "水母"},
    )
    assert lite_resp.status_code == 200
    lite_data = lite_resp.json()
    assert len(lite_data["product_cards"]) == 1
    assert lite_data["product_cards"][0]["product_name"] == "水母睡裙"
    assert lite_data["consignments"] == []
    assert lite_data["logs"] == []
    assert lite_data["log_total_items"] == 0
    assert len(lite_data["warehouses"]) == 1


def test_orders_and_presale_include_meta_flag(client: TestClient) -> None:
    ord_default = client.get("/orders")
    assert ord_default.status_code == 200
    assert ord_default.json()["meta"] is not None

    ord_lite = client.get("/orders", params={"include_meta": "false"})
    assert ord_lite.status_code == 200
    assert ord_lite.json()["meta"] is None
    assert len(ord_lite.json()["orders"]) == 1

    pre_lite = client.get("/presale", params={"include_meta": "false"})
    assert pre_lite.status_code == 200
    assert pre_lite.json()["meta"] is None
    assert len(pre_lite.json()["orders"]) == 1


def test_sales_overview_lightweight_flags(client: TestClient) -> None:
    lite = client.get("/sales/overview", params={"include_v1": "false", "include_logs": "false"})
    assert lite.status_code == 200
    body = lite.json()
    assert body["v1"]["total_sets"] == 0
    assert body["v2"]["logs"] == []


def test_assets_and_consumables_lightweight_flags(client: TestClient) -> None:
    assets_default = client.get("/assets")
    assert assets_default.status_code == 200
    assert len(assets_default.json()["logs"]) == 1

    assets_lite = client.get("/assets", params={"include_logs": "false"})
    assert assets_lite.status_code == 200
    assert len(assets_lite.json()["assets"]) == 1
    assert assets_lite.json()["logs"] == []

    cons_default = client.get("/consumables")
    assert cons_default.status_code == 200
    assert len(cons_default.json()["logs"]) == 1
    assert len(cons_default.json()["cash_accounts"]) == 1

    cons_lite = client.get("/consumables", params={"include_logs": "false", "include_meta": "false"})
    assert cons_lite.status_code == 200
    assert len(cons_lite.json()["items"]) == 1
    assert cons_lite.json()["logs"] == []
    assert cons_lite.json()["cash_accounts"] == []
    assert cons_lite.json()["products"] == []
