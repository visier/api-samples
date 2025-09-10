from typing import Dict, List, Optional, Set

import pandas as pd
import os
from dotenv import load_dotenv
from pandas import DataFrame
import json
from datetime import datetime, timezone

from visier_platform_sdk import (
    ApiClient, Configuration, PlanAdministrationApi, DataModelApi, GetPlanListResponseDTO,
    CollaborationInfo, PlanWithSchemaDTO
)

# Define CollaborationStatus enum locally since it might not be in the SDK
from enum import Enum

class CollaborationStatus(Enum):
    Closed = "Closed"
    Open = "Open"

load_dotenv()

target_plan_name = os.getenv('TARGET_PLAN_NAME')
if target_plan_name is None:
    raise ValueError("TARGET_PLAN_NAME environment variable must be defined")
TARGET_PLAN_NAME: str = target_plan_name

config = Configuration.from_env()
api_client = ApiClient(config)
data_load_api = DataModelApi()
plan_admin_api = PlanAdministrationApi(api_client)

# Calculate start of today once to ensure consistency across all plans
def get_start_of_today_timestamp() -> int:
    """
    Get the start of today in local time as a Unix timestamp in milliseconds.
    :return: Unix timestamp in milliseconds for start of today (00:00:00)
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return int(today.timestamp() * 1000)

# Cache the start of today timestamp to ensure all plans use the same value
START_OF_TODAY_MS = get_start_of_today_timestamp()


def list_plans() -> GetPlanListResponseDTO:
    """
    Retrieves all plans by paginating through all pages.
    :return: Combined response with all plans.
    """
    all_plans = []
    page = 1
    
    while True:
        print(f"Fetching plans page {page}...")
        response = data_load_api.plan_data_loadl_list(page=str(page), exclude_subplans=False)
        
        # Check if response has plans and add them to our collection
        if hasattr(response, 'plans') and response.plans:
            all_plans.extend(response.plans)
            page += 1
        else:
            # No more plans, break the loop
            break
    
    # Create a combined response object
    # Assuming the first response structure, but with all plans
    if all_plans:
        # Use the last response as a template but replace plans with all collected plans
        combined_response = response
        combined_response.plans = all_plans
        return combined_response
    else:
        # Return empty response if no plans found
        return response

def get_schema(plan_uuid: str) -> Optional[PlanWithSchemaDTO]:
    """
    Retrieves the schema for the specified plan UUID.
    :param plan_uuid: UUID of the plan to get schema for.
    :return: The schema of the plan.
    """
    if plan_uuid is None:
        raise ValueError("plan_uuid must be provided.")
    
    print(f"Fetching plan schema for plan with id: {plan_uuid}")

    try:
        # Use the dedicated API method
        response = data_load_api.plan_info_with_schema(plan_uuid)
        
        print("Successfully retrieved plan details and schema!")
        # Log the retrieved schema
        print(f"Retrieved plan schema: {json.dumps(response.model_dump() if hasattr(response, 'model_dump') else response, indent=2, default=str)}")

        return response
    except Exception as e:
        print(f"Failed to retrieve plan schema: {str(e)}")
        raise

def find_open_or_latest_collaboration(schema: PlanWithSchemaDTO) -> Optional[CollaborationInfo]:
    """
    Finds the open or latest collaboration in the given plan schema.
    :param schema: The plan schema to search within.
    :return: The open or latest collaboration, if found.
    """
    # Get collaborations from the plan object within the schema
    plan = schema.plan
    if not hasattr(plan, 'collaborations') or not plan.collaborations:
        return None

    # Find the open collaboration or the latest one
    # Check for both enum and string values since the API returns strings
    open_collab = next((c for c in plan.collaborations 
                       if (c.status == CollaborationStatus.Open.value)), None)
    if open_collab:
        return open_collab

    # If no open collaboration, return the latest one based on updated_date
    return max(plan.collaborations, key=lambda c: c.updated_date or 0, default=None)

def build_plan_tree(plans_response: GetPlanListResponseDTO) -> tuple[List[Dict], Dict[str, Dict]]:
    """
    Builds a tree structure from a flat list of plans, organizing root plans and their subplans.
    :param plans_response: Response containing the flat list of plans
    :return: Tuple of (list of root plans with nested subplans, dictionary of all plans by UUID)
    """
    if not plans_response or not hasattr(plans_response, 'plans') or not plans_response.plans:
        return [], {}
    
    # Convert plans to dictionaries for easier manipulation
    plans_dict = {}
    for plan in plans_response.plans:
        plan_data = plan.model_dump() if hasattr(plan, 'model_dump') else plan
        plan_uuid = plan_data.get('uuid') if isinstance(plan_data, dict) else plan.uuid
        plans_dict[plan_uuid] = {
            **(plan_data if isinstance(plan_data, dict) else plan.model_dump()),
            'subplans': []  # Initialize empty subplans list
        }
    
    # Build the tree structure
    root_plans = []
    
    for plan_uuid, plan_data in plans_dict.items():
        parent_uuid = plan_data.get('parent_plan_uuid')
        
        if parent_uuid and parent_uuid in plans_dict:
            # This is a subplan, add it to its parent's subplans
            plans_dict[parent_uuid]['subplans'].append(plan_data)
        else:
            # This is a root plan (no parent or parent not found)
            root_plans.append(plan_data)
    
    # Sort subplans recursively by displayName for better organization
    def sort_subplans(plan):
        if plan.get('subplans'):
            plan['subplans'].sort(key=lambda x: x.get('display_name', ''))
            for subplan in plan['subplans']:
                sort_subplans(subplan)
    
    # Sort root plans and their subplans
    root_plans.sort(key=lambda x: x.get('display_name', ''))
    for root_plan in root_plans:
        sort_subplans(root_plan)
    
    return root_plans, plans_dict

def print_plan_tree(plans_tree: List[Dict], indent: int = 0) -> None:
    """
    Prints the plan tree structure in a readable format.
    :param plans_tree: List of root plans with nested subplans
    :param indent: Current indentation level
    """
    for plan in plans_tree:
        prefix = "  " * indent + ("└─ " if indent > 0 else "")
        display_name = plan.get('display_name', 'Unnamed Plan')
        uuid = plan.get('uuid', 'No UUID')
        print(f"{prefix}{display_name} ({uuid})")
        
        if plan.get('subplans'):
            print_plan_tree(plan['subplans'], indent + 1)

def find_target_plan(plans_tree: List[Dict], target_name: str) -> Optional[Dict]:
    """
    Finds the first root plan that matches the target name.
    :param plans_tree: List of root plans with nested subplans
    :param target_name: Name of the plan to find
    :return: The matching plan dictionary or None if not found
    """
    for plan in plans_tree:
        display_name = plan.get('display_name', '')
        if display_name == target_name:
            return plan
    return None

def find_leaf_plans(plan_tree: Dict) -> List[Dict]:
    """
    Finds all leaf plans (plans with no subplans) in a plan tree.
    :param plan_tree: A plan tree dictionary
    :return: List of leaf plan dictionaries
    """
    leaf_plans = []
    
    def traverse_tree(plan):
        subplans = plan.get('subplans', [])
        if not subplans:
            # This is a leaf plan (no subplans)
            leaf_plans.append(plan)
        else:
            # Recursively check subplans
            for subplan in subplans:
                traverse_tree(subplan)
    
    traverse_tree(plan_tree)
    return leaf_plans

def submit_plan(plan_uuid: str, scenario_id: str) -> bool:
    """
    Submits a plan using the dedicated API method.
    :param plan_uuid: UUID of the plan to submit
    :param scenario_id: UUID of the scenario to submit
    :return: True if successful, False otherwise
    """
    print(f"Submitting plan {plan_uuid} with scenario {scenario_id}")
    
    try:
        # Build the payload using the appropriate action classes
        from visier_platform_sdk import PlanPatchSubmitActionRequest, SubmitActionPayload, PlanScenarioPatchRequest
        
        submit_payload = SubmitActionPayload(comment="by script")
        request = PlanPatchSubmitActionRequest(
            actionType="Submit",
            submitActionPayload=submit_payload
        )
        
        # Wrap in PlanScenarioPatchRequest
        patch_request = PlanScenarioPatchRequest(actual_instance=request)
        
        # Call the dedicated API method
        response = plan_admin_api.patch_plan(
            plan_id=plan_uuid,
            scenario_id=scenario_id,
            plan_scenario_patch_request=patch_request
        )
        
        print(f"Successfully submitted plan {plan_uuid}")
        return True
        
    except Exception as e:
        print(f"Failed to submit plan {plan_uuid}: {str(e)}")
        return False

def consolidate_plan(plan_uuid: str, scenario_id: str) -> bool:
    """
    Consolidates a plan using the dedicated API method.
    :param plan_uuid: UUID of the plan to consolidate
    :param scenario_id: UUID of the scenario to consolidate
    :return: True if successful, False otherwise
    """
    print(f"Consolidating plan {plan_uuid} with scenario {scenario_id}")
    
    try:
        # Build the payload using the appropriate action classes
        from visier_platform_sdk import PlanPatchConsolidateActionRequest, ConsolidateActionPayload, PlanScenarioPatchRequest
        
        consolidate_payload = ConsolidateActionPayload(autoRollup=True)
        request = PlanPatchConsolidateActionRequest(
            actionType="Consolidate",
            consolidateActionPayload=consolidate_payload
        )
        
        # Wrap in PlanScenarioPatchRequest
        patch_request = PlanScenarioPatchRequest(actual_instance=request)
        
        # Call the dedicated API method
        response = plan_admin_api.patch_plan(
            plan_id=plan_uuid,
            scenario_id=scenario_id,
            plan_scenario_patch_request=patch_request
        )
        
        print(f"Successfully consolidated plan {plan_uuid}")
        return True
        
    except Exception as e:
        print(f"Failed to consolidate plan {plan_uuid}: {str(e)}")
        return False

def close_collaboration(plan_uuid: str, scenario_id: str) -> bool:
    """
    Closes a collaboration using the dedicated API method.
    :param plan_uuid: UUID of the plan to close collaboration for
    :param scenario_id: UUID of the scenario to close collaboration for
    :return: True if successful, False otherwise
    """
    print(f"Closing collaboration for plan {plan_uuid} with scenario {scenario_id}")
    
    try:
        # Build the payload using the appropriate action classes
        from visier_platform_sdk import PlanPatchEndCollaborationActionRequest, EndCollaborationActionPayload, PlanScenarioPatchRequest
        
        end_collab_payload = EndCollaborationActionPayload(actionWhenUnconsolidatedPlansExists="Ignore")
        request = PlanPatchEndCollaborationActionRequest(
            actionType="EndCollaboration",
            endCollaborationActionPayload=end_collab_payload
        )
        
        # Wrap in PlanScenarioPatchRequest
        patch_request = PlanScenarioPatchRequest(actual_instance=request)
        
        # Call the dedicated API method
        response = plan_admin_api.patch_plan(
            plan_id=plan_uuid,
            scenario_id=scenario_id,
            plan_scenario_patch_request=patch_request
        )
        
        print(f"Successfully closed collaboration for plan {plan_uuid}")
        return True
        
    except Exception as e:
        print(f"Failed to close collaboration for plan {plan_uuid}: {str(e)}")
        return False

def start_collaboration(plan_uuid: str, scenario_id: str) -> bool:
    """
    Starts a collaboration using the dedicated API method.
    :param plan_uuid: UUID of the plan to start collaboration for
    :param scenario_id: UUID of the scenario to start collaboration for
    :return: True if successful, False otherwise
    """
    print(f"Starting collaboration for plan {plan_uuid} with scenario {scenario_id}")
    
    try:
        # Build the payload using the appropriate action classes
        from visier_platform_sdk import PlanPatchStartCollaborationActionRequest, StartCollaborationActionPayload, PlanScenarioPatchRequest
        
        # Use the cached start of today timestamp for consistency (as string)
        start_collab_payload = StartCollaborationActionPayload(startDate=str(START_OF_TODAY_MS))
        request = PlanPatchStartCollaborationActionRequest(
            actionType="StartCollaboration",
            startCollaborationActionPayload=start_collab_payload
        )
        
        # Wrap in PlanScenarioPatchRequest
        patch_request = PlanScenarioPatchRequest(actual_instance=request)
        
        # Call the dedicated API method
        response = plan_admin_api.patch_plan(
            plan_id=plan_uuid,
            scenario_id=scenario_id,
            plan_scenario_patch_request=patch_request
        )
        
        print(f"Successfully started collaboration for plan {plan_uuid} with start date: {datetime.fromtimestamp(START_OF_TODAY_MS/1000).strftime('%Y-%m-%d %H:%M:%S')}")
        return True
        
    except Exception as e:
        print(f"Failed to start collaboration for plan {plan_uuid}: {str(e)}")
        return False

def reopen_plan(plan_uuid: str, scenario_id: str) -> bool:
    """
    Reopens a plan using the dedicated API method.
    :param plan_uuid: UUID of the plan to reopen
    :param scenario_id: UUID of the scenario to reopen
    :return: True if successful, False otherwise
    """
    print(f"Reopening plan {plan_uuid} with scenario {scenario_id}")
    
    try:
        # Build the payload using the appropriate action classes
        from visier_platform_sdk import PlanPatchReopenActionRequest, ReopenActionPayload, PlanScenarioPatchRequest
        
        reopen_payload = ReopenActionPayload()
        request = PlanPatchReopenActionRequest(
            actionType="Reopen",
            reopenActionPayload=reopen_payload
        )
        
        # Wrap in PlanScenarioPatchRequest
        patch_request = PlanScenarioPatchRequest(actual_instance=request)
        
        # Call the dedicated API method
        response = plan_admin_api.patch_plan(
            plan_id=plan_uuid,
            scenario_id=scenario_id,
            plan_scenario_patch_request=patch_request
        )
        
        print(f"Successfully reopened plan {plan_uuid}")
        return True
        
    except Exception as e:
        print(f"Failed to reopen plan {plan_uuid}: {str(e)}")
        return False

def find_parent_plans(leaf_plans: List[Dict], all_plans: Dict[str, Dict]) -> List[Dict]:
    """
    Finds the unique parent plans of the given leaf plans.
    :param leaf_plans: List of leaf plan dictionaries
    :param all_plans: Dictionary of all plans indexed by UUID
    :return: List of unique parent plan dictionaries
    """
    parent_uuids = set()
    parent_plans = []
    
    for leaf_plan in leaf_plans:
        parent_uuid = leaf_plan.get('parent_plan_uuid')
        if parent_uuid and parent_uuid in all_plans and parent_uuid not in parent_uuids:
            parent_uuids.add(parent_uuid)
            parent_plans.append(all_plans[parent_uuid])
    
    return parent_plans

def build_hierarchy_right_to_left(target_plan: Dict, all_plans: Dict[str, Dict]) -> List[Dict]:
    """
    Builds a hierarchy where no node is a parent of any node to its left.
    Returns plans ordered from right (deepest) to left (shallowest).
    :param target_plan: The root plan to analyze
    :param all_plans: Dictionary of all plans indexed by UUID
    :return: List of plans ordered from deepest to shallowest
    """
    def get_distance_from_root(plan_uuid: str, root_uuid: str, visited: Optional[Set[str]] = None) -> int:
        """Calculate how many levels deep this plan is from the root."""
        if visited is None:
            visited = set()
        if plan_uuid in visited:
            return 0  # Avoid cycles
        visited.add(plan_uuid)
        
        if plan_uuid == root_uuid:
            return 0  # Root is at depth 0
        
        # Find plan by looking through all plans
        plan = all_plans.get(plan_uuid, {})
        parent_uuid = plan.get('parent_plan_uuid')
        
        if not parent_uuid:
            return 0  # This is a root plan
        
        return 1 + get_distance_from_root(parent_uuid, root_uuid, visited.copy())
    
    # Collect all plans under the target plan
    def collect_all_subplans(plan: Dict, collected: Optional[Set[str]] = None) -> List[Dict]:
        if collected is None:
            collected = set()
        
        result = []
        plan_uuid = plan.get('uuid')
        if plan_uuid and plan_uuid not in collected:
            collected.add(plan_uuid)
            result.append(plan)
            
            for subplan in plan.get('subplans', []):
                result.extend(collect_all_subplans(subplan, collected))
        
        return result
    
    all_target_plans = collect_all_subplans(target_plan)
    root_uuid = target_plan.get('uuid')
    
    if not root_uuid:
        return all_target_plans  # Return unsorted if no root UUID
    
    # Sort plans by distance from root (deepest first - right to left)
    all_target_plans.sort(key=lambda p: get_distance_from_root(p.get('uuid', ''), root_uuid), reverse=True)
    
    return all_target_plans

def get_child_plans(parent_uuid: str, all_plans: Dict[str, Dict]) -> List[Dict]:
    """
    Find all direct child plans of a parent plan.
    :param parent_uuid: UUID of the parent plan
    :param all_plans: Dictionary of all plans indexed by UUID
    :return: List of child plan dictionaries
    """
    child_plans = []
    for plan_uuid, plan in all_plans.items():
        if plan.get('parent_plan_uuid') == parent_uuid:
            child_plans.append(plan)
    return child_plans

def process_plan_right_to_left(plan: Dict, scenario_id: str) -> bool:
    """
    Process a single plan according to the right-to-left rule.
    :param plan: Plan dictionary to process
    :param scenario_id: Scenario ID for API calls
    :return: True if processing was successful
    """
    plan_uuid = plan.get('uuid')
    plan_name = plan.get('display_name', 'Unnamed Plan')
    parent_plan_uuid = plan.get('parent_plan_uuid')
    is_root_plan = not parent_plan_uuid
    
    if not plan_uuid:
        print(f"No UUID found for plan: {plan_name}")
        return False
    
    print(f"\nProcessing plan: {plan_name} ({plan_uuid})" + (" [ROOT PLAN]" if is_root_plan else ""))
    
    # Get schema to check for open collaboration
    try:
        plan_schema = get_schema(plan_uuid)
        if not plan_schema:
            print(f"Failed to retrieve schema for plan: {plan_name}")
            return False
        
        # Check if there's an open collaboration
        collaboration = find_open_or_latest_collaboration(plan_schema)
        has_open_collaboration = collaboration is not None and collaboration.status == CollaborationStatus.Open.value
        
        if has_open_collaboration:
            print(f"Plan {plan_name} has open collaboration - consolidating first")
            
            # Step 1: Consolidate
            if not consolidate_plan(plan_uuid, scenario_id):
                print(f"Failed to consolidate plan: {plan_name}")
                return False
            
            # Step 2: Close collaboration
            if not close_collaboration(plan_uuid, scenario_id):
                print(f"Failed to close collaboration for plan: {plan_name}")
                return False
            
            # Step 3: Submit (skip for root plans)
            if is_root_plan:
                print(f"Skipping submit for root plan: {plan_name} - root plans should not be submitted")
            else:
                if not submit_plan(plan_uuid, scenario_id):
                    print(f"Failed to submit plan: {plan_name}")
                    return False
        else:
            print(f"Plan {plan_name} has no open collaboration")
            
            # Submit directly (skip for root plans)
            if is_root_plan:
                print(f"Skipping submit for root plan: {plan_name} - root plans should not be submitted")
            else:
                print(f"Submitting plan directly")
                if not submit_plan(plan_uuid, scenario_id):
                    print(f"Failed to submit plan: {plan_name}")
                    return False
        
        return True
        
    except Exception as e:
        print(f"Error processing plan {plan_name}: {str(e)}")
        return False

def process_plan_left_to_right(plan: Dict, scenario_id: str, all_plans: Dict[str, Dict]) -> bool:
    """
    Process a single plan in the left-to-right phase (start collaboration and reopen children).
    :param plan: Plan dictionary to process
    :param scenario_id: Scenario ID for API calls
    :param all_plans: Dictionary of all plans
    :return: True if processing was successful
    """
    plan_uuid = plan.get('uuid')
    plan_name = plan.get('display_name', 'Unnamed Plan')
    
    if not plan_uuid:
        print(f"No UUID found for plan: {plan_name}")
        return False
    
    print(f"\nProcessing plan (left-to-right): {plan_name} ({plan_uuid})")
    
    # Find child plans first to determine if this is a leaf plan
    child_plans = get_child_plans(plan_uuid, all_plans)
    
    if not child_plans:
        print(f"Plan {plan_name} is a leaf plan (no children) - skipping collaboration start")
        return True
    
    # Step 1: Start collaboration (only for non-leaf plans)
    if not start_collaboration(plan_uuid, scenario_id):
        print(f"Failed to start collaboration for plan: {plan_name}")
        return False
    
    # Step 2: Reopen all child plans
    print(f"Found {len(child_plans)} child plans to reopen:")
    reopen_success_count = 0
    
    for child_plan in child_plans:
        child_uuid = child_plan.get('uuid')
        child_name = child_plan.get('display_name', 'Unnamed Child Plan')
        
        if child_uuid:
            print(f"  Reopening: {child_name} ({child_uuid})")
            if reopen_plan(child_uuid, scenario_id):
                reopen_success_count += 1
            else:
                print(f"  Failed to reopen: {child_name}")
    
    print(f"Reopened {reopen_success_count}/{len(child_plans)} child plans successfully.")
    
    return True

def main():
    print("Starting plans retrieval...")
    print(f"Using start of today timestamp for collaborations: {datetime.fromtimestamp(START_OF_TODAY_MS/1000).strftime('%Y-%m-%d %H:%M:%S')} ({START_OF_TODAY_MS}ms)")
    
    plans = list_plans()
    if not plans:
        print("No plans found.")
        return
    
    # Build and display the plan tree
    print("Building plan tree...")
    plans_tree, all_plans = build_plan_tree(plans)
    
    print("\nPlan Tree Structure:")
    print_plan_tree(plans_tree)
    
    # Find the target plan
    print(f"\nLooking for plan: '{TARGET_PLAN_NAME}'")
    target_plan = find_target_plan(plans_tree, TARGET_PLAN_NAME)
    
    if not target_plan:
        print(f"Plan '{TARGET_PLAN_NAME}' not found.")
        return
    
    print(f"Found target plan: {target_plan.get('display_name')} ({target_plan.get('uuid')})")
    root_plan_uuid = target_plan.get('uuid')
    
    if not root_plan_uuid:
        print("Root plan UUID not found.")
        return
    
    # Get collaboration info for the target plan
    plan_schema = get_schema(root_plan_uuid)
    if not plan_schema:
        print("Failed to retrieve plan collaboration info.")
        return
    
    # Find collaboration info
    collaboration = find_open_or_latest_collaboration(plan_schema)
    if not collaboration:
        print("No collaboration found for this plan.")
        return
        
    print("Found collaboration:")
    print(f"  Scenario ID: {collaboration.scenario_id}")
    print(f"  Status: {collaboration.status}")
    scenario_id = collaboration.scenario_id
    
    if not scenario_id:
        print("No scenario ID found in collaboration.")
        return
    
    # Build hierarchy ordered from right (deepest) to left (shallowest)
    print(f"\nBuilding right-to-left hierarchy...")
    ordered_plans = build_hierarchy_right_to_left(target_plan, all_plans)
    
    print(f"Found {len(ordered_plans)} plans to process:")
    for i, plan in enumerate(ordered_plans):
        print(f"  {i+1}. {plan.get('display_name')} ({plan.get('uuid')})")
    
    # Phase 1: Right-to-left processing (deepest to shallowest)
    print(f"\n{'='*80}")
    print("PHASE 1: RIGHT-TO-LEFT PROCESSING (DEEPEST TO SHALLOWEST)")
    print(f"{'='*80}")
    
    successful_plans = []
    for i, plan in enumerate(ordered_plans):
        print(f"\n--- Processing Plan {i+1}/{len(ordered_plans)} ---")
        if process_plan_right_to_left(plan, scenario_id):
            successful_plans.append(plan)
        else:
            print(f"Failed to process plan: {plan.get('display_name')}")
    
    print(f"\nPhase 1 complete: {len(successful_plans)}/{len(ordered_plans)} plans processed successfully.")
    
    # Phase 2: Left-to-right processing (shallowest to deepest)
    print(f"\n{'='*80}")
    print("PHASE 2: LEFT-TO-RIGHT PROCESSING (SHALLOWEST TO DEEPEST)")
    print(f"{'='*80}")
    
    # Use the original target tree order (reversed of right-to-left)
    left_to_right_plans = list(reversed(ordered_plans))
    
    print(f"Processing {len(left_to_right_plans)} plans in left-to-right order:")
    for i, plan in enumerate(left_to_right_plans):
        print(f"  {i+1}. {plan.get('display_name')} ({plan.get('uuid')})")
    
    collaboration_success_count = 0
    for i, plan in enumerate(left_to_right_plans):
        print(f"\n--- Processing Plan {i+1}/{len(left_to_right_plans)} (Left-to-Right) ---")
        if process_plan_left_to_right(plan, scenario_id, all_plans):
            collaboration_success_count += 1
        else:
            print(f"Failed to process collaboration for plan: {plan.get('display_name')}")
    
    print(f"\nPhase 2 complete: {collaboration_success_count}/{len(left_to_right_plans)} plans processed successfully.")
    
    print(f"\n{'='*80}")
    print("WORKFLOW COMPLETE!")
    print(f"{'='*80}")
    print(f"Phase 1 (Right-to-Left): {len(successful_plans)}/{len(ordered_plans)} plans processed")
    print(f"Phase 2 (Left-to-Right): {collaboration_success_count}/{len(left_to_right_plans)} plans processed")

if __name__ == "__main__":
    main()
