import requests

url = "http://localhost:5000/api/analyze"

with open("demo_old.c", "r") as f:
    code1 = f.read()
    
with open("demo_new.c", "r") as f:
    code2 = f.read()

payload = {
    "mode": "code",
    "code1": code1,
    "code2": code2,
    "opt1": "-O0",
    "opt2": "-O0",
    "lang": "c"
}

resp = requests.post(url, json=payload)
print(resp.status_code)
print(resp.json())
