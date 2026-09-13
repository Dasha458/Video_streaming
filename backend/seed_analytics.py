"""
Seed script: creates a demo user, channel, 3 videos + realistic analytics data.
Run: python seed_analytics.py
Requires: psycopg2-binary or psycopg2
"""

import random
import uuid
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_DNS, uuid5

import psycopg2
from psycopg2.extras import execute_values

# ── Connection ─────────────────────────────────────────────────────────────
DB = dict(
    host="postgres",
    port=5432,
    dbname="VideoDB",
    user="postgres",
    password="test_pass",
)

# ── Deterministic IDs (same as application code) ───────────────────────────
PRIVACY_PUBLIC  = uuid5(NAMESPACE_DNS, "privacy_status:public")
PRIVACY_PRIVATE = uuid5(NAMESPACE_DNS, "privacy_status:private")

STATUS_PROCESSING = uuid5(NAMESPACE_DNS, "video_status:processing")
STATUS_QUEUED     = uuid5(NAMESPACE_DNS, "video_status:queued")
STATUS_READY      = uuid5(NAMESPACE_DNS, "video_status:ready")
STATUS_FAILED     = uuid5(NAMESPACE_DNS, "video_status:failed")

CAT_EDUCATION     = uuid5(NAMESPACE_DNS, "video_category:education")
CAT_TECH          = uuid5(NAMESPACE_DNS, "video_category:technology")
CAT_ENTERTAINMENT = uuid5(NAMESPACE_DNS, "video_category:entertainment")

REACT_LIKE    = uuid5(NAMESPACE_DNS, "reaction_type:like")
REACT_DISLIKE = uuid5(NAMESPACE_DNS, "reaction_type:dislike")

ROLE_USER   = uuid5(NAMESPACE_DNS, "role:user")
STATUS_ACTIVE = uuid5(NAMESPACE_DNS, "user_status:active")

# ── Fixed seed IDs ──────────────────────────────────────────────────────────
DEMO_USER_ID    = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEMO_CHANNEL_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
VIDEO_IDS = [
    uuid.UUID("00000000-0000-0000-0000-000000000010"),
    uuid.UUID("00000000-0000-0000-0000-000000000011"),
    uuid.UUID("00000000-0000-0000-0000-000000000012"),
]

SOURCES = ["direct", "search", "recommendation", "external", "channel_page", "subscriptions"]


def now_tz() -> datetime:
    return datetime.now(timezone.utc)


def days_ago(n: float) -> datetime:
    return now_tz() - timedelta(days=n)


