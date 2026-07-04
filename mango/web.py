"""mango/web.py

HTTP primitives, re-exported under mango's own names so a consumer never
needs `import fastapi` directly. These are the exact same objects FastAPI
provides (`Router` IS `fastapi.APIRouter`, not a wrapper around it) — mango
isn't reimplementing routing, just giving it one front door so a
beginner's imports all start with `mango.` instead of juggling `fastapi.`
and `mango.` side by side.

Classes: none — this file only re-exports existing FastAPI classes/objects.

Functions: none.
"""
from fastapi import (
    Body,
    Cookie,
    File,
    Form,
    Header,
    Path,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi import APIRouter as Router
from fastapi import Depends as Depends
from fastapi import HTTPException as HTTPException
from fastapi import status
from fastapi.responses import JSONResponse, Response

__all__ = [
    "Router",
    "Depends",
    "Query",
    "Path",
    "Body",
    "Header",
    "Cookie",
    "Form",
    "File",
    "UploadFile",
    "status",
    "Request",
    "Response",
    "JSONResponse",
    "HTTPException",
    "WebSocket",
    "WebSocketDisconnect",
]
