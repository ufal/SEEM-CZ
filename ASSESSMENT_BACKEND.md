# Assessment Backend - Long Polling Implementation

This backend server provides a REST API for running inter-annotator agreement assessments with progress updates using **long polling** instead of WebSockets.

## Overview

The server integrates with the `inter_annotator_agreement.py` script to perform actual assessments, or falls back to simulation mode when dependencies are not available. Clients can:

1. Start assessment tasks asynchronously
2. Monitor progress via long polling (regularly polling for updates)
3. Retrieve final results when complete

## Why Long Polling?

Long polling is simpler and more compatible than WebSockets:
- Works through standard HTTP/HTTPS
- No special server configuration needed
- Better compatibility with proxies and load balancers
- Easier to debug and monitor

## Installation

Install the required dependencies:

```bash
# Backend dependencies
pip install -r requirements-backend.txt

# For full IAA functionality, also install:
pip install numpy statsmodels scikit-learn krippendorff jinja2
```

## Running the Server

Start the server:

```bash
python3 assessment_backend.py --host 0.0.0.0 --port 5001
```

Options:
- `--host HOST`: Host to bind to (default: 127.0.0.1)
- `--port PORT`: Port to bind to (default: 5000)
- `--debug`: Enable debug mode

## Modes of Operation

### 1. Full Mode (with dependencies)

When all dependencies are installed and valid annotation files are provided, the backend runs the actual `inter_annotator_agreement.py` calculations with real progress updates.

### 2. Simulation Mode (fallback)

When dependencies are missing or files don't exist, the backend runs in simulation mode with mock data and simulated progress updates. This is useful for testing the API without needing actual data.

## API Endpoints

### 1. Start Assessment

**POST** `/api/assess/start`

Start a new assessment task.

Request body:
```json
{
  "files": ["file1.xml", "file2.xml"],
  "features": ["use", "certainty"],  // Optional
  "weighted": true,                   // Optional, default: false
  "def_file": "path/to/def.xml",     // Optional, default: "teitok/config/markers_def.xml"
  "merge_epistemic": false,           // Optional, default: false
  "split_by_use": false,              // Optional, default: false
  "only_epistemic": false             // Optional, default: false
}
```

Parameters:
- `files`: Array of paths to annotation XML files (minimum 2 required)
- `features`: Array of feature names to analyze (optional, uses defaults if not specified)
- `weighted`: Use weighted agreement calculation (optional)
- `def_file`: Path to markers definition file (optional)
- `merge_epistemic`: Merge epistemic categories (optional)
- `split_by_use`: Split analysis by "use" attribute (optional)
- `only_epistemic`: Only analyze epistemic category (optional)

Response (202 Accepted):
```json
{
  "task_id": "uuid-string",
  "message": "Assessment task started",
  "status": "pending"
}
```

### 2. Poll for Progress (Long Polling)

**GET** `/api/assess/progress/<task_id>?timeout=30`

Long polling endpoint that waits for progress updates. The request will:
- Return immediately if there's a new update
- Wait up to `timeout` seconds for an update (default: 30s)
- Return current status if timeout is reached

Query parameters:
- `timeout`: Seconds to wait for updates (1-60, default: 30)

Response:
```json
{
  "task_id": "uuid-string",
  "status": "running",
  "progress": 0.5,
  "message": "Computing Cohen's Kappa...",
  "timestamp": "2025-10-27T15:18:37.177115",
  "result": null,
  "error": null
}
```

Status values:
- `pending`: Task is queued
- `running`: Task is in progress
- `completed`: Task finished successfully
- `failed`: Task encountered an error

### 3. Get Status (Quick Check)

**GET** `/api/assess/status/<task_id>`

Get current status without waiting (no long polling).

Response: Same as progress endpoint, but returns immediately.

### 4. Get Results

**GET** `/api/assess/result/<task_id>`

Get the final results of a completed task.

