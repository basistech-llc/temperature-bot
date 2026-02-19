"""
debugging with auto-reload
We could just use gunicorn...
"""

from livereload import Server
from app.main import app

def run():
    server = Server(app)
    server.watch("app/static/*.html")
    server.watch("app/static/*.js")
    server.watch("app/static/*.css")
    server.watch("app/templates/*.html")
    server.watch("app/*.py")
    server.serve(port=8000, host="localhost", debug=True, root="static")

if __name__ == "__main__":
    run()
