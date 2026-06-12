import os
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet
from backend.detector.framework import DetectorFramework
from backend.detector.plugins import get_all_detectors
from backend.equivalence.semantic_checker import SemanticChecker

# Color palette
COLOR_BG = HexColor("#1a1a2e")
COLOR_HEADER = HexColor("#16213e")
COLOR_ACCENT = HexColor("#0f3460")
COLOR_HIGHLIGHT = HexColor("#e94560")
COLOR_TEXT = HexColor("#222222")
COLOR_LIGHT = HexColor("#555555")
COLOR_GREEN = HexColor("#27ae60")
COLOR_RED = HexColor("#e74c3c")
COLOR_ORANGE = HexColor("#f39c12")
COLOR_BLUE = HexColor("#3498db")
COLOR_WHITE = HexColor("#ffffff")

def _new_page(c, width, height, title_text="Semantic IR Diff Report"):
    """Draw page header and return starting y position."""
    # Header bar
    c.setFillColor(COLOR_ACCENT)
    c.rect(0, height - 45, width, 45, fill=True, stroke=False)
    c.setFillColor(COLOR_WHITE)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20, height - 30, title_text)
    
    # Thin accent line
    c.setStrokeColor(COLOR_HIGHLIGHT)
    c.setLineWidth(2)
    c.line(0, height - 46, width, height - 46)
    
    return height - 70

def _check_page(c, y, width, height, title_text, min_y=80):
    """If y is too low, create a new page."""
    if y < min_y:
        c.showPage()
        y = _new_page(c, width, height, title_text)
    return y

