from flask import Flask, request, render_template_string
import hashlib
import json
import os
import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import psycopg2
import requests
from apify_client import ApifyClient
from markupsafe import escape
from psycopg2 import pool

app = Flask(__name__)

# ==========================================
# CẤU HÌNH BIẾN MÔI TRƯỜNG & DATABASE
# ==========================================
API_KEY = os.getenv("YOUTUBE_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
APIFY_TOKEN = os.getenv("APIFY_TOKEN")


def init_database():
    """Tạo bảng và tự động bổ sung cột mới cho database cũ."""
    if not DATABASE_URL:
        app.logger.warning("DATABASE_URL chưa được cấu hình.")
        return None

    connection_pool = psycopg2.pool.ThreadedConnectionPool(1, 20, dsn=DATABASE_URL)
    conn = connection_pool.getconn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS video_stats (
                    video_id VARCHAR(500) PRIMARY KEY,
                    platform TEXT,
                    title TEXT,
                    video_type TEXT,
                    view_count BIGINT DEFAULT 0,
                    like_count BIGINT DEFAULT 0,
                    comment_count BIGINT DEFAULT 0,
                    share_count BIGINT DEFAULT 0
                )
                """
            )
            # CREATE TABLE IF NOT EXISTS không bổ sung cột cho bảng đã tồn tại.
            cursor.execute(
                """
                ALTER TABLE video_stats
                ADD COLUMN IF NOT EXISTS share_count BIGINT DEFAULT 0
                """
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        connection_pool.putconn(conn)

    return connection_pool


try:
    db_pool = init_database()
except Exception as exc:
    db_pool = None
    app.logger.exception("Lỗi khởi tạo Database Pool: %s", exc)


# ==========================================
# GIAO DIỆN HTML (UI/UX)
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
        .main-container { max-width: 1100px; margin-top: 3rem; margin-bottom: 5rem; }
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
        .table-custom th { color: #475569; font-size: 0.85rem; text-transform: uppercase; padding: 1rem; border-bottom: 2px solid #e2e8f0; font-weight: 700; white-space: nowrap; }
        .table-custom td { padding: 1rem; vertical-align: middle; border-bottom: 1px solid #f1f5f9; }
        .badge-type { font-size: 0.75rem; padding: 0.4em 0.7em; border-radius: 6px; background: #e2e8f0; color: #475569; font-weight: 600; }
        .video-title { font-weight: 600; color: #1e293b; max-width: 350px; display: inline-block; }
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
                            <th width="42%">Nội dung đã quét</th>
                            <th class="text-end">Lượt xem</th>
                            <th class="text-end">Lượt thích</th>
                            <th class="text-end">Bình luận</th>
                            <th class="text-end">Chia sẻ</th>
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
                            <td class="text-end fw-bold text-dark">{{ "{:,.0f}".format(row[4] or 0) }}</td>
                            <td class="text-end text-muted fw-medium">{{ "{:,.0f}".format(row[5] or 0) }}</td>
                            <td class="text-end text-muted fw-medium">{{ "{:,.0f}".format(row[6] or 0) }}</td>
                            <td class="text-end text-muted fw-medium">{{ "{:,.0f}".format(row[7] or 0) }}</td>
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
            const btn = document.getElementById('submitBtn');
            const waitMsg = document.getElementById('waitMsg');
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
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT video_id, platform, title, video_type,
                       view_count, like_count, comment_count, share_count
                FROM video_stats
                ORDER BY view_count DESC, like_count DESC
                LIMIT 50
                """
            )
            return cursor.fetchall()
    except Exception as exc:
        conn.rollback()
        app.logger.exception("Lỗi khi đọc Database: %s", exc)
        return []
    finally:
        db_pool.putconn(conn)


