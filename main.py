import os
import requests
import cloudinary
import cloudinary.uploader
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# --- CẤU HÌNH ---
cloudinary.config( 
  cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"), 
  api_key = os.getenv("CLOUDINARY_API_KEY"), 
  api_secret = os.getenv("CLOUDINARY_API_SECRET") 
)

AI_API_KEY = os.getenv("AI_API_KEY")
AI_API_URL = "https://api.meshy.ai/openapi/v1/image-to-3d" # CHUẨN V1

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Định nghĩa body cho API check status
class StatusRequest(BaseModel):
    task_id: str

# --- API 1: GỬI YÊU CẦU (Xong ngay lập tức) ---
@app.post("/generate")
async def generate_task(file: UploadFile = File(...)):
    try:
        # 1. Upload Cloudinary
        print("1. Uploading...")
        upload_result = cloudinary.uploader.upload(file.file)
        image_url = upload_result.get("secure_url")
        
        # 2. Gọi Meshy tạo Task
        print("2. Sending to Meshy...")
        headers = {"Authorization": f"Bearer {AI_API_KEY}"}
        payload = {
            "image_url": image_url,
            "enable_pbr": True,
            "should_remesh": True,
            "should_texture": True
        }
        
        resp = requests.post(AI_API_URL, json=payload, headers=headers)
        data = resp.json()
        
        task_id = data.get("result")
        if not task_id:
            return {"errorCode": "FAIL", "message": str(data)}
            
        # TRẢ VỀ TASK ID NGAY (Không chờ vẽ)
        # Frontend sẽ dùng ID này để hỏi tiếp
        return {
            "status": "PENDING",
            "task_id": task_id, 
            "message": "Đã nhận đơn, vui lòng gọi API /check-status để xem tiến độ"
        }

    except Exception as e:
        return {"errorCode": "ERROR", "message": str(e)}

# --- API 2: KIỂM TRA TRẠNG THÁI (Frontend gọi liên tục mỗi 5s) ---
@app.post("/check-status")
async def check_status(req: StatusRequest):
    try:
        headers = {"Authorization": f"Bearer {AI_API_KEY}"}
        check_url = f"{AI_API_URL}/{req.task_id}"
        
        resp = requests.get(check_url, headers=headers)
        data = resp.json()
        
        status = data.get("status")     # SUCCEEDED, IN_PROGRESS, FAILED
        progress = data.get("progress") # 0 -> 100
        
        response_data = {
            "status": status,
            "progress": progress,
            "task_id": req.task_id
        }

        if status == "SUCCEEDED":
            response_data["glbUrl"] = data.get("model_urls", {}).get("glb")
        
        elif status == "FAILED":
            response_data["error"] = data.get("task_error", {}).get("message")
            
        return response_data

    except Exception as e:
        return {"errorCode": "CHECK_FAIL", "message": str(e)}
