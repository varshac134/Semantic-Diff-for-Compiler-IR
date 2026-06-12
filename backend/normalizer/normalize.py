import re
from collections import defaultdict

def strip_metadata_attachments(instruction_line):
    """
    Strips metadata attachments like ', !dbg !12', ', !tbaa !15' from an instruction line.
    """
    line = instruction_line.strip()
    
    # Strip debugging metadata attachments specifically first:
    line = re.sub(r',\s*!dbg\s*!\d+', '', line)
    line = re.sub(r',\s*!tbaa\s*!\d+', '', line)
    line = re.sub(r',\s*!range\s*!\d+', '', line)
    line = re.sub(r',\s*!nonnull\s*!\d+', '', line)
    line = re.sub(r',\s*!noalias\s*!\d+', '', line)
    line = re.sub(r',\s*!alias\.scope\s*!\d+', '', line)
    line = re.sub(r',\s*!llvm\.loop\s*!\d+', '', line)
    line = re.sub(r',\s*!prof\s*!\d+', '', line)
    line = re.sub(r',\s*!annotation\s*!\d+', '', line)
    
    # Also strip any generic trailing metadata comma-separated attachments
    line = re.sub(r',\s*!\w+\s*!\d+', '', line)
    line = re.sub(r',\s*!\w+\s*!\{\s*[^}]*\s*\}', '', line)
    
    return line

def strip_function_attributes(line):
    """
    Strips function attributes list bindings like '#0' from 'define void @foo() #0 {'.
    """
    if line.startswith("define "):
        line = re.sub(r'\s*#\d+\s*(?=\{)', ' ', line)
    return line

