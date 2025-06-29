"""
app.py
"""

from os.path import abspath
import os.path
import asyncio
import logging
import sqlite3

from pydantic import BaseModel, conint
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request, APIRouter, Query
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import Optional


from . import ae200
from . import aqi
from . import db # Import the db module

DEV = "/home/simsong" in abspath(__file__)

logger = logging.getLogger(__file__) # Use __file__ or __name__ for logger names

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan function to manage resources.
    This function now handles only startup/shutdown logging.
    The database schema is assumed to be managed externally or on first connect.
    """
    logger.info("Application is starting up.")
    # No database setup logic needed here as per user's request.
    # The database is long-lived and its schema is managed externally.

    yield # Application runs
    logger.info("Application is shutting down.")


app = FastAPI(lifespan=lifespan) # Keep only ONE app = FastAPI() instance
templates = Jinja2Templates(directory="templates") # Moved here for correct association


################################################################

# System map dictionary
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
    # Ensure insert_changelog expects 'conn' as first arg
    db.insert_changelog(conn, request.client.host, req.unit, str(req.speed), "web")
    await ae200.set_erv_speed(req.unit, req.speed)
    return {"status": "ok", "unit": req.unit, "speed": req.speed}


@api_v1.get("/status")
async def status(conn:sqlite3.Connection = Depends(db.get_db_connection)):
    all_task = asyncio.create_task(ae200.get_all_status())
    aqi_task = asyncio.create_task(aqi.get_aqi_async())
    all_data, aqi_data = await asyncio.gather(all_task, aqi_task)
    return {"AQI": aqi_data, "ALL": all_data}

@api_v1.get("/system_map")
async def system_map():
    return await ae200.get_system_map()
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

    logger.info("query=%s params=%s", query, params) # Changed to logger.info
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM changelog")
    total_records = c.fetchone()[0]
    c.execute(query, params)
    records = c.fetchall()

    data = [ dict(row) for row in records ] # Convert Row objects to dicts for JSON serialization

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

# Jinja2 template loader (already defined above `app = FastAPI()`)
# templates = Jinja2Templates(directory="templates") # This line is now redundant
# @app.get("/", response_class=HTMLResponse)
# async def read_index(request: Request):
#     return templates.TemplateResponse(
#         "index.html", {"request": request, "develop": DEV}
#     )


# If you have other top-level routes outside the router, include them here:
@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse(
        "index.html", {"request": request, "develop": DEV}
    )


@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})
