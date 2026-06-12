import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def generate_pdf_report(diff, old_module, new_module, title, output_path):
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter
    
    # Title
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 50, title)
    
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 80, f"Functions Compared: {len(diff.changed_functions) + len(diff.unchanged_functions) + len(diff.added_functions) + len(diff.deleted_functions)}")
    c.drawString(50, height - 100, f"Functions Changed: {len(diff.changed_functions)}")
    c.drawString(50, height - 120, f"Functions Added: {len(diff.added_functions)}")
    c.drawString(50, height - 140, f"Functions Deleted: {len(diff.deleted_functions)}")
    
    y = height - 180
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "Changed Functions Details:")
    y -= 30
    
    for name, f_diff in diff.changed_functions.items():
        if y < 100:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica-Bold", 14)
            c.drawString(50, y, "Changed Functions Details (continued):")
            y -= 30
            
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, f"Function: {name}")
        y -= 20
        
        c.setFont("Helvetica", 10)
        c.drawString(70, y, f"CFG Changed: {'Yes' if f_diff.cfg_changed else 'No'}")
        y -= 15
        c.drawString(70, y, f"Added Blocks: {len(f_diff.added_blocks)}")
        y -= 15
        c.drawString(70, y, f"Deleted Blocks: {len(f_diff.deleted_blocks)}")
        y -= 25
        
    c.save()
