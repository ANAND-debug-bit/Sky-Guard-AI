##

python -m venv .venv
pip install -r requirements.txt

## activate venv

source .venv/bin/activate (it should be in .)

## activate sensor_simulation new tab

cd microservices/app/sensor_simulation/ && uvicorn main:app --port 8000 --reload

## activate backend new tab

cd microservices/app/ && uvicorn backend:app --port 3000 --reload

# Direct Copy paste

From the **project root**, copy-paste:

```bash
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

Then run your two services in separate tabs:

**Sensor simulation:**

```bash
source .venv/bin/activate && cd microservices/app/sensor_simulation && uvicorn main:app --port 8000 --reload
```

**Backend:**

```bash
source .venv/bin/activate && cd microservices/app && uvicorn backend:app --port 3000 --reload
```
