-- Snowflake SQL. Illustrative validation queries for the production trend dataset.
-- These checks are representative and have not been executed against Snowflake.

-- Duplicate analytical dimensions must not be present.
SELECT week_start, network, segment_id, category, value, COUNT(*) AS row_count
FROM CRAWLTECH_ANALYTICS.WEEKLY_SOCIAL_TRENDS
GROUP BY week_start, network, segment_id, category, value
HAVING COUNT(*) > 1;

-- Counts must be nonnegative and a populated trend row must have a segment.
SELECT *
FROM CRAWLTECH_ANALYTICS.WEEKLY_SOCIAL_TRENDS
WHERE post_count < 0
   OR author_count < 0
   OR segment_id IS NULL;

-- Trend freshness can be monitored by comparing the latest generation timestamp.
SELECT MAX(generated_at) AS latest_generation_at
FROM CRAWLTECH_ANALYTICS.WEEKLY_SOCIAL_TRENDS;
