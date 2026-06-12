import difflib
from collections import OrderedDict

class PrimitiveChange:
    def __init__(self, change_type, block, old_inst=None, new_inst=None, metadata=None):
        self.type = change_type  # 'ADD_INSTRUCTION', 'REMOVE_INSTRUCTION', 'MODIFY_INSTRUCTION', 'REORDER_INSTRUCTION'
        self.block = block
        self.old_inst = old_inst
        self.new_inst = new_inst
        self.metadata = metadata or {}

    def to_dict(self):
        res = {
            "type": self.type,
            "block": self.block
        }
        if self.old_inst:
            res["old_instruction"] = self.old_inst.to_dict()
        if self.new_inst:
            res["new_instruction"] = self.new_inst.to_dict()
        if self.metadata:
            res["metadata"] = self.metadata
        return res

    def __repr__(self):
        return f"PrimitiveChange({self.type} in {self.block})"


class BlockDiff:
    def __init__(self, old_label, new_label):
        self.old_label = old_label
        self.new_label = new_label
        self.is_identical = True
        self.diff_lines = []
        self.primitive_changes = []
        self.added_instructions = []
        self.deleted_instructions = []
        self.matched_instructions = []

    def to_dict(self):
        return {
            "old_label": self.old_label,
            "new_label": self.new_label,
            "is_identical": self.is_identical,
            "diff_lines": [(marker, text) for marker, text, _ in self.diff_lines],
            "primitive_changes": [c.to_dict() for c in self.primitive_changes]
        }


class FunctionDiff:
    def __init__(self, name):
        self.name = name
        self.is_identical = True
        self.cfg_changed = False
        self.added_blocks = []
        self.deleted_blocks = []
        self.matched_blocks = {}
        self.old_cfg_edges = {}
        self.new_cfg_edges = {}
        self.primitive_changes = []

    def to_dict(self):
        return {
            "name": self.name,
            "is_identical": self.is_identical,
            "cfg_changed": self.cfg_changed,
            "added_blocks": self.added_blocks,
            "deleted_blocks": self.deleted_blocks,
            "matched_blocks": {lbl: diff.to_dict() for lbl, diff in self.matched_blocks.items()},
            "primitive_changes": [c.to_dict() for c in self.primitive_changes]
        }


class ModuleDiff:
    def __init__(self):
        self.added_functions = []
        self.deleted_functions = []
        self.changed_functions = {}
        self.unchanged_functions = []


def calculate_block_similarity(old_block, new_block, old_centrality=0, new_centrality=0):
    """
    Calculates a similarity score [0.0, 1.0] between two basic blocks.
    """
    if not old_block.instructions and not new_block.instructions:
        return 1.0
    if not old_block.instructions or not new_block.instructions:
        return 0.0
        
    len_old = len(old_block.instructions)
    len_new = len(new_block.instructions)
    length_sim = 1.0 - (abs(len_old - len_new) / max(len_old, len_new))
    
    old_ops = [inst.opcode for inst in old_block.instructions]
    new_ops = [inst.opcode for inst in new_block.instructions]
    
    op_matcher = difflib.SequenceMatcher(None, old_ops, new_ops)
    op_sim = op_matcher.ratio()
    
    pred_sim = 1.0 if (len(old_block.predecessors) == len(new_block.predecessors)) else 0.5
    succ_sim = 1.0 if (len(old_block.successors) == len(new_block.successors)) else 0.5
    
    cent_sim = 1.0 - abs(old_centrality - new_centrality)
    
    cfg_sim = (pred_sim + succ_sim + cent_sim) / 3.0
    
    score = (0.4 * op_sim) + (0.3 * length_sim) + (0.3 * cfg_sim)
    return score


