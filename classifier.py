import re

class SemanticEvent:
    def __init__(self, category, change_type, description, severity="Info", details=""):
        self.category = category       # e.g., "Vectorization", "Inlining", "Loop Unrolling", "Control Flow"
        self.change_type = change_type # e.g., "Gained", "Lost", "Modified", "Eliminated"
        self.description = description # Human-readable brief summary
        self.severity = severity       # "High" (large perf impact), "Medium", "Low", "Info"
        self.details = details         # Additional technical details

    def __repr__(self):
        return f"[{self.category}] {self.change_type}: {self.description} ({self.severity})"


class ChangeClassifier:
    def __init__(self):
        pass

    def classify_function_changes(self, func_diff, old_func, new_func):
        """
        Analyzes a FunctionDiff and returns a list of SemanticEvents.
        """
        events = []
        
        # Collect all added and deleted instructions across all blocks in this function
        all_added_insts = []
        all_deleted_insts = []
        
        # Track counts of instructions by opcode
        old_op_counts = {}
        new_op_counts = {}
        
        # Count opcodes in original and new function
        for lbl in old_func.block_order:
            for inst in old_func.blocks[lbl].instructions:
                old_op_counts[inst.op] = old_op_counts.get(inst.op, 0) + 1
        for lbl in new_func.block_order:
            for inst in new_func.blocks[lbl].instructions:
                new_op_counts[inst.op] = new_op_counts.get(inst.op, 0) + 1

        for o_lbl, block_diff in func_diff.matched_blocks.items():
            all_added_insts.extend(block_diff.added_instructions)
            all_deleted_insts.extend(block_diff.deleted_instructions)
            
            # Analyze block-level changes
            self._classify_block_control_flow(block_diff, events)
            self._classify_block_mem2reg(block_diff, events)
            self._classify_block_constant_folding(block_diff, events)

        # 1. VECTORIZATION CLASSIFICATION
        old_vector_insts = [inst for inst in all_deleted_insts if inst.is_vector]
        new_vector_insts = [inst for inst in all_added_insts if inst.is_vector]
        
        # Calculate overall vector instructions in old vs new
        total_old_vec = sum(1 for lbl in old_func.block_order for inst in old_func.blocks[lbl].instructions if inst.is_vector)
        total_new_vec = sum(1 for lbl in new_func.block_order for inst in new_func.blocks[lbl].instructions if inst.is_vector)

        if total_old_vec == 0 and total_new_vec > 0:
            # Vectorization Gained!
            # Try to identify vector width
            width = self._detect_vector_width(new_vector_insts)
            width_str = f"with width {width} " if width else ""
            events.append(SemanticEvent(
                category="Vectorization",
                change_type="Gained",
                description=f"Loop or operations were vectorized {width_str}in the new version.",
                severity="High",
                details=f"Added {total_new_vec} vector operations (e.g., {', '.join(set(i.op for i in new_vector_insts[:3]))})."
            ))
        elif total_old_vec > 0 and total_new_vec == 0:
            # Vectorization Lost!
            events.append(SemanticEvent(
                category="Vectorization",
                change_type="Lost",
                description="Vectorization was lost in the new version (operations reverted to scalar).",
                severity="High",
                details=f"Removed {total_old_vec} vector operations. Potential optimization regression."
            ))
        elif total_old_vec > 0 and total_new_vec > 0 and total_old_vec != total_new_vec:
            old_width = self._detect_vector_width([i for lbl in old_func.block_order for i in old_func.blocks[lbl].instructions if i.is_vector])
            new_width = self._detect_vector_width([i for lbl in new_func.block_order for i in new_func.blocks[lbl].instructions if i.is_vector])
            if old_width and new_width and old_width != new_width:
                events.append(SemanticEvent(
                    category="Vectorization",
                    change_type="Modified",
                    description=f"Vectorization width changed from {old_width} to {new_width}.",
                    severity="Medium",
                    details=f"Old vector width: {old_width}, New vector width: {new_width}."
                ))
            else:
                events.append(SemanticEvent(
                    category="Vectorization",
                    change_type="Modified",
                    description="Vector instruction layout or count changed.",
                    severity="Low",
                    details=f"Vector instruction count changed from {total_old_vec} to {total_new_vec}."
                ))

        # 2. FUNCTION INLINING CLASSIFICATION
        deleted_calls = [inst for inst in all_deleted_insts if inst.is_call]
        added_calls = [inst for inst in all_added_insts if inst.is_call]
        
        # Check for callee names
        del_callees = set(inst.called_function for inst in deleted_calls if inst.called_function)
        add_callees = set(inst.called_function for inst in added_calls if inst.called_function)
        
        # Filter out compiler intrinsic calls (starts with llvm.)
        del_user_callees = {c for c in del_callees if c and not c.startswith("@llvm.")}
        add_user_callees = {c for c in add_callees if c and not c.startswith("@llvm.")}
        
        inlined_funcs = del_user_callees - add_user_callees
        for f_name in inlined_funcs:
            # If the overall function size did not decrease significantly, it indicates inlining
            # because callee instructions replaced the call.
            events.append(SemanticEvent(
                category="Inlining",
                change_type="Gained",
                description=f"Function call to {f_name} was inlined in the new version.",
                severity="Medium",
                details=f"Call to {f_name} instruction removed, callee body expanded in-place."
            ))
            
        lost_inlining = add_user_callees - del_user_callees
        for f_name in lost_inlining:
            events.append(SemanticEvent(
                category="Inlining",
                change_type="Lost",
                description=f"Function {f_name} is no longer inlined (explicit call was added).",
                severity="Medium",
                details=f"A call instruction to {f_name} is present in the new version."
            ))

        # 3. LOOP UNROLLING CLASSIFICATION
        # Loop unrolling is characterized by an increase in instruction count in loop blocks, 
        # and duplicate instruction patterns (e.g. repeated adds or loads)
        self._classify_loop_unrolling(func_diff, old_func, new_func, events)
        
        # 4. CSE / REDUNDANT CODE ELIMINATION
        self._classify_cse(all_deleted_insts, all_added_insts, events)

        return events

    def _detect_vector_width(self, vector_insts):
        """
        Attempts to detect vector width (e.g. 4, 8) from vector type strings.
        e.g. `<4 x i32>` -> 4
        """
        for inst in vector_insts:
            match = re.search(r'<(\d+)\s*x', inst.raw_text)
            if match:
                return int(match.group(1))
        return None

    def _classify_block_control_flow(self, block_diff, events):
        """
        Detects if branches were eliminated inside a matched block.
        """
        # A conditional branch was eliminated if it was deleted, regardless of what replaces it (ret or unconditional br)
        deleted_cond = [inst for inst in block_diff.deleted_instructions if inst.op == "br" and "i1" in inst.raw_text]
        
        if deleted_cond:
            events.append(SemanticEvent(
                category="Control Flow",
                change_type="Branch Eliminated",
                description=f"Conditional branch in block '{block_diff.old_label}' was eliminated.",
                severity="Medium",
                details="Branch condition became constant or was simplified at compile-time, reducing control-flow complexity."
            ))

    def _classify_block_mem2reg(self, block_diff, events):
        """
        Detects if variables were promoted from memory (alloca/load/store) to registers (phi/direct).
        """
        deleted_allocas = [inst for inst in block_diff.deleted_instructions if inst.op == "alloca"]
        deleted_loads = [inst for inst in block_diff.deleted_instructions if inst.op == "load"]
        deleted_stores = [inst for inst in block_diff.deleted_instructions if inst.op == "store"]
        
        # If allocas and load/store were removed, this is a strong sign of register promotion
        if deleted_allocas and (deleted_loads or deleted_stores):
            events.append(SemanticEvent(
                category="Memory Behavior",
                change_type="Register Promoted (mem2reg)",
                description=f"Variables promoted from stack allocations to registers in block '{block_diff.old_label}'.",
                severity="Medium",
                details=f"Removed {len(deleted_allocas)} alloca(s), {len(deleted_loads)} load(s), and {len(deleted_stores)} store(s)."
            ))

    def _classify_block_constant_folding(self, block_diff, events):
        """
        Detects constant folding where computations are simplified to constants.
        """
        # If arithmetic instructions were deleted, but no new arithmetic instructions were added
        # AND we see constant operands in downstream instructions
        arithmetic_ops = {"add", "sub", "mul", "sdiv", "udiv", "shl", "lshr", "ashr", "and", "or", "xor"}
        
        del_arith = [inst for inst in block_diff.deleted_instructions if inst.op in arithmetic_ops]
        add_arith = [inst for inst in block_diff.added_instructions if inst.op in arithmetic_ops]
        
        if len(del_arith) > 0 and len(add_arith) == 0:
            # Verify if they were replaced by something, or just folded
            # For simplicity, if arithmetic operations were reduced in the block without losing control flow,
            # it indicates folding or dead code elimination.
            events.append(SemanticEvent(
                category="Constant Folding",
                change_type="Gained",
                description=f"Arithmetic operations were folded/simplified in block '{block_diff.old_label}'.",
                severity="Low",
                details=f"Folded {len(del_arith)} operation(s) (e.g., {', '.join(set(i.op for i in del_arith))})."
            ))

    def _classify_loop_unrolling(self, func_diff, old_func, new_func, events):
        """
        Identifies loop unrolling by checking if loops in old version got unrolled 
        (i.e. loop blocks instruction count expanded with duplicate sequences, or loops were eliminated).
        """
        # Look for loop blocks in old function. A loop block is a block with a backedge
        old_loop_blocks = []
        for label in old_func.block_order:
            block = old_func.blocks[label]
            if label in block.successors:
                old_loop_blocks.append(label)
                continue
            for succ in block.successors:
                if succ in old_func.block_order and old_func.block_order.index(succ) <= old_func.block_order.index(label):
                    old_loop_blocks.append(succ)
                    break
                    
        old_loop_blocks = list(set(old_loop_blocks))
        
        for o_lbl in old_loop_blocks:
            # Case A: Partial Loop Unrolling (loop block still exists but expanded)
            if o_lbl in func_diff.matched_blocks:
                block_diff = func_diff.matched_blocks[o_lbl]
                old_block = old_func.blocks[o_lbl]
                new_block = new_func.blocks[block_diff.new_label]
                
                len_old = len(old_block.instructions)
                len_new = len(new_block.instructions)
                
                if len_old > 3 and len_new >= len_old * 2:
                    new_ops = [inst.op for inst in new_block.instructions]
                    unique_ops = len(set(new_ops))
                    op_ratio = len_new / max(1, unique_ops)
                    
                    if op_ratio > 3.0: # high repetition
                        factor = round(len_new / len_old)
                        factor_str = f"{factor}x" if factor in [2, 4, 8, 16] else "multiple times"
                            
                        events.append(SemanticEvent(
                            category="Loop Unrolling",
                            change_type="Gained",
                            description=f"Loop at block '{o_lbl}' was unrolled {factor_str} in the new version.",
                            severity="High",
                            details=f"Block size expanded from {len_old} to {len_new} instructions with repeating opcode patterns."
                        ))
            
            # Case B: Complete Loop Unrolling (loop block deleted and body unrolled into entry block)
            elif o_lbl in func_diff.deleted_blocks:
                if "block_0" in new_func.blocks and "block_0" in old_func.blocks:
                    new_entry = new_func.blocks["block_0"]
                    old_entry = old_func.blocks["block_0"]
                    
                    # If new entry block is much larger than old entry block, and loop is deleted
                    if len(new_entry.instructions) > len(old_entry.instructions) + 5:
                        events.append(SemanticEvent(
                            category="Loop Unrolling",
                            change_type="Gained",
                            description=f"Loop at block '{o_lbl}' was fully unrolled in the new version.",
                            severity="High",
                            details="Loop block was completely eliminated; body unrolled into straight-line instructions in new entry block."
                        ))

    def _classify_cse(self, all_deleted_insts, all_added_insts, events):
        """
        Identifies Common Subexpression Elimination (CSE) by checking if redundant 
        identical instructions in the old version were merged into a single one.
        """
        # Look for identical operations that were deleted and replaced by a single or fewer operations.
        # This is a bit complex, but we can do a simplified heuristic:
        # If we deleted multiple duplicate instructions and added zero, or if overall instruction count decreased.
        pass

