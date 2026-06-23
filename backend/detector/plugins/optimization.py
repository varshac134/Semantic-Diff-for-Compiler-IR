import re
from backend.detector.framework import BaseDetector
from backend.detector.event import SemanticEvent

class ConstantFoldingDetector(BaseDetector):
    priority = 100
    def detect(self, func_diff, old_func, new_func):
        events = []
        folded_pcs = []
        
        for pc in func_diff.primitive_changes:
            if getattr(pc, "claimed", False): continue
            
            # Instruction must be removed or modified to something non-arithmetic
            if pc.old_inst and pc.old_inst.category == "Arithmetic" and pc.type in ("REMOVE_INSTRUCTION", "MODIFY_INSTRUCTION"):
                operands = pc.old_inst.operands
                is_constant = True
                for op in operands:
                    if op.startswith("%") or op.startswith("@"):
                        is_constant = False
                        break
                
                if is_constant and len(operands) > 0:
                    folded_pcs.append(pc)
                    
        if len(folded_pcs) > 0:
            for pc in folded_pcs: pc.claimed = True
            events.append(SemanticEvent(
                category="Optimization",
                change_type="Constant Folding",
                description="Arithmetic calculations with constant operands were evaluated at compile-time.",
                severity="Low",
                details=f"Simplified {len(folded_pcs)} math operation(s) (e.g. {', '.join(set(pc.old_inst.opcode for pc in folded_pcs[:3]))})."
            ))
        return events

class StrengthReductionDetector(BaseDetector):
    priority = 90
    def detect(self, func_diff, old_func, new_func):
        events = []
        strength_reduction_pairs = []
        claimed_pcs = []
        for pc in func_diff.primitive_changes:
            if getattr(pc, "claimed", False): continue
            if pc.type == "MODIFY_INSTRUCTION" and pc.old_inst and pc.new_inst:
                old_i, new_i = pc.old_inst, pc.new_inst
                if old_i.opcode in {"mul", "sdiv", "udiv"} and new_i.opcode in {"shl", "lshr", "ashr", "add"}:
                    strength_reduction_pairs.append((old_i, new_i))
                    claimed_pcs.append(pc)
                    continue
            if pc.old_inst and pc.type in ("REMOVE_INSTRUCTION", "MODIFY_INSTRUCTION"):
                ops = pc.old_inst.operands
                opc = pc.old_inst.opcode
                if (opc == "mul" and "1" in ops) or (opc in ("add", "shl", "lshr", "sub") and "0" in ops):
                    strength_reduction_pairs.append((pc.old_inst, None))
                    claimed_pcs.append(pc)
                    
        if strength_reduction_pairs:
            for pc in claimed_pcs: pc.claimed = True
            events.append(SemanticEvent(
                category="Optimization",
                change_type="Strength Reduction",
                description="Arithmetic operations replaced with cheaper alternatives or algebraic identities (e.g. mul by 1).",
                severity="Medium",
                details=f"Detected {len(strength_reduction_pairs)} strength reduction(s) or algebraic simplifications."
            ))
        return events

class ConstantPropagationDetector(BaseDetector):
    priority = 85
    def detect(self, func_diff, old_func, new_func):
        events = []
        propagations = 0
        claimed_pcs = []
        for pc in func_diff.primitive_changes:
            if getattr(pc, "claimed", False): continue
            if pc.type == "MODIFY_INSTRUCTION" and pc.old_inst and pc.new_inst:
                old_ops = pc.old_inst.operands
                new_ops = pc.new_inst.operands
                if len(old_ops) == len(new_ops):
                    is_prop = False
                    for o_op, n_op in zip(old_ops, new_ops):
                        if o_op.startswith("%") and (n_op.lstrip("-").isdigit() or n_op == "null" or n_op == "true" or n_op == "false"):
                            propagations += 1
                            is_prop = True
                    if is_prop:
                        claimed_pcs.append(pc)
                        
        if propagations > 0:
            for pc in claimed_pcs: pc.claimed = True
            events.append(SemanticEvent(
                category="Optimization",
                change_type="Constant Propagation",
                description="Variables holding constant values were replaced with the inline constants.",
                severity="Medium",
                details=f"Propagated {propagations} constant(s) directly into instructions."
            ))
        return events

