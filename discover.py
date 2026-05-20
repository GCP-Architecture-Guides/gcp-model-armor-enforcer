#!/usr/bin/env python3
"""
discover.py

Recursively discovers GCP projects under a Folder, audits them for Vertex AI API activation,
and outputs targeting lists for Terraform Model Armor deployments.
"""

import argparse
import csv
import json
import os
import random
import sys
import time
from google.cloud import resourcemanager_v3
from google.cloud import service_usage_v1
from google.api_core.exceptions import GoogleAPICallError, PermissionDenied

VERTEX_AI_API = "aiplatform.googleapis.com"

def load_config_defaults():
    defaults = {
        "force_model_armor": False
    }
    config_path = "discover_config.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                if "force_model_armor" in config:
                    defaults["force_model_armor"] = bool(config["force_model_armor"])
        except Exception as e:
            print(f"Warning: Failed to parse config file {config_path}: {e}", file=sys.stderr)
    return defaults

def parse_arguments(defaults):
    parser = argparse.ArgumentParser(
        description="Discover and audit projects under a GCP Folder or Organization hierarchy for Model Armor deployment."
    )
    parser.add_argument(
        "parent_id",
        type=str,
        help="The GCP Folder or Organization ID to start traversal (e.g., 'folders/123456' or 'organizations/789012')"
    )
    parser.add_argument(
        "--force-model-armor",
        action="store_true",
        default=defaults["force_model_armor"],
        help="Target projects even if Vertex AI is disabled (default loaded from discover_config.json)"
    )
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Only generate a CSV audit report without creating terraform.tfvars.json"
    )
    return parser.parse_args()

def format_parent_name(parent_id):
    if parent_id.startswith("folders/") or parent_id.startswith("organizations/"):
        return parent_id
    # Default to folder format if prefix is missing
    return f"folders/{parent_id}"

def get_all_folders(parent_name, folders_client, folder_list=None):
    """
    Recursively list all subfolders under parent_name.
    """
    if folder_list is None:
        folder_list = []

    try:
        print(f"Searching for subfolders under {parent_name}...", file=sys.stderr)
        request = resourcemanager_v3.ListFoldersRequest(parent=parent_name)
        page_result = folders_client.list_folders(request=request)
        for folder in page_result:
            folder_list.append(folder.name)
            # Recurse into subfolders
            get_all_folders(folder.name, folders_client, folder_list)
    except PermissionDenied as e:
        print(f"Permission denied listing folders under {parent_name}: {e.message}", file=sys.stderr)
    except GoogleAPICallError as e:
        print(f"API Error listing folders under {parent_name}: {e.message}", file=sys.stderr)
        
    return folder_list

def get_projects_in_folder(folder_name, projects_client):
    """
    List all active projects under folder_name.
    """
    projects = []
    try:
        print(f"Searching for projects directly under {folder_name}...", file=sys.stderr)
        query = f"parent:{folder_name}"
        request = resourcemanager_v3.SearchProjectsRequest(query=query)
        page_result = projects_client.search_projects(request=request)
        for project in page_result:
            if project.state == resourcemanager_v3.Project.State.ACTIVE:
                projects.append(project)
    except PermissionDenied as e:
        print(f"Permission denied listing projects under {folder_name}: {e.message}", file=sys.stderr)
    except GoogleAPICallError as e:
        print(f"API Error listing projects under {folder_name}: {e.message}", file=sys.stderr)
        
    return projects

