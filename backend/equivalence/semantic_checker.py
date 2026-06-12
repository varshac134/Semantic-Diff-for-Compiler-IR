class SemanticChecker:
    def __init__(self):
        pass

    def check_equivalence(self, func_diff, events):
        """
        Assesses if the changes in a function preserve semantic equivalence.
        Returns:
            dict: {"equivalent": bool}
        """
        if func_diff.is_identical:
            return {"equivalent": True}
            
        semantic_events = [ev for ev in events if ev.category == "Semantic"]
        optimization_events = [ev for ev in events if ev.category == "Optimization"]
        
        # Behavior changes (e.g. return values modified) are not equivalent
        if any(ev.change_type == "Function Behavior Change" for ev in semantic_events):
            return {"equivalent": False}
            
        # Arithmetic changes that are not optimizations (folding, strength reduction) are not equivalent
        has_arithmetic_change = any(ev.change_type == "Arithmetic Change" for ev in semantic_events)
        has_folding_opt = any(ev.change_type in {"Constant Folding", "Strength Reduction", "Vectorization"} for ev in optimization_events)
        if has_arithmetic_change and not has_folding_opt:
            return {"equivalent": False}
            
        # Control flow changes that are not optimizations (DCE, unrolling, inlining) are not equivalent
        has_cf_change = any(ev.change_type == "Control Flow Change" for ev in semantic_events)
        has_cf_opt = any(ev.change_type in {"Dead Code Elimination", "Loop Unrolling", "Inlining", "Vectorization"} for ev in optimization_events)
        if has_cf_change and not has_cf_opt:
            return {"equivalent": False}
            
        return {"equivalent": True}