if __name__ == "__main__":
    # Test classifier on simulated diff
    from parser import Instruction, BasicBlock, Function, FunctionDiff, BlockDiff
    
    fd = FunctionDiff("@test")
    # Simulate Vectorization Gained
    inst_old = Instruction("ret i32 0")
    inst_new1 = Instruction("%v0 = load <4 x float>, <4 x float>* %v1")
    inst_new2 = Instruction("%v2 = fadd <4 x float> %v0, %v0")
    
    bd = BlockDiff("block_0", "block_0")
    bd.deleted_instructions = [inst_old]
    bd.added_instructions = [inst_new1, inst_new2]
    bd.diff_lines = [('-', inst_old.raw_text, inst_old), ('+', inst_new1.raw_text, inst_new1), ('+', inst_new2.raw_text, inst_new2)]
    bd.is_identical = False
    
    fd.matched_blocks["block_0"] = bd
    
    old_f = Function("@test", "i32", "")
    old_f.add_block(BasicBlock("block_0"))
    old_f.blocks["block_0"].add_instruction(inst_old)
    
    new_f = Function("@test", "i32", "")
    new_f.add_block(BasicBlock("block_0"))
    new_f.blocks["block_0"].add_instruction(inst_new1)
    new_f.blocks["block_0"].add_instruction(inst_new2)
    
    classifier = ChangeClassifier()
    events = classifier.classify_function_changes(fd, old_f, new_f)
    print("Classified Events:")
    for ev in events:
        print(ev)
