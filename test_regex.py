import re
ir_text = """define i32 @test() {
block_0:
%1 = add i32 2, 3
ret i32 %1
}"""
func_pattern = re.compile(r'^(define\s+[^{]+)\s*\{\s*$', re.MULTILINE)
matches = list(func_pattern.finditer(ir_text))
print("MATCHES:", len(matches))
match = matches[0]
start_pos = match.start()
end_pos = ir_text.find("\n}", start_pos)
print("END POS:", end_pos)
if end_pos == -1:
    end_pos = len(ir_text)
else:
    end_pos += 2
func_body = ir_text[start_pos:end_pos]
print("FUNC BODY:")
print(repr(func_body))
from backend.normalizer.normalize import IRNormalizer
n = IRNormalizer()
norm_func = n.normalize_function(func_body)
print("NORM FUNC:")
print(repr(norm_func))

