#!/usr/bin/env python3
"""
Assessment Backend Server

This server runs inter-annotator agreement calculations and provides
progress updates to clients using long polling instead of WebSocket.

The server provides the following endpoints:
- POST /api/assess/start - Start a new assessment task
- GET /api/assess/progress/<task_id> - Long polling endpoint for progress updates
- GET /api/assess/result/<task_id> - Get final results when complete
- GET /api/assess/status/<task_id> - Get current status without long polling
"""

import argparse
import json
import logging
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any
from queue import Queue, Empty

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes


class TaskStatus(str, Enum):
    """Status of an assessment task"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProgressUpdate:
    """Progress update for a task"""
    task_id: str
    status: TaskStatus
    progress: float  # 0.0 to 1.0
    message: str
    timestamp: str
    result: Optional[Dict] = None
    error: Optional[str] = None


class TaskManager:
    """Manages assessment tasks and their progress"""
    
    def __init__(self):
        self.tasks: Dict[str, ProgressUpdate] = {}
        self.progress_queues: Dict[str, Queue] = {}
        self.lock = threading.Lock()
    
    def create_task(self, task_id: str) -> str:
        """Create a new task and return its ID"""
        with self.lock:
            progress = ProgressUpdate(
                task_id=task_id,
                status=TaskStatus.PENDING,
                progress=0.0,
                message="Task created",
                timestamp=datetime.now().isoformat()
            )
            self.tasks[task_id] = progress
            self.progress_queues[task_id] = Queue()
            return task_id
    
    def update_progress(self, task_id: str, progress: float, message: str, status: Optional[TaskStatus] = None):
        """Update task progress"""
        with self.lock:
            if task_id not in self.tasks:
                logger.warning(f"Task {task_id} not found")
                return
            
            current = self.tasks[task_id]
            update = ProgressUpdate(
                task_id=task_id,
                status=status or current.status,
                progress=progress,
                message=message,
                timestamp=datetime.now().isoformat(),
                result=current.result,
                error=current.error
            )
            self.tasks[task_id] = update
            
            # Add to queue for long polling clients
            if task_id in self.progress_queues:
                self.progress_queues[task_id].put(update)
    
    def complete_task(self, task_id: str, result: Dict):
        """Mark task as completed with results"""
        with self.lock:
            if task_id not in self.tasks:
                logger.warning(f"Task {task_id} not found")
                return
            
            update = ProgressUpdate(
                task_id=task_id,
                status=TaskStatus.COMPLETED,
                progress=1.0,
                message="Task completed successfully",
                timestamp=datetime.now().isoformat(),
                result=result
            )
            self.tasks[task_id] = update
            
            # Notify all waiting clients
            if task_id in self.progress_queues:
                self.progress_queues[task_id].put(update)
    
    def fail_task(self, task_id: str, error: str):
        """Mark task as failed"""
        with self.lock:
            if task_id not in self.tasks:
                logger.warning(f"Task {task_id} not found")
                return
            
            update = ProgressUpdate(
                task_id=task_id,
                status=TaskStatus.FAILED,
                progress=0.0,
                message="Task failed",
                timestamp=datetime.now().isoformat(),
                error=error
            )
            self.tasks[task_id] = update
            
            # Notify all waiting clients
            if task_id in self.progress_queues:
                self.progress_queues[task_id].put(update)
    
    def get_status(self, task_id: str) -> Optional[ProgressUpdate]:
        """Get current task status"""
        with self.lock:
            return self.tasks.get(task_id)
    
    def wait_for_update(self, task_id: str, timeout: int = 30) -> Optional[ProgressUpdate]:
        """Wait for a progress update (long polling)"""
        if task_id not in self.progress_queues:
            return self.get_status(task_id)
        
        try:
            # Wait for an update in the queue
            update = self.progress_queues[task_id].get(timeout=timeout)
            return update
        except Empty:
            # Timeout - return current status
            return self.get_status(task_id)


# Global task manager
task_manager = TaskManager()


def run_assessment_task(task_id: str, files: List[str], features: Optional[List[str]], 
                        weighted: bool, def_file: str, merge_epistemic: bool = False,
                        split_by_use: bool = False, only_epistemic: bool = False):
    """
    Run the inter-annotator agreement assessment in a background thread.
    This integrates with the actual inter_annotator_agreement module.
    """
    try:
        task_manager.update_progress(task_id, 0.0, "Starting assessment...", TaskStatus.RUNNING)
        
        logger.info(f"Starting assessment task {task_id} with files: {files}")
        
        # Add scripts directory to Python path to import the IAA module
        scripts_dir = Path(__file__).parent / 'scripts'
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        
        # Import the actual assessment module
        try:
            from inter_annotator_agreement import (
                load_marker_doc, load_feature_definitions, 
                AgreementCalculator, NumpyEncoder
            )
        except ImportError as e:
            logger.error(f"Failed to import inter_annotator_agreement module: {e}")
            # Fall back to simulation mode if import fails
            return run_assessment_simulation(task_id, files, features, weighted, def_file)
        
        # Load feature definitions
        task_manager.update_progress(task_id, 0.05, "Loading feature definitions...")
        feature_definitions = {}
        def_file_path = Path(def_file)
        if def_file_path.exists():
            try:
                feature_definitions = load_feature_definitions(
                    str(def_file_path), merge_epistemic, split_by_use, only_epistemic
                )
                logger.info(f"Loaded definitions for features: {', '.join(feature_definitions.keys())}")
            except Exception as e:
                logger.warning(f"Failed to load feature definitions: {e}")
        
        # Load annotation files
        task_manager.update_progress(task_id, 0.1, "Loading annotation files...")
        marker_docs = []
        for i, filepath in enumerate(files):
            try:
                marker_doc = load_marker_doc(filepath)
                marker_docs.append(marker_doc)
                progress = 0.1 + (0.2 * (i + 1) / len(files))
                task_manager.update_progress(
                    task_id, progress, 
                    f"Loaded {i + 1}/{len(files)} files..."
                )
            except Exception as e:
                raise ValueError(f"Failed to load file {filepath}: {e}")
        
        # Create agreement calculator
        task_manager.update_progress(task_id, 0.3, "Initializing agreement calculator...")
        calculator = AgreementCalculator(marker_docs, feature_definitions)
        
        # Calculate agreement metrics
        task_manager.update_progress(task_id, 0.4, "Computing agreement metrics...")
        
        # Get results for the specified features
        if not features:
            features = ['use', 'certainty', 'commfuntype', 'scope', 'tfpos', 
                       'sentpos', 'neg', 'contrast', 'modalpersp']
        
        results = calculator.get_results_dict(features, weighted=weighted)
        
        task_manager.update_progress(task_id, 0.9, "Finalizing results...")
        
        # Format the results
        result = {
            "summary": "Assessment completed successfully",
            "annotators": results.get("annotators", []),
            "total_units": results.get("total_units", 0),
            "features": results.get("features", {}),
            "files": files,
            "timestamp": datetime.now().isoformat()
        }
        
        task_manager.complete_task(task_id, result)
        logger.info(f"Assessment task {task_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Assessment task {task_id} failed: {e}", exc_info=True)
        task_manager.fail_task(task_id, str(e))


def run_assessment_simulation(task_id: str, files: List[str], features: Optional[List[str]], 
                              weighted: bool, def_file: str):
    """
    Simulation mode when actual IAA module is not available.
    This simulates the process with progress updates.
    """
    try:
        logger.info(f"Running in simulation mode for task {task_id}")
        
        # Simulate loading files
        task_manager.update_progress(task_id, 0.1, "Loading annotation files (simulation)...")
        time.sleep(1)
        
        # Simulate processing
        task_manager.update_progress(task_id, 0.3, "Calculating agreement metrics (simulation)...")
        time.sleep(2)
        
        task_manager.update_progress(task_id, 0.5, "Computing Cohen's Kappa (simulation)...")
        time.sleep(1.5)
        
        task_manager.update_progress(task_id, 0.7, "Computing Krippendorff's Alpha (simulation)...")
        time.sleep(1.5)
        
        task_manager.update_progress(task_id, 0.9, "Finalizing results (simulation)...")
        time.sleep(1)
        
        # Simulate results
        result = {
            "summary": "Assessment completed successfully (simulation mode)",
            "metrics": {
                "cohens_kappa": 0.75,
                "krippendorffs_alpha": 0.72,
                "agreement_percentage": 85.5
            },
            "files": files,
            "timestamp": datetime.now().isoformat(),
            "note": "This is simulated data. Install dependencies and provide valid files for real results."
        }
        
        task_manager.complete_task(task_id, result)
        logger.info(f"Assessment task {task_id} completed successfully (simulation)")
        
    except Exception as e:
        logger.error(f"Assessment task {task_id} failed: {e}", exc_info=True)
        task_manager.fail_task(task_id, str(e))


@app.route('/api/assess/start', methods=['POST'])
def start_assessment():
    """Start a new assessment task"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        files = data.get('files', [])
        if not files or len(files) < 2:
            return jsonify({"error": "At least 2 files are required"}), 400
        
        features = data.get('features')
        weighted = data.get('weighted', False)
        def_file = data.get('def_file', 'teitok/config/markers_def.xml')
        merge_epistemic = data.get('merge_epistemic', False)
        split_by_use = data.get('split_by_use', False)
        only_epistemic = data.get('only_epistemic', False)
        
        # Create a new task
        task_id = str(uuid.uuid4())
        task_manager.create_task(task_id)
        
        # Start the assessment in a background thread
        thread = threading.Thread(
            target=run_assessment_task,
            args=(task_id, files, features, weighted, def_file, 
                  merge_epistemic, split_by_use, only_epistemic),
            daemon=True
        )
        thread.start()
        
        logger.info(f"Started assessment task {task_id}")
        
        return jsonify({
            "task_id": task_id,
            "message": "Assessment task started",
            "status": "pending"
        }), 202
        
    except Exception as e:
        logger.error(f"Failed to start assessment: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/api/assess/progress/<task_id>', methods=['GET'])
def get_progress(task_id: str):
    """
    Long polling endpoint for progress updates.
    Waits up to 30 seconds for a new update, or returns current status.
    """
    try:
        # Get timeout from query parameters (default 30 seconds)
        timeout = int(request.args.get('timeout', 30))
        timeout = min(max(timeout, 1), 60)  # Clamp between 1 and 60 seconds
        
        # Wait for an update or timeout
        update = task_manager.wait_for_update(task_id, timeout)
        
        if not update:
            return jsonify({"error": "Task not found"}), 404
        
        return jsonify(asdict(update))
        
    except Exception as e:
        logger.error(f"Failed to get progress for task {task_id}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/api/assess/status/<task_id>', methods=['GET'])
def get_status(task_id: str):
    """Get current task status without long polling"""
    try:
        status = task_manager.get_status(task_id)
        
        if not status:
            return jsonify({"error": "Task not found"}), 404
        
        return jsonify(asdict(status))
        
    except Exception as e:
        logger.error(f"Failed to get status for task {task_id}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/api/assess/result/<task_id>', methods=['GET'])
def get_result(task_id: str):
    """Get final results of a completed task"""
    try:
        status = task_manager.get_status(task_id)
        
        if not status:
            return jsonify({"error": "Task not found"}), 404
        
        if status.status == TaskStatus.RUNNING or status.status == TaskStatus.PENDING:
            return jsonify({"error": "Task not yet completed", "status": status.status}), 400
        
        if status.status == TaskStatus.FAILED:
            return jsonify({"error": status.error, "status": status.status}), 500
        
        return jsonify({
            "status": status.status,
            "result": status.result,
            "timestamp": status.timestamp
        })
        
    except Exception as e:
        logger.error(f"Failed to get result for task {task_id}: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/')
def index():
    """Serve the test frontend"""
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Assessment Backend - Long Polling Test</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
        h1 { color: #333; }
        .section { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
        button { padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 3px; cursor: pointer; }
        button:hover { background: #0056b3; }
        button:disabled { background: #ccc; cursor: not-allowed; }
        #progress { margin-top: 20px; }
        .progress-bar { width: 100%; height: 30px; background: #f0f0f0; border-radius: 3px; overflow: hidden; }
        .progress-fill { height: 100%; background: #28a745; transition: width 0.3s; }
        .log { background: #f8f9fa; padding: 10px; border-radius: 3px; font-family: monospace; font-size: 12px; max-height: 300px; overflow-y: auto; }
        .log-entry { margin: 5px 0; }
        .error { color: #dc3545; }
        .success { color: #28a745; }
    </style>
</head>
<body>
    <h1>Assessment Backend - Long Polling Test</h1>
    
    <div class="section">
        <h2>Start Assessment</h2>
        <p>This demo simulates running an inter-annotator agreement assessment.</p>
        <button id="startBtn" onclick="startAssessment()">Start Assessment</button>
        <button id="cancelBtn" onclick="cancelPolling()" disabled>Cancel</button>
    </div>
    
    <div class="section" id="progress" style="display:none;">
        <h2>Progress</h2>
        <div class="progress-bar">
            <div class="progress-fill" id="progressFill" style="width: 0%;"></div>
        </div>
        <p id="progressText">0% - Waiting...</p>
    </div>
    
    <div class="section">
        <h2>Log</h2>
        <div class="log" id="log"></div>
    </div>
    
    <script>
        let taskId = null;
        let polling = false;
        
        function addLog(message, className = '') {
            const log = document.getElementById('log');
            const entry = document.createElement('div');
            entry.className = 'log-entry ' + className;
            entry.textContent = new Date().toLocaleTimeString() + ' - ' + message;
            log.appendChild(entry);
            log.scrollTop = log.scrollHeight;
        }
        
        async function startAssessment() {
            try {
                document.getElementById('startBtn').disabled = true;
                document.getElementById('cancelBtn').disabled = false;
                addLog('Starting assessment...');
                
                const response = await fetch('/api/assess/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        files: ['file1.xml', 'file2.xml'],
                        weighted: true
                    })
                });
                
                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.error || 'Failed to start assessment');
                }
                
                taskId = data.task_id;
                addLog('Assessment started with task ID: ' + taskId, 'success');
                
                document.getElementById('progress').style.display = 'block';
                polling = true;
                pollProgress();
                
            } catch (error) {
                addLog('Error: ' + error.message, 'error');
                document.getElementById('startBtn').disabled = false;
                document.getElementById('cancelBtn').disabled = true;
            }
        }
        
        async function pollProgress() {
            if (!polling || !taskId) return;
            
            try {
                addLog('Polling for progress...');
                
                const response = await fetch('/api/assess/progress/' + taskId + '?timeout=30');
                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.error || 'Failed to get progress');
                }
                
                const progress = Math.round(data.progress * 100);
                document.getElementById('progressFill').style.width = progress + '%';
                document.getElementById('progressText').textContent = progress + '% - ' + data.message;
                
                addLog('Progress: ' + progress + '% - ' + data.message);
                
                if (data.status === 'completed') {
                    addLog('Assessment completed!', 'success');
                    addLog('Result: ' + JSON.stringify(data.result, null, 2));
                    polling = false;
                    document.getElementById('startBtn').disabled = false;
                    document.getElementById('cancelBtn').disabled = true;
                } else if (data.status === 'failed') {
                    addLog('Assessment failed: ' + data.error, 'error');
                    polling = false;
                    document.getElementById('startBtn').disabled = false;
                    document.getElementById('cancelBtn').disabled = true;
                } else {
                    // Continue polling
                    setTimeout(pollProgress, 100);
                }
                
            } catch (error) {
                addLog('Error polling: ' + error.message, 'error');
                polling = false;
                document.getElementById('startBtn').disabled = false;
                document.getElementById('cancelBtn').disabled = true;
            }
        }
        
        function cancelPolling() {
            polling = false;
            addLog('Polling cancelled');
            document.getElementById('startBtn').disabled = false;
            document.getElementById('cancelBtn').disabled = true;
        }
    </script>
</body>
</html>
    """


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Assessment backend server with long polling")
    parser.add_argument(
        '--host',
        type=str,
        default='127.0.0.1',
        help='Host to bind to (default: 127.0.0.1)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=5000,
        help='Port to bind to (default: 5000)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode'
    )
    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_arguments()
    
    logger.info(f"Starting assessment backend server on {args.host}:{args.port}")
    logger.info("Access the test page at http://{}:{}".format(args.host, args.port))
    
    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
        threaded=True  # Enable threading for concurrent requests
    )


if __name__ == '__main__':
    main()
