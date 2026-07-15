from flask import Flask, request, render_template_string
import requests
import re
import psycopg2
from psycopg2 import pool
import os

app = Flask(__name__)

API_KEY = os.getenv("YOUTUBE_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# HỒ CHỨA KẾT NỐI (POOLING)
try:
    db_pool = psycopg2.pool.ThreadedConnectionPool(1, 20, dsn=DATABASE_URL)
    conn = db_pool.getconn()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS video_stats (
            video_id TEXT PRIMARY KEY,
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

# HTML GIAO DIỆN (Đã bổ sung bảng hiển thị Database)
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube Data Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #f4f7f6; color: #2c3e50; }
        .main-container { max-width: 900px; margin-top: 3rem; margin-bottom: 5rem; }
        .app-card { background: #ffffff; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.08); border: none; overflow: hidden; }
        .header-banner { background: linear-gradient(135deg, #ff0000 0%, #b30000 100%); color: white; padding: 2rem; text-align: center; }
        .header-banner h2 { font-weight: 700; margin: 0; font-size: 1.7rem; }
        .header-banner p { opacity: 0.85; margin-top: 0.5rem; margin-bottom: 0; font-size: 0.95rem; }
        .content-section { padding: 2.5rem; }
        .form-control { border-radius: 8px; padding: 0.85rem 1.25rem; border: 1px solid #e2e8f0; background-color: #f8fafc; font-size: 1rem; }
        .form-control:focus { border-color: #ff0000; box-shadow: 0 0 0 0.25rem rgba(255, 0, 0, 0.1); background-color: #ffffff; }
        .btn-submit { background: #ff0000; color: white; border: none; border-radius: 8px; padding: 0.85rem; font-weight: 600; font-size: 1rem; transition: all 0.3s ease; }
        .btn-submit:hover { background: #d90000; color: white; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(255,0,0,0.2); }
        
        /* CSS cho bảng hiển thị dữ liệu */
        .db-section { margin-top: 3rem; }
        .table-custom { font-size: 0.95rem; }
        .table-custom thead { background-color: #f8fafc; color: #64748b; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.5px; }
        .table-custom th { border-bottom: 2px solid #e2e8f0; padding: 1rem; font-weight: 600; }
        .table-custom td { padding: 1rem; vertical-align: middle; border-bottom: 1px solid #f1f5f9; }
        .video-link { color: #0f172a; text-decoration: none; font-weight: 600; transition: color 0.2s; }
        .video-link:hover { color: #ff0000; }
        .badge-type { font-size: 0.75rem; padding: 0.35em 0.65em; border-radius: 6px; background: #e2e8f0; color: #475569; }
    </style>
</head>
<body>
    <div class="container main-container">
        <!-- Khu vực nhập liệu (Ghi vào DB) -->
        <div class="card app-card mb-4">
            <div class="header-banner">
                <h2><i class="fa-brands fa-youtube me-2"></i>YouTube Analytics API</h2>
                <p>Hệ thống trích xuất & thống kê dữ liệu tự động</p>
            </div>
            <div class="content-section pb-2">
                <form method="POST" id="fetchForm">
                    <div class="mb-4">
                        <label class="form-label fw-bold text-muted small text-uppercase">Thêm Video Mới Vào Hệ Thống</label>
                        <div class="input-group">
                            <span class="input-group-text bg-white"><i class="fa-solid fa-link text-muted"></i></span>
                            <input type="text" class="form-control border-start-0 ps-0" name="youtube_url" placeholder="Dán link YouTube (Video/Short) vào đây..." required>
                        </div>
                    </div>
                    <button type="submit" class="btn btn-submit w-100" id="submitBtn">
                        <i class="fa-solid fa-cloud-arrow-down me-2"></i>Xử lý & Lưu Database
                    </button>
                </form>
                
                {% if message %}
                    <div class="mt-4">{{ message | safe }}</div>
                {% endif %}
            </div>
        </div>

        <!-- Khu vực hiển thị Database (Đọc từ DB) -->
        <div class="card app-card">
            <div class="content-section">
                <h4 class="mb-4 fw-bold text-dark"><i class="fa-solid fa-database me-2 text-danger"></i>Kho Dữ Liệu Đã Lưu</h4>
                
                {% if records %}
                <div class="table-responsive">
                    <table class="table table-custom table-hover mb-0">
                        <thead>
                            <tr>
                                <th width="45%">Video</th>
                                <th class="text-end">Lượt xem</th>
                                <th class="text-end">Lượt thích</th>
                                <th class="text-end">Bình luận</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for row in records %}
                            <tr>
                                <td>
                                    <a href="https://youtube.com/watch?v={{ row[0] }}" target="_blank" class="video-link d-block mb-1">
                                        {{ row[1] }}
                                    </a>
                                    <span class="badge-type"><i class="fa-solid fa-tag me-1"></i>{{ row[2] }}</span>
                                </td>
                                <td class="text-end fw-bold text-dark">{{ "{:,.0f}".format(row[3]) }}</td>
                                <td class="text-end text-muted">{{ "{:,.0f}".format(row[4]) }}</td>
                                <td class="text-end text-muted">{{ "{:,.0f}".format(row[5]) }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
                {% else %}
                <div class="text-center text-muted py-4">
                    <i class="fa-regular fa-folder-open fs-1 mb-3 text-light"></i>
                    <p>Database hiện tại đang trống. Hãy nhập link ở trên để nạp dữ liệu!</p>
                </div>
                {% endif %}
            </div>
        </div>
    </div>

    <script>
        document.getElementById('fetchForm').addEventListener('submit', function() {
            var btn = document.getElementById('submitBtn');
            btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin me-2"></i>Đang xử lý dữ liệu...';
            btn.style.opacity = '0.8';
            btn.style.pointerEvents = 'none';
        });
    </script>
</body>
</html>
'''

# Hàm lấy tất cả dữ liệu từ Database
def get_all_records():
    conn = db_pool.getconn()
    records = []
    try:
        cursor = conn.cursor()
        # Sắp xếp theo view giảm dần, giới hạn lấy 50 video mới nhất/hot nhất
        cursor.execute("SELECT video_id, title, video_type, view_count, like_count, comment_count FROM video_stats ORDER BY view_count DESC LIMIT 50")
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
        url = request.form.get("youtube_url")
        video_id, video_type = None, "Normal Video"
        
        if "/shorts/" in url:
            video_type = "Shorts"
            match = re.search(r"/shorts/([a-zA-Z0-9_-]+)", url)
            if match: video_id = match.group(1)
        else:
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
            if match: video_id = match.group(1)

        if not video_id:
            message = '<div class="alert alert-danger bg-danger bg-opacity-10 text-danger border-0"><i class="fa-solid fa-triangle-exclamation me-2"></i>Link không hợp lệ!</div>'
        else:
            api_url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics,snippet&id={video_id}&key={API_KEY}"
            try:
                response = requests.get(api_url).json()
                if not response.get('items'):
                    message = '<div class="alert alert-danger bg-danger bg-opacity-10 text-danger border-0"><i class="fa-solid fa-circle-xmark me-2"></i>Không tìm thấy video!</div>'
                else:
                    item = response['items'][0]
                    title = item['snippet']['title']
                    stats = item['statistics']
                    
                    views = int(stats.get('viewCount', 0))
                    likes = int(stats.get('likeCount', 0))
                    comments = int(stats.get('commentCount', 0))

                    # Ghi vào DB
                    conn = db_pool.getconn()
                    try:
                        cursor = conn.cursor()
                        cursor.execute('''
                            INSERT INTO video_stats (video_id, title, video_type, view_count, like_count, comment_count)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT(video_id) DO UPDATE SET
                                title=EXCLUDED.title,
                                video_type=EXCLUDED.video_type,
                                view_count=EXCLUDED.view_count,
                                like_count=EXCLUDED.like_count,
                                comment_count=EXCLUDED.comment_count
                        ''', (video_id, title, video_type, views, likes, comments))
                        conn.commit()
                        message = f'<div class="alert alert-success bg-success bg-opacity-10 text-success border-0"><i class="fa-solid fa-circle-check me-2"></i>Đã cập nhật: <b>{title}</b></div>'
                    finally:
                        db_pool.putconn(conn)
            except Exception as e:
                message = f'<div class="alert alert-danger bg-danger bg-opacity-10 text-danger border-0"><i class="fa-solid fa-bug me-2"></i>Lỗi: {str(e)}</div>'

    # ĐỌC DB: Sau khi xử lý xong (hoặc khi mới tải trang), gọi hàm đọc DB để ném ra giao diện
    saved_records = get_all_records()
    
    return render_template_string(HTML_TEMPLATE, message=message, records=saved_records)

if __name__ == "__main__":
    app.run(debug=True, port=5000)