from flask import Flask, request, render_template_string
import requests
import re
import psycopg2
import os

app = Flask(__name__)

API_KEY = os.getenv("YOUTUBE_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube Data Extractor | Pro Version</title>
    <!-- Thư viện CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    
    <style>
        body {
            font-family: 'Inter', sans-serif;
            background-color: #f4f7f6;
            color: #2c3e50;
        }
        .main-container {
            max-width: 750px;
            margin-top: 5rem;
            margin-bottom: 5rem;
        }
        .app-card {
            background: #ffffff;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.08);
            border: none;
            overflow: hidden;
        }
        .header-banner {
            background: linear-gradient(135deg, #ff0000 0%, #b30000 100%);
            color: white;
            padding: 2rem;
            text-align: center;
        }
        .header-banner h2 {
            font-weight: 700;
            margin: 0;
            font-size: 1.7rem;
            letter-spacing: -0.5px;
        }
        .header-banner p {
            opacity: 0.85;
            margin-top: 0.5rem;
            margin-bottom: 0;
            font-size: 0.95rem;
        }
        .content-section {
            padding: 2.5rem;
        }
        .form-control {
            border-radius: 8px;
            padding: 0.85rem 1.25rem;
            border: 1px solid #e2e8f0;
            background-color: #f8fafc;
            font-size: 1rem;
        }
        .form-control:focus {
            border-color: #ff0000;
            box-shadow: 0 0 0 0.25rem rgba(255, 0, 0, 0.1);
            background-color: #ffffff;
        }
        .input-group-text {
            border-radius: 8px 0 0 8px;
            border: 1px solid #e2e8f0;
        }
        .btn-submit {
            background: #ff0000;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 0.85rem;
            font-weight: 600;
            font-size: 1rem;
            transition: all 0.3s ease;
        }
        .btn-submit:hover {
            background: #d90000;
            color: white;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(255,0,0,0.2);
        }
        
        /* Căn chỉnh khối hiển thị dữ liệu */
        .result-wrapper {
            margin-top: 2rem;
            border-top: 1px solid #f1f5f9;
            padding-top: 2rem;
        }
        .video-info {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            padding: 1.2rem;
            border-radius: 12px;
            margin-bottom: 1.5rem;
        }
        .video-title {
            font-weight: 600;
            color: #0f172a;
            font-size: 1.1rem;
            margin-bottom: 0.5rem;
            line-height: 1.4;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1rem;
        }
        .stat-box {
            background: #ffffff;
            padding: 1.2rem 1rem;
            border-radius: 12px;
            text-align: center;
            border: 1px solid #e2e8f0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
        }
        .stat-icon {
            font-size: 1.4rem;
            margin-bottom: 0.5rem;
        }
        .stat-value {
            font-size: 1.3rem;
            font-weight: 700;
            color: #0f172a;
            margin-bottom: 0.2rem;
        }
        .stat-label {
            font-size: 0.75rem;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
        }
    </style>
</head>
<body>
    <div class="container main-container">
        <div class="card app-card">
            <div class="header-banner">
                <h2><i class="fa-brands fa-youtube me-2"></i>YouTube Analytics API</h2>
                <p>Hệ thống tự động trích xuất & lưu trữ CSDL</p>
            </div>
            <div class="content-section">
                <form method="POST" id="fetchForm">
                    <div class="mb-4">
                        <label class="form-label fw-bold text-muted small text-uppercase letter-spacing-1">Đường dẫn Video / Short</label>
                        <div class="input-group">
                            <span class="input-group-text bg-white"><i class="fa-solid fa-link text-muted"></i></span>
                            <input type="text" class="form-control border-start-0 ps-0" name="youtube_url" placeholder="VD: https://www.youtube.com/watch?v=..." required>
                        </div>
                    </div>
                    <button type="submit" class="btn btn-submit w-100" id="submitBtn">
                        <i class="fa-solid fa-cloud-arrow-down me-2"></i>Bắt đầu đồng bộ dữ liệu
                    </button>
                </form>
                
                {% if message %}
                    <div class="result-wrapper">
                        {{ message | safe }}
                    </div>
                {% endif %}
            </div>
        </div>
    </div>

    <!-- Script tạo hiệu ứng xoay khi bấm nút -->
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

def setup_db():
    conn = psycopg2.connect(DATABASE_URL)
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
    return conn

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
            message = '''
            <div class="alert alert-danger border-0 bg-danger bg-opacity-10 text-danger mb-0">
                <i class="fa-solid fa-triangle-exclamation me-2"></i>Đường dẫn không hợp lệ, vui lòng kiểm tra lại!
            </div>'''
            return render_template_string(HTML_TEMPLATE, message=message)

        api_url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics,snippet&id={video_id}&key={API_KEY}"
        
        try:
            response = requests.get(api_url).json()
            if not response.get('items'):
                message = '''
                <div class="alert alert-danger border-0 bg-danger bg-opacity-10 text-danger mb-0">
                    <i class="fa-solid fa-circle-xmark me-2"></i>Không tìm thấy dữ liệu! Video có thể ở trạng thái riêng tư hoặc đã bị xóa.
                </div>'''
                return render_template_string(HTML_TEMPLATE, message=message)
            
            item = response['items'][0]
            title = item['snippet']['title']
            stats = item['statistics']
            
            views = int(stats.get('viewCount', 0))
            likes = int(stats.get('likeCount', 0))
            comments = int(stats.get('commentCount', 0))

            conn = setup_db()
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
            conn.close()
            
            # Giao diện hiển thị kết quả cực kỳ chuyên nghiệp
            message = f'''
            <div class="alert alert-success border-0 bg-success bg-opacity-10 text-success mb-3 py-2">
                <i class="fa-solid fa-circle-check me-2"></i>Đã đồng bộ dữ liệu vào PostgreSQL
            </div>
            
            <div class="video-info">
                <div class="video-title"><i class="fa-brands fa-youtube text-danger me-2"></i>{title}</div>
                <div class="text-muted small">
                    <i class="fa-solid fa-fingerprint me-1"></i> ID: <strong>{video_id}</strong> &nbsp;|&nbsp; 
                    <i class="fa-solid fa-tags me-1 text-secondary"></i> Loại: {video_type}
                </div>
            </div>
            
            <div class="stats-grid">
                <div class="stat-box">
                    <div class="stat-icon text-primary"><i class="fa-regular fa-eye"></i></div>
                    <div class="stat-value">{views:,}</div>
                    <div class="stat-label">Lượt xem</div>
                </div>
                <div class="stat-box">
                    <div class="stat-icon text-success"><i class="fa-regular fa-thumbs-up"></i></div>
                    <div class="stat-value">{likes:,}</div>
                    <div class="stat-label">Lượt thích</div>
                </div>
                <div class="stat-box">
                    <div class="stat-icon text-warning"><i class="fa-regular fa-comments"></i></div>
                    <div class="stat-value">{comments:,}</div>
                    <div class="stat-label">Bình luận</div>
                </div>
            </div>
            '''
            
        except Exception as e:
            message = f'''
            <div class="alert alert-danger border-0 bg-danger bg-opacity-10 text-danger mb-0">
                <i class="fa-solid fa-triangle-exclamation me-2"></i>Lỗi truy vấn: {str(e)}
            </div>'''

    return render_template_string(HTML_TEMPLATE, message=message)

if __name__ == "__main__":
    app.run(debug=True, port=5000)