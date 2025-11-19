from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import cloudinary
import cloudinary.uploader
import requests
import time

app = FastAPI()

# --- CẤU HÌNH (CONFIG) ---

# 1. Chế độ Test: Bật lên (True) để không mất tiền/token khi đang code giao diện
# Khi nào nộp bài thì sửa thành False
TEST_MODE = True 

# [cite_start]2. Cấu hình Cloudinary (Lấy tại cloudinary.com - BẮT BUỘC để có link ảnh public) [cite: 43, 44]
cloudinary.config( 
  cloud_name = "DIEN_TEN_CLOUD_CUA_BAN", 
  api_key = "DIEN_API_KEY", 
  api_secret = "DIEN_API_SECRET" 
)

# [cite_start]3. Cấu hình API AI (Synexa hoặc Meshy) [cite: 51, 52]
# Ví dụ cấu hình cho Synexa (hoặc thay bằng Meshy nếu Synexa hết free)
AI_API_KEY = "DIEN_KEY_CUA_BEN_AI_VAO_DAY"
AI_ENDPOINT = "https://api.synexa.ai/v1/generate" # Kiểm tra lại doc của họ

# --- THIẾT LẬP SERVER ---

# [cite_start]Cho phép Frontend gọi vào từ mọi nơi (CORS) [cite: 66]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/generate")
async def generate_3d_model(file: UploadFile = File(...)):
    
    # [cite_start]BƯỚC 1: UPLOAD ẢNH LÊN CLOUD (Để lấy Public URL) [cite: 47, 48]
    try:
        print("--- Bắt đầu xử lý ---")
        # Upload lên Cloudinary
        upload_result = cloudinary.uploader.upload(file.file)
        image_public_url = upload_result.get("secure_url")
        print(f"1. Ảnh đã lên mây: {image_public_url}")
        
        if not image_public_url:
            return {"errorCode": "UPLOAD_ERR", "message": "Lỗi upload ảnh"}

    except Exception as e:
        return {"errorCode": "UPLOAD_EXCEPTION", "message": str(e)}

    # [cite_start]BƯỚC 2: GỌI AI TẠO 3D [cite: 50]
    
    # --- A. NẾU ĐANG TEST (Tiết kiệm tiền/thời gian) ---
    if TEST_MODE:
        print("2. Chế độ TEST: Trả về file mẫu sau 3s...")
        time.sleep(3) # Giả vờ đợi
        # Link file .glb mẫu (Con vịt) để Frontend test hiển thị
        dummy_glb = "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Models/master/2.0/Duck/glTF-Binary/Duck.glb"
        
        # [cite_start]Trả về đúng định dạng JSON mà PDF yêu cầu [cite: 60, 80]
        return {"glbUrl": dummy_glb}

    # --- B. NẾU CHẠY THẬT (Gọi API) ---
    print("2. Chế độ REAL: Đang gọi AI API...")
    
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "image_url": image_public_url,
        # [cite_start]Các tham số khác tùy vào document của bên AI [cite: 52]
        "format": "glb" 
    }

    try:
        response = requests.post(AI_ENDPOINT, json=payload, headers=headers)
        
        # [cite_start]Xử lý lỗi từ AI [cite: 56, 69]
        if response.status_code != 200:
            print(f"Lỗi API: {response.text}")
            return {"errorCode": "AI_FAIL", "message": "AI từ chối phục vụ"}

        data = response.json()
        
        # [cite_start]Lấy link GLB từ kết quả trả về [cite: 53]
        # Cần xem kỹ JSON của Synexa để sửa dòng dưới cho đúng key (ví dụ: data['model_url'] hay data['result']['url'])
        final_glb_url = data.get("data", {}).get("model_url") 
        
        if not final_glb_url:
             return {"errorCode": "NO_GLB", "message": "AI chạy xong nhưng không thấy link file"}

        return {"glbUrl": final_glb_url}

    except Exception as e:
        return {"errorCode": "API_CRASH", "message": str(e)}

# Chạy server: uvicorn main:app --reload