class CommonSubexpressionEliminationDetector(BaseDetector):
    priority = 80
    
    def _build_expression_table(self, func):
        """
        Build an expression table for a function.
        Maps: canonical_expression -> list of (block_label, instruction, lhs)
        
        This is the core data structure described in the user's algorithm:
        Expression Table: unordered_map<string, string> exprTable
        """
        expr_table = {}  # canonical_rhs -> [(block, inst, lhs)]
        
        for lbl in func.block_order:
            for inst in func.blocks[lbl].instructions:
                if inst.lhs and inst.opcode and inst.category not in ("Control Flow", "Function"):
                    # Build canonical RHS: "opcode operand1, operand2, ..."
                    canonical_rhs = self._canonical_expression(inst)
                    if canonical_rhs:
                        expr_table.setdefault(canonical_rhs, []).append((lbl, inst, inst.lhs))
        
        return expr_table
    
    def _canonical_expression(self, inst):
        """
        Create a canonical string for the RHS of an instruction.
        Strips type info and focuses on opcode + operands.
        For commutative operations, sorts operands for equivalence.
        """
        if not inst.opcode or not inst.operands:
            return None
        
        commutative_ops = {"add", "mul", "fadd", "fmul", "and", "or", "xor"}
        ops = list(inst.operands)
        
        if inst.opcode in commutative_ops and len(ops) == 2:
            ops.sort()
        
        return f"{inst.opcode}({', '.join(ops)})"
    
    def _build_value_map(self, func):
        """
        Build a map from LHS variable -> canonical expression.
        This enables transitive expression tracking:
          %t1 = add %a, %b         -> value_map[%t1] = "add(%a, %b)"
          %t3 = mul %t1, %c        -> value_map[%t3] = "mul(%t1, %c)"
        """
        value_map = {}  # lhs -> canonical_rhs
        for lbl in func.block_order:
            for inst in func.blocks[lbl].instructions:
                if inst.lhs and inst.opcode and inst.category not in ("Control Flow", "Function"):
                    canonical = self._canonical_expression(inst)
                    if canonical:
                        value_map[inst.lhs] = canonical
        return value_map
    
    def _resolve_expression(self, expr, value_map, depth=0):
        """
        Recursively resolve an expression by substituting temporaries.
        e.g. "mul(%t1, %c)" where value_map[%t1] = "add(%a, %b)"
             -> "mul(add(%a, %b), %c)"
        This allows detecting that two expressions are the same
        even when one uses intermediaries.
        """
        if depth > 5:  # Prevent infinite recursion
            return expr
        
        import re
        resolved = expr
        # Find all %variables in the expression
        vars_in_expr = re.findall(r'%[a-zA-Z0-9._]+', expr)
        for var in vars_in_expr:
            if var in value_map:
                resolved = resolved.replace(var, value_map[var])
        
        if resolved != expr:
            return self._resolve_expression(resolved, value_map, depth + 1)
        return resolved
    
    def detect(self, func_diff, old_func, new_func):
        events = []
        
        # Step 1: Build expression tables for old and new functions
        old_expr_table = self._build_expression_table(old_func)
        new_expr_table = self._build_expression_table(new_func)
        
        # Step 2: Build value maps for transitive resolution
        old_value_map = self._build_value_map(old_func)
        new_value_map = self._build_value_map(new_func)
        
        # Step 3: Find expressions that appeared multiple times in old
        #         but fewer times (or once) in new -> CSE was applied
        cse_expressions = []
        cse_count = 0
        
        for rhs, old_occurrences in old_expr_table.items():
            new_occurrences = new_expr_table.get(rhs, [])
            
            if len(old_occurrences) > 1 and len(new_occurrences) < len(old_occurrences):
                eliminated = len(old_occurrences) - len(new_occurrences)
                cse_count += eliminated
                cse_expressions.append((rhs, old_occurrences, eliminated))
        
        # Step 4: Deep equivalence check using resolved expressions
        #         Detect CSE even when the new IR uses different temporaries
        #         e.g. old has "add(%a, %b)" 3 times, new has it once as %t1
        #              and other places use %t1 directly
        old_resolved_counts = {}
        for rhs in old_expr_table:
            resolved = self._resolve_expression(rhs, old_value_map)
            old_resolved_counts[resolved] = old_resolved_counts.get(resolved, 0) + len(old_expr_table[rhs])
        
        new_resolved_counts = {}
        for rhs in new_expr_table:
            resolved = self._resolve_expression(rhs, new_value_map)
            new_resolved_counts[resolved] = new_resolved_counts.get(resolved, 0) + len(new_expr_table[rhs])
        
        for resolved_rhs, old_count in old_resolved_counts.items():
            new_count = new_resolved_counts.get(resolved_rhs, 0)
            if old_count > 1 and new_count > 0 and new_count < old_count:
                additional = old_count - new_count
                # Only count if not already counted in direct match
                if additional > cse_count:
                    cse_count = additional
        
        # Step 5: Check for hoisted temporaries (expressions moved to dominator block)
        #         In the user's example: (a+b) computed in both if/else branches
        #         gets hoisted to a single t1 = a+b before the if/else
        hoisted_count = 0
        for rhs, new_occurrences in new_expr_table.items():
            if len(new_occurrences) == 1:
                new_block, new_inst, new_lhs = new_occurrences[0]
                # Check if this temporary is used in multiple blocks
                uses_in_blocks = set()
                for lbl in new_func.block_order:
                    for inst in new_func.blocks[lbl].instructions:
                        if new_lhs in inst.operands:
                            uses_in_blocks.add(lbl)
                
                if len(uses_in_blocks) > 1:
                    # This value is computed once but used across multiple blocks
                    # Check if the old IR had the same expression in those blocks
                    old_occurrences = old_expr_table.get(rhs, [])
                    old_blocks_with_expr = {occ[0] for occ in old_occurrences}
                    
                    if len(old_blocks_with_expr) > 1:
                        hoisted_count += len(old_blocks_with_expr) - 1
        
        cse_count = max(cse_count, hoisted_count)
        
        # Step 6: Claim primitive changes
        claimed_pcs = []
        if cse_count > 0:
            for pc in func_diff.primitive_changes:
                if getattr(pc, "claimed", False): continue
                if pc.type in ("REMOVE_INSTRUCTION", "MODIFY_INSTRUCTION") and pc.old_inst:
                    pc_canonical = self._canonical_expression(pc.old_inst)
                    if pc_canonical:
                        # Check if this expression exists in our CSE set
                        for cse_rhs, old_occs, _ in cse_expressions:
                            if pc_canonical == cse_rhs:
                                claimed_pcs.append(pc)
                                break
                        else:
                            # Also check resolved equivalence
                            pc_resolved = self._resolve_expression(pc_canonical, old_value_map)
                            for cse_rhs, old_occs, _ in cse_expressions:
                                cse_resolved = self._resolve_expression(cse_rhs, old_value_map)
                                if pc_resolved == cse_resolved:
                                    claimed_pcs.append(pc)
                                    break
            
            for pc in claimed_pcs: pc.claimed = True
            
            # Build details with expression table
            expr_details = []
            for rhs, old_occs, elim in cse_expressions[:5]:
                blocks = ", ".join(set(occ[0] for occ in old_occs))
                expr_details.append(f"'{rhs}' (in blocks: {blocks}, eliminated {elim}x)")
            
            events.append(SemanticEvent(
                category="Optimization",
                change_type="Common Subexpression Elimination",
                description=f"Redundant computations were consolidated using shared temporaries across {len(set(o[0] for cse in cse_expressions for o in cse[1]))} block(s).",
                severity="Medium",
                details=f"CSE applied to {cse_count} expression(s). " + "; ".join(expr_details) if expr_details else f"Eliminated {cse_count} redundant computation(s) via expression table consolidation."
            ))
        
        return events

