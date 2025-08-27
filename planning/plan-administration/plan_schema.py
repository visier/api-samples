from dataclasses import dataclass, field
from enum import Enum
from pydantic import BaseModel
from typing import List, Optional

class PlanScenarioPatchActionType(Enum):
    Update = "Update"
    Consolidate = "Consolidate"
    Submit = "Submit"
    Reopen = "Reopen"
    StartCollaboration = "StartCollaboration"
    EndCollaboration = "EndCollaboration"

    class Config:
        use_enum_values = True

class ActionWhenUnconsolidatedPlansExists(Enum):
    Ignore = "Ignore"
    Revert = "Revert"

    class Config:
        use_enum_values = True

@dataclass
class ConsolidateActionPayload:
    autoRollup: Optional[bool] = True
    includedSubPlans: List[str] = field(default_factory=list)

@dataclass
class ReopenActionPayload:
    assignee: Optional[str] = None
    dueDate: Optional[int] = None

@dataclass
class SubmitActionPayload:
    comment: Optional[str] = None

@dataclass
class StartCollaborationActionPayload:
    startDate: Optional[int] = None
    dueDate: Optional[int] = None

@dataclass
class EndCollaborationActionPayload:
    actionWhenUnconsolidatedPlansExists: ActionWhenUnconsolidatedPlansExists = ActionWhenUnconsolidatedPlansExists.Ignore

@dataclass
class ErrorSummary:
    rci: str
    message: str

@dataclass
class PlanScenarioPatchActionResult:
    planId: str
    success: bool
    error: Optional[ErrorSummary] = None

@dataclass
class PlanScenarioPatchRequest:
    actionType: PlanScenarioPatchActionType
    actionPayload: Optional[
        ConsolidateActionPayload
        | ReopenActionPayload
        | SubmitActionPayload
        | StartCollaborationActionPayload
        | EndCollaborationActionPayload
    ] = None

@dataclass
class PlanScenarioPatchResponse:
    actionResults: List[PlanScenarioPatchActionResult] = field(default_factory=list)


class CollaborationStatus(Enum):
    Closed = "Closed"
    Open = "Open"

class CollaborationInfo(BaseModel):
    scenarioId: str
    startDate: Optional[int] = None  # unix timestamp milliseconds
    dueDate: Optional[int] = None    # unix timestamp milliseconds  
    updatedDate: Optional[int] = None # unix timestamp milliseconds
    status: CollaborationStatus = CollaborationStatus.Closed

    class Config:
        use_enum_values = True

class ScenarioInfoDTO(BaseModel):
    uuid: str
    displayName: str
    versionedScenarioId: Optional[str] = None

class ExtendedPlanInfoDTO(BaseModel):
    uuid: str
    displayName: str
    modelId: str
    scenarios: List[ScenarioInfoDTO] = field(default_factory=list)
    collaborations: List[CollaborationInfo] = field(default_factory=list)
    parentPlanUuid: Optional[str] = None
    currencyCode: str

class ExtendedPlanSchemaDTO(BaseModel):
    uuid: str
    displayName: str
    modelId: str
    scenarios: List[ScenarioInfoDTO] = []
    collaborations: List[CollaborationInfo] = []
    parentPlanUuid: Optional[str] = None
    currencyCode: str

    class Config:
        use_enum_values = True

