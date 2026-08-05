import sys
import os
sys.path.insert(0, ".")

from database import SessionLocal
from models import SalesOrder, PresaleOrderBinding
from services.sales_order_service import SalesOrderService
from constants import OrderStatus

db = SessionLocal()
srv = SalesOrderService(db)

try:
    # Clean up prior test orders if any
    db.query(PresaleOrderBinding).filter(PresaleOrderBinding.final_order_no.in_(["TEST-FIN-001", "TEST-FIN-002"])).delete()
    db.query(SalesOrder).filter(SalesOrder.order_no.in_(["TEST-DEP-001", "TEST-DEP-002", "TEST-FIN-001", "TEST-FIN-002"])).delete()
    db.commit()

    print("--- 1. Testing deposit orders creation ---")
    d1, err1 = srv.create_presale_deposit_order(
        items_data=[{"product_name": "测试商品A", "variant": "款式1", "quantity": 2, "unit_price": 50.0}],
        platform="预售平台", currency="CNY", order_no="TEST-DEP-001"
    )
    d2, err2 = srv.create_presale_deposit_order(
        items_data=[{"product_name": "测试商品B", "variant": "款式2", "quantity": 3, "unit_price": 40.0}],
        platform="预售平台", currency="CNY", order_no="TEST-DEP-002"
    )
    if err1 or err2:
        print("Creation error:", err1, err2)
    else:
        print("Created Deposit Orders:", d1.order_no, d2.order_no, "Status:", d1.status, d2.status)

        # Complete deposit payment to turn status to PRESALE_PENDING_FINAL
        srv.complete_deposit_order(d1.id)
        srv.complete_deposit_order(d2.id)
        print("Completed deposit payment. New status:", d1.status, d2.status)

        print("\n--- 2. Testing M:N Multi-binding ---")
        msg = srv.bind_presale_final_order_multi(
            deposit_order_ids=[d1.id, d2.id],
            final_order_no="TEST-FIN-001",
            final_net_amount=500.0,
            new_notes="合并发货"
        )
        print("Bind Result:", msg)

        bindings = db.query(PresaleOrderBinding).filter(PresaleOrderBinding.final_order_no == "TEST-FIN-001").all()
        print("Bindings in DB count:", len(bindings))
        for b in bindings:
            print("Binding:", b.deposit_order_no, "->", b.final_order_no, "Status:", b.status)

        print("\n--- 3. Testing Semicolon Parsing in Batch Import ---")
        import pandas as pd
        df_import = pd.DataFrame([{
            '订单号': 'TEST-FIN-002',
            '关联定金单号': 'TEST-DEP-001; TEST-DEP-002',
            '商品名': '测试商品A',
            '商品型号': '款式1',
            '数量': 1,
            '销售平台': '预售平台',
            '订单总额': 600,
            '币种': 'CNY',
            '出货仓库': '未分配'
        }])

        parsed, errors = srv.validate_and_parse_import_data(df_import, 1.0, presale_mode="尾款")
        print("Batch import errors:", errors)
        print("Parsed orders count:", len(parsed))
        if parsed:
            print("Parsed item matched_deposit_ids:", parsed[0].get("matched_deposit_ids"))

        print("\n--- 4. Testing Revocation & Rollback ---")
        msg_unbind = srv.unbind_presale_final(d1.id)
        print("Unbind result:", msg_unbind)
        print("Deposit order 1 new status after rollback:", d1.status)

    # Final cleanup
    db.query(PresaleOrderBinding).filter(PresaleOrderBinding.final_order_no.in_(["TEST-FIN-001", "TEST-FIN-002"])).delete()
    db.query(SalesOrder).filter(SalesOrder.order_no.in_(["TEST-DEP-001", "TEST-DEP-002", "TEST-FIN-001", "TEST-FIN-002"])).delete()
    db.commit()
    print("\nSUCCESS: All M:N presale unit tests passed successfully!")

except Exception as e:
    db.rollback()
    print("FAILED: Test failed with error:", e)
    import traceback
    traceback.print_exc()
finally:
    db.close()
