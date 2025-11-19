import os
import time
import requests
import cloudinary
import cloudinary.uploader
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# --- CẤU HÌNH (BẮT BUỘC) ---

# 1. Cloudinary: Vẫn cần dùng để biến ảnh thành link URL
cloudinary.config( 
  cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"), 
  api_key = os.getenv("CLOUDINARY_API_KEY"), 
  api_secret = os.getenv("CLOUDINARY_API_SECRET") 
)

# 2. Meshy API Key
AI_API_KEY = os.getenv("AI_API_KEY")

# 3. Endpoint CHUẨN (Theo code bạn gửi)
# Lưu ý: Có chữ "openapi" ở giữa
AI_API_URL = "https://api.meshy.ai/openapi/v1/image-to-3d"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/generate")
async def generate_3d_model(file: UploadFile = File(...)):
    
    # --- BƯỚC 1: UPLOAD ẢNH LÊN CLOUD ---
    try:
        print("1. Uploading image to Cloudinary...")
        upload_result = cloudinary.uploader.upload(file.file)
        image_public_url = upload_result.get("secure_url")
        print(f"   -> Image URL: {image_public_url}")
    except Exception as e:
        return {"errorCode": "UPLOAD_FAIL", "message": str(e)}

    # --- BƯỚC 2: GỬI YÊU CẦU TẠO (POST) ---
    print("2. Calling Meshy API...")
    
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Payload chuẩn theo code mẫu bạn gửi
    payload = {
        "image_url": image_public_url,
        "enable_pbr": True,      # Bật vật liệu PBR
        "should_remesh": True,   # Tối ưu lưới
        "should_texture": True   # Tạo texture màu
    }

    try:
        # Gửi yêu cầu POST
        response = requests.post(AI_API_URL, json=payload, headers=headers)
        
        # Check lỗi ngay lập tức nếu API từ chối
        if response.status_code != 202 and response.status_code != 200:
            print(f"❌ API Error: {response.text}")
            return {"errorCode": "AI_REJECT", "message": response.text}
        
        data = response.json()
        
        # Meshy trả về task ID trong field "result"
        task_id = data.get("result")
        
        if not task_id:
             return {"errorCode": "NO_TASK_ID", "message": "No Task ID returned"}
        
        print(f"   -> Task ID received: {task_id}. Waiting for result...")

    except Exception as e:
        return {"errorCode": "CONNECTION_ERROR", "message": str(e)}

    # --- BƯỚC 3: CHỜ KẾT QUẢ (POLLING) ---
    # Code mẫu bạn gửi chỉ có phần gửi (POST), còn phần lấy (GET) thì phải tự code thêm vòng lặp này
    
    max_retries = 60   # Chờ tối đa 2 phút (60 lần x 2s)
    
    for i in range(max_retries):
        time.sleep(2) # Nghỉ 2 giây
        
        try:
            # Đường dẫn check status: thêm task_id vào sau URL gốc
            check_url = f"{AI_API_URL}/{task_id}"
            
            check_response = requests.get(check_url, headers=headers)
            check_data = check_response.json()
            
            status = check_data.get("status") # SUCCEEDED / IN_PROGRESS
            progress = check_data.get("progress", 0)
            
            print(f"   -> Progress: {progress}% ({status})")

            if status == "SUCCEEDED":
                # Lấy link GLB
                model_urls = check_data.get("model_urls", {})
                glb_url = model_urls.get("glb")
                
                print(f"✅ SUCCESS! GLB URL: {glb_url}")
                return {"glbUrl": glb_url}
            
            elif status == "FAILED":
                err = check_data.get("task_error", {}).get("message")
                return {"errorCode": "AI_FAILED", "message": err}

        except Exception as e:
            print(f"Polling error: {e}")
            continue

    return {"errorCode": "TIMEOUT", "message": "Task took too long"}