# ==========================================
# CHUẨN HÓA SỐ LIỆU FACEBOOK
# ==========================================
def parse_number(value):
    """Đổi int/float/string/dict summary thành số nguyên; không biến None thành 0."""
    if value is None or isinstance(value, bool):
        return None

    try:
        if isinstance(value, (int, float)):
            return int(value)

        if isinstance(value, dict):
            summary = value.get("summary")
            if isinstance(summary, dict):
                for key in ("total_count", "totalCount", "count", "total"):
                    parsed = parse_number(summary.get(key))
                    if parsed is not None:
                        return parsed

            for key in ("total_count", "totalCount", "count", "total", "value"):
                parsed = parse_number(value.get(key))
                if parsed is not None:
                    return parsed
            return None

        if isinstance(value, str):
            text = value.strip().upper().replace("\u00A0", "").replace(" ", "")
            if not text:
                return None

            multiplier = 1
            if text[-1:] in {"K", "M", "B"}:
                suffix = text[-1]
                text = text[:-1]
                multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[suffix]
                # Dạng 1,2K thường dùng dấu phẩy làm phần thập phân.
                if "," in text and "." not in text and text.count(",") == 1:
                    text = text.replace(",", ".")
                else:
                    text = text.replace(",", "")
            else:
                text = text.replace(",", "")

            text = re.sub(r"[^0-9.+-]", "", text)
            if not text:
                return None
            return int(float(text) * multiplier)
    except (TypeError, ValueError, OverflowError):
        return None

    return None


def numeric_candidates(item, keys):
    """Lấy toàn bộ giá trị hợp lệ ở các key, thay vì dừng ở key đầu tiên có số 0."""
    values = []
    for key in keys:
        if key not in item:
            continue
        parsed = parse_number(item.get(key))
        if parsed is not None:
            values.append(parsed)
    return values


def max_stat(item, keys):
    values = numeric_candidates(item, keys)
    return max(values) if values else 0


def extract_facebook_metrics(item):
    # Các key theo output hiện tại của apify/facebook-posts-scraper được đặt trước.
    views = max_stat(
        item,
        [
            "viewsCount",
            "videoPostViewCount",
            "videoViewCount",
            "viewCount",
            "playCount",
            "views",
            "play_count",
        ],
    )

    likes = max_stat(
        item,
        [
            "likes",                 # Tổng reaction theo schema hiện tại
            "topReactionsCount",
            "reactionsCount",
            "reactionCount",
            "likesCount",
            "postLikes",
            "reaction_count",
        ],
    )

    # Nếu tổng reaction không có, cộng từng loại reaction.
    reaction_sum = sum(
        max_stat(item, [key])
        for key in (
            "reactionLikeCount",
            "reactionLoveCount",
            "reactionHahaCount",
            "reactionWowCount",
            "reactionSadCount",
            "reactionAngryCount",
            "reactionCareCount",
        )
    )
    likes = max(likes, reaction_sum)

    # 'likers' có thể chỉ là danh sách/mẫu hoặc count cũ, không cho nó đè tổng reaction.
    if likes == 0:
        likes = max_stat(item, ["likers"])

    comments = max_stat(
        item,
        [
            "comments",              # Schema hiện tại
            "commentsCount",
            "commentCount",
            "postComments",
            "comment_count",
        ],
    )
    if comments == 0 and not numeric_candidates(
        item,
        ["comments", "commentsCount", "commentCount", "postComments", "comment_count"],
    ):
        comments = max_stat(item, ["total_comment_count"])

    shares = max_stat(
        item,
        [
            "shares",                # Schema hiện tại
            "sharesCount",
            "shareCount",
            "postShares",
            "share_count",
        ],
    )

    return views, likes, comments, shares


def normalize_facebook_url(url):
    """Chuẩn hóa domain và bỏ các tham số tracking nhưng giữ ID cần thiết."""
    if "fb.watch" in url.lower():
        raise ValueError(
            "Hệ thống chưa xử lý link fb.watch. Hãy mở link và copy URL facebook.com gốc."
        )

    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        url = "https://" + url

    parts = urlsplit(url)
    host = parts.netloc.lower()
    if host != "facebook.com" and not host.endswith(".facebook.com"):
        raise ValueError("URL Facebook không hợp lệ.")

    query = parse_qs(parts.query, keep_blank_values=True)
    keep_query = {}
    for key in ("story_fbid", "id", "fbid", "v"):
        if key in query:
            keep_query[key] = query[key]

    return urlunsplit(
        (
            "https",
            "www.facebook.com",
            re.sub(r"/{2,}", "/", parts.path),
            urlencode(keep_query, doseq=True),
            "",
        )
    )


