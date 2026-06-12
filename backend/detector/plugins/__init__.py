from .structural import StructuralChangeDetector
from .semantic import SemanticChangeDetector
from .optimization import ConstantFoldingDetector, StrengthReductionDetector, DeadCodeDetector, VectorizationDetector, InliningDetector, Mem2RegDetector, LoopUnrollingDetector, ConstantPropagationDetector, CommonSubexpressionEliminationDetector, LICMDetector, RedundantLoadEliminationDetector

def get_all_detectors():
    return [
        StructuralChangeDetector(),
        SemanticChangeDetector(),
        ConstantFoldingDetector(),
        StrengthReductionDetector(),
        DeadCodeDetector(),
        VectorizationDetector(),
        InliningDetector(),
        Mem2RegDetector(),
        LoopUnrollingDetector(),
        ConstantPropagationDetector(),
        CommonSubexpressionEliminationDetector(),
        LICMDetector(),
        RedundantLoadEliminationDetector()
    ]
