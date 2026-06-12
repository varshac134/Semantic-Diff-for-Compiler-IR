import os
import re
from backend.detector.framework import DetectorFramework
from backend.detector.plugins import get_all_detectors
from backend.equivalence.semantic_checker import SemanticChecker

def build_mermaid_cfg(func, matched_blocks, is_new=False, added_blocks=None, deleted_blocks=None):
    """
    Generates a Mermaid graph string for the function's CFG.
    """
    if added_blocks is None: added_blocks = []
    if deleted_blocks is None: deleted_blocks = []
    
    lines = ["graph TD"]
    
    lines.append("classDef default fill:#111827,stroke:#374151,stroke-width:1px,color:#f3f4f6;")
    lines.append("classDef added fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#d1fae5;")
    lines.append("classDef deleted fill:#7f1d1d,stroke:#ef4444,stroke-width:2px,color:#fee2e2;")
    lines.append("classDef changed fill:#78350f,stroke:#f59e0b,stroke-width:2px,color:#fef3c7;")
    
    for lbl in func.block_order:
        block = func.blocks[lbl]
        inst_count = len(block.instructions)
        label_text = f"<b>{lbl}</b><br/>({inst_count} instructions)"
        
        style_class = ""
        if is_new and lbl in added_blocks:
            style_class = ":::added"
        elif not is_new and lbl in deleted_blocks:
            style_class = ":::deleted"
        elif lbl in matched_blocks:
            b_diff = matched_blocks[lbl] if not is_new else None
            if is_new:
                for o_lbl, diff in matched_blocks.items():
                    if diff.new_label == lbl:
                        b_diff = diff
                        break
            if b_diff and not b_diff.is_identical:
                style_class = ":::changed"
                
        lines.append(f'    {lbl}["{label_text}"]{style_class}')
        
        for succ in block.successors:
            lines.append(f"    {lbl} --> {succ}")
            
    return "\n".join(lines)