def generate_pdf_report(diff, old_module, new_module, title, output_path):
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter
    
    # Run detection framework
    framework = DetectorFramework()
    for detector in get_all_detectors():
        framework.register(detector)
    checker = SemanticChecker()
    
    # =========== PAGE 1: Title + Summary ===========
    # Title page header
    c.setFillColor(COLOR_ACCENT)
    c.rect(0, height - 80, width, 80, fill=True, stroke=False)
    c.setFillColor(COLOR_WHITE)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(30, height - 45, "Semantic IR Diff Report")
    c.setFont("Helvetica", 12)
    c.drawString(30, height - 65, title)
    
    # Accent line
    c.setStrokeColor(COLOR_HIGHLIGHT)
    c.setLineWidth(3)
    c.line(0, height - 81, width, height - 81)
    
    y = height - 110
    
    # Summary stats
    total_funcs = len(diff.changed_functions) + len(diff.unchanged_functions) + len(diff.added_functions) + len(diff.deleted_functions)
    
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(COLOR_TEXT)
    c.drawString(30, y, "Summary")
    y -= 5
    c.setStrokeColor(COLOR_BLUE)
    c.setLineWidth(1)
    c.line(30, y, 200, y)
    y -= 20
    
    stats = [
        ("Functions Compared", str(total_funcs)),
        ("Functions Changed", str(len(diff.changed_functions))),
        ("Functions Added", str(len(diff.added_functions))),
        ("Functions Deleted", str(len(diff.deleted_functions))),
        ("Functions Unchanged", str(len(diff.unchanged_functions))),
    ]
    
    for label, value in stats:
        c.setFont("Helvetica", 11)
        c.setFillColor(COLOR_LIGHT)
        c.drawString(40, y, label + ":")
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(COLOR_TEXT)
        c.drawString(200, y, value)
        y -= 18
    
    y -= 15
    
    # =========== Per-Function Analysis ===========
    for func_name, f_diff in diff.changed_functions.items():
        old_f = old_module.functions[func_name]
        new_f = new_module.functions[func_name]
        
        # Run detectors
        events = framework.run_all(f_diff, old_f, new_f)
        eq_res = checker.check_equivalence(f_diff, events)
        
        y = _check_page(c, y, width, height, title, min_y=150)
        
        # Function header
        c.setFillColor(COLOR_HEADER)
        c.rect(25, y - 5, width - 50, 25, fill=True, stroke=False)
        c.setFillColor(COLOR_WHITE)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(35, y, f"Function: {func_name}")
        y -= 30
        
        # Semantic Status
        is_eq = eq_res["equivalent"]
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(COLOR_GREEN if is_eq else COLOR_RED)
        status_text = "Semantically Equivalent" if is_eq else "Not Equivalent"
        c.drawString(40, y, f"Status: {status_text}")
        y -= 18
        
        c.setFont("Helvetica", 10)
        c.setFillColor(COLOR_LIGHT)
        c.drawString(40, y, f"CFG Changed: {'Yes' if f_diff.cfg_changed else 'No'}   |   Added Blocks: {len(f_diff.added_blocks)}   |   Deleted Blocks: {len(f_diff.deleted_blocks)}")
        y -= 22
        
        # Events / Optimizations
        if events:
            c.setFont("Helvetica-Bold", 11)
            c.setFillColor(COLOR_TEXT)
            c.drawString(40, y, "Detected Optimizations & Changes:")
            y -= 18
            
            for ev in events:
                y = _check_page(c, y, width, height, title)
                
                # Severity color
                if ev.severity == "High":
                    sev_color = COLOR_RED
                elif ev.severity == "Medium":
                    sev_color = COLOR_ORANGE
                else:
                    sev_color = COLOR_BLUE
                
                # Colored bullet
                c.setFillColor(sev_color)
                c.circle(55, y + 3, 4, fill=True, stroke=False)
                
                c.setFont("Helvetica-Bold", 10)
                c.setFillColor(COLOR_TEXT)
                c.drawString(65, y, f"[{ev.category}] {ev.change_type}")
                y -= 14
                
                c.setFont("Helvetica", 9)
                c.setFillColor(COLOR_LIGHT)
                # Word-wrap description
                desc = ev.description
                max_chars = 90
                while len(desc) > max_chars:
                    split_at = desc[:max_chars].rfind(' ')
                    if split_at == -1: split_at = max_chars
                    c.drawString(65, y, desc[:split_at])
                    desc = desc[split_at:].strip()
                    y -= 12
                    y = _check_page(c, y, width, height, title)
                c.drawString(65, y, desc)
                y -= 12
                
                if ev.details:
                    c.setFont("Helvetica-Oblique", 8)
                    c.setFillColor(HexColor("#888888"))
                    details = ev.details
                    while len(details) > max_chars:
                        split_at = details[:max_chars].rfind(' ')
                        if split_at == -1: split_at = max_chars
                        c.drawString(70, y, details[:split_at])
                        details = details[split_at:].strip()
                        y -= 11
                        y = _check_page(c, y, width, height, title)
                    c.drawString(70, y, details)
                    y -= 11
                
                y -= 6
        
        # Diff Lines
        has_diff = False
        for old_lbl, b_diff in f_diff.matched_blocks.items():
            if not b_diff.is_identical:
                has_diff = True
                break
        
        if has_diff:
            y = _check_page(c, y, width, height, title, min_y=100)
            c.setFont("Helvetica-Bold", 11)
            c.setFillColor(COLOR_TEXT)
            c.drawString(40, y, "Instruction Diff:")
            y -= 16
            
            for old_lbl, b_diff in f_diff.matched_blocks.items():
                if b_diff.is_identical:
                    continue
                
                y = _check_page(c, y, width, height, title)
                c.setFont("Helvetica-Bold", 9)
                c.setFillColor(COLOR_ACCENT)
                c.drawString(50, y, f"Block: {old_lbl} -> {b_diff.new_label}")
                y -= 14
                
                for marker, line, *_ in b_diff.diff_lines:
                    y = _check_page(c, y, width, height, title)
                    
                    if marker == '-':
                        c.setFillColor(HexColor("#fdecea"))
                        c.rect(50, y - 3, width - 100, 13, fill=True, stroke=False)
                        c.setFillColor(COLOR_RED)
                        prefix = "- "
                    elif marker == '+':
                        c.setFillColor(HexColor("#eafaf1"))
                        c.rect(50, y - 3, width - 100, 13, fill=True, stroke=False)
                        c.setFillColor(COLOR_GREEN)
                        prefix = "+ "
                    else:
                        c.setFillColor(COLOR_LIGHT)
                        prefix = "  "
                    
                    c.setFont("Courier", 8)
                    display_line = prefix + str(line)
                    if len(display_line) > 100:
                        display_line = display_line[:97] + "..."
                    c.drawString(55, y, display_line)
                    y -= 13
                
                y -= 8
        
        y -= 20
    
    # =========== Footer on last page ===========
    c.setStrokeColor(COLOR_HIGHLIGHT)
    c.setLineWidth(1)
    c.line(30, 40, width - 30, 40)
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(COLOR_LIGHT)
    c.drawString(30, 28, "Generated by Semantic IR Diff Tool")
    c.drawString(width - 200, 28, "github.com/varshac134/Semantic-Diff-for-Compiler-IR")
    
    c.save()
