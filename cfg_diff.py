import difflib
from collections import OrderedDict

class BlockDiff:
    def __init__(self, old_label, new_label):
        self.old_label = old_label
        self.new_label = new_label
        self.is_identical = True
        self.diff_lines = []          # List of (marker, line_text, instruction_obj)
        self.added_instructions = []   # List of Instruction objects
        self.deleted_instructions = [] # List of Instruction objects
        self.matched_instructions = [] # List of (old_inst, new_inst)

class FunctionDiff:
    def __init__(self, name):
        self.name = name
        self.is_identical = True
        self.cfg_changed = False
        
        self.added_blocks = []   # Blocks present in new but not old
        self.deleted_blocks = [] # Blocks present in old but not new
        self.matched_blocks = {} # old_label -> BlockDiff
        
        self.old_cfg_edges = {}  # label -> list of successors
        self.new_cfg_edges = {}  # label -> list of successors

class ModuleDiff:
    def __init__(self):
        self.added_functions = []
        self.deleted_functions = []
        self.changed_functions = {} # name -> FunctionDiff
        self.unchanged_functions = []

def calculate_block_similarity(old_block, new_block):
    """
    Calculates a similarity score [0.0, 1.0] between two basic blocks.
    Based on:
    1. Instruction count ratio.
    2. Opcode sequence similarity.
    3. CFG structure signature (pred/succ counts).
    """
    if not old_block.instructions and not new_block.instructions:
        return 1.0
    if not old_block.instructions or not new_block.instructions:
        return 0.0
        
    # 1. Length similarity
    len_old = len(old_block.instructions)
    len_new = len(new_block.instructions)
    length_sim = 1.0 - (abs(len_old - len_new) / max(len_old, len_new))
    
    # 2. Opcode sequence similarity using difflib
    old_ops = [inst.op for inst in old_block.instructions]
    new_ops = [inst.op for inst in new_block.instructions]
    
    op_matcher = difflib.SequenceMatcher(None, old_ops, new_ops)
    op_sim = op_matcher.ratio()
    
    # 3. CFG signature similarity
    pred_sim = 1.0 if (len(old_block.predecessors) == len(new_block.predecessors)) else 0.5
    succ_sim = 1.0 if (len(old_block.successors) == len(new_block.successors)) else 0.5
    cfg_sim = (pred_sim + succ_sim) / 2.0
    
    # Weighted average: 50% opcode similarity, 30% instruction length similarity, 20% CFG similarity
    score = (0.5 * op_sim) + (0.3 * length_sim) + (0.2 * cfg_sim)
    return score

