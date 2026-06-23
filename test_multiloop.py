import requests
import json

URL = "http://127.0.0.1:5000/api/analyze"

# User's exact multi-loop CSE example
data = {
    "mode": "code",
    "code1": """
void compute(int n, int m, int r, int a, int b, int c, int d, int e) {
    int x, y, p, q, u, v, w;
    int i, j, k;

    // Loop 1
    for(i=0; i<n; i++) {
        x = a+b;
        y = a+b+c;
    }

    // Loop 2
    for(j=0; j<m; j++) {
        p = a*b;
        q = a*b+d;
    }

    // Loop 3
    for(k=0; k<r; k++) {
        u = (a+b)*c;
        v = (a+b)*c + d;
        w = (a+b)*c + e;
    }
}
""",
    "code2": """
void compute(int n, int m, int r, int a, int b, int c, int d, int e) {
    int x, y, p, q, u, v, w;
    int i, j, k;

    int t1 = a+b;
    int t2 = a*b;
    int t3 = t1*c;

    // Loop 1
    for(i=0; i<n; i++) {
        x = t1;
        y = t1+c;
    }

    // Loop 2
    for(j=0; j<m; j++) {
        p = t2;
        q = t2+d;
    }

    // Loop 3
    for(k=0; k<r; k++) {
        u = t3;
        v = t3+d;
        w = t3+e;
    }
}
""",
    "opt1": "-O0",
    "opt2": "-O0"
}

resp = requests.post(URL, json=data, timeout=30)
if resp.status_code == 200:
    res = resp.json()
    print(f"Stats: {json.dumps(res['stats'], indent=2)}")
    print()
    for fname, fval in res.get("changed_functions", {}).items():
        print(f"Function: {fname}")
        for ev in fval.get("events", []):
            print(f"  [{ev['category']}] {ev['change_type']}")
            print(f"    {ev['description']}")
            if ev.get('details'):
                print(f"    Details: {ev['details']}")
        print()
else:
    print(f"Error {resp.status_code}: {resp.text[:500]}")