class IRNormalizer:
    def __init__(self):
        pass

    def normalize(self, ir_content):
        """
        Main entry point for IR normalization.
        Takes raw IR string, applies filters, and returns normalized IR.
        """
        lines = ir_content.splitlines()
        clean_lines = []
        
        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                clean_lines.append("")
                continue
                
            # Skip comments (unless it's a basic block label comment like `; <label>:12`)
            if trimmed.startswith(";") and not re.search(r';\s*<label>:', trimmed):
                continue
                
            # Skip metadata declarations starting with !
            if trimmed.startswith("!"):
                continue
                
            # Skip target/module headers
            if (trimmed.startswith("source_filename") or 
                trimmed.startswith("target datalayout") or 
                trimmed.startswith("target triple")):
                continue
                
            # Skip attribute group definitions: 'attributes #0 = { ... }'
            if trimmed.startswith("attributes #"):
                continue
                
            # Strip debug/tbaa attachments on instruction lines
            trimmed = strip_metadata_attachments(trimmed)
            trimmed = strip_function_attributes(trimmed)
            
            clean_lines.append(trimmed)

        # Reconstruct normalized template
        ir_text = "\n".join(clean_lines)
        
        # Phase 2: Process function-by-function to canonicalize Basic Blocks and Registers
        normalized_functions = []
        func_pattern = re.compile(r'^(define\s+[^{]+)\s*\{\s*$', re.MULTILINE)
        
        matches = list(func_pattern.finditer(ir_text))
        
        if matches:
            normalized_functions.append(ir_text[:matches[0].start()])
            
        for i, match in enumerate(matches):
            start_pos = match.start()
            end_pos = ir_text.find("\n}", start_pos)
            if end_pos == -1:
                end_pos = len(ir_text)
            else:
                end_pos += 2
                
            func_body = ir_text[start_pos:end_pos]
            norm_func = self.normalize_function(func_body)
            normalized_functions.append(norm_func)
            
            next_start = matches[i+1].start() if i + 1 < len(matches) else len(ir_text)
            inter_text = ir_text[end_pos:next_start]
            normalized_functions.append(inter_text)
            
        return "".join(normalized_functions)

    def normalize_function(self, func_text):
        """
        Normalizes a single function body.
        """
        lines = func_text.splitlines()
        if not lines:
            return func_text
            
        header = lines[0]
        
        # Safely extract footer only if it is a closing brace
        if lines[-1].strip() == "}":
            footer = lines[-1]
            body_lines = lines[1:-1]
        else:
            footer = "}"
            body_lines = lines[1:]
            
        blocks = []
        current_block_lines = []
        current_block_label = "entry"
        
        explicit_label_re = re.compile(r'^([a-zA-Z0-9._]+):\s*(?:;.*)?$')
        numeric_label_re = re.compile(r'^(\d+):\s*(?:;.*)?$')
        comment_label_re = re.compile(r'^;\s*<label>:(\d+)\s*(?:;.*)?$')
        
        for line in body_lines:
            trimmed = line.strip()
            if not trimmed:
                continue
                
            label_match = explicit_label_re.match(trimmed) or numeric_label_re.match(trimmed)
            comment_match = comment_label_re.match(trimmed)
            
            if label_match or comment_match:
                # Save previous block if it has content (fixed empty block bug)
                if current_block_lines:
                    blocks.append((current_block_label, current_block_lines))
                
                current_block_label = label_match.group(1) if label_match else comment_match.group(1)
                current_block_lines = []
            else:
                current_block_lines.append(line)
                
        if current_block_lines or current_block_label == "entry":
            blocks.append((current_block_label, current_block_lines))
            
        successors = defaultdict(list)
        block_by_label = {b[0]: b for b in blocks}
        
        br_cond_re = re.compile(r'br\s+i1\s+[^,]+,\s*label\s+%([a-zA-Z0-9._]+),\s*label\s+%([a-zA-Z0-9._]+)')
        br_uncond_re = re.compile(r'br\s+label\s+%([a-zA-Z0-9._]+)')
        switch_re = re.compile(r'label\s+%([a-zA-Z0-9._]+)')
        
        for label, lines_list in blocks:
            if not lines_list:
                continue
            last_line = lines_list[-1].strip()
            
            cond_match = br_cond_re.search(last_line)
            if cond_match:
                successors[label].extend([cond_match.group(1), cond_match.group(2)])
                continue
                
            uncond_match = br_uncond_re.search(last_line)
            if uncond_match:
                successors[label].append(uncond_match.group(1))
                continue
                
            if last_line.startswith("switch "):
                lbls = switch_re.findall(last_line)
                successors[label].extend(lbls)
                continue
                
        entry_label = blocks[0][0] if blocks else "entry"
        visited = set()
        bb_rename_map = {}
        bb_counter = 0
        
        def dfs(node):
            nonlocal bb_counter
            if node in visited:
                return
            visited.add(node)
            bb_rename_map[node] = f"block_{bb_counter}"
            bb_counter += 1
            for succ in successors[node]:
                if succ in block_by_label:
                    dfs(succ)
                    
        dfs(entry_label)
        
        for label, _ in blocks:
            if label not in bb_rename_map:
                bb_rename_map[label] = f"block_{bb_counter}"
                bb_counter += 1
                
        reg_rename_map = {}
        reg_counter = 0
        
        param_section_match = re.search(r'@[a-zA-Z0-9._]+\s*\(([^)]*)\)', header)
        if param_section_match:
            param_section = param_section_match.group(1)
            for param_reg in re.findall(r'%[a-zA-Z0-9._]+', param_section):
                if param_reg not in reg_rename_map and param_reg[1:] not in bb_rename_map:
                    reg_rename_map[param_reg] = f"%v{reg_counter}"
                    reg_counter += 1
                    
        ordered_labels = sorted(blocks, key=lambda b: bb_rename_map.get(b[0], "block_9999"))
        lhs_reg_re = re.compile(r'^\s*(%[a-zA-Z0-9._]+)\s*=')
        
        for label, lines_list in ordered_labels:
            for line in lines_list:
                lhs_match = lhs_reg_re.match(line)
                if lhs_match:
                    reg = lhs_match.group(1)
                    if reg not in reg_rename_map and reg[1:] not in bb_rename_map:
                        reg_rename_map[reg] = f"%v{reg_counter}"
                        reg_counter += 1
                        
                for used_reg in re.findall(r'%[a-zA-Z0-9._]+', line):
                    if (used_reg not in reg_rename_map and 
                        used_reg[1:] not in bb_rename_map and 
                        not lhs_reg_re.match(line)):
                        reg_rename_map[used_reg] = f"%v{reg_counter}"
                        reg_counter += 1
                        
        sorted_regs = sorted(reg_rename_map.keys(), key=len, reverse=True)
        sorted_bbs = sorted(bb_rename_map.keys(), key=len, reverse=True)
        
        def rename_line(line):
            for old_bb in sorted_bbs:
                line = re.sub(r'%' + re.escape(old_bb) + r'\b', '%' + bb_rename_map[old_bb], line)
            for old_reg in sorted_regs:
                line = re.sub(re.escape(old_reg) + r'\b', reg_rename_map[old_reg], line)
            return line

        new_header = rename_line(header)
        new_body_lines = []
        
        for label, lines_list in ordered_labels:
            canonical_label = bb_rename_map[label]
            new_body_lines.append(f"{canonical_label}:")
            for line in lines_list:
                new_line = rename_line(line)
                new_body_lines.append(new_line)
                
        return "\n".join([new_header] + new_body_lines + [footer])