def extract_facebook_content_id(url):
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    for key in ("story_fbid", "fbid", "v"):
        if query.get(key):
            return str(query[key][0])

    path = parts.path
    patterns = (
        r"/reel/(\d+)",
        r"/reels/(\d+)",
        r"/videos/(?:[^/]+/)?(\d+)",
        r"/posts/([^/?#]+)",
        r"/permalink/([^/?#]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, path, flags=re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def stable_fallback_id(url):
    return "fb_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def get_facebook_title(item, video_id):
    title_raw = (
        item.get("text")
        or item.get("message")
        or item.get("description")
        or item.get("title")
        or item.get("content")
        or ""
    )
    if isinstance(title_raw, dict):
        title_raw = title_raw.get("text") or title_raw.get("message") or ""

    title_raw = str(title_raw).strip()
    if not title_raw or title_raw == "None":
        author = item.get("user") or item.get("author") or item.get("pageName")
        if isinstance(author, dict):
            author_name = author.get("name") or author.get("pageName") or ""
        else:
            author_name = str(author or "").strip()
        title_raw = f"Bài viết của {author_name}" if author_name else ""

    if len(title_raw) > 65:
        return title_raw[:65] + "..."
    return title_raw or f"Nội dung Facebook ({video_id[:8]})"


def upsert_record(video_id, platform, title, video_type, views, likes, comments, shares):
    if not db_pool:
        raise RuntimeError("Database chưa được kết nối.")

    conn = db_pool.getconn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO video_stats (
                    video_id, platform, title, video_type,
                    view_count, like_count, comment_count, share_count
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (video_id) DO UPDATE SET
                    platform = EXCLUDED.platform,
                    title = EXCLUDED.title,
                    video_type = EXCLUDED.video_type,
                    view_count = CASE
                        WHEN EXCLUDED.view_count > 0 THEN EXCLUDED.view_count
                        ELSE COALESCE(video_stats.view_count, 0)
                    END,
                    like_count = CASE
                        WHEN EXCLUDED.like_count > 0 THEN EXCLUDED.like_count
                        ELSE COALESCE(video_stats.like_count, 0)
                    END,
                    comment_count = CASE
                        WHEN EXCLUDED.comment_count > 0 THEN EXCLUDED.comment_count
                        ELSE COALESCE(video_stats.comment_count, 0)
                    END,
                    share_count = CASE
                        WHEN EXCLUDED.share_count > 0 THEN EXCLUDED.share_count
                        ELSE COALESCE(video_stats.share_count, 0)
                    END
                """,
                (video_id, platform, title, video_type, views, likes, comments, shares),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        db_pool.putconn(conn)


@app.route("/", methods=["GET", "POST"])
def index():
    message = ""

    if request.method == "POST":
        url = (request.form.get("video_url") or "").strip()
        video_id = None
        title = ""
        video_type = "Video"
        platform = ""
        views = likes = comments = shares = 0
        success = False
        debug_msg = ""  # Phải khởi tạo cho cả nhánh YouTube lẫn Facebook.

        try:
            if "youtube.com" in url or "youtu.be" in url:
                platform = "youtube"
                if not API_KEY:
                    raise RuntimeError("YOUTUBE_API_KEY chưa được cấu hình.")

                if "/shorts/" in url:
                    video_type = "Shorts"
                    match = re.search(r"/shorts/([a-zA-Z0-9_-]{11})", url)
                else:
                    match = re.search(r"(?:v=|youtu\.be/|/embed/)([0-9A-Za-z_-]{11})", url)

                if not match:
                    raise ValueError("Định dạng link YouTube không hợp lệ.")

                video_id = match.group(1)
                api_url = "https://www.googleapis.com/youtube/v3/videos"
                response = requests.get(
                    api_url,
                    params={
                        "part": "statistics,snippet",
                        "id": video_id,
                        "key": API_KEY,
                    },
                    timeout=20,
                )
                response.raise_for_status()
                payload = response.json()

                if not payload.get("items"):
                    raise LookupError("Không tìm thấy video YouTube.")

                item = payload["items"][0]
                title = item["snippet"]["title"]
                stats = item.get("statistics", {})
                views = int(stats.get("viewCount", 0))
                likes = int(stats.get("likeCount", 0))
                comments = int(stats.get("commentCount", 0))
                shares = 0  # YouTube Data API không trả share count trong statistics.
                success = True

            elif "facebook.com" in url or "fb.watch" in url:
                platform = "facebook"
                if not APIFY_TOKEN:
                    raise RuntimeError("APIFY_TOKEN chưa được cấu hình.")

                safe_url = normalize_facebook_url(url)
                requested_id = extract_facebook_content_id(safe_url)

                client = ApifyClient(APIFY_TOKEN)
                run_input = {
                    "startUrls": [{"url": safe_url}],
                    "resultsLimit": 1,
                    "proxyConfiguration": {"useApifyProxy": True},
                }

                run = client.actor("apify/facebook-posts-scraper").call(run_input=run_input)
                dataset_id = getattr(run, "default_dataset_id", None)
                if not dataset_id and hasattr(run, "get"):
                    dataset_id = run.get("defaultDatasetId") or run.get("default_dataset_id")
                if not dataset_id:
                    raise RuntimeError("Apify run không trả defaultDatasetId.")

                items = client.dataset(dataset_id).list_items().items
                if not items:
                    raise LookupError("Bot không lấy được dữ liệu. Bài viết có thể không công khai hoặc Actor không hỗ trợ URL này.")

                item = items[0]

                raw_id = item.get("postId") or item.get("id") or item.get("post_id") or requested_id
                if isinstance(raw_id, dict):
                    raw_id = raw_id.get("id")
                video_id = str(raw_id or stable_fallback_id(safe_url))[:250]

                title = get_facebook_title(item, video_id)

                if "/reel/" in safe_url or "/reels/" in safe_url:
                    video_type = "Reels"
                elif "/posts/" in safe_url or "story_fbid=" in safe_url:
                    video_type = "Bài Viết FB"
                elif item.get("isVideo") or item.get("is_video") or "/videos/" in safe_url or "/watch" in safe_url:
                    video_type = "Video FB"
                else:
                    video_type = "Post FB"

                views, likes, comments, shares = extract_facebook_metrics(item)
                success = True

                metric_keys = {
                    key: item.get(key)
                    for key in item.keys()
                    if any(token in key.lower() for token in ("like", "reaction", "comment", "share", "view", "play"))
                }
                app.logger.info(
                    "Facebook metric fields (%s): %s",
                    safe_url,
                    json.dumps(metric_keys, ensure_ascii=False, default=str),
                )

                if views == likes == comments == shares == 0:
                    debug_msg = (
                        '<br><small class="text-danger mt-2 d-block">'
                        '<i class="fa-solid fa-bug me-1"></i>'
                        '<b>Không thấy số liệu công khai trong dataset.</b> '
                        'Kiểm tra log "Facebook metric fields" và dataset của lần chạy Apify.'
                        "</small>"
                    )
            else:
                raise ValueError("Chỉ hỗ trợ link YouTube và Facebook.")

            if success and video_id:
                upsert_record(
                    video_id,
                    platform,
                    title,
                    video_type,
                    views,
                    likes,
                    comments,
                    shares,
                )
                safe_title = escape(title)
                message = (
                    '<div class="alert alert-success border-0 bg-success bg-opacity-10 text-success">'
                    '<i class="fa-solid fa-circle-check me-2"></i>'
                    f'Đã thu thập và lưu thành công: <b>{safe_title}</b> '
                    f'— xem {views:,}, thích {likes:,}, bình luận {comments:,}, chia sẻ {shares:,}'
                    f'{debug_msg}</div>'
                )

        except Exception as exc:
            app.logger.exception("Lỗi thu thập dữ liệu: %s", exc)
            safe_error = escape(str(exc))
            message = (
                '<div class="alert alert-danger border-0">'
                '<i class="fa-solid fa-triangle-exclamation me-2"></i>'
                f'Lỗi: {safe_error}'
                '</div>'
            )

    saved_records = get_all_records()
    return render_template_string(HTML_TEMPLATE, message=message, records=saved_records)


if __name__ == "__main__":
    app.run(debug=True, port=5000)