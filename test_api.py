import requests

ir1 = """define i32 @test() {
block_0:
  %1 = add i32 2, 3
  ret i32 %1
}"""

ir2 = """define i32 @test() {
block_0:
  ret i32 5
}"""

resp = requests.post('http://127.0.0.1:5000/api/analyze', json={'mode':'ir', 'ir1': ir1, 'ir2': ir2})
import json
print(json.dumps(resp.json(), indent=2))