class DeadCodeDetector(BaseDetector):
    priority = 10
    def detect(self, func_diff, old_func, new_func):
        events = []
        deleted_branches = []
        deleted_regular = []
        
        # Track added opcodes per block to detect unaligned replacements
        added_opcodes_by_block = {}
        for pc in func_diff.primitive_changes:
            if pc.type == "ADD_INSTRUCTION" and pc.new_inst:
                added_opcodes_by_block.setdefault(pc.block, set()).add(pc.new_inst.opcode)

        for pc in func_diff.primitive_changes:
            if getattr(pc, "claimed", False): continue
            
            # True dead code must be a pure removal
            if pc.type != "REMOVE_INSTRUCTION" or not pc.old_inst:
                continue
                
            # If the same opcode was added in the same block, it's an unaligned replacement, not dead code
            if pc.old_inst.opcode in added_opcodes_by_block.get(pc.block, set()):
                continue
            
            if pc.old_inst.opcode == "br" and "i1" in pc.old_inst.raw_text:
                deleted_branches.append(pc.old_inst)
            elif pc.old_inst.category != "Control Flow":
                deleted_regular.append(pc.old_inst)
                
        if deleted_branches and not func_diff.added_blocks and len(func_diff.deleted_blocks) > 0:
            events.append(SemanticEvent(
                category="Optimization",
                change_type="Dead Code Elimination",
                description="Unreachable control flow blocks or dead branch instructions were eliminated.",
                severity="Medium",
                details=f"Eliminated {len(func_diff.deleted_blocks)} unreachable block(s)."
            ))
        elif len(deleted_regular) > 0:
            deleted_texts = [inst.raw_text for inst in deleted_regular]
            events.append(SemanticEvent(
                category="Optimization",
                change_type="Dead Code Elimination",
                description="Unused instructions with no side-effects were removed.",
                severity="Low",
                details=f"Removed {len(deleted_regular)} dead instruction(s): {', '.join(deleted_texts)}"
            ))
        return events

