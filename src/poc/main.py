
from .ag_ui_server import app  
import uvicorn



def run():
    # uvicorn.run(app, host="0.0.0.0", port=8000)
    uvicorn.run("poc.ag_ui_server:app", host="0.0.0.0", port=8000, workers=1)


if __name__ == '__main__':
    run()
   