def generate_html_report(diff, old_module, new_module, title, out_path):
    """
    Generates an obsidian-dark, premium, glassmorphic standalone HTML report.
    """
    html_funcs = ""
    framework = DetectorFramework()
    for d in get_all_detectors():
        framework.register(d)
    checker = SemanticChecker()
    
    # 1. Added & Deleted Functions Section
    if diff.added_functions or diff.deleted_functions:
        html_funcs += "<div class='grid-2'>"
        if diff.added_functions:
            html_funcs += "<div class='card card-added'><h3>➕ Added Functions</h3><ul>"
            for f in diff.added_functions:
                html_funcs += f"<li><code>{f}</code></li>"
            html_funcs += "</ul></div>"
            
        if diff.deleted_functions:
            html_funcs += "<div class='card card-deleted'><h3>➖ Deleted Functions</h3><ul>"
            for f in diff.deleted_functions:
                html_funcs += f"<li><code>{f}</code></li>"
            html_funcs += "</ul></div>"
        html_funcs += "</div>"

    # 2. Changed functions
    for func_idx, (name, f_diff) in enumerate(diff.changed_functions.items()):
        old_f = old_module.functions[name]
        new_f = new_module.functions[name]
        
        events = framework.run_all(f_diff, old_f, new_f)
        eq_res = checker.check_equivalence(f_diff, events)
        eq_status = "Equivalent" if eq_res["equivalent"] else "Not Equivalent"
        badge_eq_class = "badge-low" if eq_res["equivalent"] else "badge-high"
        
        event_html = ""
        if events:
            event_html += "<div class='optimizations-section'><h4>💡 Semantic Optimizations / Regressions Identified</h4><table class='event-table'><thead><tr><th>Category</th><th>Type</th><th>Description</th><th>Impact</th></tr></thead><tbody>"
            for ev in events:
                badge_class = f"badge-{ev.severity.lower()}"
                event_html += f"<tr><td><strong>{ev.category}</strong></td><td><code>{ev.change_type}</code></td><td>{ev.description}<br><small class='details'>{ev.details}</small></td><td><span class='badge {badge_class}'>{ev.severity}</span></td></tr>"
            event_html += "</tbody></table></div>"
            
        old_mermaid = build_mermaid_cfg(old_f, f_diff.matched_blocks, is_new=False, deleted_blocks=f_diff.deleted_blocks)
        new_mermaid = build_mermaid_cfg(new_f, f_diff.matched_blocks, is_new=True, added_blocks=f_diff.added_blocks)
        
        cfg_html = f"""
        <div class='cfg-section'>
            <h4>📊 Control Flow Graph (CFG) Structure Comparison</h4>
            <div class='grid-2'>
                <div class='cfg-container card'>
                    <div class='cfg-header'>Old CFG Graph ({old_f.name})</div>
                    <pre class='mermaid'>{old_mermaid}</pre>
                </div>
                <div class='cfg-container card'>
                    <div class='cfg-header'>New CFG Graph ({new_f.name})</div>
                    <pre class='mermaid'>{new_mermaid}</pre>
                </div>
            </div>
        </div>
        """
        
        block_html = "<h4>🔍 Basic Block Split Diff Analysis</h4>"
        printed_blocks = set()
        
        for o_lbl in old_f.block_order:
            if o_lbl not in f_diff.matched_blocks:
                block_html += f"""
                <div class='block-diff deleted-block-wrapper card'>
                    <h5>❌ Deleted Block: <code>{o_lbl}</code></h5>
                    <table class='split-diff-table'>
                        <thead><tr><th>Old {o_lbl}</th><th>New (Deleted)</th></tr></thead>
                        <tbody>
                """
                for inst in old_f.blocks[o_lbl].instructions:
                    block_html += f"<tr><td class='code-col deleted-line'><pre>{inst.raw_text}</pre></td><td class='code-col empty-line'></td></tr>"
                block_html += "</tbody></table></div>"
                continue
                
            b_diff = f_diff.matched_blocks[o_lbl]
            printed_blocks.add(b_diff.new_label)
            
            if b_diff.is_identical:
                continue
                
            block_html += f"""
            <div class='block-diff changed-block-wrapper card'>
                <h5>⚡ Changed Block: <code>{o_lbl}</code> &rarr; <code>{b_diff.new_label}</code></h5>
                <table class='split-diff-table'>
                    <thead><tr><th>Old {o_lbl}</th><th>New {b_diff.new_label}</th></tr></thead>
                    <tbody>
            """
            
            for marker, line in b_diff.diff_lines:
                if marker == '-':
                    block_html += f"<tr><td class='code-col deleted-line'><pre>- {line}</pre></td><td class='code-col empty-line'></td></tr>"
                elif marker == '+':
                    block_html += f"<tr><td class='code-col empty-line'></td><td class='code-col added-line'><pre>+ {line}</pre></td></tr>"
                else:
                    block_html += f"<tr><td class='code-col unchanged-line'><pre>  {line}</pre></td><td class='code-col unchanged-line'><pre>  {line}</pre></td></tr>"
                    
            block_html += "</tbody></table></div>"
            
        for n_lbl in f_diff.added_blocks:
            block_html += f"""
            <div class='block-diff added-block-wrapper card'>
                <h5>✨ Added Block: <code>{n_lbl}</code></h5>
                <table class='split-diff-table'>
                    <thead><tr><th>Old (None)</th><th>New {n_lbl}</th></tr></thead>
                    <tbody>
            """
            for inst in new_f.blocks[n_lbl].instructions:
                block_html += f"<tr><td class='code-col empty-line'></td><td class='code-col added-line'><pre>+ {inst.raw_text}</pre></td></tr>"
            block_html += "</tbody></table></div>"

        html_funcs += f"""
        <div class='card function-card card-glow-{func_idx % 2}'>
            <div class='function-title-row'>
                <h2>Function <code>{name}</code></h2>
                <div class='metadata'>
                    Equivalence Status: <span class='badge {badge_eq_class}'>{eq_status}</span> &nbsp;|&nbsp;
                    CFG Changed: <span class='badge {"badge-high" if f_diff.cfg_changed else "badge-info"}'>{"Yes" if f_diff.cfg_changed else "No"}</span>
                </div>
            </div>
            {event_html}
            {cfg_html}
            {block_html}
        </div>
        """

    # Obsidian dark mode CSS + HTML layout
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Semantic IR Diff Report</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>
        mermaid.initialize({{
            theme: 'dark',
            startOnLoad: true,
            flowchart: {{
                useMaxWidth: true,
                htmlLabels: true,
                curve: 'basis'
            }}
        }});
    </script>
    <style>
        :root {{
            --bg-obsidian: #030712;
            --bg-panel: rgba(17, 24, 39, 0.65);
            --bg-code: #0b0f19;
            --border-muted: rgba(255, 255, 255, 0.05);
            --border-glow: rgba(6, 182, 212, 0.15);
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --color-emerald: #10b981;
            --color-rose: #ef4444;
            --color-amber: #f59e0b;
            --color-cyan: #06b6d4;
        }}
        body {{
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-obsidian);
            background-image: radial-gradient(ellipse at top, #111827 0%, #030712 100%);
            color: var(--text-primary);
            margin: 0;
            padding: 30px 20px;
            line-height: 1.6;
        }}
        .container {{
            max-width: 1280px;
            margin: 0 auto;
        }}
        h1 {{
            font-size: 2.2rem;
            font-weight: 700;
            background: linear-gradient(135deg, #06b6d4, #8b5cf6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-top: 0;
            margin-bottom: 5px;
            text-align: center;
        }}
        .card {{
            background: var(--bg-panel);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid var(--border-muted);
            border-radius: 14px;
            box-shadow: 0 10px 30px -10 rgba(0,0,0,0.5);
            padding: 24px;
            margin-bottom: 30px;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }}
        .card:hover {{
            border-color: rgba(255, 255, 255, 0.1);
            transform: translateY(-2px);
        }}
        .card-added {{ border-top: 4px solid var(--color-emerald); }}
        .card-deleted {{ border-top: 4px solid var(--color-rose); }}
        .card-glow-0:hover {{
            box-shadow: 0 12px 40px -15px rgba(6, 182, 212, 0.15);
            border-color: rgba(6, 182, 212, 0.2);
        }}
        .card-glow-1:hover {{
            box-shadow: 0 12px 40px -15px rgba(139, 92, 246, 0.15);
            border-color: rgba(139, 92, 246, 0.2);
        }}
        .function-title-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-muted);
            padding-bottom: 12px;
            margin-bottom: 20px;
        }}
        .function-card h2 {{
            margin: 0;
            font-size: 1.5rem;
            font-weight: 600;
            color: #fff;
        }}
        h3, h4, h5 {{
            color: #fff;
            margin-top: 0;
        }}
        h4 {{
            font-size: 1.15rem;
            margin-bottom: 12px;
            border-left: 3px solid var(--color-cyan);
            padding-left: 10px;
        }}
        h5 {{
            font-size: 1rem;
            margin-bottom: 10px;
            color: var(--text-secondary);
        }}
        .grid-2 {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(450px, 1fr));
            gap: 20px;
            margin-bottom: 24px;
        }}
        ul {{
            margin: 0;
            padding-left: 20px;
            color: var(--text-secondary);
        }}
        li {{
            margin-bottom: 8px;
        }}
        code {{
            background-color: var(--bg-code);
            color: #a5f3fc;
            padding: 3px 6px;
            border-radius: 4px;
            font-family: 'Fira Code', monospace;
            font-size: 0.88em;
            border: 1px solid rgba(255,255,255,0.03);
        }}
        .metadata {{
            font-size: 0.88em;
            color: var(--text-secondary);
        }}
        .split-diff-table {{
            width: 100%;
            border-collapse: collapse;
            font-family: 'Fira Code', monospace;
            font-size: 0.82em;
            background-color: var(--bg-code);
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid var(--border-muted);
            margin-top: 10px;
            table-layout: fixed;
        }}
        .split-diff-table th {{
            background-color: rgba(255,255,255,0.02);
            padding: 8px 12px;
            font-weight: 600;
            text-align: left;
            border-bottom: 1px solid var(--border-muted);
            color: var(--text-secondary);
            font-family: 'Inter', sans-serif;
            font-size: 0.95em;
        }}
        .split-diff-table td {{
            padding: 4px 10px;
            vertical-align: top;
            white-space: pre-wrap;
            word-break: break-all;
        }}
        .code-col {{
            width: 50%;
        }}
        .split-diff-table tr {{
            border-bottom: 1px solid rgba(255, 255, 255, 0.01);
        }}
        .split-diff-table pre {{
            margin: 0;
            font-family: inherit;
            white-space: pre-wrap;
        }}
        .unchanged-line {{
            color: #64748b;
        }}
        .deleted-line {{
            background-color: rgba(239, 68, 68, 0.14);
            color: #f87171;
        }}
        .added-line {{
            background-color: rgba(16, 185, 129, 0.14);
            color: #4ade80;
        }}
        .empty-line {{
            background-color: rgba(15, 23, 42, 0.4);
        }}
        .badge {{
            display: inline-block;
            padding: 3px 10px;
            font-size: 0.72em;
            font-weight: 700;
            border-radius: 9999px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .badge-high {{ background-color: rgba(239, 68, 68, 0.15); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.3); }}
        .badge-medium {{ background-color: rgba(245, 158, 11, 0.15); color: #fde047; border: 1px solid rgba(245, 158, 11, 0.3); }}
        .badge-low {{ background-color: rgba(6, 182, 212, 0.15); color: #a5f3fc; border: 1px solid rgba(6, 182, 212, 0.3); }}
        .badge-info {{ background-color: rgba(156, 163, 175, 0.12); color: #e5e7eb; border: 1px solid rgba(156, 163, 175, 0.2); }}
        
        .event-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
            font-size: 0.88em;
            background: rgba(255, 255, 255, 0.01);
            border-radius: 8px;
            border: 1px solid var(--border-muted);
            overflow: hidden;
        }}
        .event-table th, .event-table td {{
            text-align: left;
            padding: 12px;
            border-bottom: 1px solid var(--border-muted);
        }}
        .event-table th {{
            background-color: rgba(255, 255, 255, 0.02);
            color: #fff;
            font-weight: 600;
        }}
        .details {{
            color: var(--text-secondary);
            font-size: 0.9em;
            display: inline-block;
            margin-top: 4px;
        }}
        .optimizations-section {{
            margin-bottom: 25px;
        }}
        .cfg-section {{
            margin-bottom: 30px;
        }}
        .cfg-container {{
            background: rgba(15, 23, 42, 0.35);
            padding: 16px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        .cfg-header {{
            font-size: 0.88rem;
            color: var(--text-secondary);
            font-weight: 600;
            margin-bottom: 12px;
            width: 100%;
            text-align: center;
            border-bottom: 1px solid rgba(255,255,255,0.02);
            padding-bottom: 8px;
        }}
        .mermaid {{
            width: 100%;
            background: transparent !important;
            display: flex;
            justify-content: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Semantic IR Diff Report</h1>
        <p style="text-align: center; color: var(--text-secondary); margin-top: 0; margin-bottom: 30px;">
            Comparing: <code>{title}</code>
        </p>
        
        {html_funcs}
    </div>
</body>
</html>
"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
