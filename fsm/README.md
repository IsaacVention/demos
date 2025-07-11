---

## 🛠️ Prerequisites

- Python 3.10+  
- [transitions[asyncio]](https://pypi.org/project/transitions/)  
- [fastapi](https://pypi.org/project/fastapi/)  
- [uvicorn](https://pypi.org/project/uvicorn/)  

You can install all dependencies with:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

🚀 Running the Demo
	1.	Start the server
```bash
    uvicorn server:app --reload
```