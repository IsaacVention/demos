from fastapi import FastAPI
from orchestrator import storage
from fastapi.responses import FileResponse

app = FastAPI()
storage.bootstrap(app)

@app.get("/")
def serve_index():
    return FileResponse("./static/index.html")
