from flask import Flask, request, render_template_string
import requests
import re
import psycopg2
from psycopg2 import pool
import os
from apify_client import ApifyClient

app = Flask(__name__)

# LẤY BIẾN MÔI TRƯỜNG TỪ RENDER
API_KEY = os.getenv("YOUTUBE_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
APIFY_TOKEN = os.getenv("APIFY_TOKEN") 

# HỒ CHỨA KẾT NỐI DATABASE
try:
    db_pool = psycopg2.pool.ThreadedConnectionPool(1, 20, dsn=DATABASE_URL)
    conn = db_pool.getconn()
    cursor = conn.cursor()
    # TẠO BẢNG (Đã mở rộng độ dài video_id để chứa các mã pfbid siêu dài của Facebook)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS video_stats (
            video_id VARCHAR(500) PRIMARY KEY,
            platform TEXT,
            title TEXT,
            video_type TEXT,
            view_count BIGINT,
            like_count BIGINT,
            comment_count BIGINT
        )
    ''')
    conn.commit()
    db_pool.putconn(conn)
except Exception as e:
    print("Lỗi khởi tạo Database Pool:", e)

# GIAO DIỆN HTML
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Social Media Data Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        body { background-color: #f4f7f6; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #2c3e50; }
        .main-container { max-width: 950px; margin-top: 3rem; margin-bottom: 5rem;}
        .app-card { background: #ffffff; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.08); padding: 2.5rem; border: none; }
        .header-title { color: #1e3c72; font-weight: 800; margin-bottom: 0.5rem; text-align: center; font-size: 2rem; }
        .header-subtitle { text-align: center; color: #64748b; margin-bottom: 2.5rem; font-size: 0.95rem; }
        .form-control { border-radius: 8px; padding: 0.85rem 1.25rem; border: 1px solid #e2e8f0; background-color: #f8fafc; font-size: 1rem; }
        .form-control:focus { border-color: #1e3c72; box-shadow: 0 0 0 0.25rem rgba(30, 60, 114, 0.1); background-color: #ffffff; }
        .btn-submit { background: #1e3c72; color: white; border-radius: 8px; padding: 0.85rem; font-weight: 600; font-size: 1.05rem; transition: all 0.3s ease; border: none; }
        .btn-submit:hover { background: #152a55; color: white; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(30,60,114,0.2); }
        .platform-icon { font-size: 1.3rem; margin-right: 10px; }
        .fa-youtube { color: #ff0000; }
        .fa-facebook { color: #0866FF; }
        .table-custom { font-size: 0.95rem; }
        .table-custom thead { background-color: #f8fafc; }
        .table-custom th { color: #475569; font-size: 0.85rem; text-transform: uppercase; padding: 1rem; border-bottom: 2px solid #e2e8f0; font-weight: 700; }
        .table-custom td { padding: 1rem; vertical-align: middle; border-bottom: 1px solid #f1f5f9; }
        .badge-type { font-size: 0.75rem; padding: 0.4em 0.7em; border-radius: 6px; background: #e2e8f0; color: #475569; font-weight: 600; }
        .video-title { font-weight: 600; color: #1e293b; max-width: 320px; display: inline-block; }
    </style>
</head>
<body>
    <div class="container main-container">
        <!-- Khu vực nhập liệu -->
        <div class="card app-card mb-4">
            <h2 class="header-title"><i class="fa-solid fa-bolt text-warning me-2"></i>Social Media Data Pro</h2>
            <p class="header-subtitle">Hệ thống quét dữ liệu đa nền tảng tự động</p>
            
            <form method="POST" id="fetchForm">
                <div class="mb-4">
                    <label class="form-label fw-bold text-muted small text-uppercase">Nguồn Dữ Liệu (YouTube / Facebook)</label>
                    <div class="input-group">
                        <span class="input-group-text bg-white border-end-0"><i class="fa-solid fa-link text-muted"></i></span>
                        <input type="text" class="form-control border-start-0 ps-0" name="video_url" placeholder="Dán link bài viết, video, shorts, reels vào đây..." required>
                    </div>
                </div>
                <button type="submit" class="btn btn-submit w-100" id="submitBtn">
                    <i class="fa-solid fa-cloud-arrow-down me-2"></i>Tiến Hành Thu Thập Dữ Liệu
                </button>
                <div id="waitMsg" class="text-center mt-3 text-primary fw-medium" style="display:none; font-size: 0.9rem;">
                    <i class="fa-solid fa-circle-notch fa-spin me-2"></i>Hệ thống đang quét... (Link Facebook cần khởi tạo Bot nên sẽ mất 1-2 phút)
                </div>
            </form>
            
            {% if message %}
                <div class="mt-4">{{ message | safe }}</div>
            {% endif %}
        </div>

        <!-- Khu vực hiển thị Database -->
        <div class="card app-card">
            <h4 class="mb-4 fw-bold text-dark"><i class="fa-solid fa-server me-2 text-primary"></i>Kho Dữ Liệu Đã Lưu</h4>
            
            {% if records %}
            <div class="table-responsive">
                <table class="table table-custom table-hover align-middle mb-0">
                    <thead>
                        <tr>
                            <th width="45%">Nội dung đã quét</th>
                            <th class="text-end">Lượt xem</th>
                            <th class="text-end">Lượt thích</th>
                            <th class="text-end">Bình luận</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for row in records %}
                        <tr>
                            <td>
                                <div class="d-flex align-items-center mb-1">
                                    <i class="fa-brands fa-{{ row[1] }} platform-icon"></i>
                                    <span class="video-title text-truncate" title="{{ row[2] }}">{{ row[2] }}</span>
                                </div>
                                <span class="badge-type"><i class="fa-solid fa-tag me-1"></i>{{ row[3] }}</span>
                            </td>
                            <td class="text-end fw-bold text-dark">{{ "{:,.0f}".format(row[4]) }}</td>
                            <td class="text-end text-muted fw-medium">{{ "{:,.0f}".format(row[5]) }}</td>
                            <td class="text-end text-muted fw-medium">{{ "{:,.0f}".format(row[6]) }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% else %}
            <div class="text-center text-muted py-5">
                <i class="fa-regular fa-folder-open mb-3 text-light" style="font-size: 4rem;"></i>
                <h5 class="fw-bold">Database Đang Trống</h5>
                <p>Hãy dán link vào công cụ bên trên để bắt đầu thu thập dữ liệu đầu tiên!</p>
            </div>
            {% endif %}
        </div>
    </div>

    <script>
        document.getElementById('fetchForm').addEventListener('submit', function() {
            var btn = document.getElementById('submitBtn');
            var waitMsg = document.getElementById('waitMsg');
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2"></i>Đang xử lý...';
            btn.style.opacity = '0.8';
            btn.style.pointerEvents = 'none';
            waitMsg.style.display = 'block';
        });
    </script>
</body>
</html>
'''

