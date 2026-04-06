# PythonAnywhere dashboard setup

## Expected repo path
Clone this repo on PythonAnywhere as:

```bash
git clone git@github.com-luapicone:luapicone/luca123.git ~/luca123
```

The dashboard expects the summary report at:

```bash
/home/lucapicone/luca123/reversion_scalp_v1/reversion_scalp_v1_summary_report.txt
```

## Install

```bash
cd ~/luca123
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r web_dashboard/requirements.txt
```

## Web app entrypoint
Use `web_dashboard/app.py` for the Flask app.

## WSGI quick setup
Inside the PythonAnywhere WSGI file, add:

```python
import sys
path = '/home/lucapicone/luca123'
if path not in sys.path:
    sys.path.insert(0, path)

from web_dashboard.app import app as application
```

## Refreshing code

```bash
cd ~/luca123
git pull
```

## Generating the report for the dashboard
After a run finishes:

```bash
cd ~/luca123
source .venv/bin/activate
python -m reversion_scalp_v1.make_summary_report
```
