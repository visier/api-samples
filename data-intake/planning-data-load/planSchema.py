from dataclasses import dataclass, field
from typing import List, Optional


# Data classes from Planning Data Load API

@dataclass
class PlanItem:
    id: str
    displayName: str
    dataType: str


@dataclass
class TimePeriod:
    date: str
    displayName: str


@dataclass
class PlanSegmentLevel:
    id: str
    displayName: str
    order: int
    segmentId: str
    segmentDisplayName: str


@dataclass
class PlanSegmentLevelMember:
    id: str
    displayName: str
    isCustom: bool = field(default=False)
    parentId: Optional[str] = None


@dataclass
class PlanSegmentLevelMemberList:
    segmentLevelId: str
    members: List[PlanSegmentLevelMember]
    segmentId: str


@dataclass
class PlanSegmentLevel:
    id: str
    displayName: str
    order: int
    segmentId: str
    segmentDisplayName: str


@dataclass
class PlanSchema:
    planItems: List[PlanItem]
    timePeriods: List[TimePeriod]
    planSegmentLevels: List[PlanSegmentLevel]
    planSegmentLevelMembers: List[PlanSegmentLevelMemberList]


@dataclass
class PlanDataLoadError:
    rci: str
    errorMessage: str
    row: int = 0


@dataclass
class PlanDataLoadChange:
    rowMembers: List[str]
    period: str
    oldValue: float
    newValue: float


@dataclass
class PlanDataLoadChangeList:
    planItem: str
    changes: List


@dataclass
class PlanDataUploadResponse:
    updatedCellsCount: int = 0
    potentialUpdatedCellsCount: int = 0
    errors: List[PlanDataLoadError] = field(default_factory=list)
    changelists: List[PlanDataLoadChangeList] = field(default_factory=list)


@dataclass
class PlanRowDataLoadResponse:
    addedRowsCount: int = 0
    removedRowsCount: int = 0
    potentialAddedRowsCount: int = 0
    potentialRemovedRowsCount: int = 0
    errors: List[PlanDataLoadError] = field(default_factory=list)
    customMembers: List[PlanSegmentLevelMember] = field(default_factory=list)


# Data classes for the script

@dataclass
class DataLoadResult:
    response: PlanDataUploadResponse
    missingRowIndices: List[int]


@dataclass
class PlanSegmentMemberWithLevelId:
    id: str
    displayName: str
    segmentId: str
    isCustom: bool
    parentId: Optional[str] = None
