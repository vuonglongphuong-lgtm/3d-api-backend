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

# Đổi sang Key của Synexa
SYNEXA_API_KEY = os.getenv("SYNEXA_API_KEY")

# Endpoint của Synexa
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

# --- API 1: GỬI YÊU CẦU (CREATE PREDICTION) ---
@app.post("/generate")
async def generate_task(file: UploadFile = File(...)):
    try:
        # 1. Upload Cloudinary (Giữ nguyên)
        print("1. Uploading to Cloudinary...")
        upload_result = cloudinary.uploader.upload(file.file)
        image_url = upload_result.get("secure_url")
        
        # 2. Gọi Synexa (Hunyuan3D)
        print("2. Sending to Synexa (Hunyuan)...")
        
        # Header của Synexa dùng 'x-api-key' thay vì 'Authorization'
        headers = {
            "x-api-key": SYNEXA_API_KEY,
            "Content-Type": "application/json"
        }
        
        # Payload theo đúng mẫu curl bạn gửi
        # Tôi đã chỉnh 'shape_only': False để nó có màu (Texture)
        # Và tăng 'steps' lên 30 để đẹp hơn (5 bước thì nhanh nhưng xấu)
        payload = {
            "model": "tencent/hunyuan3d-2",
            "input": {
                "image": image_url,
                "seed": 1234,      # Có thể random nếu muốn
                "steps": 30,       # Tăng lên 30-50 cho đẹp
                "caption": "",
                "shape_only": False, # False = Có màu, True = Trắng đen
                "guidance_scale": 5.5,
                "check_box_rembg": True,
                "octree_resolution": "256"
            }
        }
        
        resp = requests.post(SYNEXA_URL, json=payload, headers=headers)
        
        # Check lỗi
        if resp.status_code != 201 and resp.status_code != 200:
            print(f"❌ Synexa Error: {resp.text}")
            return {"errorCode": "AI_REJECT", "message": resp.text}

        data = resp.json()
        
        # Synexa trả về ID ở field "id"
        task_id = data.get("id")
        
        if not task_id:
            return {"errorCode": "FAIL", "message": "No ID returned from Synexa"}
            
        print(f"   -> Task ID: {task_id}")

        # Trả về format cũ để Frontend không phải sửa code
        return {
            "status": "PENDING",
            "task_id": task_id, 
            "message": "Synexa đã nhận việc."
        }

    except Exception as e:
        return {"errorCode": "ERROR", "message": str(e)}

# --- API 2: KIỂM TRA TRẠNG THÁI (GET PREDICTION) ---
@app.post("/check-status")
async def check_status(req: StatusRequest):
    try:
        headers = {
            "x-api-key": SYNEXA_API_KEY,
            "Content-Type": "application/json"
        }
        
        # URL check status: .../predictions/{id}
        check_url = f"{SYNEXA_URL}/{req.task_id}"
        
        resp = requests.get(check_url, headers=headers)
        data = resp.json()
        
        # Synexa trả về status dạng chữ thường: "starting", "processing", "succeeded", "failed"
        raw_status = data.get("status")
        
        # MAP STATUS: Chuyển đổi trạng thái của Synexa sang chuẩn chung của App mình
        # Để Unity không bị ngáo
        final_status = "IN_PROGRESS"
        progress = 0
        
        if raw_status == "succeeded":
            final_status = "SUCCEEDED"
            progress = 100
        elif raw_status == "failed":
            final_status = "FAILED"
        elif raw_status == "processing":
            progress = 50 # Fake progress vì Synexa ko trả về % cụ thể
        
        response_data = {
            "status": final_status,
            "progress": progress,
            "task_id": req.task_id
        }

        if final_status == "SUCCEEDED":
            # Synexa trả về link GLB trong field "output"
            # Lưu ý: output có thể là string url hoặc list, ta lấy an toàn
            output = data.get("output")
            if isinstance(output, list):
                glb_url = output[0] # Nếu là list lấy phần tử đầu
            else:
                glb_url = output    # Nếu là string lấy luôn
            
            response_data["glbUrl"] = glb_url
        
        elif final_status == "FAILED":
            response_data["error"] = data.get("error", "Unknown Synexa Error")
            
        return response_data

    except Exception as e:
        return {"errorCode": "CHECK_FAIL", "message": str(e)}
