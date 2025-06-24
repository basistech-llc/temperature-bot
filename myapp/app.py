# app.py
from os.path import dirname,abspath,join
import json
import asyncio
import logging

from pydantic import BaseModel, conint
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, APIRouter
from fastapi.responses import HTMLResponse,FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from livereload import Server

import requests

from . import ae200
from . import aqi

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)
logger = logging.getLogger("air")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application is starting up.")
    yield
    logger.info("Application is shutting down.")

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")


# System map dictionary
# SYSTEM_MAP = {i: f"Unit {i} - Description" for i in range(21)}
SYSTEM_MAP = {12:'Kitchen ERV',
              13:'Bathroom ERV'}

# Pydantic model with input validation
class SpeedRequest(BaseModel):
    unit: conint(ge=0, le=20)
    speed: conint(ge=0, le=4)

# Versioned API router
api_v1 = APIRouter(prefix="/api/v1")


@api_v1.post("/set_speed")
async def set_speed(req: SpeedRequest):
    logger.info("set speed: %s",req)
    await ae200.set_erv_speed( req.unit, req.speed )
    return {"status": "ok", "unit": req.unit, "speed": req.speed}

@api_v1.get('/status')
async def status():
    erv_task = asyncio.create_task(ae200.get_erv_status())
    aqi_task = asyncio.create_task(aqi.get_aqi_async())
    erv, aqi_data = await asyncio.gather(erv_task, aqi_task)
    return {'AQI': aqi_data, 'ERV': erv}


@api_v1.get("/system_map")
async def system_map():
    return SYSTEM_MAP

# Register the router
app.include_router(api_v1)

@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/privacy", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})