def run():
    conn = psycopg2.connect(**DB)
    conn.autocommit = False
    cur = conn.cursor()

    print("Seeding lookup tables…")

    # ── Lookup: user_statuses ───────────────────────────────────────────────
    cur.execute("""
        INSERT INTO user_statuses (id, value) VALUES (%s, %s)
        ON CONFLICT (id) DO NOTHING
    """, (str(STATUS_ACTIVE), "active"))

    # ── Lookup: roles ───────────────────────────────────────────────────────
    cur.execute("""
        INSERT INTO roles (id, name) VALUES (%s, %s)
        ON CONFLICT (id) DO NOTHING
    """, (str(ROLE_USER), "user"))

    # ── Lookup: privacy_statuses ────────────────────────────────────────────
    for pid, name in [(PRIVACY_PUBLIC, "public"), (PRIVACY_PRIVATE, "private")]:
        cur.execute("""
            INSERT INTO privacy_statuses (id, name) VALUES (%s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (str(pid), name))

    # ── Lookup: video_statuses ──────────────────────────────────────────────
    for sid, val in [
        (STATUS_PROCESSING, "processing"),
        (STATUS_QUEUED, "queued"),
        (STATUS_READY, "ready"),
        (STATUS_FAILED, "failed"),
    ]:
        cur.execute("""
            INSERT INTO video_statuses (id, value) VALUES (%s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (str(sid), val))

    # ── Lookup: categories ──────────────────────────────────────────────────
    for cid, cname in [
        (CAT_EDUCATION, "education"),
        (CAT_TECH, "technology"),
        (CAT_ENTERTAINMENT, "entertainment"),
    ]:
        cur.execute("""
            INSERT INTO categories (id, name) VALUES (%s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (str(cid), cname))

    # ── Lookup: reaction_types ──────────────────────────────────────────────
    for rid, rname in [(REACT_LIKE, "like"), (REACT_DISLIKE, "dislike")]:
        cur.execute("""
            INSERT INTO reaction_types (id, name) VALUES (%s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (str(rid), rname))

    print("Seeding demo user + channel…")

    # ── Demo user ───────────────────────────────────────────────────────────
    # bcrypt hash of "Demo1234!" — generated offline
    HASHED_PW = "$2b$12$3WTcZMH1kFGRsVP1zF7Bv.Fk7hqGXpqZG9vPzHHMc0kq1L5Zk8Y6"
    cur.execute("""
        INSERT INTO users (id, username, email, hashed_password, is_active, is_superuser, is_verified, created_at)
        VALUES (%s, %s, %s, %s, true, false, true, %s)
        ON CONFLICT (id) DO NOTHING
    """, (str(DEMO_USER_ID), "DemoCreator", "demo@streamhub.test", HASHED_PW, days_ago(90)))

    # ── Demo channel ────────────────────────────────────────────────────────
    cur.execute("""
        INSERT INTO channels (id, name, user_id, subscribers_count, views_count, description, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """, (
        str(DEMO_CHANNEL_ID),
        "DemoCreator",
        str(DEMO_USER_ID),
        3840,
        95200,
        "Tech tutorials, education and entertainment.",
        days_ago(90),
    ))

    # ── Videos ─────────────────────────────────────────────────────────────
    videos_meta = [
        (VIDEO_IDS[0], "Python Async Explained in 15 Minutes",
         "Deep dive into asyncio, tasks and event loops.", CAT_TECH,    days_ago(60),  120800, 9400, 310),
        (VIDEO_IDS[1], "Build a REST API with FastAPI",
         "Step-by-step FastAPI tutorial with auth.",       CAT_EDUCATION, days_ago(30), 64300,  5100, 190),
        (VIDEO_IDS[2], "Top 10 VS Code Extensions 2026",
         "Must-have extensions for Python developers.",    CAT_ENTERTAINMENT, days_ago(7), 18700, 1820,  85),
    ]

    for vid, title, desc, cat_id, created_at, views_count, likes_count, dislikes_count in videos_meta:
        cur.execute("""
            INSERT INTO videos
              (id, name, description, size, hash, channel_id,
               privacy_id, category_id, status_id,
               views_count, likes_count, dislikes_count, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
        """, (
            str(vid), title, desc,
            random.randint(50_000_000, 500_000_000),
            str(uuid.uuid4()),
            str(DEMO_CHANNEL_ID),
            str(PRIVACY_PUBLIC), str(cat_id), str(STATUS_READY),
            views_count, likes_count, dislikes_count,
            created_at, created_at,
        ))

    print("Seeding video views…")

    # ── Video views (last 30 days, realistic daily distribution) ───────────
    view_rows = []
    for vid_idx, video_id in enumerate(VIDEO_IDS):
        days_active = [60, 30, 7][vid_idx]
        total_views  = [800, 450, 180][vid_idx]
        for _ in range(total_views):
            age_days  = random.uniform(0, days_active)
            viewed_at = now_tz() - timedelta(days=age_days)
            source    = random.choices(
                SOURCES,
                weights=[10, 30, 25, 10, 15, 10],
            )[0]
            view_rows.append((str(uuid.uuid4()), str(video_id), None, viewed_at, source))

    execute_values(cur,
        "INSERT INTO video_views (id, video_id, user_id, viewed_at, source_type) VALUES %s ON CONFLICT DO NOTHING",
        view_rows,
    )

    print("Seeding watch sessions…")

    # ── Watch sessions ──────────────────────────────────────────────────────
    session_rows = []
    durations = [900, 1800, 600]   # video durations in seconds
    for vid_idx, video_id in enumerate(VIDEO_IDS):
        duration = durations[vid_idx]
        n_sessions = [300, 170, 70][vid_idx]
        for _ in range(n_sessions):
            age_days   = random.uniform(0, [60, 30, 7][vid_idx])
            started_at = now_tz() - timedelta(days=age_days)
            watched    = int(random.betavariate(2, 1.5) * duration)
            pct        = round(watched / duration, 4)
            session_rows.append((
                str(uuid.uuid4()), str(video_id), None,
                started_at, started_at,
                watched, duration, pct,
            ))

    execute_values(cur, """
        INSERT INTO video_watch_sessions
          (id, video_id, user_id, started_at, updated_at, watched_seconds, video_duration_seconds, completed_percent)
        VALUES %s ON CONFLICT DO NOTHING
    """, session_rows)

    print("Seeding reactions…")

    # ── Reactions (likes/dislikes from unique fake users) ───────────────────
    reaction_rows = []
    for vid_idx, video_id in enumerate(VIDEO_IDS):
        n_likes    = [9400, 5100, 1820][vid_idx]
        n_dislikes = [310, 190, 85][vid_idx]
        for _ in range(min(n_likes, 200)):          # cap at 200 per video for speed
            fake_uid = uuid.uuid4()
            reaction_rows.append((str(uuid.uuid4()), str(fake_uid), str(video_id), str(REACT_LIKE), now_tz()))
        for _ in range(min(n_dislikes, 50)):
            fake_uid = uuid.uuid4()
            reaction_rows.append((str(uuid.uuid4()), str(fake_uid), str(video_id), str(REACT_DISLIKE), now_tz()))

    execute_values(cur, """
        INSERT INTO video_reactions (id, user_id, video_id, reaction_type_id, created_at)
        VALUES %s ON CONFLICT DO NOTHING
    """, reaction_rows)

    print("Seeding comments…")

    # ── Comments ────────────────────────────────────────────────────────────
    sample_comments = [
        "Great video, very clear explanation!",
        "This helped me understand async so much better.",
        "Can you do a follow-up on error handling?",
        "Best tutorial on this topic I have found.",
        "Thanks for the detailed breakdown.",
        "I have been struggling with this for days, finally got it!",
        "The live coding examples are really helpful.",
        "Please do more FastAPI content.",
        "Subscribed, looking forward to more!",
        "Excellent content as always.",
    ]
    comment_rows = []
    for vid_idx, video_id in enumerate(VIDEO_IDS):
        n_comments = [40, 25, 12][vid_idx]
        for i in range(n_comments):
            age_days = random.uniform(0, [60, 30, 7][vid_idx])
            created  = now_tz() - timedelta(days=age_days)
            comment_rows.append((
                str(uuid.uuid4()),
                str(DEMO_USER_ID),
                str(video_id),
                random.choice(sample_comments),
                created,
                created,
            ))

    execute_values(cur, """
        INSERT INTO comments (id, user_id, video_id, content, created_at, updated_at)
        VALUES %s ON CONFLICT DO NOTHING
    """, comment_rows)

    conn.commit()
    cur.close()
    conn.close()

    print()
    print("=" * 50)
    print("Seed complete!")
    print(f"  User:    DemoCreator  /  demo@streamhub.test")
    print(f"  Channel: DemoCreator")
    print(f"  Videos:  3 (with views, watch sessions, reactions, comments)")
    print()
    print("To view analytics:")
    print("  1. http://localhost  →  login as demo@streamhub.test  /  Demo1234!")
    print("  2. Click avatar (top-right)  →  Creator Studio")
    print("  3. In Studio click any video title  →  Video Analytics")
    print("=" * 50)


if __name__ == "__main__":
    run()
