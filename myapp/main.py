"""
app.py
"""

from os.path import abspath
import os.path
#import json
import asyncio
import logging
#import time
import sqlite3

from pydantic import BaseModel, conint
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request, APIRouter, Query
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Optional


#import requests

from . import ae200
from . import aqi
from . import db

DEV = "/home/simsong" in abspath(__file__)

logger = logging.getLogger(__file__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application is starting up.")
    yield
    logger.info("Application is shutting down.")


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

app = FastAPI()

################################################################

# System map dictionary
# SYSTEM_MAP = {i: f"Unit {i} - Description" for i in range(21)}
SYSTEM_MAP = {12: "Kitchen ERV", 13: "Bathroom ERV"}

# Pydantic model with input validation
# pylint: disable=missing-class-docstring
class SpeedControl(BaseModel):
    unit: conint(ge=0, le=20)
    speed: conint(ge=0, le=4)


################################################################
# Versioned API router
api_v1 = APIRouter(prefix="/api/v1")

@api_v1.post("/set_speed")
async def set_speed(request: Request, req: SpeedControl, conn:sqlite3.Connection = Depends(db.get_db_connection)):
    logger.info("set speed: %s", req)
    db.insert_changelog(conn, request.client.host, req.unit, str(req.speed), "web")
    await ae200.set_erv_speed(req.unit, req.speed)
    return {"status": "ok", "unit": req.unit, "speed": req.speed}


@api_v1.get("/status")
async def status(conn:sqlite3.Connection = Depends(db.get_db_connection)):
    erv_task = asyncio.create_task(ae200.get_erv_status())
    aqi_task = asyncio.create_task(aqi.get_aqi_async())
    erv, aqi_data = await asyncio.gather(erv_task, aqi_task)
    return {"AQI": aqi_data, "ERV": erv}

@api_v1.get("/system_map")
async def system_map():
    return SYSTEM_MAP


@api_v1.get("/logs")
async def get_logs( start: Optional[int] = Query(None),
                    end: Optional[int] = Query(None),
                    draw: Optional[int] = Query(1),
                    start_row: Optional[int] = Query(0),
                    length: Optional[int] = Query(100),conn:sqlite3.Connection = Depends(db.get_db_connection) ):
    query = "SELECT logtime, ipaddr, unit, new_value, agent, comment FROM changelog WHERE 1=1"
    params = []

    if start is not None:
        query += " AND logtime >= ?"
        params.append(start)
    if end is not None:
        query += " AND logtime <= ?"
        params.append(end)

    query += " ORDER BY logtime DESC LIMIT ? OFFSET ?"
    params.extend([length, start_row])

    logging.info("query=%s params=%s", query, params)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM log")
    total_records = c.fetchone()[0]
    c.execute(query, params)
    records = c.fetchall()

    data = [ row for row in records ]

    return JSONResponse( {
            "draw": draw,
            "recordsTotal": total_records,
            "recordsFiltered": total_records,  # Adjust if implementing search
            "data": data } )


# Register the router
app.include_router(api_v1)


################################################################
## Main app

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Jinja2 template loader
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse(
        "index.html", {"request": request, "develop": DEV}
    )


@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})
