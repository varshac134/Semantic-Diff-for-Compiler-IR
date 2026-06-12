from backend.detector.framework import BaseDetector
from backend.detector.event import SemanticEvent

class StructuralChangeDetector(BaseDetector):
    priority = 25
    def detect(self, func_diff, old_func, new_func):
        events = []
        added_instructions = []
        deleted_instructions = []
        reordered_instructions = []
        
        for pc in func_diff.primitive_changes:
            if getattr(pc, "claimed", False): continue
            if pc.new_inst and pc.type in ("ADD_INSTRUCTION", "MODIFY_INSTRUCTION"):
                added_instructions.append(pc.new_inst)
            if pc.old_inst and pc.type in ("REMOVE_INSTRUCTION", "MODIFY_INSTRUCTION"):
                deleted_instructions.append(pc.old_inst)
            if pc.type == "REORDER_INSTRUCTION" and pc.old_inst and pc.new_inst:
                reordered_instructions.append((pc.old_inst, pc.new_inst))

        renamed_count = 0
        for old_lbl, b_diff in func_diff.matched_blocks.items():
            for marker, line, _ in b_diff.diff_lines:
                if marker in ['-', '+'] and '%' in line:
                    renamed_count += 1

        # Check for Pure Refactoring
        # Pure refactoring means no opcodes added or removed (DFG structure intact),
        # but reorderings or variable renaming exists.
        has_real_adds = any(pc.type == 'ADD_INSTRUCTION' for pc in func_diff.primitive_changes)
        has_real_rems = any(pc.type == 'REMOVE_INSTRUCTION' for pc in func_diff.primitive_changes)
        
        is_pure_refactoring = False
        if not has_real_adds and not has_real_rems and not func_diff.cfg_changed:
            if reordered_instructions or renamed_count > 0:
                is_pure_refactoring = True
                events.append(SemanticEvent(
                    category="Structural",
                    change_type="Pure Refactoring",
                    description="Only renaming or structural reorganization occurred without modifying data-flow or operations.",
                    severity="Info",
                    details=f"Reordered ops: {len(reordered_instructions)}, Renames: {renamed_count}"
                ))

        if not is_pure_refactoring:
            if added_instructions:
                events.append(SemanticEvent(
                    category="Structural",
                    change_type="Instruction Added",
                    description=f"Added {len(added_instructions)} new instruction(s) in the modified code.",
                    severity="Info",
                    details=f"Opcodes added: {', '.join(set(i.opcode for i in added_instructions[:4]))}"
                ))
                
            if deleted_instructions:
                events.append(SemanticEvent(
                    category="Structural",
                    change_type="Instruction Removed",
                    description=f"Removed {len(deleted_instructions)} instruction(s) from the original code.",
                    severity="Info",
                    details=f"Opcodes removed: {', '.join(set(i.opcode for i in deleted_instructions[:4]))}"
                ))
                
            if reordered_instructions:
                events.append(SemanticEvent(
                    category="Structural",
                    change_type="Instruction Reordered",
                    description=f"Reordered {len(reordered_instructions)} instruction(s) inside matched blocks.",
                    severity="Info",
                    details=f"Opcodes swapped: {', '.join(set(i[0].opcode for i in reordered_instructions[:4]))}"
                ))

        return events
