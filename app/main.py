"""
app.py
"""

from os.path import abspath
import os
import asyncio
import logging
import sqlite3
import json
#from typing import Optional

from contextlib import asynccontextmanager

from pydantic import BaseModel, conint
from fastapi import FastAPI, Depends, Request, APIRouter, Query
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import ae200
from . import weather
from . import db
from . import airnow

__version__ = '0.0.1'

DEV = "/home/simsong" in abspath(__file__)
API_V1_PREFIX = "/api/v1"
DEFAULT_LOG_LEVEL = 'INFO'
LOGGING_CONFIG='%(asctime)s  %(filename)s:%(lineno)d %(levelname)s: %(message)s'
LOG_LEVEL = os.getenv("LOG_LEVEL",DEFAULT_LOG_LEVEL).upper()

ENABLE_AIRNOW = False

logging.basicConfig(format=LOGGING_CONFIG, level=LOG_LEVEL, force=True)
logger = logging.getLogger(__name__)

def fix_boto_log_level():
    """Do not run boto loggers at debug level"""
    for name in logging.root.manager.loggerDict: # pylint: disable=no-member
        if name.startswith('boto'):
            logging.getLogger(name).setLevel(logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan function to manage resources.
    This function now handles only startup/shutdown logging.
    The database schema is assumed to be managed externally or on first connect.
    """
    # No database setup logic needed here as per user's request.
    # The database is long-lived and its schema is managed externally.

    logger.info("Application %s is starting up.", app)
    fix_boto_log_level()
    yield # Application runs
    logger.info("Application %s is shutting down.", app)


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


class SpeedSetResponse(BaseModel):
    status: str
    unit: int
    speed: int


async def get_cached_aqi(conn, cache_hours=1):
    """
    Get AQI data from cache if available and recent, otherwise fetch from API.

    :param conn: database connection
    :param cache_hours: number of hours to cache AQI data
    :return: AQI data dict with value, color, name
    """
    cache_seconds = cache_hours * 3600

    # Check for recent AQI data in database
    if recent_logs:= db.get_recent_devlogs(conn, 'aqi', cache_seconds):
        latest_log = recent_logs[0]
        logger.debug("latest_log=%s",latest_log)
        if latest_log['temp10x']:
            return json.loads(latest_log['temp10x'])

    try:
        if not ENABLE_AIRNOW:
            return {'error':f'ENABLE_AIRNOW={ENABLE_AIRNOW}'}
        aqi_data = await airnow.get_aqi_async()
        if 'error' in aqi_data:
            logger.error("aqi_data=%s", aqi_data)
        else:
            logger.debug("aqi_data=%s",aqi_data)
            db.insert_devlog_entry(conn, 'aqi', temp=aqi_data['value'])
        return aqi_data

    except airnow.AirnowError as api_error:
        logger.error("api_error=%s",api_error)
        return {"value": "N/A", "color": "#cccccc", "name": "Unavailable"}

async def get_last_db_data(conn):
    def fix_status_json(devdict):
        devdict = dict(devdict)
        try:
            devdict['status'] = json.loads(devdict['status_json'])
        except (TypeError,json.JSONDecodeError):
            pass
        del devdict['status_json']
        return devdict
    return [fix_status_json(dd) for dd in db.fetch_last_status(conn)]

################################################################
# Versioned API router
api_v1 = APIRouter(prefix=API_V1_PREFIX)

@api_v1.get("/version")
async def get_version_json():
    return {"version":__version__}

@api_v1.post("/set_speed", response_model=SpeedSetResponse)
async def set_speed(request: Request, req: SpeedControl, conn: sqlite3.Connection = Depends(db.get_db_connection)):
    logger.info("set speed: %s", req)
    db.insert_changelog(conn, request.client.host, req.unit, str(req.speed), "web")
    await ae200.set_fan_speed(req.unit, req.speed)
    return SpeedSetResponse(status="ok", unit=req.unit, speed=req.speed)

@api_v1.get("/status")
async def get_status(conn:sqlite3.Connection = Depends(db.get_db_connection)):
    # debug just one service:
    #data = await asyncio.create_task(weather.get_weather_data_async())
    #return data

    device_task       = asyncio.create_task(get_last_db_data(conn))
    device_data,      = await asyncio.gather(device_task) # final, is important becuase it returns a list

    # Annotation the device_data
    for data in device_data:
        if data.get('status',[]):
            data.update(ae200.extract_status(data['status']))
    return {"devices": device_data}


@api_v1.get("/weather")
async def get_weather(conn:sqlite3.Connection = Depends(db.get_db_connection)):
    aqi_task          = asyncio.create_task(get_cached_aqi(conn, cache_hours=1))
    weather_data_task = asyncio.create_task(weather.get_weather_data_async())
    aqi_data, weather_data= await asyncio.gather(aqi_task, weather_data_task)

    return {"aqi": aqi_data, "weather": weather_data}

# pylint: disable=too-many-arguments, disable=too-many-positional-arguments
@api_v1.get("/logs")
async def get_logs( start: int | None = Query(default=None),
                    end: int | None = Query(default=None),
                    draw: int = Query(default=1),
                    start_row: int = Query(default=0),
                    length: int = Query(default=100),
                    conn: sqlite3.Connection = Depends(db.get_db_connection)):
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
    logger.info("query=%s params=%s", query, params)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM changelog")
    total_records = c.fetchone()[0]
    c.execute(query, params)
    data = [ dict(row) for row in c.fetchall() ]  # Convert Row objects to dicts for JSON serialization

    return JSONResponse( {
            "draw": draw,
            "recordsTotal": total_records,
            "recordsFiltered": total_records,  # Adjust if implementing search
            "data": data } )

# This must be done after all routes are defined
app.include_router(api_v1)

################################################################
# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")


################################################################
# Othe top-level routes
@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse( "index.html", {"request": request, "develop": DEV} )

@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})

@app.get("/version", response_class=PlainTextResponse)
async def get_version():
    return f"version: {__version__}"

print(f"main.py: app id={id(app)}")
