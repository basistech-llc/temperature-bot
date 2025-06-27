from myapp.app import app
import logging

# This just imports and exposes `app` for uvicorn or gunicorn
# Example: uvicorn main:app

logging.debug("app=%s",app)
