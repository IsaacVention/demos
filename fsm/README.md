## Prerequisites

You can install all dependencies with:
FYI: graphviz must be installed through brew on macOS or apt on linux
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