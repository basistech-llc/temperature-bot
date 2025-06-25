"""
app.py
"""
import logging
import json
from typing import Optional
from pathlib import Path
from os.path import dirname,abspath,join
import time
import sqlite3
from pydantic import BaseModel, conint
import requests

from fastapi import FastAPI, Request, APIRouter, Query
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import ae200

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)
logger = logging.getLogger("air")

DEV = "/home/simsong" in abspath(__file__)

app = FastAPI()

# pylint: disable=missing-function-docstring


################################################################
## log system

DB_PATH = Path(__file__).parent / "storage.db"

def init_db():
    """Initialize database"""
    if not DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    logtime INTEGER NOT NULL,
                    ipaddr TEXT NOT NULL,
                    unit INTEGER NOT NULL,
                    new_value TEXT,
                    agent TEXT,
                    comment TEXT
                )
            ''')
            conn.commit()

init_db()

def insert_log(request: Request, unit: int, new_value: str, agent: str = "", comment: str = ""):
    ip = request.client.host
    logtime = int(time.time())
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO log (logtime, ipaddr, unit, new_value, agent, comment)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (logtime, ip, unit, new_value, agent, comment))
        conn.commit()

################################################################

# System map dictionary
# SYSTEM_MAP = {i: f"Unit {i} - Description" for i in range(21)}
SYSTEM_MAP = {12:'Kitchen ERV',
              13:'Bathroom ERV'}

# pylint: disable=line-too-long
AQI_URL = 'https://www.airnowapi.org/aq/observation/zipCode/current/?format=application/json&zipCode=02144&distance=15&API_KEY={API_KEY}'
SECRETS_PATH = join(dirname(__file__), 'secrets.json')

# https://docs.airnowapi.org/aq101
AQI_TABLE = [ (0,50,'Good','Green','#00e400',1),
              (51, 100,'Moderate','Yellow', '#ffff00', 2),
              (101, 150,'Unhealthy for Sensitive Groups','Orange','#ff7e00', 3),
              (151, 200,'Unhealthy','Red', '#ff0000', 4),
              (201, 300,'Very Unhealthy', 'Purple','#8f3f97', 5),
              (301, 500,'Hazardous','Maroon', '#7e0023', 6)]

# pylint: disable=unspecified-encoding
def get_secrets():
    """gets the secrets"""
    with open(SECRETS_PATH,'r') as f:
        return json.load(f)

def get_aqi():
    api_key = get_secrets()['AIRNOW_API_KEY']
    r = requests.get(AQI_URL.format(API_KEY=api_key), timeout=5)
    return r.json()[0]['AQI']

def aqi_color(aqi):
    for row in AQI_TABLE:
        if row[0] <= aqi <= row[1]:
            return (row[2],row[4])
    return None


# Pydantic model with input validation
# pylint: disable=missing-class-docstring
class SpeedControl(BaseModel):
    unit: conint(ge=0, le=20)
    speed: conint(ge=0, le=4)

################################################################
# Versioned API router
api_v1 = APIRouter(prefix="/api/v1")

@app.on_event("startup")
async def startup_event():
    logger.info("Application is starting up.")

@api_v1.post("/set_speed")
async def set_speed(request: Request, req: SpeedControl):
    logger.info("set speed: %s",req)
    insert_log(request, req.unit, str(req.speed), "web")
    await ae200.set_erv_speed( req.unit, req.speed )
    return {"status": "ok", "unit": req.unit, "speed": req.speed}

@api_v1.get('/status')
async def status():
    aqi = get_aqi()
    erv = await ae200.get_erv_status()
    (name, color) = aqi_color(aqi)
    return {'AQI':{'value':aqi,
                   'color':color,
                   'name':name},
            'ERV':erv }

@api_v1.get("/system_map")
async def system_map():
    return SYSTEM_MAP

@api_v1.get("/logs")
async def get_logs(
    start: Optional[int] = Query(None),
    end: Optional[int] = Query(None),
    draw: Optional[int] = Query(1),
    start_row: Optional[int] = Query(0),
    length: Optional[int] = Query(100) ):

    query = "SELECT logtime, ipaddr, unit, new_value, agent, comment FROM log WHERE 1=1"
    params = []

    if start is not None:
        query += " AND logtime >= ?"
        params.append(start)
    if end is not None:
        query += " AND logtime <= ?"
        params.append(end)

    query += " ORDER BY logtime DESC LIMIT ? OFFSET ?"
    params.extend([length, start_row])

    logging.info("query=%s params=%s",query,params)
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM log")
        total_records = c.fetchone()[0]

        c.execute(query, params)
        records = c.fetchall()

    data = [
        {
            "logtime": row[0],
            "ip": row[1],
            "unit": row[2],
            "new_value": row[3],
            "agent": row[4],
            "comment": row[5]
        }
        for row in records
    ]

    return JSONResponse({
        "draw": draw,
        "recordsTotal": total_records,
        "recordsFiltered": total_records,  # Adjust if implementing search
        "data": data
    })

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
    return templates.TemplateResponse("index.html",
                                      {"request": request,
                                       "develop": DEV })

@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})
