from flask import Flask, request, render_template_string
import requests
import re
import psycopg2
import os

app = Flask(__name__)

# Lấy các biến từ môi trường (trên Render sẽ cấu hình sau)
API_KEY = os.getenv("YOUTUBE_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Tool Lấy Data YouTube</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
    <div class="container mt-5">
        <div class="card shadow-sm p-4">
            <h2 class="text-center mb-4 text-primary">NẠP DATA YOUTUBE</h2>
            <form method="POST">
                <div class="mb-3">
                    <label class="form-label fw-bold">Link YouTube (Video/Short):</label>
                    <input type="text" class="form-control" name="youtube_url" placeholder="Dán link vào đây..." required>
                </div>
                <button type="submit" class="btn btn-primary w-100">Xử Lý & Lưu CSDL</button>
            </form>
            {% if message %}
                <div class="alert alert-{{ msg_type }} mt-4">{{ message | safe }}</div>
            {% endif %}
        </div>
    </div>
</body>
</html>
'''

def setup_db():
    # Kết nối DB và tự động tạo bảng nếu chưa có
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS video_stats (
            video_id TEXT PRIMARY KEY,
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
    message, msg_type = "", "info"
    if request.method == "POST":
        url = request.form.get("youtube_url")
        video_id, video_type = None, "Normal Video"
        
        # Lấy ID
        if "/shorts/" in url:
            video_type = "Shorts"
            match = re.search(r"/shorts/([a-zA-Z0-9_-]+)", url)
            if match: video_id = match.group(1)
        else:
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
            if match: video_id = match.group(1)

        if not video_id:
            return render_template_string(HTML_TEMPLATE, message="❌ Link sai rồi!", msg_type="danger")

        # Gọi Google API
        api_url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics&id={video_id}&key={API_KEY}"
        try:
            response = requests.get(api_url).json()
            if not response.get('items'):
                return render_template_string(HTML_TEMPLATE, message="❌ Không tìm thấy video.", msg_type="danger")
            
            stats = response['items'][0]['statistics']
            views = int(stats.get('viewCount', 0))
            likes = int(stats.get('likeCount', 0))
            comments = int(stats.get('commentCount', 0))

            # Lưu vào Supabase
            conn = setup_db()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO video_stats (video_id, video_type, view_count, like_count, comment_count)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(video_id) DO UPDATE SET
                    view_count=EXCLUDED.view_count,
                    like_count=EXCLUDED.like_count,
                    comment_count=EXCLUDED.comment_count
            ''', (video_id, video_type, views, likes, comments))
            conn.commit()
            conn.close()
            message = f"✅ <b>Thành công!</b> ID: {video_id} <br> View: {views} | Like: {likes} | Cmt: {comments}"
            msg_type = "success"
        except Exception as e:
            message = f"❌ Lỗi hệ thống: {str(e)}"
            msg_type = "danger"

    return render_template_string(HTML_TEMPLATE, message=message, msg_type=msg_type)

if __name__ == "__main__":
    app.run(debug=True, port=5000)