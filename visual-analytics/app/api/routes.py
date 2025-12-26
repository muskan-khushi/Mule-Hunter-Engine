from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import List
import asyncio

from app.core.security import verify_internal_api_key
from app.services.node_pipeline import run_node_pipeline

router = APIRouter()



# REQUEST MODELS


class NodePayload(BaseModel):
    nodeId: int
    role: str


class VisualReanalyzeRequest(BaseModel):
    trigger: str
    transactionId: str
    nodes: List[NodePayload]



# BACKGROUND RUNNER


def _run_pipeline_sync(nodes: List[NodePayload]):
    asyncio.run(run_node_pipeline(nodes))



# NODE-BASED ENTRY POINT


@router.post(
    "/visual/reanalyze/nodes",
    dependencies=[Depends(verify_internal_api_key)]
)
def reanalyze_nodes(
    request: VisualReanalyzeRequest,
    background_tasks: BackgroundTasks
):
    background_tasks.add_task(_run_pipeline_sync, request.nodes)

    return {
        "status": "started",
        "transactionId": request.transactionId,
        "nodes": [n.nodeId for n in request.nodes]
    }
