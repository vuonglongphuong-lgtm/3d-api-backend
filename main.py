import os
import time
import requests
import cloudinary
import cloudinary.uploader
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# --- CẤU HÌNH ---

# 1. Cloudinary (Vẫn bắt buộc để lưu ảnh trung gian) 
cloudinary.config( 
  cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"), 
  api_key = os.getenv("CLOUDINARY_API_KEY"), 
  api_secret = os.getenv("CLOUDINARY_API_SECRET") 
)

# 2. AI Key (Lấy từ Environment Render) 
AI_API_KEY = os.getenv("AI_API_KEY") 

# Endpoint Meshy v2 (Bản ổn định nhất hiện tại) 
AI_API_URL = "https://api.meshy.ai/v2/image-to-3d"

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
        print("1. [PRO] Đang upload ảnh HD lên Cloudinary...")
        upload_result = cloudinary.uploader.upload(file.file)
        image_public_url = upload_result.get("secure_url")
        print(f"   -> Link ảnh: {image_public_url}")
    except Exception as e:
        return {"errorCode": "UPLOAD_FAIL", "message": str(e)}

    # --- BƯỚC 2: GỬI YÊU CẦU MAX SETTING ---
    print("2. [PRO] Đang gọi AI tạo model chất lượng cao...")
    
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Cấu hình tham số "Xịn" nhất 
    payload = {
        "image_url": image_public_url,
        "enable_pbr": True,      # QUAN TRỌNG: Tạo chất liệu PBR (kim loại, gỗ, da...)
        # "surface_mode": "hard", # Bật cái này nếu vật thể là đồ cứng (xe, bàn ghế). Nếu là nhân vật thì bỏ qua.
    }

    try:
        # Gửi request tạo
        response = requests.post(AI_API_URL, json=payload, headers=headers)
        
        if response.status_code != 202 and response.status_code != 200:
            print(f"❌ Lỗi AI: {response.text}")
            return {"errorCode": "AI_REJECT", "message": response.text}
        
        data = response.json()
        task_id = data.get("result") # Lấy mã vé đợi
        
        if not task_id:
             return {"errorCode": "NO_TASK_ID", "message": "AI không trả về ID"}
        
        print(f"   -> Task ID: {task_id}. Đang chờ vẽ (sẽ mất khoảng 1-2 phút)...")

    except Exception as e:
        return {"errorCode": "AI_CONN_ERR", "message": str(e)}

    # --- BƯỚC 3: VÒNG LẶP CHỜ (POLLING) ---
    # Chế độ Pro vẽ lâu hơn, nên kiên nhẫn chờ 
    
    max_retries = 40     # Thử 40 lần
    sleep_interval = 3   # Mỗi lần nghỉ 3 giây
    # Tổng thời gian chờ tối đa = 120 giây (2 phút)
    
    for i in range(max_retries):
        time.sleep(sleep_interval) 
        
        try:
            # Hỏi trạng thái
            check_url = f"{AI_API_URL}/{task_id}" 
            check_response = requests.get(check_url, headers=headers)
            check_data = check_response.json()
            
            status = check_data.get("status") # SUCCEEDED / IN_PROGRESS
            
            # In log ra màn hình Render để bạn theo dõi
            progress = check_data.get("progress", 0)
            print(f"   -> [Lần {i+1}/{max_retries}] Tiến độ: {progress}% - {status}")

            if status == "SUCCEEDED":
                model_urls = check_data.get("model_urls", {})
                glb_url = model_urls.get("glb") 
                
                print(f"✅ DONE! Link hàng xịn: {glb_url}")
                
                # Trả về đúng format cho Frontend 
                return {"glbUrl": glb_url}
            
            elif status == "FAILED":
                 err_msg = check_data.get("task_error", {}).get("message", "Unknown Error")
                 return {"errorCode": "AI_FAILED", "message": err_msg}

        except Exception as e:
            print(f"Lỗi check status: {e}")
            continue

    # Nếu chờ quá 2 phút
    return {"errorCode": "TIMEOUT", "message": "AI vẽ quá kỹ nên lâu quá, thử lại sau!"}
