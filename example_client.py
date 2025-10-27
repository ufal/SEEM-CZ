#!/usr/bin/env python3
"""
Example client for the Assessment Backend

This script demonstrates how to use the assessment backend API
to run inter-annotator agreement calculations with progress monitoring.
"""

import requests
import time
import json
import sys
from typing import Optional, Dict, Any, List


class AssessmentClient:
    """Client for interacting with the assessment backend"""
    
    def __init__(self, base_url: str = "http://localhost:5001"):
        self.base_url = base_url
    
    def start_assessment(self, files: List[str], **kwargs) -> str:
        """
        Start a new assessment task.
        
        Args:
            files: List of annotation file paths
            **kwargs: Additional parameters (features, weighted, def_file, etc.)
        
        Returns:
            task_id: UUID of the created task
        """
        url = f"{self.base_url}/api/assess/start"
        data = {"files": files, **kwargs}
        
        response = requests.post(url, json=data)
        response.raise_for_status()
        
        result = response.json()
        return result["task_id"]
    
    def poll_progress(self, task_id: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Poll for progress update (long polling).
        
        Args:
            task_id: UUID of the task
            timeout: Seconds to wait for an update (1-60)
        
        Returns:
            Progress update dictionary
        """
        url = f"{self.base_url}/api/assess/progress/{task_id}"
        params = {"timeout": timeout}
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        return response.json()
    
    def get_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get current status without waiting.
        
        Args:
            task_id: UUID of the task
        
        Returns:
            Status dictionary
        """
        url = f"{self.base_url}/api/assess/status/{task_id}"
        
        response = requests.get(url)
        response.raise_for_status()
        
        return response.json()
    
    def get_result(self, task_id: str) -> Dict[str, Any]:
        """
        Get final results of a completed task.
        
        Args:
            task_id: UUID of the task
        
        Returns:
            Result dictionary
        """
        url = f"{self.base_url}/api/assess/result/{task_id}"
        
        response = requests.get(url)
        response.raise_for_status()
        
        return response.json()
    
    def run_assessment_with_progress(self, files: List[str], **kwargs) -> Dict[str, Any]:
        """
        Run an assessment and monitor progress until completion.
        
        Args:
            files: List of annotation file paths
            **kwargs: Additional parameters
        
        Returns:
            Final result dictionary
        """
        # Start the assessment
        print(f"Starting assessment for {len(files)} files...")
        task_id = self.start_assessment(files, **kwargs)
        print(f"Task started with ID: {task_id}")
        
        # Poll for progress until complete
        while True:
            progress = self.poll_progress(task_id, timeout=30)
            
            # Display progress
            percent = int(progress["progress"] * 100)
            status = progress["status"]
            message = progress["message"]
            
            print(f"[{status.upper()}] {percent}% - {message}")
            
            # Check if complete
            if status == "completed":
                print("\n✓ Assessment completed successfully!")
                return progress["result"]
            elif status == "failed":
                error = progress.get("error", "Unknown error")
                print(f"\n✗ Assessment failed: {error}")
                raise Exception(error)
            
            # Note: Long polling already waits, no need for additional sleep


def main():
    """Example usage"""
    
    # Create client
    client = AssessmentClient("http://localhost:5001")
    
    # Example 1: Run with simulation (when files don't exist)
    print("=" * 60)
    print("Example 1: Simulation Mode")
    print("=" * 60)
    
    try:
        result = client.run_assessment_with_progress(
            files=["demo_file1.xml", "demo_file2.xml"],
            weighted=True
        )
        
        print("\nResults:")
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(f"Error: {e}")
    
    # Example 2: Run with actual files (if they exist)
    # Uncomment and modify paths as needed
    # print("\n" + "=" * 60)
    # print("Example 2: Actual Files")
    # print("=" * 60)
    # 
    # try:
    #     result = client.run_assessment_with_progress(
    #         files=[
    #             "teitok/markers/duplicate_annot/markers_VP-cs-urcite.xml",
    #             "teitok/markers/duplicate_annot/markers_IS-cs-urcite.xml"
    #         ],
    #         features=["use", "certainty", "scope"],
    #         weighted=True,
    #         def_file="teitok/config/markers_def.xml"
    #     )
    #     
    #     print("\nResults:")
    #     print(json.dumps(result, indent=2))
    #     
    # except Exception as e:
    #     print(f"Error: {e}")


if __name__ == "__main__":
    # Check if server is running
    try:
        response = requests.get("http://localhost:5001/")
        if response.status_code == 200:
            print("✓ Server is running\n")
            main()
        else:
            print("✗ Server returned unexpected status code")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("✗ Could not connect to server at http://localhost:5001")
        print("Please start the server first:")
        print("  python3 assessment_backend.py --host 0.0.0.0 --port 5001")
        sys.exit(1)
