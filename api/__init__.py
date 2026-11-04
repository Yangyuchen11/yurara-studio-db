"""
FastAPI Mobile REST Gateway for Yurara Studio Android App.
Mounted at /api/v1 on the Reflex backend.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.system_routes import router as system_router
from api.finance_routes import router as finance_router
from api.product_cost_routes import router as product_cost_router
from api.sales_routes import router as sales_router
from api.inventory_asset_schedule_routes import router as inv_asset_sched_router


def create_mobile_api_app() -> FastAPI:
    mobile_api = FastAPI(
        title="Yurara Studio Mobile ERP API",
        version="1.0.0",
        description="REST API Gateway sharing 100% of business services and database with Yurara Studio Web.",
    )
    mobile_api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    mobile_api.include_router(system_router)
    mobile_api.include_router(finance_router)
    mobile_api.include_router(product_cost_router)
    mobile_api.include_router(sales_router)
    mobile_api.include_router(inv_asset_sched_router)
    return mobile_api