Response (200 OK):
```json
{
  "status": "completed",
  "timestamp": "2025-10-27T15:18:44.177946",
  "result": {
    "summary": "Assessment completed successfully",
    "metrics": {
      "cohens_kappa": 0.75,
      "krippendorffs_alpha": 0.72,
      "agreement_percentage": 85.5
    },
    "files": ["file1.xml", "file2.xml"],
    "timestamp": "2025-10-27T15:18:44.177919"
  }
}
```

## Usage Example

### Using the Example Client

We provide a ready-to-use Python client in `example_client.py`:

```bash
# Make sure the server is running first
python3 assessment_backend.py --host 0.0.0.0 --port 5001

# In another terminal, run the example client
python3 example_client.py
```

The example client demonstrates:
- Starting an assessment task
- Polling for progress updates
- Displaying progress to the user
- Retrieving final results

### Using curl

```bash
# Start an assessment
TASK_ID=$(curl -X POST http://localhost:5001/api/assess/start \
  -H "Content-Type: application/json" \
  -d '{"files": ["file1.xml", "file2.xml"], "weighted": true}' \
  | jq -r '.task_id')

# Poll for progress (repeats automatically via long polling)
while true; do
  STATUS=$(curl "http://localhost:5001/api/assess/progress/${TASK_ID}?timeout=30" | jq -r '.status')
  echo "Status: ${STATUS}"
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    break
  fi
done

# Get final results
curl "http://localhost:5001/api/assess/result/${TASK_ID}" | jq
```

### Using JavaScript

```javascript
async function runAssessment() {
  // Start assessment
  const startResponse = await fetch('/api/assess/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      files: ['file1.xml', 'file2.xml'],
      weighted: true
    })
  });
  
  const { task_id } = await startResponse.json();
  console.log('Task started:', task_id);
  
  // Poll for progress
  let completed = false;
  while (!completed) {
    const progressResponse = await fetch(
      `/api/assess/progress/${task_id}?timeout=30`
    );
    const progress = await progressResponse.json();
    
    console.log(`${Math.round(progress.progress * 100)}% - ${progress.message}`);
    
    if (progress.status === 'completed') {
      console.log('Results:', progress.result);
      completed = true;
    } else if (progress.status === 'failed') {
      console.error('Error:', progress.error);
      completed = true;
    }
  }
}
```

## Test Frontend

The server includes a built-in test frontend. Access it at:

```
http://localhost:5001/
```

This provides a web interface to test the long polling functionality.

## Architecture

### Long Polling Flow

1. Client starts an assessment task via POST to `/api/assess/start`
2. Server creates a task and starts processing in a background thread
3. Client polls `/api/assess/progress/<task_id>` with a timeout
4. Server either:
   - Returns immediately if there's a new update
   - Waits up to `timeout` seconds for an update
   - Returns current status if timeout expires
5. Client receives the update and immediately sends another poll request
6. This continues until the task is completed or failed
7. Client can then fetch the final result from `/api/assess/result/<task_id>`

### Advantages over WebSocket

- **Simpler setup**: No WebSocket configuration needed
- **Better compatibility**: Works through all HTTP proxies and firewalls
- **Easier debugging**: Standard HTTP requests visible in network tools
- **Stateless**: Each request is independent
- **Reliable**: Automatic reconnection through standard HTTP retry logic

### Progress Updates

The backend regularly updates progress during assessment:
- Loading files: 10%
- Calculating agreement: 30%
- Computing Cohen's Kappa: 50%
- Computing Krippendorff's Alpha: 70%
- Finalizing: 90%
- Completed: 100%

## Production Deployment

For production use, deploy with a production WSGI server:

```bash
# Using gunicorn
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5001 assessment_backend:app

# Or using waitress
pip install waitress
waitress-serve --host=0.0.0.0 --port=5001 assessment_backend:app
```

## Error Handling

The API uses standard HTTP status codes:
- `200 OK`: Success
- `202 Accepted`: Task accepted and started
- `400 Bad Request`: Invalid request
- `404 Not Found`: Task not found
- `500 Internal Server Error`: Server error

All error responses include an error message:
```json
{
  "error": "Detailed error message"
}
```