# HÀM ĐỌC DỮ LIỆU TỪ DB
def get_all_records():
    conn = db_pool.getconn()
    records = []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT video_id, platform, title, video_type, view_count, like_count, comment_count FROM video_stats ORDER BY view_count DESC LIMIT 50")
        records = cursor.fetchall()
    except Exception as e:
        print("Lỗi khi đọc Database:", e)
    finally:
        db_pool.putconn(conn)
    return records

@app.route("/", methods=["GET", "POST"])
def index():
    message = ""
    
    if request.method == "POST":
        url = request.form.get("video_url").strip()
        video_id = None
        title = ""
        video_type = "Video"
        platform = ""
        views = likes = comments = 0
        success = False

        try:
            # ==========================================
            # 1. NHÁNH XỬ LÝ YOUTUBE
            # ==========================================
            if "youtube.com" in url or "youtu.be" in url:
                platform = "youtube"
                
                if "/shorts/" in url:
                    video_type = "Shorts"
                    match = re.search(r"/shorts/([a-zA-Z0-9_-]+)", url)
                else:
                    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
                
                if match: 
                    video_id = match.group(1)

                if video_id:
                    api_url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics,snippet&id={video_id}&key={API_KEY}"
                    response = requests.get(api_url).json()
                    
                    if response.get('items'):
                        item = response['items'][0]
                        title = item['snippet']['title']
                        stats = item['statistics']
                        
                        views = int(stats.get('viewCount', 0))
                        likes = int(stats.get('likeCount', 0))
                        comments = int(stats.get('commentCount', 0))
                        success = True
                    else:
                        message = '<div class="alert alert-warning border-0"><i class="fa-solid fa-circle-xmark me-2"></i>Không tìm thấy video YouTube!</div>'
                else:
                    message = '<div class="alert alert-danger border-0"><i class="fa-solid fa-triangle-exclamation me-2"></i>Định dạng link YouTube không hợp lệ!</div>'

            # ==========================================
            # 2. NHÁNH XỬ LÝ FACEBOOK (XỬ LÝ REEL, POST, PFBID)
            # ==========================================
            elif "facebook.com" in url or "fb.watch" in url:
                platform = "facebook"
                client = ApifyClient(APIFY_TOKEN)
                
                # CẬP NHẬT CỐT LÕI: pageUrls MANG ĐÚNG ĐỊNH DẠNG LIST OF STRINGS
                run_input = {
                    "pageUrls": [url],
                    "proxyConfiguration": {"useApifyProxy": True},
                    "resultsLimit": 1
                }
                
                # Gọi Bot Apify
                run = client.actor("zanTWNqB3Poz44qdY").call(run_input=run_input)
                dataset = client.dataset(run.default_dataset_id)
                items = dataset.list_items().items
                
                if items:
                    item = items[0]
                    
                    # RÚT TRÍCH ID THÔNG MINH (Xử lý các đuôi / pfbid phức tạp)
                    # Loại bỏ dấu '/' ở cuối link để cắt ID chuẩn xác hơn
                    url_parts = [p for p in url.split('/') if p]
                    fallback_id = url_parts[-1] if url_parts else 'fb_' + str(abs(hash(url)))
                    
                    # Lấy ID từ Apify trả về, nếu không có thì lấy phần đuôi của URL
                    raw_id = str(item.get('postId') or item.get('id') or fallback_id)
                    # Cắt ngắn ID nếu nó dài quá 250 ký tự (phòng hờ pfbid siêu dài)
                    video_id = raw_id[:250]
                    
                    # Lấy Tiêu Đề
                    title_raw = item.get('text') or item.get('description') or item.get('content') or item.get('title') or ''
                    title = title_raw[:65] + "..." if title_raw and len(title_raw) > 65 else (title_raw or f"Nội dung Facebook ({video_id[:8]})")
                    
                    # Phân loại rạch ròi
                    if "reel" in url:
                        video_type = "Reels"
                    elif "posts" in url or "pfbid" in url:
                        video_type = "Bài Viết FB"
                    elif item.get('is_video') or "watch" in url or "video" in url:
                        video_type = "Video FB"
                    elif "photo" in url:
                        video_type = "Ảnh FB"
                    else:
                        video_type = "Post FB"
                    
                    # Trích xuất chỉ số (Quét cạn)
                    views = int(item.get('viewsCount') or item.get('views') or item.get('playCount') or 0)
                    likes = int(item.get('likesCount') or item.get('likes') or item.get('reactionCount') or 0)
                    comments = int(item.get('commentsCount') or item.get('comments') or 0)
                    
                    success = True
                else:
                    message = '<div class="alert alert-warning border-0"><i class="fa-solid fa-user-secret me-2"></i>Bot bị chặn hoặc bài viết này không được công khai!</div>'

            else:
                message = '<div class="alert alert-danger border-0"><i class="fa-solid fa-triangle-exclamation me-2"></i>Chỉ hỗ trợ Link YouTube và Facebook!</div>'

            # ==========================================
            # 3. LƯU VÀO DATABASE
            # ==========================================
            if success and video_id:
                conn = db_pool.getconn()
                try:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO video_stats (video_id, platform, title, video_type, view_count, like_count, comment_count)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT(video_id) DO UPDATE SET
                            platform=EXCLUDED.platform,
                            title=EXCLUDED.title,
                            video_type=EXCLUDED.video_type,
                            view_count=EXCLUDED.view_count,
                            like_count=EXCLUDED.like_count,
                            comment_count=EXCLUDED.comment_count
                    ''', (video_id, platform, title, video_type, views, likes, comments))
                    conn.commit()
                    message = f'<div class="alert alert-success border-0 bg-success bg-opacity-10 text-success"><i class="fa-solid fa-circle-check me-2"></i>Đã thu thập và lưu thành công: <b>{title}</b></div>'
                except Exception as db_err:
                    message = f'<div class="alert alert-danger border-0"><i class="fa-solid fa-database me-2"></i>Lỗi ghi DB: {str(db_err)}</div>'
                finally:
                    db_pool.putconn(conn)

        except Exception as e:
            message = f'<div class="alert alert-danger border-0"><i class="fa-solid fa-triangle-exclamation me-2"></i>Lỗi gọi API: {str(e)}</div>'

    # Hiển thị lại danh sách
    saved_records = get_all_records()
    return render_template_string(HTML_TEMPLATE, message=message, records=saved_records)

if __name__ == "__main__":
    app.run(debug=True, port=5000)