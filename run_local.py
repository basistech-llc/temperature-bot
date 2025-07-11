"""
debugging with auto-reload
"""

from livereload import Server
from app.main import app

def run():
    server = Server(app)
    server.watch("static/*.html")
    server.watch("static/*.js")
    server.watch("static/*.css")
    server.watch("templates/*.html")
    server.watch("app/*.py")
    server.serve(port=8000, host="localhost", debug=True, root="static")

if __name__ == "__main__":
    run()
