from enum import Enum

class PipelineStage(Enum):
    """Pipeline execution stages."""
    IDLE = "idle"
    VALIDATING = "validating"
    PARSING = "parsing"
    TRANSLATING = "translating"
    SAVING = "saving"
    COMPLETED = "completed"
    ERROR = "error"
