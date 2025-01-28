from dataclasses import dataclass
from typing import List, Optional

from visier_api_data_in import PlanDataUploadResponseDTO

@dataclass
class DataLoadResult:
    response: PlanDataUploadResponseDTO
    missingRowIndices: List[int]


@dataclass
class PlanSegmentMemberWithLevelId:
    id: str
    displayName: str
    segmentId: str
    isCustom: bool
    parentId: Optional[str] = None