class VectorizationDetector(BaseDetector):
    priority = 70
    def detect(self, func_diff, old_func, new_func):
        events = []
        total_old_vec = sum(1 for lbl in old_func.block_order for inst in old_func.blocks[lbl].instructions if inst.is_vector)
        total_new_vec = sum(1 for lbl in new_func.block_order for inst in new_func.blocks[lbl].instructions if inst.is_vector)
        
        vector_ops_added = [pc.new_inst for pc in func_diff.primitive_changes if pc.new_inst and pc.new_inst.is_vector and pc.type in ("ADD_INSTRUCTION", "MODIFY_INSTRUCTION")]
        
        if total_old_vec == 0 and total_new_vec > 0:
            width = self._detect_vector_width(vector_ops_added)
            width_str = f"with width {width} " if width else ""
            events.append(SemanticEvent(
                category="Optimization",
                change_type="Vectorization",
                description=f"Scalar loop converted to vectorized SIMD operations {width_str}in the modified version.",
                severity="High",
                details=f"Added {total_new_vec} vector operations (e.g., {', '.join(set(i.opcode for i in vector_ops_added[:3]))})."
            ))
        elif total_old_vec > 0 and total_new_vec == 0:
            events.append(SemanticEvent(
                category="Optimization",
                change_type="Vectorization",
                description="Loop Vectorization was lost (vector operations reverted back to scalar code).",
                severity="High",
                details=f"Removed {total_old_vec} vector operations. Potential optimization regression."
            ))
        return events
        
    def _detect_vector_width(self, vector_insts):
        for inst in vector_insts:
            match = re.search(r'<(\d+)\s*x', inst.raw_text)
            if match:
                return int(match.group(1))
        return None

