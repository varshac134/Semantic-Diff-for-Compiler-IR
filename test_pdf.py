import requests
import json

URL = "http://127.0.0.1:5000/api/download_pdf_report"

data = {
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

resp = requests.post(URL, json=data)
if resp.status_code == 200:
    with open("test_report.pdf", "wb") as f:
        f.write(resp.content)
    print(f"PDF saved successfully! Size: {len(resp.content)} bytes")
else:
    print(f"Error {resp.status_code}: {resp.text}")
