import os
import requests
import cloudinary
import cloudinary.uploader
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# --- CẤU HÌNH ---
cloudinary.config( 
  cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"), 
  api_key = os.getenv("CLOUDINARY_API_KEY"), 
  api_secret = os.getenv("CLOUDINARY_API_SECRET") 
)

# Key của Synexa
SYNEXA_API_KEY = os.getenv("SYNEXA_API_KEY")

# Endpoint API (Dùng requests gọi API an toàn hơn dùng thư viện synexa.run)
SYNEXA_URL = "https://api.synexa.ai/v1/predictions"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class StatusRequest(BaseModel):
    task_id: str

# --- API 1: GỬI YÊU CẦU (Cập nhật tham số chuẩn) ---
@app.post("/generate")
async def generate_task(file: UploadFile = File(...)):
    try:
        # 1. Upload Cloudinary
        print("1. Uploading to Cloudinary...")
        upload_result = cloudinary.uploader.upload(file.file)
        image_url = upload_result.get("secure_url")
        
        # 2. Gọi Synexa (Hunyuan3D-2)
        print("2. Sending to Synexa...")
        
        headers = {
            "x-api-key": SYNEXA_API_KEY,
            "Content-Type": "application/json"
        }
        
        # --- CẬP NHẬT QUAN TRỌNG Ở ĐÂY ---
        # Tôi đã map các tham số từ code python bạn gửi vào đây
        payload = {
            "model": "tencent/hunyuan3d-2",
            "input": {
                "image": image_url,
                "seed": 1234,         # Giữ nguyên seed
                "steps": 30,          # LƯU Ý: Code bạn là 5, tôi tăng lên 30 cho đẹp (giá ko đổi)
                "caption": "",
                "shape_only": False,  # LƯU Ý: Tôi để False để có MÀU SẮC (AR cần màu). True là trắng đen.
                "guidance_scale": 5.5,
                "multiple_views": [], # Đã thêm dòng này theo code bạn gửi
                "check_box_rembg": True,
                "octree_resolution": "256"
            }
        }
        
        # Gửi đi (Mất 1 giây)
        resp = requests.post(SYNEXA_URL, json=payload, headers=headers)
        
        if resp.status_code != 201 and resp.status_code != 200:
            print(f"❌ Synexa Error: {resp.text}")
            return {"errorCode": "AI_REJECT", "message": resp.text}

        data = resp.json()
        task_id = data.get("id")
        
        if not task_id:
            return {"errorCode": "FAIL", "message": "No ID returned"}
            
        # Trả ID về ngay để né Timeout
        return {
            "status": "PENDING",
            "task_id": task_id, 
            "message": "Synexa đang xử lý, vui lòng gọi /check-status"
        }

    except Exception as e:
        return {"errorCode": "ERROR", "message": str(e)}

# --- API 2: KIỂM TRA TRẠNG THÁI (Giữ nguyên logic Async) ---
@app.post("/check-status")
async def check_status(req: StatusRequest):
    try:
        headers = {
            "x-api-key": SYNEXA_API_KEY,
            "Content-Type": "application/json"
        }
        
        check_url = f"{SYNEXA_URL}/{req.task_id}"
        
        resp = requests.get(check_url, headers=headers)
        data = resp.json()
        
        raw_status = data.get("status") # succeeded, processing, failed
        
        final_status = "IN_PROGRESS"
        progress = 0
        
        if raw_status == "succeeded":
            final_status = "SUCCEEDED"
            progress = 100
        elif raw_status == "failed":
            final_status = "FAILED"
        elif raw_status == "processing":
            progress = 50
        
        response_data = {
            "status": final_status,
            "progress": progress,
            "task_id": req.task_id
        }

        if final_status == "SUCCEEDED":
            # Lấy link GLB từ output
            output = data.get("output")
            if isinstance(output, list):
                glb_url = output[0]
            else:
                glb_url = output
            
            response_data["glbUrl"] = glb_url
        
        elif final_status == "FAILED":
            response_data["error"] = data.get("error", "Unknown Error")
            
        return response_data

    except Exception as e:
        return {"errorCode": "CHECK_FAIL", "message": str(e)}