class InliningDetector(BaseDetector):
    priority = 60
    def detect(self, func_diff, old_func, new_func):
        events = []
        calls_added = [pc.new_inst for pc in func_diff.primitive_changes if pc.new_inst and pc.new_inst.is_call and pc.type in ("ADD_INSTRUCTION", "MODIFY_INSTRUCTION")]
        calls_deleted = [pc.old_inst for pc in func_diff.primitive_changes if pc.old_inst and pc.old_inst.is_call and pc.type in ("REMOVE_INSTRUCTION", "MODIFY_INSTRUCTION")]
        
        del_user_callees = {inst.called_function for inst in calls_deleted if inst.called_function and not inst.called_function.startswith("@llvm.")}
        add_user_callees = {inst.called_function for inst in calls_added if inst.called_function and not inst.called_function.startswith("@llvm.")}
        
        inlined_funcs = del_user_callees - add_user_callees
        for f_name in inlined_funcs:
            events.append(SemanticEvent(
                category="Optimization",
                change_type="Inlining",
                description=f"Function call to {f_name} was inlined in the modified version.",
                severity="Medium",
                details=f"Call instruction removed; callee instructions expanded in-place."
            ))
            
        lost_inlining = add_user_callees - del_user_callees
        for f_name in lost_inlining:
            events.append(SemanticEvent(
                category="Optimization",
                change_type="Inlining",
                description=f"Function call to {f_name} is no longer inlined (explicit call instruction added).",
                severity="Medium",
                details=f"Call to {f_name} instruction is present in the modified version."
            ))
        return events

class Mem2RegDetector(BaseDetector):
    priority = 50
    def detect(self, func_diff, old_func, new_func):
        events = []
        allocas_deleted = []
        loads_deleted = []
        stores_deleted = []
        for pc in func_diff.primitive_changes:
            if pc.old_inst and pc.type in ("REMOVE_INSTRUCTION", "MODIFY_INSTRUCTION"):
                if pc.old_inst.opcode == "alloca":
                    allocas_deleted.append(pc.old_inst)
                elif pc.old_inst.opcode == "load":
                    loads_deleted.append(pc.old_inst)
                elif pc.old_inst.opcode == "store":
                    stores_deleted.append(pc.old_inst)

        if allocas_deleted and (loads_deleted or stores_deleted):
            events.append(SemanticEvent(
                category="Optimization",
                change_type="Register Promoted (mem2reg)",
                description="Variables promoted from memory stack allocations to local registers (mem2reg).",
                severity="Medium",
                details=f"Removed {len(allocas_deleted)} stack allocation(s), {len(loads_deleted)} load(s), and {len(stores_deleted)} store(s)."
            ))
            events.append(SemanticEvent(
                category="Optimization",
                change_type="Memory Behavior",
                description="Variables promoted from memory allocations to registers (mem2reg).",
                severity="Medium"
            ))
        return events

class LoopUnrollingDetector(BaseDetector):
    priority = 40
    def detect(self, func_diff, old_func, new_func):
        events = []
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
            if o_lbl in func_diff.matched_blocks:
                block_diff = func_diff.matched_blocks[o_lbl]
                old_block = old_func.blocks[o_lbl]
                new_block = new_func.blocks[block_diff.new_label]
                
                len_old = len(old_block.instructions)
                len_new = len(new_block.instructions)
                
                if len_old > 3 and len_new >= len_old * 2:
                    new_ops = [inst.opcode for inst in new_block.instructions]
                    unique_ops = len(set(new_ops))
                    op_ratio = len_new / max(1, unique_ops)
                    
                    if op_ratio > 3.0:
                        factor = round(len_new / len_old)
                        factor_str = f"{factor}x" if factor in [2, 4, 8, 16] else "multiple times"
                        events.append(SemanticEvent(
                            category="Optimization",
                            change_type="Loop Unrolling",
                            description=f"Loop block '{o_lbl}' unrolled {factor_str} in the modified version.",
                            severity="High",
                            details=f"Block expanded from {len_old} to {len_new} instructions with duplicate sequences."
                        ))
            
            elif o_lbl in func_diff.deleted_blocks:
                if "block_0" in new_func.blocks and "block_0" in old_func.blocks:
                    new_entry = new_func.blocks["block_0"]
                    old_entry = old_func.blocks["block_0"]
                    if len(new_entry.instructions) > len(old_entry.instructions) + 5:
                        events.append(SemanticEvent(
                            category="Optimization",
                            change_type="Loop Unrolling",
                            description=f"Loop at block '{o_lbl}' was fully unrolled and branch eliminated.",
                            severity="High",
                            details="Loop block completely removed; body unrolled straight-line into entry block."
                        ))
        return events

