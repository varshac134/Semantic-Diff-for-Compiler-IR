from backend.detector.framework import BaseDetector
from backend.detector.event import SemanticEvent

class SemanticChangeDetector(BaseDetector):
    priority = 30
    def detect(self, func_diff, old_func, new_func):
        events = []
        
        added_instructions = []
        deleted_instructions = []
        modified_instructions = []
        
        for pc in func_diff.primitive_changes:
            if getattr(pc, "claimed", False): continue
            if pc.new_inst and pc.type in ("ADD_INSTRUCTION", "MODIFY_INSTRUCTION"):
                added_instructions.append(pc.new_inst)
            if pc.old_inst and pc.type in ("REMOVE_INSTRUCTION", "MODIFY_INSTRUCTION"):
                deleted_instructions.append(pc.old_inst)
            if pc.type == "MODIFY_INSTRUCTION" and pc.old_inst and pc.new_inst:
                modified_instructions.append((pc.old_inst, pc.new_inst))

        # Arithmetic Changes
        arithmetic_mods = [pair for pair in modified_instructions if pair[0].category == "Arithmetic"]
        if arithmetic_mods:
            events.append(SemanticEvent(
                category="Semantic",
                change_type="Arithmetic Change",
                description="Arithmetic computation logic or constant operands were modified.",
                severity="Medium",
                details=f"Opcodes modified: {', '.join(set(p[0].opcode + ' -> ' + p[1].opcode for p in arithmetic_mods[:3]))}"
            ))
            
        # Control Flow Changes
        if func_diff.cfg_changed:
            events.append(SemanticEvent(
                category="Semantic",
                change_type="Control Flow Change",
                description="Control Flow Graph (CFG) structure has been modified (branches altered or blocks added/deleted).",
                severity="High",
                details=f"Added blocks: {len(func_diff.added_blocks)}, Deleted blocks: {len(func_diff.deleted_blocks)}"
            ))
            
        # Memory Access Changes
        mem_added = [i for i in added_instructions if i.category == "Memory"]
        mem_deleted = [i for i in deleted_instructions if i.category == "Memory"]
        if mem_added or mem_deleted:
            events.append(SemanticEvent(
                category="Semantic",
                change_type="Memory Access Change",
                description="Memory access pattern modified (stack allocations, loads, or stores added/removed).",
                severity="Medium",
                details=f"Memory ops added: {len(mem_added)}, Memory ops removed: {len(mem_deleted)}"
            ))
            
        # Function Behavior Changes
        ret_mods = [pair for pair in modified_instructions if pair[0].opcode == "ret"]
        if ret_mods:
            events.append(SemanticEvent(
                category="Semantic",
                change_type="Function Behavior Change",
                description="Return instruction values or operands changed, modifying function output behavior.",
                severity="High",
                details=f"Original return: {ret_mods[0][0].raw_text} -> New: {ret_mods[0][1].raw_text}"
            ))

        return events
