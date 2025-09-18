from typing import Dict, List, Optional, Set

import pandas as pd
import os
from dotenv import load_dotenv
from pandas import DataFrame
import json
from datetime import datetime, timezone, timedelta

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

"""
PLAN HIERARCHY TERMINOLOGY:

Root Plans:
- Top-level plans in the hierarchy that have no parent plan
- These are the main/primary plans that contain all subplans
- Identified by having parent_plan_uuid = None or empty
- Root plans should NOT be submitted during processing as they serve as containers
- Example: "Annual Budget 2024" might be a root plan

Leaf Plans:
- Bottom-level plans in the hierarchy that have no child plans (subplans)
- These are the most granular plans where actual work/data entry happens
- Identified by having an empty subplans list or no subplans
- Leaf plans are typically submitted as part of the workflow
- Example: "Q1 Sales Team Budget" might be a leaf plan under a quarterly root plan

Intermediate Plans:
- Plans that have both a parent (not root) and children (not leaf)
- These serve as organizational containers between root and leaf levels
- Example: "Q1 Budget" under "Annual Budget 2024" with team-specific subplans

Processing Order:
- Leaf-to-Root (Leaf-to-Root): Process deepest plans first, moving toward root
  Used for consolidation, submission, and closing collaborations
- Root-to-Leaf (Root-to-Leaf): Process shallowest plans first, moving toward leaves
  Used for starting collaborations and reopening plans
"""

target_plan_name = os.getenv('TARGET_PLAN_NAME')
if target_plan_name is None:
    raise ValueError("TARGET_PLAN_NAME environment variable must be defined")
TARGET_PLAN_NAME: str = target_plan_name

# Enable verbose logging for non-error information (default: False)
VERBOSE = os.getenv('VERBOSE', 'false').lower() in ('true', '1', 'yes', 'on')

config = Configuration.from_env()
api_client = ApiClient(config)
data_load_api = DataModelApi()
plan_admin_api = PlanAdministrationApi(api_client)

