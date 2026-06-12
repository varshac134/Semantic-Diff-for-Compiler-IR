import requests
import json

URL = "http://127.0.0.1:5000/api/analyze"

test_cases = [
    {
        "name": "Pure Refactoring",
        "old_ir": """
define i32 @test_refactor() {
block_0:
  %x = add i32 2, 3
  %y = sub i32 5, 2
  %z = add i32 %x, %y
  ret i32 %z
}""",
        "new_ir": """
define i32 @test_refactor() {
block_0:
  %y = sub i32 5, 2
  %x = add i32 2, 3
  %z = add i32 %x, %y
  ret i32 %z
}"""
    },
    {
        "name": "Redundant Load Elimination",
        "old_ir": """
define i32 @test_load(i32* %ptr) {
block_0:
  %a = load i32, i32* %ptr
  %b = load i32, i32* %ptr
  %c = add i32 %a, %b
  ret i32 %c
}""",
        "new_ir": """
define i32 @test_load(i32* %ptr) {
block_0:
  %a = load i32, i32* %ptr
  %c = add i32 %a, %a
  ret i32 %c
}"""
    },
    {
        "name": "LICM",
        "old_ir": """
define i32 @test_licm() {
block_0:
  br label %block_1
block_1:
  %inv = add i32 10, 20
  %i = phi i32 [ 0, %block_0 ], [ %next, %block_1 ]
  %next = add i32 %i, 1
  %cond = icmp slt i32 %next, 100
  br i1 %cond, label %block_1, label %block_2
block_2:
  ret i32 %inv
}""",
        "new_ir": """
define i32 @test_licm() {
block_0:
  %inv = add i32 10, 20
  br label %block_1
block_1:
  %i = phi i32 [ 0, %block_0 ], [ %next, %block_1 ]
  %next = add i32 %i, 1
  %cond = icmp slt i32 %next, 100
  br i1 %cond, label %block_1, label %block_2
block_2:
  ret i32 %inv
}"""
    }
]

for tc in test_cases:
    print(f"--- Running Test: {tc['name']} ---")
    data = {
        "ir1": tc["old_ir"],
        "ir2": tc["new_ir"]
    }
    resp = requests.post(URL, json=data)
    if resp.status_code == 200:
        res = resp.json()
        func_res = res["changed_functions"]
        for fname, fval in func_res.items():
            print(f"Function: {fname}")
            for ev in fval.get("events", []):
                print(f"  [{ev['category']}] {ev['change_type']}: {ev['description']}")
                if 'details' in ev:
                    print(f"    Details: {ev['details']}")
    else:
        print("Error:", resp.text)
    print()