class LICMDetector(BaseDetector):
    priority = 75
    def detect(self, func_diff, old_func, new_func):
        events = []
        claimed_pcs = []
        licm_count = 0
        
        removed_insts = []
        for pc in func_diff.primitive_changes:
            if getattr(pc, "claimed", False): continue
            if pc.type in ("REMOVE_INSTRUCTION", "MODIFY_INSTRUCTION") and pc.old_inst and pc.old_inst.opcode:
                removed_insts.append(pc)
                
        added_insts = []
        for pc in func_diff.primitive_changes:
            if getattr(pc, "claimed", False): continue
            if pc.type in ("ADD_INSTRUCTION", "MODIFY_INSTRUCTION") and pc.new_inst and pc.new_inst.opcode:
                added_insts.append(pc)
                
        for r_pc in removed_insts:
            for a_pc in added_insts:
                if r_pc.old_inst.opcode == a_pc.new_inst.opcode and r_pc.old_inst.operands == a_pc.new_inst.operands:
                    o_idx = old_func.block_order.index(r_pc.block) if r_pc.block in old_func.block_order else -1
                    n_idx = new_func.block_order.index(a_pc.block) if a_pc.block in new_func.block_order else -1
                    
                    if n_idx != -1 and o_idx != -1 and n_idx < o_idx:
                        licm_count += 1
                        claimed_pcs.append(r_pc)
                        claimed_pcs.append(a_pc)
                        break
                        
        if licm_count > 0:
            for pc in claimed_pcs: pc.claimed = True
            events.append(SemanticEvent(
                category="Optimization",
                change_type="Loop-Invariant Code Motion",
                description="Computations not dependent on loop variables were moved to the preheader (LICM).",
                severity="High",
                details=f"Moved {licm_count} instruction(s) outside of loops."
            ))
        return events

class RedundantLoadEliminationDetector(BaseDetector):
    priority = 82
    def detect(self, func_diff, old_func, new_func):
        events = []
        claimed_pcs = []
        eliminated_count = 0
        
        for pc in func_diff.primitive_changes:
            if getattr(pc, "claimed", False): continue
            if pc.type in ("REMOVE_INSTRUCTION", "MODIFY_INSTRUCTION") and pc.old_inst and pc.old_inst.opcode == "load":
                ptr = None
                if len(pc.old_inst.operands) > 0:
                    ptr = pc.old_inst.operands[-1]
                
                if ptr:
                    load_found = False
                    for lbl in new_func.block_order:
                        for inst in new_func.blocks[lbl].instructions:
                            if inst.opcode == "load" and ptr in inst.operands:
                                load_found = True
                                break
                        if load_found: break
                    
                    if load_found:
                        eliminated_count += 1
                        claimed_pcs.append(pc)
                        
        if eliminated_count > 0:
            for pc in claimed_pcs: pc.claimed = True
            events.append(SemanticEvent(
                category="Optimization",
                change_type="Redundant Load Elimination",
                description="Repeated memory reads (loads) from the same address were eliminated.",
                severity="Medium",
                details=f"Removed {eliminated_count} redundant load(s)."
            ))
        return events
