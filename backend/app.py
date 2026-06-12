from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import os
import tempfile
import traceback
import sys
import pandas as pd
from werkzeug.utils import secure_filename

# Add parent dir to path to import compiler.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from compiler import compile_to_ir, CompilerError

# Import local backend modules
from backend.normalizer.normalize import IRNormalizer
from backend.parser.ir_parser import IRParser
from backend.diff.diff_engine import CFGDiffEngine
from backend.detector.framework import DetectorFramework
from backend.detector.plugins import get_all_detectors
from backend.equivalence.semantic_checker import SemanticChecker
from backend.report.report_generator import generate_html_report
from backend.report.pdf_generator import generate_pdf_report

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
OUTPUT_FOLDER = os.path.join(os.path.dirname(__file__), 'outputs')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Helper to write to uploads temp file
def save_upload_file(content, suffix):
    fd, path = tempfile.mkstemp(suffix=suffix, dir=UPLOAD_FOLDER)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(content)
    return path

# Helper to serialize diff results for JSON responses
def serialize_diff_results(diff, old_module, new_module):
    checker = SemanticChecker()
    
    framework = DetectorFramework()
    for detector in get_all_detectors():
        framework.register(detector)
    
    result = {
        "added_functions": diff.added_functions,
        "deleted_functions": diff.deleted_functions,
        "unchanged_functions": diff.unchanged_functions,
        "changed_functions": {}
    }
    
    for name, f_diff in diff.changed_functions.items():
        old_f = old_module.functions[name]
        new_f = new_module.functions[name]
        
        events = framework.run_all(f_diff, old_f, new_f)
        
        # Run equivalence checker
        eq_res = checker.check_equivalence(f_diff, events)
        
        serialized_events = [ev.to_dict() for ev in events]
            
        matched_blocks = {}
        for old_lbl, b_diff in f_diff.matched_blocks.items():
            matched_blocks[old_lbl] = {
                "old_label": b_diff.old_label,
                "new_label": b_diff.new_label,
                "is_identical": b_diff.is_identical,
                "diff_lines": [(marker, line) for marker, line, _ in b_diff.diff_lines],
                "primitive_changes": [c.to_dict() for c in b_diff.primitive_changes]
            }
            
        old_blocks = {}
        for lbl in old_f.block_order:
            old_blocks[lbl] = {
                "label": lbl,
                "successors": list(old_f.blocks[lbl].successors),
                "instructions": [inst.raw_text for inst in old_f.blocks[lbl].instructions]
            }
            
        new_blocks = {}
        for lbl in new_f.block_order:
            new_blocks[lbl] = {
                "label": lbl,
                "successors": list(new_f.blocks[lbl].successors),
                "instructions": [inst.raw_text for inst in new_f.blocks[lbl].instructions]
            }
            
        result["changed_functions"][name] = {
            "name": name,
            "cfg_changed": f_diff.cfg_changed,
            "added_blocks": f_diff.added_blocks,
            "deleted_blocks": f_diff.deleted_blocks,
            "matched_blocks": matched_blocks,
            "events": serialized_events,
            "old_blocks": old_blocks,
            "new_blocks": new_blocks,
            "old_block_order": old_f.block_order,
            "new_block_order": new_f.block_order,
            # Equivalence & Primitive Outputs
            "semantic_status": "Equivalent" if eq_res["equivalent"] else "Not Equivalent",
            "equivalent": eq_res["equivalent"],
            "primitive_changes": [c.to_dict() for c in f_diff.primitive_changes]
        }
        
    return result

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/analyze', methods=['POST'])
def analyze_diff():
    temp_files = []
    try:
        data = request.json or {}
        mode = data.get('mode', 'ir')
        
        extra_flags_str = data.get('extra_flags', '')
        extra_flags = [flag.strip() for flag in extra_flags_str.split(',') if flag.strip()]
        
        ll_path1 = None
        ll_path2 = None
        title = "Semantic IR Diff Analysis"
        
        if mode == 'ir':
            ir_raw_1 = data.get('ir1', '')
            ir_raw_2 = data.get('ir2', '')
            
            if not ir_raw_1.strip() or not ir_raw_2.strip():
                return jsonify({"error": "Both IR inputs are required"}), 400
                
            ll_path1 = save_upload_file(ir_raw_1, ".ll")
            ll_path2 = save_upload_file(ir_raw_2, ".ll")
            temp_files.extend([ll_path1, ll_path2])
            title = "Uploaded IR Comparison"
            
        elif mode == 'code':
            code1 = data.get('code1', '')
            code2 = data.get('code2', '')
            
            opt1 = data.get('opt1', '-O0')
            opt2 = data.get('opt2', '-O3')
            lang = data.get('lang', 'c')
            suffix = ".cpp" if lang == 'cpp' else ".c"
            
            if not code1.strip():
                return jsonify({"error": "First code input is required"}), 400
                
            c_path1 = save_upload_file(code1, suffix)
            temp_files.append(c_path1)
            
            ll_path1 = tempfile.mktemp(suffix=".ll", dir=UPLOAD_FOLDER)
            temp_files.append(ll_path1)
            
            compile_to_ir(c_path1, ll_path1, opt_level=opt1, extra_flags=extra_flags)
            
            if not code2.strip():
                ll_path2 = tempfile.mktemp(suffix=".ll", dir=UPLOAD_FOLDER)
                temp_files.append(ll_path2)
                compile_to_ir(c_path1, ll_path2, opt_level=opt2, extra_flags=extra_flags)
                title = f"Source Code ({opt1} vs {opt2})"
            else:
                c_path2 = save_upload_file(code2, suffix)
                temp_files.append(c_path2)
                
                ll_path2 = tempfile.mktemp(suffix=".ll", dir=UPLOAD_FOLDER)
                temp_files.append(ll_path2)
                
                compile_to_ir(c_path2, ll_path2, opt_level=opt2, extra_flags=extra_flags)
                title = f"Source Code Comparison ({opt1} vs {opt2})"
        else:
            return jsonify({"error": "Invalid analysis mode"}), 400
            
        with open(ll_path1, 'r', encoding='utf-8') as f:
            ir_raw_1 = f.read()
        with open(ll_path2, 'r', encoding='utf-8') as f:
            ir_raw_2 = f.read()
            
        # 1. Normalizer
        normalizer = IRNormalizer()
        ir_norm_1 = normalizer.normalize(ir_raw_1)
        ir_norm_2 = normalizer.normalize(ir_raw_2)
        
        # 2. Parser
        parser = IRParser()
        mod_1 = parser.parse(ir_norm_1)
        mod_2 = parser.parse(ir_norm_2)
        
        # 3. Diff Engine
        diff_engine = CFGDiffEngine()
        diff = diff_engine.diff_modules(mod_1, mod_2)
        
        # 4. Serialization (calls Detector, Classifier, Equivalence Checker internally)
        serialized_res = serialize_diff_results(diff, mod_1, mod_2)
        serialized_res["title"] = title
        
        # 5. Statistics Engine counts
        total_changed = len(diff.changed_functions)
        total_added = len(diff.added_functions)
        total_deleted = len(diff.deleted_functions)
        total_unchanged = len(diff.unchanged_functions)
        
        total_inst_added = 0
        total_inst_deleted = 0
        total_inst_modified = 0
        
        high_severity_events = 0
        med_severity_events = 0
        low_severity_events = 0
        
        for f_name, f_diff in serialized_res["changed_functions"].items():
            for b_lbl, b_diff in f_diff["matched_blocks"].items():
                for marker, _ in b_diff["diff_lines"]:
                    if marker == '+':
                        total_inst_added += 1
                    elif marker == '-':
                        total_inst_deleted += 1
            for b_lbl in f_diff["added_blocks"]:
                total_inst_added += len(f_diff["new_blocks"][b_lbl]["instructions"])
            for b_lbl in f_diff["deleted_blocks"]:
                total_inst_deleted += len(f_diff["old_blocks"][b_lbl]["instructions"])
                
            # Count modified / reordered primitive edits
            for pc in f_diff["primitive_changes"]:
                if pc["type"] == "MODIFY_INSTRUCTION":
                    total_inst_modified += 1
                
            for ev in f_diff["events"]:
                if ev["severity"] == "High":
                    high_severity_events += 1
                elif ev["severity"] == "Medium":
                    med_severity_events += 1
                else:
                    low_severity_events += 1
                    
        serialized_res["stats"] = {
            "functions_compared": total_changed + total_added + total_deleted + total_unchanged,
            "functions_changed": total_changed,
            "functions_added": total_added,
            "functions_deleted": total_deleted,
            "instructions_added": total_inst_added,
            "instructions_deleted": total_inst_deleted,
            "instructions_modified": total_inst_modified,
            "events_high": high_severity_events,
            "events_medium": med_severity_events,
            "events_low": low_severity_events
        }
        
        return jsonify(serialized_res)
        
    except CompilerError as e:
        return jsonify({"error": f"Compilation failed: {str(e)}", "details": e.stderr}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Internal server error: {str(e)}", "details": traceback.format_exc()}), 500
    finally:
        for f in temp_files:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass

@app.route('/api/download_report', methods=['POST'])
def download_report():
    temp_files = []
    try:
        data = request.json or {}
        mode = data.get('mode', 'ir')
        
        extra_flags_str = data.get('extra_flags', '')
        extra_flags = [flag.strip() for flag in extra_flags_str.split(',') if flag.strip()]
        
        ll_path1 = None
        ll_path2 = None
        title = "Semantic IR Diff Analysis"
        
        if mode == 'ir':
            ir_raw_1 = data.get('ir1', '')
            ir_raw_2 = data.get('ir2', '')
            
            if not ir_raw_1.strip() or not ir_raw_2.strip():
                return jsonify({"error": "Both IR inputs are required"}), 400
                
            ll_path1 = save_upload_file(ir_raw_1, ".ll")
            ll_path2 = save_upload_file(ir_raw_2, ".ll")
            temp_files.extend([ll_path1, ll_path2])
            title = "Uploaded IR Comparison"
            
        elif mode == 'code':
            code1 = data.get('code1', '')
            code2 = data.get('code2', '')
            
            opt1 = data.get('opt1', '-O0')
            opt2 = data.get('opt2', '-O3')
            lang = data.get('lang', 'c')
            suffix = ".cpp" if lang == 'cpp' else ".c"
            
            if not code1.strip():
                return jsonify({"error": "First code input is required"}), 400
                
            c_path1 = save_upload_file(code1, suffix)
            temp_files.append(c_path1)
            
            ll_path1 = tempfile.mktemp(suffix=".ll", dir=UPLOAD_FOLDER)
            temp_files.append(ll_path1)
            
            compile_to_ir(c_path1, ll_path1, opt_level=opt1, extra_flags=extra_flags)
            
            if not code2.strip():
                ll_path2 = tempfile.mktemp(suffix=".ll", dir=UPLOAD_FOLDER)
                temp_files.append(ll_path2)
                compile_to_ir(c_path1, ll_path2, opt_level=opt2, extra_flags=extra_flags)
                title = f"Source Code ({opt1} vs {opt2})"
            else:
                c_path2 = save_upload_file(code2, suffix)
                temp_files.append(c_path2)
                
                ll_path2 = tempfile.mktemp(suffix=".ll", dir=UPLOAD_FOLDER)
                temp_files.append(ll_path2)
                
                compile_to_ir(c_path2, ll_path2, opt_level=opt2, extra_flags=extra_flags)
                title = f"Source Code Comparison ({opt1} vs {opt2})"
        else:
            return jsonify({"error": "Invalid analysis mode"}), 400
            
        with open(ll_path1, 'r', encoding='utf-8') as f:
            ir_raw_1 = f.read()
        with open(ll_path2, 'r', encoding='utf-8') as f:
            ir_raw_2 = f.read()
            
        normalizer = IRNormalizer()
        ir_norm_1 = normalizer.normalize(ir_raw_1)
        ir_norm_2 = normalizer.normalize(ir_raw_2)
        
        parser = IRParser()
        mod_1 = parser.parse(ir_norm_1)
        mod_2 = parser.parse(ir_norm_2)
        
        diff_engine = CFGDiffEngine()
        diff = diff_engine.diff_modules(mod_1, mod_2)
        
        report_path = tempfile.mktemp(suffix=".html", dir=OUTPUT_FOLDER)
        temp_files.append(report_path)
        
        generate_html_report(diff, mod_1, mod_2, title, report_path)
        
        safe_title = secure_filename(title) or "report"
        return send_file(report_path, as_attachment=True, download_name=f"{safe_title}.html")
        
    except CompilerError as e:
        return jsonify({"error": f"Compilation failed: {str(e)}", "details": e.stderr}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500
    finally:
        for f in temp_files:
            if f != report_path and os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass

@app.route('/api/export_stats', methods=['POST'])
def export_stats():
    try:
        data = request.json or {}
        stats = data.get('stats', {})
        if not stats:
            return jsonify({"error": "No stats provided"}), 400
            
        df = pd.DataFrame([stats])
        
        csv_path = tempfile.mktemp(suffix=".csv", dir=OUTPUT_FOLDER)
        df.to_csv(csv_path, index=False)
        
        safe_title = secure_filename(data.get('title', 'stats')) or "stats"
        return send_file(csv_path, as_attachment=True, download_name=f"{safe_title}.csv")
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@app.route('/api/download_pdf_report', methods=['POST'])
def download_pdf_report():
    temp_files = []
    report_path = None
    try:
        data = request.json or {}
        mode = data.get('mode', 'ir')
        
        extra_flags_str = data.get('extra_flags', '')
        extra_flags = [flag.strip() for flag in extra_flags_str.split(',') if flag.strip()]
        
        ll_path1 = None
        ll_path2 = None
        title = "Semantic IR Diff Analysis"
        
        if mode == 'ir':
            ir_raw_1 = data.get('ir1', '')
            ir_raw_2 = data.get('ir2', '')
            
            if not ir_raw_1.strip() or not ir_raw_2.strip():
                return jsonify({"error": "Both IR inputs are required"}), 400
                
            ll_path1 = save_upload_file(ir_raw_1, ".ll")
            ll_path2 = save_upload_file(ir_raw_2, ".ll")
            temp_files.extend([ll_path1, ll_path2])
            title = "Uploaded IR Comparison"
            
        elif mode == 'code':
            code1 = data.get('code1', '')
            code2 = data.get('code2', '')
            
            opt1 = data.get('opt1', '-O0')
            opt2 = data.get('opt2', '-O3')
            lang = data.get('lang', 'c')
            suffix = ".cpp" if lang == 'cpp' else ".c"
            
            if not code1.strip():
                return jsonify({"error": "First code input is required"}), 400
                
            c_path1 = save_upload_file(code1, suffix)
            temp_files.append(c_path1)
            
            ll_path1 = tempfile.mktemp(suffix=".ll", dir=UPLOAD_FOLDER)
            temp_files.append(ll_path1)
            
            compile_to_ir(c_path1, ll_path1, opt_level=opt1, extra_flags=extra_flags)
            
            if not code2.strip():
                ll_path2 = tempfile.mktemp(suffix=".ll", dir=UPLOAD_FOLDER)
                temp_files.append(ll_path2)
                compile_to_ir(c_path1, ll_path2, opt_level=opt2, extra_flags=extra_flags)
                title = f"Source Code ({opt1} vs {opt2})"
            else:
                c_path2 = save_upload_file(code2, suffix)
                temp_files.append(c_path2)
                
                ll_path2 = tempfile.mktemp(suffix=".ll", dir=UPLOAD_FOLDER)
                temp_files.append(ll_path2)
                
                compile_to_ir(c_path2, ll_path2, opt_level=opt2, extra_flags=extra_flags)
                title = f"Source Code Comparison ({opt1} vs {opt2})"
        else:
            return jsonify({"error": "Invalid analysis mode"}), 400
            
        with open(ll_path1, 'r', encoding='utf-8') as f:
            ir_raw_1 = f.read()
        with open(ll_path2, 'r', encoding='utf-8') as f:
            ir_raw_2 = f.read()
            
        normalizer = IRNormalizer()
        ir_norm_1 = normalizer.normalize(ir_raw_1)
        ir_norm_2 = normalizer.normalize(ir_raw_2)
        
        parser = IRParser()
        mod_1 = parser.parse(ir_norm_1)
        mod_2 = parser.parse(ir_norm_2)
        
        diff_engine = CFGDiffEngine()
        diff = diff_engine.diff_modules(mod_1, mod_2)
        
        report_path = tempfile.mktemp(suffix=".pdf", dir=OUTPUT_FOLDER)
        temp_files.append(report_path)
        
        generate_pdf_report(diff, mod_1, mod_2, title, report_path)
        
        safe_title = secure_filename(title) or "report"
        return send_file(report_path, as_attachment=True, download_name=f"{safe_title}.pdf")
        
    except CompilerError as e:
        return jsonify({"error": f"Compilation failed: {str(e)}", "details": e.stderr}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500
    finally:
        for f in temp_files:
            if report_path and f == report_path:
                continue
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass

if __name__ == '__main__':
    print("Starting Restructured Semantic IR Diff server on http://127.0.0.1:5000")
    app.run(host='127.0.0.1', port=5000, debug=True)
