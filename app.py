from flask import Flask, request, render_template_string
import requests
import re
import psycopg2
from psycopg2 import pool
import os
from apify_client import ApifyClient

app = Flask(__name__)

# ==========================================
# CẤU HÌNH BIẾN MÔI TRƯỜNG & DATABASE
# ==========================================
API_KEY = os.getenv("YOUTUBE_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
APIFY_TOKEN = os.getenv("APIFY_TOKEN") 

db_pool = None
try:
    db_pool = psycopg2.pool.ThreadedConnectionPool(1, 20, dsn=DATABASE_URL)
    conn = db_pool.getconn()
    cursor = conn.cursor()
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

# ==========================================
# GIAO DIỆN HTML
# ==========================================
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
                    <i class="fa-solid fa-circle-notch fa-spin me-2"></i>Hệ thống đang quét... (Quá trình cào Facebook có thể mất 15-30 giây)
                </div>
            </form>
            
            {% if message %}
                <div class="mt-4">{{ message | safe }}</div>
            {% endif %}
        </div>

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

def get_all_records():
    if not db_pool:
        return []
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

# ==========================================
# CỖ MÁY NHAI SỐ (Xử lý mọi định dạng: 1.5K, 12,000, Dict...)
# ==========================================
def parse_number(val):
    if val is None:
        return None
    try:
        # Nếu đã là số chuẩn
        if isinstance(val, (int, float)):
            return int(val)
        
        # Nếu bị giấu trong Dictionary
        if isinstance(val, dict):
            val = val.get('count') or val.get('totalCount') or val.get('total_count') or val.get('total')
            if val is None:
                return None
            
        # Nếu là dạng chuỗi có chứa K, M, B hoặc dấu phẩy (vd: 3.5K, 12,000)
        if isinstance(val, str):
            s = val.upper().strip().replace(',', '').replace(' ', '')
            multiplier = 1
            if s.endswith('K'):
                multiplier = 1000
                s = s[:-1]
            elif s.endswith('M'):
                multiplier = 1000000
                s = s[:-1]
            elif s.endswith('B'):
                multiplier = 1000000000
                s = s[:-1]
            return int(float(s) * multiplier)
    except:
        return None
    return None

def extract_stat(item, keys):
    for key in keys:
        val = parse_number(item.get(key))
        if val is not None:
            return val
    return 0

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

            elif "facebook.com" in url or "fb.watch" in url:
                platform = "facebook"
                safe_url = url
                if "fb.watch" in safe_url:
                    raise Exception("Hệ thống không hỗ trợ link fb.watch. Hãy mở trình duyệt và copy link facebook.com gốc.")
                
                safe_url = re.sub(r'^(https?://)?([a-zA-Z0-9_.-]+\.)?facebook\.com', 'https://www.facebook.com', safe_url)

                client = ApifyClient(APIFY_TOKEN)
                run_input = {
                    "startUrls": [{"url": safe_url}],
                    "resultsLimit": 1,
                    "proxyConfiguration": {"useApifyProxy": True}
                }
                
                run = client.actor("apify/facebook-posts-scraper").call(run_input=run_input)
                dataset = client.dataset(run.default_dataset_id)
                items = dataset.list_items().items
                
                if items:
                    item = items[0]
                    
                    url_parts = [p for p in url.split('/') if p]
                    fallback_id = url_parts[-1] if url_parts else 'fb_' + str(abs(hash(url)))
                    raw_id = item.get('postId') or item.get('id') or item.get('post_id') or fallback_id
                    
                    if isinstance(raw_id, dict):
                        raw_id = raw_id.get('id') or str(raw_id)
                    video_id = str(raw_id)[:250]
                    
                    title_raw = item.get('text') or item.get('message') or item.get('description') or item.get('title') or item.get('content') or ''
                    if isinstance(title_raw, dict):
                        title_raw = title_raw.get('text') or title_raw.get('message') or ''
                        
                    title_raw = str(title_raw).strip()
                    
                    if not title_raw or title_raw == "None":
                        author = item.get('user') or item.get('author')
                        author_name = author.get('name') if isinstance(author, dict) else ''
                        title_raw = f"Bài viết của {author_name}" if author_name else ""
                        
                    title = title_raw[:65] + "..." if len(title_raw) > 65 else (title_raw or f"Nội dung Facebook ({video_id[:8]})")
                    
                    if "reel" in url:
                        video_type = "Reels"
                    elif "posts" in url or "pfbid" in url:
                        video_type = "Bài Viết FB"
                    elif item.get('is_video') or "watch" in url or "video" in url:
                        video_type = "Video FB"
                    else:
                        video_type = "Post FB"
                    
                    # Quét toàn bộ bộ từ điển
                    views = extract_stat(item, ['videoViewCount', 'viewsCount', 'views', 'playCount', 'viewCount'])
                    likes = extract_stat(item, ['likes', 'likesCount', 'reactionsCount', 'reactionCount', 'postLikes', 'reaction_count'])
                    comments = extract_stat(item, ['comments', 'commentsCount', 'postComments', 'comment_count'])
                    
                    success = True
                    
                    # TÍNH NĂNG DEBUG MỚI
                    debug_msg = ""
                    if views == 0 and likes == 0 and comments == 0:
                        # Rút trích các key khả nghi để bắt lỗi
                        sus_keys = [k for k in item.keys() if 'like' in k.lower() or 'view' in k.lower() or 'count' in k.lower() or 'stat' in k.lower() or 'reaction' in k.lower()]
                        debug_msg = f'<br><small class="text-danger mt-2 d-block"><i class="fa-solid fa-bug me-1"></i><b>Chế độ Siêu Âm:</b> Tiêu đề lấy được nhưng số bị Facebook giấu. Các biến Bot tìm thấy: {", ".join(sus_keys[:10])}</small>'
                else:
                    message = '<div class="alert alert-warning border-0"><i class="fa-solid fa-user-secret me-2"></i>Bot không thu thập được gì. Bài viết có thể bị ẩn!</div>'
            else:
                message = '<div class="alert alert-danger border-0"><i class="fa-solid fa-triangle-exclamation me-2"></i>Chỉ hỗ trợ Link YouTube và Facebook!</div>'

            if success and video_id and db_pool:
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
                    # Hiển thị thông báo thành công kèm Debug nếu có
                    message = f'<div class="alert alert-success border-0 bg-success bg-opacity-10 text-success"><i class="fa-solid fa-circle-check me-2"></i>Đã thu thập và lưu thành công: <b>{title}</b> {debug_msg}</div>'
                except Exception as db_err:
                    message = f'<div class="alert alert-danger border-0"><i class="fa-solid fa-database me-2"></i>Lỗi ghi DB: {str(db_err)}</div>'
                finally:
                    db_pool.putconn(conn)

        except Exception as e:
            message = f'<div class="alert alert-danger border-0"><i class="fa-solid fa-triangle-exclamation me-2"></i>Lỗi gọi API: {str(e)}</div>'

    saved_records = get_all_records()
    return render_template_string(HTML_TEMPLATE, message=message, records=saved_records)

if __name__ == "__main__":
    app.run(debug=True, port=5000)