import subprocess
import json
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class PipelineRequest(BaseModel):
    industry: str
    location: str
    limit: int = 5
    queries: str = ""

@app.post("/run-pipeline")
def run_pipeline_endpoint(req: PipelineRequest):
    cmd = [
        "python", "-u", "run_pipeline.py",
        "--industry", req.industry,
        "--locations", req.location,
        "--limit", str(req.limit),
    ]
    if req.queries:
        cmd.extend(["--queries", req.queries])

    print(f"\n[STARTING PIPELINE] Industry: {req.industry} | Location: {req.location} | Limit: {req.limit}\n", flush=True)

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    last_line = "{}"
    # Stream output line by line live to VS Code terminal
    for line in iter(process.stdout.readline, ''):
        if not line:
            break
        print(line, end='', flush=True)
        if line.strip():
            last_line = line.strip()

    process.stdout.close()
    process.wait()

    try:
        data = json.loads(last_line)
    except Exception:
        data = {"status": "completed", "raw_last_line": last_line}
    return data

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)