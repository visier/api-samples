from dataclasses import dataclass
from typing import List, Optional

from visier_api_data_in import PlanDataUploadResponseDTO

@dataclass
class DataLoadResult:
    response: PlanDataUploadResponseDTO
    missing_row_indices: List[int]


@dataclass
class PlanSegmentMemberWithLevelId:
    id: str
    display_name: str
    segment_id: str
    is_custom: bool
    parent_id: Optional[str] = None
