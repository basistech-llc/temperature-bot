# app.py
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)
logger = logging.getLogger("air")


from fastapi import FastAPI, Request, APIRouter
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, conint
import json
from os.path import dirname,abspath,join

import requests

from . import ae200

DEV = "/home/simsong" in __file__

app = FastAPI()

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Jinja2 template loader
templates = Jinja2Templates(directory="templates")

# System map dictionary
# SYSTEM_MAP = {i: f"Unit {i} - Description" for i in range(21)}
SYSTEM_MAP = {12:'Kitchen ERV',
              13:'Bathroom ERV'}

AQI_URL = 'https://www.airnowapi.org/aq/observation/zipCode/current/?format=application/json&zipCode=02144&distance=15&API_KEY={API_KEY}'
SECRETS_PATH = join(dirname(__file__), 'secrets.json')

# https://docs.airnowapi.org/aq101
AQI_TABLE = [ (0,50,'Good','Green','#00e400',1),
              (51, 100,'Moderate','Yellow', '#ffff00', 2),
              (101, 150,'Unhealthy for Sensitive Groups','Orange','#ff7e00', 3),
              (151, 200,'Unhealthy','Red', '#ff0000', 4),
              (201, 300,'Very Unhealthy', 'Purple','#8f3f97', 5),
              (301, 500,'Hazardous','Maroon', '#7e0023', 6)]

def get_secrets():
    with open(SECRETS_PATH,'r') as f:
        return json.load(f)

def get_aqi():
    API_KEY = get_secrets()['AIRNOW_API_KEY']
    r = requests.get(AQI_URL.format(API_KEY=API_KEY))
    return r.json()[0]['AQI']

def aqi_color(aqi):
    for row in AQI_TABLE:
        if row[0] <= aqi <= row[1]:
            return (row[2],row[4])


# Pydantic model with input validation
class SpeedRequest(BaseModel):
    unit: conint(ge=0, le=20)
    speed: conint(ge=0, le=4)

# Versioned API router
api_v1 = APIRouter(prefix="/api/v1")

@app.on_event("startup")
async def startup_event():
    logger.info("Application is starting up.")

@api_v1.post("/set_speed")
async def set_speed(req: SpeedRequest):
    logger.info("set speed: %s",req)
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

# Register the router
app.include_router(api_v1)

@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse("index.html",
                                      {"request": request,
                                       "develop": DEV })

@app.get("/privacy", response_class=HTMLResponse)
async def read_index(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})
