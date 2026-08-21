import json
import time
import uuid
import logging
import io
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Folder name on Google Drive to store flow tasks and media
FLOW_DRIVE_FOLDER_NAME = "REVENUE_AI_FLOW_QUEUE"

def _get_drive_service():
    try:
        import sys
        sys.path.append(r"D:\ai-revenue")
        import google_drive
        return google_drive._build_service()
    except Exception as e:
        logger.warning(f"Could not build Google Drive service: {e}")
        return None

def _get_or_create_flow_folder(service) -> Optional[str]:
    """Find or create REVENUE_AI_FLOW_QUEUE folder on Google Drive."""
    try:
        # Search for existing folder
        q = f"name = '{FLOW_DRIVE_FOLDER_NAME}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        res = service.files().list(q=q, fields="files(id, name)").execute()
        files = res.get("files", [])
        if files:
            return files[0]["id"]
        
        # Create folder if not found
        meta = {
            "name": FLOW_DRIVE_FOLDER_NAME,
            "mimeType": "application/vnd.google-apps.folder"
        }
        folder = service.files().create(body=meta, fields="id").execute()
        return folder["id"]
    except Exception as e:
        logger.error(f"Error getting flow folder: {e}")
        return None

def submit_request(prompt: str, media_type: str = "image") -> str:
    """Submit a request to Google Drive flow queue."""
    task_id = str(uuid.uuid4())
    task_data = {
        "id": task_id,
        "prompt": prompt,
        "media_type": media_type,
        "status": "PENDING",
        "created_at": time.time(),
        "result_path": None,
        "drive_file_id": None,
        "error_message": None
    }
    
    # Save to local queue directory as fallback
    local_dir = Path(r"D:\ai-revenue\data\flow_queue")
    local_dir.mkdir(parents=True, exist_ok=True)
    local_file = local_dir / f"{task_id}.json"
    local_file.write_text(json.dumps(task_data, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # Upload to Google Drive
    service = _get_drive_service()
    if service:
        try:
            folder_id = _get_or_create_flow_folder(service)
            if folder_id:
                from googleapiclient.http import MediaIoBaseUpload
                meta = {
                    "name": f"task_{task_id}.json",
                    "parents": [folder_id]
                }
                raw_bytes = json.dumps(task_data, ensure_ascii=False, indent=2).encode("utf-8")
                media = MediaIoBaseUpload(io.BytesIO(raw_bytes), mimetype="application/json", resumable=False)
                service.files().create(body=meta, media_body=media, fields="id").execute()
                logger.info(f"✓ Submitted task {task_id} to Google Drive")
        except Exception as e:
            logger.error(f"Failed to submit task to Google Drive: {e}")
            
    return task_id

def get_request_status(task_id: str) -> Optional[Dict[str, Any]]:
    """Check task status from Google Drive (or local fallback)."""
    # 1. Try Google Drive
    service = _get_drive_service()
    if service:
        try:
            folder_id = _get_or_create_flow_folder(service)
            if folder_id:
                q = f"name = 'task_{task_id}.json' and '{folder_id}' in parents and trashed = false"
                res = service.files().list(q=q, fields="files(id, name)").execute()
                files = res.get("files", [])
                if files:
                    file_id = files[0]["id"]
                    content = service.files().get_media(fileId=file_id).execute()
                    data = json.loads(content.decode("utf-8"))
                    
                    # If status is DONE and has drive_file_id, download media bytes
                    if data.get("status") == "DONE" and data.get("drive_file_id") and not data.get("media_bytes"):
                        try:
                            media_content = service.files().get_media(fileId=data["drive_file_id"]).execute()
                            data["media_bytes"] = media_content
                        except Exception as e:
                            logger.error(f"Failed to download media bytes: {e}")
                    return data
        except Exception as e:
            logger.warning(f"Drive status check failed: {e}")
            
    # 2. Local fallback
    local_file = Path(r"D:\ai-revenue\data\flow_queue") / f"{task_id}.json"
    if local_file.exists():
        try:
            return json.loads(local_file.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None

def get_pending_request(worker_id: str = "default_worker") -> Optional[Dict[str, Any]]:
    """Worker function: Check Google Drive (and local) for PENDING tasks with distributed claim lock."""
    # 1. Check Google Drive
    service = _get_drive_service()
    if service:
        try:
            folder_id = _get_or_create_flow_folder(service)
            if folder_id:
                q = f"name contains 'task_' and name contains '.json' and '{folder_id}' in parents and trashed = false"
                res = service.files().list(q=q, fields="files(id, name, createdTime)", orderBy="createdTime").execute()
                files = res.get("files", [])
                for f in files:
                    try:
                        content = service.files().get_media(fileId=f["id"]).execute()
                        data = json.loads(content.decode("utf-8"))
                        if data.get("status") == "PENDING":
                            # Try to claim this task atomically
                            data["status"] = "PROCESSING"
                            data["claimed_by"] = worker_id
                            
                            from googleapiclient.http import MediaIoBaseUpload
                            new_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
                            media_update = MediaIoBaseUpload(io.BytesIO(new_bytes), mimetype="application/json", resumable=False)
                            service.files().update(fileId=f["id"], media_body=media_update).execute()
                            
                            # Read back to verify claim
                            verify_content = service.files().get_media(fileId=f["id"]).execute()
                            verify_data = json.loads(verify_content.decode("utf-8"))
                            if verify_data.get("claimed_by") == worker_id:
                                verify_data["_drive_file_id"] = f["id"]
                                return verify_data
                    except Exception:
                        continue
        except Exception as e:
            logger.warning(f"Error checking pending tasks on Drive: {e}")
            
    # 2. Local fallback
    local_dir = Path(r"D:\ai-revenue\data\flow_queue")
    if local_dir.exists():
        for f in sorted(local_dir.glob("*.json"), key=lambda p: p.stat().st_mtime):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("status") == "PENDING":
                    return data
            except Exception:
                continue
    return None

def update_request(task_id: str, updates: Dict[str, Any], result_file_path: Optional[str] = None):
    """Worker function: Update task status and upload resulting media to Google Drive."""
    # 1. Update local file
    local_file = Path(r"D:\ai-revenue\data\flow_queue") / f"{task_id}.json"
    if local_file.exists():
        try:
            data = json.loads(local_file.read_text(encoding="utf-8"))
            data.update(updates)
            local_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # 2. Upload resulting media and update JSON on Google Drive
    service = _get_drive_service()
    if service:
        try:
            folder_id = _get_or_create_flow_folder(service)
            if folder_id:
                from googleapiclient.http import MediaIoBaseUpload, MediaFileUpload
                
                # Upload generated video or image to Google Drive
                drive_media_id = None
                if result_file_path and Path(result_file_path).exists():
                    p = Path(result_file_path)
                    mime = "video/mp4" if p.suffix == ".mp4" else "image/png"
                    media_meta = {
                        "name": f"flow_result_{task_id}{p.suffix}",
                        "parents": [folder_id]
                    }
                    media_body = MediaFileUpload(str(p), mimetype=mime, resumable=True)
                    uploaded_media = service.files().create(body=media_meta, media_body=media_body, fields="id").execute()
                    drive_media_id = uploaded_media.get("id")
                    updates["drive_file_id"] = drive_media_id
                    logger.info(f"✓ Uploaded result {p.name} to Google Drive (ID: {drive_media_id})")

                # Update the task JSON file on Google Drive
                q = f"name = 'task_{task_id}.json' and '{folder_id}' in parents and trashed = false"
                res = service.files().list(q=q, fields="files(id, name)").execute()
                files = res.get("files", [])
                
                # Read current data
                task_data = {}
                task_file_id = None
                if files:
                    task_file_id = files[0]["id"]
                    content = service.files().get_media(fileId=task_file_id).execute()
                    task_data = json.loads(content.decode("utf-8"))
                
                task_data.update(updates)
                new_bytes = json.dumps(task_data, ensure_ascii=False, indent=2).encode("utf-8")
                media_update = MediaIoBaseUpload(io.BytesIO(new_bytes), mimetype="application/json", resumable=False)
                
                if task_file_id:
                    service.files().update(fileId=task_file_id, media_body=media_update).execute()
                else:
                    meta = {"name": f"task_{task_id}.json", "parents": [folder_id]}
                    service.files().create(body=meta, media_body=media_update, fields="id").execute()
                logger.info(f"✓ Updated task_{task_id}.json on Google Drive to {updates.get('status')}")
        except Exception as e:
            logger.error(f"Failed to update task on Google Drive: {e}")