# Calculate start of today once to ensure consistency across all plans
def get_start_of_today_timestamp() -> int:
    """
    Get the start of today in UTC time as a Unix timestamp in milliseconds.
    If UTC now is the next day compared to local time, move it back one day,
    then set to the start of that UTC day (00:00:00 UTC).
    :return: Unix timestamp in milliseconds for start of day (00:00:00 UTC)
    """
    utc_now = datetime.now(timezone.utc)
    local_now = datetime.now()
    
    # Check if UTC date is next day compared to local date
    if utc_now.date() > local_now.date():
        # Move UTC back one day
        utc_target_date = utc_now.date() - timedelta(days=1)
    else:
        # Use current UTC date
        utc_target_date = utc_now.date()
    
    # Create start of day in UTC (00:00:00 UTC)
    start_of_day_utc = datetime.combine(utc_target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    return int(start_of_day_utc.timestamp() * 1000)

# Cache the start of today timestamp to ensure all plans use the same value
START_OF_TODAY_MS = get_start_of_today_timestamp()


def verbose_print(*args, **kwargs) -> None:
    """
    Print messages only when VERBOSE mode is enabled.
    Always prints error messages regardless of VERBOSE setting.
    :param args: Arguments to pass to print()
    :param kwargs: Keyword arguments to pass to print()
    """
    if VERBOSE:
        print(*args, **kwargs)


def log_info(*args, **kwargs) -> None:
    """
    Log informational messages (only shown in verbose mode).
    :param args: Arguments to pass to print()
    :param kwargs: Keyword arguments to pass to print()
    """
    verbose_print(*args, **kwargs)


def log_error(*args, **kwargs) -> None:
    """
    Log error messages (always shown regardless of verbose setting).
    :param args: Arguments to pass to print()
    :param kwargs: Keyword arguments to pass to print()
    """
    print(*args, **kwargs)


def check_plan_operation_response(response, plan_uuid: str, operation_name: str) -> bool:
    """
    Check the response from a plan operation for errors.
    :param response: The response from the plan operation API call
    :param plan_uuid: UUID of the plan being operated on
    :param operation_name: Name of the operation (for error messages)
    :return: True if successful or RCIP991031 error (continue processing), False for other errors
    """
    # Check response for errors in actionResults
    if hasattr(response, 'action_results') and response.action_results:
        for action_result in response.action_results:
            if hasattr(action_result, 'success') and not action_result.success:
                # Check if this is the specific "plan needs to be open" error
                if hasattr(action_result, 'error') and action_result.error:
                    error_rci = action_result.error.rci if action_result.error.rci else ''
                    error_message = action_result.error.message if action_result.error.message else 'Unknown error'
                    if error_rci == 'RCIP991031':
                        print(f"Plan {plan_uuid} is not in the expected state (plan needs to be open) - continuing operation")
                        return True
                    else:
                        print(f"Failed to {operation_name} plan {plan_uuid}: {error_message} (rci: {error_rci})")
                        return False
                else:
                    print(f"Failed to {operation_name} plan {plan_uuid}: Action result indicates failure")
                    return False
    
    # If we get here, the operation was successful
    return True


def list_plans() -> GetPlanListResponseDTO:
    """
    Retrieves all plans by paginating through all pages.
    :return: Combined response with all plans.
    """
    all_plans = []
    page = 1
    
    while True:
        log_info(f"Fetching plans page {page}...")
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
    
    log_info(f"Fetching plan schema for plan with id: {plan_uuid}")

    try:
        # Use the dedicated API method
        response = data_load_api.plan_info_with_schema(plan_uuid)
        
        log_info("Successfully retrieved plan details and schema!")
        # Log the retrieved schema in verbose mode only
        log_info(f"Retrieved plan schema: {json.dumps(response.model_dump() if hasattr(response, 'model_dump') else response, indent=2, default=str)}")

        return response
    except Exception as e:
        log_error(f"Failed to retrieve plan schema: {str(e)}")
        raise

def find_open_or_latest_collaboration(schema: PlanWithSchemaDTO) -> Optional[CollaborationInfo]:
    """
    Returns the info for the latest collaboration, which can be open or closed,
    with given plan schema.
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
    log_info(f"Submitting plan {plan_uuid} with scenario {scenario_id}")
    
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
        
        # Check response for errors
        if not check_plan_operation_response(response, plan_uuid, "submit"):
            return False
        
        log_info(f"Successfully submitted plan {plan_uuid}")
        return True
        
    except Exception as e:
        error_message = str(e)
        # Check if this is the specific "plan needs to be open" error (RCIP991031)
        if "RCIP991031" in error_message:
            log_info(f"Plan {plan_uuid} is not in the expected state (plan needs to be open) - continuing operation")
            return True  # Treat this as success to continue processing
        else:
            log_error(f"Failed to submit plan {plan_uuid}: {error_message}")
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
        
        # Check response for errors
        if not check_plan_operation_response(response, plan_uuid, "consolidate"):
            return False
        
        print(f"Successfully consolidated plan {plan_uuid}")
        return True
        
    except Exception as e:
        error_message = str(e)
        # Check if this is the specific "plan needs to be open" error (RCIP991031)
        if "RCIP991031" in error_message:
            print(f"Plan {plan_uuid} is not in the expected state (plan needs to be open) - continuing operation")
            return True  # Treat this as success to continue processing
        else:
            print(f"Failed to consolidate plan {plan_uuid}: {error_message}")
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
        
        # Check response for errors
        if not check_plan_operation_response(response, plan_uuid, "close collaboration for"):
            return False
        
        print(f"Successfully closed collaboration for plan {plan_uuid}")
        return True
        
    except Exception as e:
        error_message = str(e)
        # Check if this is the specific "plan needs to be open" error (RCIP991031)
        if "RCIP991031" in error_message:
            print(f"Plan {plan_uuid} is not in the expected state (plan needs to be open) - continuing operation")
            return True  # Treat this as success to continue processing
        else:
            print(f"Failed to close collaboration for plan {plan_uuid}: {error_message}")
            return False

def start_collaboration(plan_uuid: str, scenario_id: str) -> bool:
    """
    Starts a collaboration using the dedicated API method.
    :param plan_uuid: UUID of the plan to start collaboration for
    :param scenario_id: UUID of the scenario to start collaboration for
    :return: True if successful, False otherwise
    """
    log_info(f"Starting collaboration for plan {plan_uuid} with scenario {scenario_id}")
    
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
        
        # Check response for errors
        if not check_plan_operation_response(response, plan_uuid, "start collaboration for"):
            return False
        
        log_info(f"Successfully started collaboration for plan {plan_uuid} with start date: {datetime.fromtimestamp(START_OF_TODAY_MS/1000, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        return True
        
    except Exception as e:
        error_message = str(e)
        # Check if this is the specific "plan needs to be open" error (RCIP991031)
        if "RCIP991031" in error_message:
            log_info(f"Plan {plan_uuid} is not in the expected state (plan needs to be open) - continuing operation")
            return True  # Treat this as success to continue processing
        else:
            log_error(f"Failed to start collaboration for plan {plan_uuid}: {error_message}")
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
        
        # Check response for errors
        if not check_plan_operation_response(response, plan_uuid, "reopen"):
            return False
        
        print(f"Successfully reopened plan {plan_uuid}")
        return True
        
    except Exception as e:
        error_message = str(e)
        # Check if this is the specific "plan needs to be open" error (RCIP991031)
        if "RCIP991031" in error_message:
            print(f"Plan {plan_uuid} is not in the expected state (plan needs to be open) - continuing operation")
            return True  # Treat this as success to continue processing
        else:
            print(f"Failed to reopen plan {plan_uuid}: {error_message}")
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

def build_hierarchy_leaf_to_root(target_plan: Dict, all_plans: Dict[str, Dict]) -> List[Dict]:
    """
    Builds a hierarchy where no node is a parent of any node to its left.
    Returns plans ordered from leaf (deepest) to root (shallowest).
    :param target_plan: The root plan to analyze
    :param all_plans: Dictionary of all plans indexed by UUID
    :return: List of plans ordered from deepest to shallowest (leaf to root)
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
    
    # Sort plans by distance from root (deepest first - leaf to root)
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

def process_plan_leaf_to_root(plan: Dict, scenario_id: str) -> bool:
    """
    Process a single plan according to the leaf-to-root rule.
    
    In the plan hierarchy:
    - Root plans: Top-level plans with no parent (parent_plan_uuid is None)
    - Leaf plans: Bottom-level plans with no children/subplans
    
    This function processes plans from leaf (deepest) to root (shallowest), handling
    consolidation, submission, and closing collaborations.
    
    :param plan: Plan dictionary to process
    :param scenario_id: Scenario ID for API calls
    :return: True if processing was successful
    """
    plan_uuid = plan.get('uuid')
    plan_name = plan.get('display_name', 'Unnamed Plan')
    parent_plan_uuid = plan.get('parent_plan_uuid')
    is_root_plan = not parent_plan_uuid
    
    if not plan_uuid:
        log_error(f"No UUID found for plan: {plan_name}")
        return False
    
    log_info(f"\nProcessing plan: {plan_name} ({plan_uuid})" + (" [ROOT PLAN]" if is_root_plan else ""))
    
    # Get schema to check for open collaboration
    try:
        plan_schema = get_schema(plan_uuid)
        if not plan_schema:
            log_error(f"Failed to retrieve schema for plan: {plan_name}")
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

def process_plan_root_to_leaf(plan: Dict, scenario_id: str, all_plans: Dict[str, Dict]) -> bool:
    """
    Process a single plan in the root-to-leaf phase (start collaboration and reopen children).
    
    In the plan hierarchy:
    - Root plans: Top-level plans with no parent (parent_plan_uuid is None)
    - Leaf plans: Bottom-level plans with no children/subplans
    
    This function processes plans from root (shallowest) to leaf (deepest), starting
    collaborations for non-leaf plans and reopening their child plans.
    
    :param plan: Plan dictionary to process
    :param scenario_id: Scenario ID for API calls
    :param all_plans: Dictionary of all plans
    :return: True if processing was successful
    """
    plan_uuid = plan.get('uuid')
    plan_name = plan.get('display_name', 'Unnamed Plan')
    
    if not plan_uuid:
        log_error(f"No UUID found for plan: {plan_name}")
        return False
    
    log_info(f"\nProcessing plan (root-to-leaf): {plan_name} ({plan_uuid})")
    
    # Find child plans first to determine if this is a leaf plan
    child_plans = get_child_plans(plan_uuid, all_plans)
    
    if not child_plans:
        log_info(f"Plan {plan_name} is a leaf plan (no children) - skipping collaboration start")
        return True
    
    # Step 1: Start collaboration (only for non-leaf plans)
    if not start_collaboration(plan_uuid, scenario_id):
        log_error(f"Failed to start collaboration for plan: {plan_name}")
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
    print(f"Verbose logging: {'ENABLED' if VERBOSE else 'DISABLED'}")
    print(f"Using start of today timestamp for collaborations: {datetime.fromtimestamp(START_OF_TODAY_MS/1000, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} ({START_OF_TODAY_MS}ms)")
    
    plans = list_plans()
    if not plans:
        log_error("CRITICAL ERROR: No plans found.")
        return
    
    # Build and display the plan tree
    log_info("Building plan tree...")
    plans_tree, all_plans = build_plan_tree(plans)
    
    log_info("\nPlan Tree Structure:")
    if VERBOSE:
        print_plan_tree(plans_tree)
    
    # Find the target plan
    print(f"\nLooking for plan: '{TARGET_PLAN_NAME}'")
    target_plan = find_target_plan(plans_tree, TARGET_PLAN_NAME)
    
    if not target_plan:
        log_error(f"CRITICAL ERROR: Plan '{TARGET_PLAN_NAME}' not found.")
        return
    
    print(f"Found target plan: {target_plan.get('display_name')} ({target_plan.get('uuid')})")
    root_plan_uuid = target_plan.get('uuid')
    
    if not root_plan_uuid:
        log_error("CRITICAL ERROR: Root plan UUID not found.")
        return
    
    # Get collaboration info for the target plan
    plan_schema = get_schema(root_plan_uuid)
    if not plan_schema:
        log_error("CRITICAL ERROR: Failed to retrieve plan collaboration info.")
        return
    
    # Find collaboration info
    collaboration = find_open_or_latest_collaboration(plan_schema)
    if not collaboration:
        log_error("CRITICAL ERROR: No collaboration found for this plan.")
        return
        
    print("Found collaboration:")
    print(f"  Scenario ID: {collaboration.scenario_id}")
    print(f"  Status: {collaboration.status}")
    scenario_id = collaboration.scenario_id
    
    if not scenario_id:
        log_error("CRITICAL ERROR: No scenario ID found in collaboration.")
        return
    
    # Build hierarchy ordered from leaf (deepest) to root (shallowest)
    log_info(f"\nBuilding leaf-to-root hierarchy...")
    ordered_plans = build_hierarchy_leaf_to_root(target_plan, all_plans)
    
    print(f"Found {len(ordered_plans)} plans to process:")
    if VERBOSE:
        for i, plan in enumerate(ordered_plans):
            print(f"  {i+1}. {plan.get('display_name')} ({plan.get('uuid')})")
    
    # Phase 1: Leaf-to-root processing (deepest to shallowest)
    print(f"\n{'='*80}")
    print("PHASE 1: LEAF-TO-ROOT PROCESSING (DEEPEST TO SHALLOWEST)")
    print(f"{'='*80}")
    
    successful_plans = []
    for i, plan in enumerate(ordered_plans):
        log_info(f"\n--- Processing Plan {i+1}/{len(ordered_plans)} ---")
        if process_plan_leaf_to_root(plan, scenario_id):
            successful_plans.append(plan)
        else:
            log_error(f"CRITICAL ERROR: Failed to process plan: {plan.get('display_name')}")
            log_error("Operation terminated due to error.")
            return
    
    print(f"\nPhase 1 complete: {len(successful_plans)}/{len(ordered_plans)} plans processed successfully.")
    
    # Phase 2: Root-to-leaf processing (shallowest to deepest)
    print(f"\n{'='*80}")
    print("PHASE 2: ROOT-TO-LEAF PROCESSING (SHALLOWEST TO DEEPEST)")
    print(f"{'='*80}")
    
    # Use the original target tree order (reversed of leaf-to-root)
    left_to_right_plans = list(reversed(ordered_plans))
    
    print(f"Processing {len(left_to_right_plans)} plans in root-to-leaf order:")
    for i, plan in enumerate(left_to_right_plans):
        print(f"  {i+1}. {plan.get('display_name')} ({plan.get('uuid')})")
    
    collaboration_success_count = 0
    for i, plan in enumerate(left_to_right_plans):
        print(f"\n--- Processing Plan {i+1}/{len(left_to_right_plans)} (Root-to-Leaf) ---")
        if process_plan_root_to_leaf(plan, scenario_id, all_plans):
            collaboration_success_count += 1
        else:
            print(f"CRITICAL ERROR: Failed to process collaboration for plan: {plan.get('display_name')}")
            print("Operation terminated due to error.")
            return
    
    print(f"\nPhase 2 complete: {collaboration_success_count}/{len(left_to_right_plans)} plans processed successfully.")
    
    print(f"\n{'='*80}")
    print("WORKFLOW COMPLETE!")
    print(f"{'='*80}")
    print(f"Phase 1 (Leaf-to-Root): {len(successful_plans)}/{len(ordered_plans)} plans processed")
    print(f"Phase 2 (Root-to-Leaf): {collaboration_success_count}/{len(left_to_right_plans)} plans processed")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nCRITICAL ERROR: Unexpected error occurred: {str(e)}")
        print("Operation terminated due to unexpected error.")
        import traceback
        traceback.print_exc()
        exit(1)
