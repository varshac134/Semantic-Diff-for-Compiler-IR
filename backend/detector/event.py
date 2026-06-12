class SemanticEvent:
    def __init__(self, category, change_type, description, severity="Info", details=""):
        self.category = category       # "Optimization", "Structural", "Semantic"
        self.change_type = change_type # Specific sub-category name
        self.description = description
        self.severity = severity       # "High", "Medium", "Low", "Info"
        self.details = details

    def to_dict(self):
        return {
            "category": self.category,
            "change_type": self.change_type,
            "description": self.description,
            "severity": self.severity,
            "details": self.details
        }

    def __repr__(self):
        return f"[{self.category}] {self.change_type}: {self.description} ({self.severity})"
