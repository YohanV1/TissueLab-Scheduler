from fastapi import APIRouter, File, Header, HTTPException, UploadFile

from .file_store import file_store
from .schemas import FileInfo, UploadFileResponse


router = APIRouter(prefix="/files", tags=["files"])


@router.post("/", response_model=UploadFileResponse)
async def upload_file(x_user_id: str = Header(alias="X-User-ID"), file: UploadFile = File(...)) -> UploadFileResponse:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    info = await file_store.save_upload(user_id=x_user_id, upload=file)
    return UploadFileResponse(file=info)


@router.get("/{file_id}", response_model=FileInfo)
async def get_file_info(file_id: str, x_user_id: str = Header(alias="X-User-ID")) -> FileInfo:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    info = await file_store.get_info(file_id)
    if info is None or info.user_id != x_user_id:
        raise HTTPException(status_code=404, detail="File not found")
    return info