class CFGDiffEngine:
    def __init__(self):
        pass

    def diff_modules(self, old_module, new_module):
        """
        Compares two Module objects and returns a ModuleDiff.
        """
        diff = ModuleDiff()
        
        # 1. Match functions by name
        old_funcs = set(old_module.functions.keys())
        new_funcs = set(new_module.functions.keys())
        
        diff.deleted_functions = sorted(list(old_funcs - new_funcs))
        diff.added_functions = sorted(list(new_funcs - old_funcs))
        
        matched_func_names = old_funcs & new_funcs
        
        for name in sorted(list(matched_func_names)):
            old_func = old_module.functions[name]
            new_func = new_module.functions[name]
            
            func_diff = self.diff_functions(old_func, new_func)
            
            if func_diff.is_identical:
                diff.unchanged_functions.append(name)
            else:
                diff.changed_functions[name] = func_diff
                
        return diff

    def diff_functions(self, old_func, new_func):
        """
        Compares two Function objects and returns a FunctionDiff.
        """
        func_diff = FunctionDiff(old_func.name)
        func_diff.old_cfg_edges = {lbl: list(old_func.blocks[lbl].successors) for lbl in old_func.block_order}
        func_diff.new_cfg_edges = {lbl: list(new_func.blocks[lbl].successors) for lbl in new_func.block_order}
        
        # Match basic blocks
        old_labels = list(old_func.block_order)
        new_labels = list(new_func.block_order)
        
        # Greedy matching algorithm
        # Calculate pairwise similarity scores for all combinations
        similarities = []
        for o_lbl in old_labels:
            for n_lbl in new_labels:
                score = calculate_block_similarity(old_func.blocks[o_lbl], new_func.blocks[n_lbl])
                similarities.append((score, o_lbl, n_lbl))
                
        # Sort by similarity score descending
        similarities.sort(key=lambda x: x[0], reverse=True)
        
        matched_old = {}
        matched_new = {}
        
        # Match blocks greedily above a threshold (e.g. 0.3)
        # However, block_0 (entry block) should always match block_0 if they both exist!
        if "block_0" in old_labels and "block_0" in new_labels:
            matched_old["block_0"] = "block_0"
            matched_new["block_0"] = "block_0"
            
        for score, o_lbl, n_lbl in similarities:
            if o_lbl in matched_old or n_lbl in matched_new:
                continue
            if score >= 0.3:
                matched_old[o_lbl] = n_lbl
                matched_new[n_lbl] = o_lbl
                
        # Classify added/deleted blocks
        func_diff.deleted_blocks = sorted([lbl for lbl in old_labels if lbl not in matched_old])
        func_diff.added_blocks = sorted([lbl for lbl in new_labels if lbl not in matched_new])
        
        # If any block is added/deleted or if matching isn't identical naming, control flow has changed
        if func_diff.added_blocks or func_diff.deleted_blocks:
            func_diff.cfg_changed = True
            
        # Diff matched blocks
        func_is_identical = True
        for o_lbl in old_labels:
            if o_lbl not in matched_old:
                func_is_identical = False
                continue
                
            n_lbl = matched_old[o_lbl]
            old_block = old_func.blocks[o_lbl]
            new_block = new_func.blocks[n_lbl]
            
            block_diff = self.diff_blocks(old_block, new_block)
            func_diff.matched_blocks[o_lbl] = block_diff
            
            if not block_diff.is_identical:
                func_is_identical = False
                
            # Verify CFG matching: Do successors match?
            # Maps successors of old block using block mapping and checks if they match new block successors
            old_succs_mapped = []
            for s in old_block.successors:
                if s in matched_old:
                    old_succs_mapped.append(matched_old[s])
                else:
                    old_succs_mapped.append(None) # successor was deleted
                    
            if old_succs_mapped != new_block.successors:
                func_diff.cfg_changed = True
                func_is_identical = False

        if func_diff.added_blocks or func_diff.deleted_blocks:
            func_is_identical = False
            
        func_diff.is_identical = func_is_identical
        return func_diff

    def diff_blocks(self, old_block, new_block):
        """
        Diffs two individual BasicBlocks line-by-line and returns a BlockDiff.
        """
        block_diff = BlockDiff(old_block.label, new_block.label)
        
        old_inst_texts = [inst.raw_text for inst in old_block.instructions]
        new_inst_texts = [inst.raw_text for inst in new_block.instructions]
        
        # Perform SequenceMatcher diff
        sm = difflib.SequenceMatcher(None, old_inst_texts, new_inst_texts)
        
        diff_lines = []
        is_identical = True
        
        # Align instructions to populate matched list
        # For simplicity, we loop through opcodes matching
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'equal':
                for idx in range(i1, i2):
                    old_idx = idx
                    new_idx = j1 + (idx - i1)
                    old_inst = old_block.instructions[old_idx]
                    new_inst = new_block.instructions[new_idx]
                    diff_lines.append((' ', old_inst.raw_text, old_inst))
                    block_diff.matched_instructions.append((old_inst, new_inst))
            elif tag == 'delete':
                is_identical = False
                for idx in range(i1, i2):
                    old_inst = old_block.instructions[idx]
                    diff_lines.append(('-', old_inst.raw_text, old_inst))
                    block_diff.deleted_instructions.append(old_inst)
            elif tag == 'insert':
                is_identical = False
                for idx in range(j1, j2):
                    new_inst = new_block.instructions[idx]
                    diff_lines.append(('+', new_inst.raw_text, new_inst))
                    block_diff.added_instructions.append(new_inst)
            elif tag == 'replace':
                is_identical = False
                # First delete old instructions, then insert new ones
                for idx in range(i1, i2):
                    old_inst = old_block.instructions[idx]
                    diff_lines.append(('-', old_inst.raw_text, old_inst))
                    block_diff.deleted_instructions.append(old_inst)
                for idx in range(j1, j2):
                    new_inst = new_block.instructions[idx]
                    diff_lines.append(('+', new_inst.raw_text, new_inst))
                    block_diff.added_instructions.append(new_inst)
                    
        block_diff.diff_lines = diff_lines
        block_diff.is_identical = is_identical
        return block_diff

if __name__ == "__main__":
    from parser import IRParser
    p = IRParser()
    
    old_ir = """
define i32 @test(i32 %v0, i32 %v1) {
block_0:
  %v2 = icmp sgt i32 %v0, %v1
  br i1 %v2, label %block_1, label %block_2
block_1:
  %v3 = add nsw i32 %v0, 10
  br label %block_3
block_2:
  %v4 = sub nsw i32 %v1, 5
  br label %block_3
block_3:
  %v5 = phi i32 [ %v3, %block_1 ], [ %v4, %block_2 ]
  ret i32 %v5
}
"""

    new_ir = """
define i32 @test(i32 %v0, i32 %v1) {
block_0:
  %v2 = icmp sgt i32 %v0, %v1
  br i1 %v2, label %block_1, label %block_2
block_1:
  %v3 = shl i32 %v0, 1
  br label %block_3
block_2:
  %v4 = sub nsw i32 %v1, 5
  br label %block_3
block_3:
  %v5 = phi i32 [ %v3, %block_1 ], [ %v4, %block_2 ]
  ret i32 %v5
}
"""

    old_mod = p.parse(old_ir)
    new_mod = p.parse(new_ir)
    
    engine = CFGDiffEngine()
    diff = engine.diff_modules(old_mod, new_mod)
    print("Changed functions:", diff.changed_functions.keys())
    f_diff = diff.changed_functions["@test"]
    print("Function identical:", f_diff.is_identical)
    print("CFG changed:", f_diff.cfg_changed)
    b_diff = f_diff.matched_blocks["block_1"]
    print("Block 1 identical:", b_diff.is_identical)
    for marker, line, _ in b_diff.diff_lines:
        print(f"  {marker} {line}")
