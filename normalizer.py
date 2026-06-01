import re
from collections import defaultdict, deque

def strip_metadata_attachments(instruction_line):
    """
    Strips metadata attachments like ', !dbg !12', ', !tbaa !15' from an instruction line.
    LLVM metadata attachments start with comma followed by whitespace and '!name !value'.
    """
    # Pattern to match metadata attachments.
    # LLVM metadata looks like: , !dbg !12 or , !tbaa !3 or !nonnull !4
    # We remove these from the end of instructions or in-line.
    line = instruction_line.strip()
    
    # We can remove the !dbg, !tbaa, !range, !nonnull, !prof, !annotation, !noalias, !alias.scope, !llvm.loop
    # using regex.
    # Find any , !name !digits or , !name !{...} or !name !digits
    # A generic approach: remove anything from the first exclamation mark that is a metadata attachment.
    # But wait! We must not strip strings like "hello!" or global variables like @.str = ...
    # Typically, metadata attachments on instructions are at the end of the line, preceded by a comma and a space:
    # e.g., `%5 = load i32, i32* %1, align 4, !dbg !15`
    # Let's match from the end of the line.
    
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
    # e.g. , !12
    line = re.sub(r',\s*!\w+\s*!\d+', '', line)
    line = re.sub(r',\s*!\w+\s*!\{\s*[^}]*\s*\}', '', line)
    
    return line

