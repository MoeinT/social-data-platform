-- Snowflake SQL. Production analytical transformation; not executed against Snowflake.
-- Assumes incremental loads have populated the CRAWLTECH_ANALYTICS schema from
-- operational CDC/snapshots and that segment assignment history is retained.

CREATE OR REPLACE DYNAMIC TABLE CRAWLTECH_ANALYTICS.WEEKLY_SOCIAL_TRENDS
    TARGET_LAG = '1 hour'
    WAREHOUSE = TRANSFORMING_WH
AS
WITH current_author_segments AS (
    SELECT author_id, segment_id
    FROM CRAWLTECH_ANALYTICS.AUTHOR_SEGMENT_ASSIGNMENTS
    WHERE valid_from <= CURRENT_TIMESTAMP()
      AND (valid_to IS NULL OR valid_to > CURRENT_TIMESTAMP())
),
current_post_overrides AS (
    SELECT post_id, segment_id
    FROM CRAWLTECH_ANALYTICS.POST_SEGMENT_ASSIGNMENTS
    WHERE valid_from <= CURRENT_TIMESTAMP()
      AND (valid_to IS NULL OR valid_to > CURRENT_TIMESTAMP())
),
post_attributes AS (
    SELECT DISTINCT
        p.post_id,
        p.author_id,
        p.network,
        DATE_TRUNC('WEEK', p.published_at)::DATE AS week_start,
        a.category,
        a.value,
        COALESCE(pso.segment_id, cas.segment_id) AS segment_id
    FROM CRAWLTECH_ANALYTICS.POSTS AS p
    INNER JOIN CRAWLTECH_ANALYTICS.POST_IMAGES AS pi
        ON pi.post_id = p.post_id
    INNER JOIN CRAWLTECH_ANALYTICS.ANALYSIS_RESULTS AS ar
        ON ar.image_id = pi.image_id
       AND ar.status = 'succeeded'
    INNER JOIN CRAWLTECH_ANALYTICS.DETECTED_ATTRIBUTES AS a
        ON a.analysis_id = ar.analysis_id
    LEFT JOIN current_post_overrides AS pso
        ON pso.post_id = p.post_id
    LEFT JOIN current_author_segments AS cas
        ON cas.author_id = p.author_id
    WHERE ar.analyzer_name = 'mock-vision'
      AND ar.analyzer_version = '1.0.0'
)
SELECT
    week_start,
    network,
    segment_id,
    category,
    value,
    COUNT(DISTINCT post_id) AS post_count,
    COUNT(DISTINCT author_id) AS author_count,
    CURRENT_TIMESTAMP() AS generated_at
FROM post_attributes
WHERE segment_id IS NOT NULL
GROUP BY week_start, network, segment_id, category, value;