def check_vertex_ai_enabled(project_id, service_usage_client):
    """
    Checks if the Vertex AI API (aiplatform.googleapis.com) is enabled on the project.
    Implements exponential backoff with jitter to handle HTTP 429 rate limit codes.
    """
    name = f"projects/{project_id}/services/{VERTEX_AI_API}"
    max_retries = 5
    base_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            request = service_usage_v1.GetServiceRequest(name=name)
            service = service_usage_client.get_service(request=request)
            return service.state == service_usage_v1.State.ENABLED
        except PermissionDenied:
            print(f"Permission denied checking API usage for project: {project_id}", file=sys.stderr)
            return False
        except GoogleAPICallError as e:
            # Check if status is 429 (Too Many Requests) or 503 (Service Unavailable)
            # The status code is typically available in the gRPC or HTTP status code of GoogleAPICallError
            status_code = getattr(e, "code", None)
            if status_code in [429, 503] or "429" in str(e) or "503" in str(e):
                delay = (base_delay * (2 ** attempt)) + random.uniform(0, 1)
                print(f"Rate limit/service unavailable (status={status_code}) checking project {project_id}. Retrying in {delay:.2f} seconds... (Attempt {attempt + 1}/{max_retries})", file=sys.stderr)
                time.sleep(delay)
                continue
            else:
                print(f"API Error checking service status for project {project_id}: {e.message}", file=sys.stderr)
                return False
        except Exception as e:
            print(f"Unexpected error checking project {project_id}: {e}", file=sys.stderr)
            return False
            
    print(f"Failed to verify API status for {project_id} after {max_retries} retries due to rate limit restrictions.", file=sys.stderr)
    return False

def main():
    defaults = load_config_defaults()
    args = parse_arguments(defaults)
    root_parent = format_parent_name(args.parent_id)

    print(f"Starting discovery process from root: {root_parent}", file=sys.stderr)

    folders_client = resourcemanager_v3.FoldersClient()
    projects_client = resourcemanager_v3.ProjectsClient()
    service_usage_client = service_usage_v1.ServiceUsageClient()

    # 1. Recursively discover all folders (including root parent)
    all_parents = [root_parent]
    get_all_folders(root_parent, folders_client, all_parents)
    print(f"Total folder/org nodes discovered: {len(all_parents)}", file=sys.stderr)

    # 2. Discover all active projects under all discovered parents
    all_projects = []
    for parent in all_parents:
        projects = get_projects_in_folder(parent, projects_client)
        all_projects.extend(projects)
    
    print(f"Total active projects discovered: {len(all_projects)}", file=sys.stderr)

    # 3. Process projects and apply target validation rules
    target_projects = []
    audit_results = []

    for project in all_projects:
        project_id = project.project_id
        project_name = project.display_name
        
        vertex_enabled = check_vertex_ai_enabled(project_id, service_usage_client)
        
        # Decision logic matrix
        deploy_action = False
        if vertex_enabled:
            deploy_action = True
        elif args.force_model_armor:
            deploy_action = True
        
        action_str = "Deploy" if deploy_action else "Skip"
        
        print(f"Project: {project_id} | Vertex AI: {vertex_enabled} | Action: {action_str}", file=sys.stderr)
        
        if deploy_action:
            target_projects.append(project_id)
            
        audit_results.append({
            "Project ID": project_id,
            "Project Name": project_name,
            "Vertex AI Enabled": str(vertex_enabled),
            "Planned Action": action_str
        })

    # 4. Generate outputs depending on mode
    if args.audit_only:
        csv_filename = "model_armor_audit.csv"
        try:
            with open(csv_filename, mode="w", newline="", encoding="utf-8") as csv_file:
                fieldnames = ["Project ID", "Project Name", "Vertex AI Enabled", "Planned Action"]
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(audit_results)
            print(f"Audit CSV file generated successfully: {csv_filename}", file=sys.stdout)
        except IOError as e:
            print(f"Failed to write CSV audit file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        tf_vars_filename = "terraform.tfvars.json"
        tf_vars_data = {
            "target_projects": target_projects
        }
        try:
            with open(tf_vars_filename, mode="w", encoding="utf-8") as json_file:
                json.dump(tf_vars_data, json_file, indent=2)
            print(f"Terraform variables JSON file generated successfully: {tf_vars_filename}", file=sys.stdout)
        except IOError as e:
            print(f"Failed to write JSON tfvars file: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