def strip_function_attributes(line):
    """
    Strips function attributes list bindings like '#0' from 'define void @foo() #0 {'.
    """
    if line.startswith("define "):
        # Replace '#[0-9]+' with empty space before '{'
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
        
        # Phase 1: Strip metadata lines, target triple, datalayout, source_filename, and attribute declarations
        in_attribute_group = False
        
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
        
        # Parse functions
        # A function starts with `define ... @func_name(...) ... {` and ends with `}`
        func_pattern = re.compile(r'^(define\s+[^{]+)\s*\{\s*$', re.MULTILINE)
        
        last_idx = 0
        matches = list(func_pattern.finditer(ir_text))
        
        # Add everything before the first function as-is (globals, declarations)
        if matches:
            normalized_functions.append(ir_text[:matches[0].start()])
            
        for i, match in enumerate(matches):
            start_pos = match.start()
            # Find matching closing brace
            # Since LLVM IR functions don't nest, the next closing brace at the start of a line is the end.
            end_pos = ir_text.find("\n}", start_pos)
            if end_pos == -1:
                end_pos = len(ir_text)
            else:
                end_pos += 2 # include "\n}"
                
            func_body = ir_text[start_pos:end_pos]
            norm_func = self.normalize_function(func_body)
            normalized_functions.append(norm_func)
            
            # Add text between this function and the next
            next_start = matches[i+1].start() if i + 1 < len(matches) else len(ir_text)
            inter_text = ir_text[end_pos:next_start]
            normalized_functions.append(inter_text)
            
        return "".join(normalized_functions)

    def normalize_function(self, func_text):
        """
        Normalizes a single function body:
        1. Identifies and parses basic blocks.
        2. Renames basic block labels in DFS order of the CFG.
        3. Renames local registers sequentially.
        """
        lines = func_text.splitlines()
        if not lines:
            return func_text
            
        header = lines[0]
        body_lines = lines[1:-1]
        footer = lines[-1]
        
        # Step 2a: Parse basic blocks and build local CFG
        blocks = []          # List of tuples: (block_label_or_id, list_of_lines)
        current_block_lines = []
        current_block_label = "entry" # First block is entry, might not have explicit label
        
        # Patterns to detect basic block labels:
        # e.g., `label_name:` or `; <label>:12` or `5:`
        explicit_label_re = re.compile(r'^([a-zA-Z0-9._]+):\s*(?:;.*)?$')
        numeric_label_re = re.compile(r'^(\d+):\s*(?:;.*)?$')
        comment_label_re = re.compile(r'^;\s*<label>:(\d+)\s*(?:;.*)?$')
        
        for line in body_lines:
            trimmed = line.strip()
            if not trimmed:
                continue
                
            # Check if this line is a basic block label
            label_match = explicit_label_re.match(trimmed) or numeric_label_re.match(trimmed)
            comment_match = comment_label_re.match(trimmed)
            
            if label_match or comment_match:
                # Save previous block if it has content
                if current_block_lines or current_block_label == "entry":
                    blocks.append((current_block_label, current_block_lines))
                
                current_block_label = label_match.group(1) if label_match else comment_match.group(1)
                current_block_lines = []
            else:
                # Append instruction to current block
                current_block_lines.append(line)
                
        # Append the last block
        if current_block_lines or current_block_label == "entry":
            blocks.append((current_block_label, current_block_lines))
            
        # Step 2b: Build successor edges for DFS traversal
        # We need to find branches in each block to build CFG
        successors = defaultdict(list)
        block_by_label = {b[0]: b for b in blocks}
        
        # LLVM IR branching instructions:
        # `br i1 %cond, label %true_label, label %false_label`
        # `br label %dest_label`
        # `switch i32 %val, label %default [ i32 0, label %l1 ... ]`
        # `ret ...` (no successors)
        br_cond_re = re.compile(r'br\s+i1\s+[^,]+,\s*label\s+%([a-zA-Z0-9._]+),\s*label\s+%([a-zA-Z0-9._]+)')
        br_uncond_re = re.compile(r'br\s+label\s+%([a-zA-Z0-9._]+)')
        switch_re = re.compile(r'label\s+%([a-zA-Z0-9._]+)')
        
        for label, lines_list in blocks:
            # Succs are usually defined by the last instruction in the block
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
                # Find all labels referenced in the switch instruction
                lbls = switch_re.findall(last_line)
                # The first one is the default label, and others are case labels
                successors[label].extend(lbls)
                continue
                
        # Step 2c: DFS traversal to canonicalize Basic Blocks
        # Starting from the entry block (which is the first block in the list)
        entry_label = blocks[0][0] if blocks else "entry"
        visited = set()
        bb_rename_map = {}
        bb_counter = 0
        
        def dfs(node):
            nonlocal bb_counter
            if node in visited:
                return
            visited.add(node)
            
            # Map node to a canonical name
            bb_rename_map[node] = f"block_{bb_counter}"
            bb_counter += 1
            
            # Visit successors in order of appearance
            for succ in successors[node]:
                if succ in block_by_label: # Only visit local blocks
                    dfs(succ)
                    
        dfs(entry_label)
        
        # Add any unvisited blocks (e.g. dead blocks) to make sure everything gets renamed
        for label, _ in blocks:
            if label not in bb_rename_map:
                bb_rename_map[label] = f"block_{bb_counter}"
                bb_counter += 1
                
        # Step 2d: Canonicalize local register names within this function
        # A register starts with `%` and represents a temporary value
        # Pattern to extract registers: %[a-zA-Z0-9._]+ or %"\d+" or similar
        # But we must NOT rename basic block label references in the same way as registers, 
        # or we should handle block label references using our bb_rename_map first!
        
        # We rename local registers in order of definition (e.g., as LHS of `=`) 
        # or appearance in function signature.
        reg_rename_map = {}
        reg_counter = 0
        
        # First, find parameters in the function signature:
        # define i32 @foo(i32 %a, i32* %b) ...
        # Match anything starting with `%` inside parameters part
        param_section_match = re.search(r'@[a-zA-Z0-9._]+\s*\(([^)]*)\)', header)
        if param_section_match:
            param_section = param_section_match.group(1)
            # Find all registers in parameters
            for param_reg in re.findall(r'%[a-zA-Z0-9._]+', param_section):
                if param_reg not in reg_rename_map and param_reg[1:] not in bb_rename_map:
                    reg_rename_map[param_reg] = f"%v{reg_counter}"
                    reg_counter += 1
                    
        # Now, scan blocks in topological/DFS order to assign canonical register names to values defined in instructions.
        ordered_labels = sorted(blocks, key=lambda b: bb_rename_map.get(b[0], "block_9999"))
        
        # Instruction assignment pattern: e.g. `%add = add i32 %a, %b`
        # LHS is before `=` and must be a register
        lhs_reg_re = re.compile(r'^\s*(%[a-zA-Z0-9._]+)\s*=')
        
        for label, lines_list in ordered_labels:
            for line in lines_list:
                lhs_match = lhs_reg_re.match(line)
                if lhs_match:
                    reg = lhs_match.group(1)
                    if reg not in reg_rename_map and reg[1:] not in bb_rename_map:
                        reg_rename_map[reg] = f"%v{reg_counter}"
                        reg_counter += 1
                        
                # Also capture any remaining used registers that were somehow never defined (e.g. inputs)
                # except basic block references
                for used_reg in re.findall(r'%[a-zA-Z0-9._]+', line):
                    # If this is referencing a basic block, it will be in bb_rename_map, so we skip it.
                    if (used_reg not in reg_rename_map and 
                        used_reg[1:] not in bb_rename_map and 
                        not lhs_reg_re.match(line)): # if it's not LHS
                        reg_rename_map[used_reg] = f"%v{reg_counter}"
                        reg_counter += 1
                        
        # Step 2e: Apply renaming mapping (reconstruct function text)
        # We rename block labels and registers.
        # To avoid partial replacements (e.g. renaming %v0 in %v01), we sort keys by length descending!
        sorted_regs = sorted(reg_rename_map.keys(), key=len, reverse=True)
        sorted_bbs = sorted(bb_rename_map.keys(), key=len, reverse=True)
        
        # Helper to rename a line
        def rename_line(line, is_header=False):
            # First, rename basic block label references:
            # Block references in branches/phis are like `%label`
            # In PHI nodes, they look like `[ %val, %label_name ]`
            # In branches, they look like `br label %label_name` or `label %label_name`
            
            # To be absolutely safe and prevent conflicts, we rename block labels first using %<name>
            for old_bb in sorted_bbs:
                # Replace `%old_bb` with `%bb_rename_map[old_bb]`
                # Match `%old_bb` with word boundary or non-alphanumeric boundary
                line = re.sub(r'%' + re.escape(old_bb) + r'\b', '%' + bb_rename_map[old_bb], line)
                
            # Second, rename local registers:
            for old_reg in sorted_regs:
                line = re.sub(re.escape(old_reg) + r'\b', reg_rename_map[old_reg], line)
                
            return line

        # Reconstruct
        new_header = rename_line(header, is_header=True)
        new_body_lines = []
        
        # Output blocks in DFS canonical order
        for label, lines_list in ordered_labels:
            canonical_label = bb_rename_map[label]
            # Write block header (except for entry block if it wasn't named in original, but we write it for uniformity)
            new_body_lines.append(f"{canonical_label}:")
            
            for line in lines_list:
                new_line = rename_line(line)
                new_body_lines.append(new_line)
                
        return "\n".join([new_header] + new_body_lines + [footer])

if __name__ == "__main__":
    # Quick visual check
    normalizer = IRNormalizer()
    sample_ir = """
define i32 @test(i32 %arg1, i32 %arg2) #0 {
entry:
  %cmp = icmp sgt i32 %arg1, %arg2, !dbg !10
  br i1 %cmp, label %if.then, label %if.else

if.then:                                          ; preds = %entry
  %add = add nsw i32 %arg1, 10, !dbg !12
  br label %return

if.else:                                          ; preds = %entry
  %sub = sub nsw i32 %arg2, 5
  br label %return

return:                                           ; preds = %if.else, %if.then
  %retval.0 = phi i32 [ %add, %if.then ], [ %sub, %if.else ]
  ret i32 %retval.0
}
"""
    print(normalizer.normalize(sample_ir))
