class BaseDetector:
    """
    Base class for all semantic change and optimization detectors.
    """
    priority = 50
    def detect(self, func_diff, old_func, new_func):
        """
        Analyzes the function diff and returns a list of SemanticEvent objects.
        """
        raise NotImplementedError("Detectors must implement detect()")

class DetectorFramework:
    def __init__(self):
        self.detectors = []

    def register(self, detector: BaseDetector):
        self.detectors.append(detector)

    def run_all(self, func_diff, old_func, new_func):
        """
        Runs all registered detectors on the provided diff.
        Returns a flat list of SemanticEvent objects.
        """
        self.detectors.sort(key=lambda d: getattr(d, 'priority', 50), reverse=True)
        for pc in func_diff.primitive_changes:
            pc.claimed = False
            
        events = []
        for detector in self.detectors:
            results = detector.detect(func_diff, old_func, new_func)
            if results:
                events.extend(results)
        return events
