-- Seed analytics data for all videos (views, sessions, reactions, comments, subscriptions, watch history)
-- Skip the 3 DemoCreator videos that already have data.

DO $$
DECLARE
    like_id    UUID := '8fe6a79f-6fc7-58af-955c-96795238aa38';
    dislike_id UUID := '2154b11c-8c8c-5b7d-b9c0-6e90c91aed91';
    viewer_ids UUID[];
    vcount     INT;
BEGIN
    SELECT ARRAY(SELECT id FROM users WHERE username LIKE 'viewer_%' ORDER BY id)
    INTO viewer_ids;
    vcount := array_length(viewer_ids, 1);

    RAISE NOTICE 'Loaded % viewer users', vcount;

    -- ── 1. video_views (anonymous) ────────────────────────────────────────────
    RAISE NOTICE 'Inserting video_views...';
    INSERT INTO video_views (id, video_id, user_id, viewed_at, source_type)
    SELECT
        gen_random_uuid(),
        t.vid,
        NULL,
        t.created_at + (t.ts_frac * EXTRACT(EPOCH FROM (NOW() - t.created_at)) * INTERVAL '1 second'),
        CASE
            WHEN t.r < 0.10 THEN 'direct'
            WHEN t.r < 0.40 THEN 'search'
            WHEN t.r < 0.65 THEN 'recommendation'
            WHEN t.r < 0.75 THEN 'external'
            WHEN t.r < 0.90 THEN 'channel_page'
            ELSE                 'subscriptions'
        END
    FROM (
        SELECT v.id AS vid, v.created_at, random() AS ts_frac, random() AS r
        FROM videos v, generate_series(1, v.views_count) gs
        WHERE v.id NOT IN (
            '00000000-0000-0000-0000-000000000010',
            '00000000-0000-0000-0000-000000000011',
            '00000000-0000-0000-0000-000000000012'
        )
        AND v.views_count > 0
    ) t;

    GET DIAGNOSTICS vcount = ROW_COUNT;
    RAISE NOTICE 'Inserted % view rows', vcount;

    -- ── 2. video_watch_sessions (~40 %% of views, 90 s videos) ───────────────
    RAISE NOTICE 'Inserting watch sessions...';
    INSERT INTO video_watch_sessions
        (id, video_id, user_id, started_at, updated_at,
         watched_seconds, video_duration_seconds, completed_percent)
    SELECT
        gen_random_uuid(),
        t.vid,
        NULL,
        t.ts,
        t.ts,
        t.watched,
        90,
        t.watched / 90.0
    FROM (
        SELECT
            v.id AS vid,
            v.created_at + (random() * EXTRACT(EPOCH FROM (NOW() - v.created_at)) * INTERVAL '1 second') AS ts,
            LEAST(90, GREATEST(3, (power(random(), 0.6) * 90)::INT)) AS watched
        FROM videos v, generate_series(1, GREATEST(1, (v.views_count * 0.40)::INT)) gs
        WHERE v.id NOT IN (
            '00000000-0000-0000-0000-000000000010',
            '00000000-0000-0000-0000-000000000011',
            '00000000-0000-0000-0000-000000000012'
        )
        AND v.views_count > 0
    ) t;

    GET DIAGNOSTICS vcount = ROW_COUNT;
    RAISE NOTICE 'Inserted % session rows', vcount;

    -- ── 3. video_reactions – likes ────────────────────────────────────────────
    RAISE NOTICE 'Inserting likes...';
    INSERT INTO video_reactions (id, user_id, video_id, reaction_type_id, created_at)
    SELECT
        gen_random_uuid(),
        viewer_ids[gs.n],
        v.id,
        like_id,
        v.created_at + (random() * EXTRACT(EPOCH FROM (NOW() - v.created_at)) * INTERVAL '1 second')
    FROM videos v,
         generate_series(1, LEAST(v.likes_count, array_length(viewer_ids, 1))) gs(n)
    WHERE v.id NOT IN (
        '00000000-0000-0000-0000-000000000010',
        '00000000-0000-0000-0000-000000000011',
        '00000000-0000-0000-0000-000000000012'
    )
    AND v.likes_count > 0
    ON CONFLICT DO NOTHING;

    -- ── 4. video_reactions – dislikes (use last N viewers) ────────────────────
    RAISE NOTICE 'Inserting dislikes...';
    INSERT INTO video_reactions (id, user_id, video_id, reaction_type_id, created_at)
    SELECT
        gen_random_uuid(),
        viewer_ids[array_length(viewer_ids, 1) - gs.n + 1],
        v.id,
        dislike_id,
        v.created_at + (random() * EXTRACT(EPOCH FROM (NOW() - v.created_at)) * INTERVAL '1 second')
    FROM videos v,
         generate_series(1, LEAST(v.dislikes_count, 50)) gs(n)
    WHERE v.id NOT IN (
        '00000000-0000-0000-0000-000000000010',
        '00000000-0000-0000-0000-000000000011',
        '00000000-0000-0000-0000-000000000012'
    )
    AND v.dislikes_count > 0
    ON CONFLICT DO NOTHING;

    -- ── 5. comments ───────────────────────────────────────────────────────────
    RAISE NOTICE 'Inserting comments...';
    INSERT INTO comments (id, user_id, video_id, content, created_at, likes_count, dislikes_count)
    SELECT
        gen_random_uuid(),
        viewer_ids[1 + (floor(random() * array_length(viewer_ids, 1)))::INT],
        v.id,
        (ARRAY[
            'Great content, really enjoyed this one!',
            'This was exactly what I needed, thank you!',
            'Can you make more videos like this?',
            'Amazing quality, subscribed!',
            'I watched this three times already.',
            'Best explanation I have found on this topic.',
            'You deserve way more subscribers!',
            'Sharing this with all my friends.',
            'Loved the editing style here.',
            'This helped me so much, keep it up!',
            'The production quality is top notch.',
            'Very clear and easy to follow.',
            'Finally someone explained this properly.',
            'Instant like from me!',
            'Came here from a recommendation — not disappointed.',
            'Such a calm and relaxing video.',
            'This popped up in my feed and I have no regrets.',
            'You make this look so easy.',
            'Looking forward to the next upload!',
            'Already saved this to my playlist.',
            'This is the content the internet was made for.',
            'Short and straight to the point, love it.',
            'I have been following you for a while and this is your best yet.',
            'Absolutely worth watching all the way through.',
            'More people should see this!'
        ])[1 + (floor(random() * 25))::INT],
        v.created_at + (random() * EXTRACT(EPOCH FROM (NOW() - v.created_at)) * INTERVAL '1 second'),
        (random() * 40)::INT,
        (random() * 3)::INT
    FROM videos v, generate_series(1,
        CASE
            WHEN v.views_count >= 1500 THEN 28
            WHEN v.views_count >= 900  THEN 18
            WHEN v.views_count >= 500  THEN 12
            ELSE 6
        END
    ) gs
    WHERE v.id NOT IN (
        '00000000-0000-0000-0000-000000000010',
        '00000000-0000-0000-0000-000000000011',
        '00000000-0000-0000-0000-000000000012'
    )
    AND v.views_count > 0;

    GET DIAGNOSTICS vcount = ROW_COUNT;
    RAISE NOTICE 'Inserted % comments', vcount;

    -- ── 6. subscriptions (each viewer subscribes to ~25 %% of channels) ──────
    RAISE NOTICE 'Inserting subscriptions...';
    INSERT INTO subscriptions (subscriber_id, channel_id, notifications_enabled, created_at)
    SELECT DISTINCT ON (u.id, c.id)
        u.id,
        c.id,
        random() > 0.5,
        NOW() - (random() * 400 * INTERVAL '1 day')
    FROM users u
    CROSS JOIN channels c
    WHERE u.username LIKE 'viewer_%'
    AND random() < 0.28
    ON CONFLICT DO NOTHING;

    GET DIAGNOSTICS vcount = ROW_COUNT;
    RAISE NOTICE 'Inserted % subscriptions', vcount;

    -- ── 7. watch_history (each viewer watches ~10 %% of videos) ──────────────
    RAISE NOTICE 'Inserting watch_history...';
    INSERT INTO watch_history (id, user_id, video_id, last_watched_at)
    SELECT DISTINCT ON (u.id, v.id)
        gen_random_uuid(),
        u.id,
        v.id,
        NOW() - (random() * 400 * INTERVAL '1 day')
    FROM users u
    CROSS JOIN videos v
    WHERE u.username LIKE 'viewer_%'
    AND random() < 0.10
    ON CONFLICT (user_id, video_id) DO NOTHING;

    GET DIAGNOSTICS vcount = ROW_COUNT;
    RAISE NOTICE 'Inserted % watch_history rows', vcount;

    -- ── 8. update channels.subscribers_count ─────────────────────────────────
    RAISE NOTICE 'Updating channel subscriber counts...';
    UPDATE channels ch
    SET subscribers_count = (
        SELECT count(*) FROM subscriptions s WHERE s.channel_id = ch.id
    );

    RAISE NOTICE 'Done!';
END $$;
