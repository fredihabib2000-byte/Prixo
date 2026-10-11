import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from central_db import init_central_db
from config import SESSION_SECRET
from db import close_pool
from routers import auth, dashboard, products, labels, gateways, stores, api, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_central_db()  # creates tables on first run, seeds the owner account
    yield
    close_pool()


app = FastAPI(title="PRIXO ESL Manager", version="3.1", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(products.router)
app.include_router(labels.router)
app.include_router(gateways.router)
app.include_router(stores.router)
app.include_router(api.router)
app.include_router(admin.router)
