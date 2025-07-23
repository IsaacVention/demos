## Prerequisites

- Python 3.10+  
- [transitions[asyncio]](https://pypi.org/project/transitions/)  
- [fastapi](https://pypi.org/project/fastapi/)  
- [uvicorn](https://pypi.org/project/uvicorn/)  

You can install all dependencies with:
FYI: graphviz must be installed through brew on macOS
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

🚀 Running the Demo
	1.	Start the server
```bash
    python -m uvicorn server:app --reload
```
The core of the deliverable is fsm.py and fsm_router.py.
The "demo" components are app.py and server.py, all demo related business logic lives in one of the two.