class CFGDiffEngine:
    def __init__(self):
        pass

    def diff_modules(self, old_module, new_module):
        diff = ModuleDiff()
        
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
        import networkx as nx
        func_diff = FunctionDiff(old_func.name)
        func_diff.old_cfg_edges = {lbl: list(old_func.blocks[lbl].successors) for lbl in old_func.block_order}
        func_diff.new_cfg_edges = {lbl: list(new_func.blocks[lbl].successors) for lbl in new_func.block_order}
        
        # Build NetworkX DiGraphs
        old_G = nx.DiGraph()
        for u, succs in func_diff.old_cfg_edges.items():
            for v in succs:
                old_G.add_edge(u, v)
                
        new_G = nx.DiGraph()
        for u, succs in func_diff.new_cfg_edges.items():
            for v in succs:
                new_G.add_edge(u, v)
                
        # Optional: compute degree centrality for deeper structural hints
        old_centrality = nx.degree_centrality(old_G) if old_G.nodes else {}
        new_centrality = nx.degree_centrality(new_G) if new_G.nodes else {}

        
        old_labels = list(old_func.block_order)
        new_labels = list(new_func.block_order)
        
        similarities = []
        for o_lbl in old_labels:
            for n_lbl in new_labels:
                o_cent = old_centrality.get(o_lbl, 0)
                n_cent = new_centrality.get(n_lbl, 0)
                score = calculate_block_similarity(old_func.blocks[o_lbl], new_func.blocks[n_lbl], o_cent, n_cent)
                similarities.append((score, o_lbl, n_lbl))
                
        similarities.sort(key=lambda x: x[0], reverse=True)
        
        matched_old = {}
        matched_new = {}
        
        if "block_0" in old_labels and "block_0" in new_labels:
            matched_old["block_0"] = "block_0"
            matched_new["block_0"] = "block_0"
            
        for score, o_lbl, n_lbl in similarities:
            if o_lbl in matched_old or n_lbl in matched_new:
                continue
            if score >= 0.3:
                matched_old[o_lbl] = n_lbl
                matched_new[n_lbl] = o_lbl
                
        func_diff.deleted_blocks = sorted([lbl for lbl in old_labels if lbl not in matched_old])
        func_diff.added_blocks = sorted([lbl for lbl in new_labels if lbl not in matched_new])
        
        if func_diff.added_blocks or func_diff.deleted_blocks:
            func_diff.cfg_changed = True
            
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
                
            func_diff.primitive_changes.extend(block_diff.primitive_changes)
            
            old_succs_mapped = []
            for s in old_block.successors:
                if s in matched_old:
                    old_succs_mapped.append(matched_old[s])
                else:
                    old_succs_mapped.append(None)
                    
            if old_succs_mapped != new_block.successors:
                func_diff.cfg_changed = True
                func_is_identical = False

        if func_diff.added_blocks or func_diff.deleted_blocks:
            func_is_identical = False
            
        func_diff.is_identical = func_is_identical
        return func_diff

    def diff_blocks(self, old_block, new_block):
        block_diff = BlockDiff(old_block.label, new_block.label)
        
        old_inst_texts = [inst.raw_text for inst in old_block.instructions]
        new_inst_texts = [inst.raw_text for inst in new_block.instructions]
        
        sm = difflib.SequenceMatcher(None, old_inst_texts, new_inst_texts)
        
        diff_lines = []
        is_identical = True
        
        deleted_insts = []
        added_insts = []
        
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
                    deleted_insts.append((idx, old_inst))
            elif tag == 'insert':
                is_identical = False
                for idx in range(j1, j2):
                    new_inst = new_block.instructions[idx]
                    diff_lines.append(('+', new_inst.raw_text, new_inst))
                    added_insts.append((idx, new_inst))
            elif tag == 'replace':
                is_identical = False
                for idx in range(i1, i2):
                    old_inst = old_block.instructions[idx]
                    diff_lines.append(('-', old_inst.raw_text, old_inst))
                    deleted_insts.append((idx, old_inst))
                for idx in range(j1, j2):
                    new_inst = new_block.instructions[idx]
                    diff_lines.append(('+', new_inst.raw_text, new_inst))
                    added_insts.append((idx, new_inst))
                    
        block_diff.diff_lines = diff_lines
        block_diff.is_identical = is_identical
        
        matched_del_idx = set()
        matched_add_idx = set()
        
        # Pass 1: Reordering check
        for del_idx, del_inst in deleted_insts:
            for add_idx, add_inst in added_insts:
                if add_idx in matched_add_idx:
                    continue
                if del_inst.opcode == add_inst.opcode and del_inst.operands == add_inst.operands:
                    block_diff.primitive_changes.append(PrimitiveChange(
                        "REORDER_INSTRUCTION",
                        old_block.label,
                        old_inst=del_inst,
                        new_inst=add_inst,
                        metadata={"old_index": del_idx, "new_index": add_idx}
                    ))
                    matched_del_idx.add(del_idx)
                    matched_add_idx.add(add_idx)
                    break
                    
        # Pass 2: Modification check
        remaining_deletes = [(idx, inst) for idx, inst in deleted_insts if idx not in matched_del_idx]
        remaining_adds = [(idx, inst) for idx, inst in added_insts if idx not in matched_add_idx]
        
        min_len = min(len(remaining_deletes), len(remaining_adds))
        for i in range(min_len):
            del_idx, del_inst = remaining_deletes[i]
            add_idx, add_inst = remaining_adds[i]
            
            opcode_changed = del_inst.opcode != add_inst.opcode
            operands_changed = del_inst.operands != add_inst.operands
            
            block_diff.primitive_changes.append(PrimitiveChange(
                "MODIFY_INSTRUCTION",
                old_block.label,
                old_inst=del_inst,
                new_inst=add_inst,
                metadata={
                    "opcode_changed": opcode_changed,
                    "operands_changed": operands_changed,
                    "old_opcode": del_inst.opcode,
                    "new_opcode": add_inst.opcode
                }
            ))
            matched_del_idx.add(del_idx)
            matched_add_idx.add(add_idx)
            
        # Pass 3: Added / Removed instructions
        for del_idx, del_inst in deleted_insts:
            if del_idx not in matched_del_idx:
                block_diff.primitive_changes.append(PrimitiveChange(
                    "REMOVE_INSTRUCTION",
                    old_block.label,
                    old_inst=del_inst
                ))
                block_diff.deleted_instructions.append(del_inst)
                
        for add_idx, add_inst in added_insts:
            if add_idx not in matched_add_idx:
                block_diff.primitive_changes.append(PrimitiveChange(
                    "ADD_INSTRUCTION",
                    old_block.label,
                    new_inst=add_inst
                ))
                block_diff.added_instructions.append(add_inst)
                
        return block_diff
