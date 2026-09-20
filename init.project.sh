sudo apt update
sudo apt install python3-virtualenv -y
virtualenv venv
source venv/bin/activate

pip install "fastapi[standard]" sqlmodel

pip freeze > requirements.txt

touch main.py

cat << 'EOF' > main.py
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "ok", "mensaje": "Listo!"}
EOF

