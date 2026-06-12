import requests

url = "http://localhost:5000/api/analyze"

sampleC1 = """
void compute(float* a, float* b, float* c, int n) {
    for (int i = 0; i < n; i++) {
        c[i] = a[i] + b[i];
    }
}
"""

payload = {
    "mode": "code",
    "code1": sampleC1,
    "code2": "",
    "opt1": "-O0",
    "opt2": "-O3",
    "lang": "c"
}

resp = requests.post(url, json=payload)
print(resp.status_code)
data = resp.json()
print("Stats:", data.get("stats"))
if "error" in data:
    print("ERROR:", data["error"])
else:
    for f in data.get("changed_functions", {}):
        print(f"Changed function {f}: {data['changed_functions'][f]['events']}")
