import requests
import json

URL = "http://127.0.0.1:5000/api/analyze"

# Test with the user's exact CSE example (multi-block, branches)
test_cases = [
    {
        "name": "Multi-Block CSE with Branches (User's Example)",
        "mode": "code",
        "code1": """
int compute(int a, int b, int c, int flag) {
    int x, y, z, w;

    if (flag > 0) {
        x = (a + b) * c;
        y = (a + b) + c;
        z = (a * b) + (a * b);
    } else {
        x = (a + b) * c;
        y = (a + b) - c;
        z = (a * b) * 2;
    }

    w = (a + b) * c + (a + b);

    return x + y + z + w;
}
""",
        "code2": """
int compute(int a, int b, int c, int flag) {
    int t1 = a + b;
    int t2 = a * b;
    int t3 = t1 * c;

    int x, y, z, w;

    if (flag > 0) {
        x = t3;
        y = t1 + c;
        z = t2 + t2;
    } else {
        x = t3;
        y = t1 - c;
        z = t2 * 2;
    }

    w = t3 + t1;

    return x + y + z + w;
}
""",
        "opt1": "-O0",
        "opt2": "-O0"
    },
    {
        "name": "Simple CSE (same block)",
        "mode": "ir",
        "ir1": """
define i32 @test_cse(i32 %a, i32 %b) {
block_0:
  %x = add i32 %a, %b
  %y = add i32 %a, %b
  %z = add i32 %x, %y
  ret i32 %z
}""",
        "ir2": """
define i32 @test_cse(i32 %a, i32 %b) {
block_0:
  %x = add i32 %a, %b
  %z = add i32 %x, %x
  ret i32 %z
}"""
    },
    {
        "name": "Constant Folding (should not trigger CSE)",
        "mode": "ir",
        "ir1": """
define i32 @test() {
block_0:
  %1 = add i32 2, 3
  ret i32 %1
}""",
        "ir2": """
define i32 @test() {
block_0:
  ret i32 5
}"""
    }
]

for tc in test_cases:
    print(f"=== {tc['name']} ===")
    
    if tc["mode"] == "ir":
        data = {"ir1": tc["ir1"], "ir2": tc["ir2"]}
    else:
        data = {"mode": "code", "code1": tc["code1"], "code2": tc["code2"], "opt1": tc["opt1"], "opt2": tc["opt2"]}
    
    try:
        resp = requests.post(URL, json=data, timeout=30)
        if resp.status_code == 200:
            res = resp.json()
            for fname, fval in res.get("changed_functions", {}).items():
                print(f"  Function: {fname}")
                for ev in fval.get("events", []):
                    print(f"    [{ev['category']}] {ev['change_type']}")
                    print(f"      {ev['description']}")
                    if ev.get('details'):
                        print(f"      Details: {ev['details']}")
        else:
            print(f"  Error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"  Exception: {e}")
    print()
