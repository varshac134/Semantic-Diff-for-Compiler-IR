import unittest
import json
from app import app

class TestSemanticIRDiffBackend(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_analyze_ir_mode(self):
        # Sample IR comparison
        payload = {
            "mode": "ir",
            "ir1": """
define i32 @test(i32 %n) {
block_0:
  ret i32 %n
}
""",
            "ir2": """
define i32 @test(i32 %n) {
block_0:
  %add = add nsw i32 %n, 10
  ret i32 %add
}
"""
        }
        response = self.app.post('/api/analyze', 
                                 data=json.dumps(payload),
                                 content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertIn("title", data)
        self.assertIn("stats", data)
        self.assertIn("changed_functions", data)
        self.assertIn("@test", data["changed_functions"])
        
        func = data["changed_functions"]["@test"]
        self.assertFalse(func["cfg_changed"])
        self.assertIn("block_0", func["matched_blocks"])
        self.assertFalse(func["matched_blocks"]["block_0"]["is_identical"])

    def test_analyze_code_mode(self):
        # Sample C code comparison
        payload = {
            "mode": "code",
            "code1": """
int compute(int x) {
    int y = x * 2;
    int condition = 0;
    if (condition) {
        y += 100;
    }
    return y;
}
""",
            "code2": "", # Empty code2 to compare opt1 vs opt2
            "opt1": "-O0",
            "opt2": "-O1",
            "lang": "c",
            "extra_flags": ""
        }
        
        response = self.app.post('/api/analyze', 
                                 data=json.dumps(payload),
                                 content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertIn("title", data)
        self.assertIn("stats", data)
        self.assertIn("changed_functions", data)
        
        # Dead code elimination should have triggered or branch eliminated
        self.assertGreaterEqual(data["stats"]["functions_compared"], 1)

    def test_download_report(self):
        payload = {
            "mode": "ir",
            "ir1": """
define i32 @test(i32 %n) {
block_0:
  ret i32 %n
}
""",
            "ir2": """
define i32 @test(i32 %n) {
block_0:
  %add = add nsw i32 %n, 10
  ret i32 %add
}
"""
        }
        response = self.app.post('/api/download_report', 
                                 data=json.dumps(payload),
                                 content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Disposition'], 'attachment; filename=semantic_ir_diff_report.html')
        self.assertIn(b"Semantic IR Diff Report", response.data)

if __name__ == '__main__':
    unittest.main()
