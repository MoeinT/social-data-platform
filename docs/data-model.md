# Data Model

## Operational entities

| Area | Tables | Purpose |
| --- | --- | --- |
| Source identity | `social_networks`, `authors`, `posts` | Natural keys are network name, `(network_id, external_id)` for authors, and `(network_id, external_id)` for posts. |
| Media | `images`, `post_images` | `images.sha256` deduplicates content globally; the association table permits multiple images per post and the same image to appear on several posts. Bytes remain in file/object storage. |
| Analysis | `analysis_results`, `detected_attributes`, `bounding_boxes` | One result per `(image_id, analyzer_name, analyzer_version)` preserves re-analysis across versions. Child rows are scoped to that immutable result. |
| Segmentation | `segments`, `author_segment_assignments`, `post_segment_assignments` | Many-to-many membership and explicit post overrides, with source, actor, reason, and effective dates. |
| Operations | `crawl_runs`, `crawl_batches`, `data_quality_results` | Durable execution state and repeatable quality outcomes. |
| Local analytics | `trend_metrics` | Rebuildable local analogue of the Snowflake trend dataset; not the production warehouse. |

## Assignment history

Assignment rows use `valid_from` inclusive and `valid_to` exclusive. A null `valid_to` marks the current membership. Changing/removing an assignment closes the current row and retains it; manual and automated sources are both recorded. Each author can have multiple active segments. A post may also have explicit segment overrides; when at least one current post override exists, it takes precedence over author memberships for that post's trend classification.

The operational repository serializes updates to one assignment in a transaction and adjusts equal/backdated boundaries by one microsecond to keep a positive interval. A production Snowflake model should carry the same interval fields and use effective-time joins for historical point-in-time reporting rather than replacing old rows.

## Keys and deduplication

- Author and post external IDs are unique within a network, not globally.
- Image SHA-256 is the content key. The local adapter materializes deterministic bytes from each source reference, so multiple references may deduplicate to one file and database row.
- The post-image edge has a unique `(post_id, image_id)` key and a unique ordinal per post. Reprocessing an edge is harmless.
- Analysis results are unique by image and analyzer version. Re-running the same version is a no-op; a new version creates a new fact set.
- Analytical rows are grouped by week, network, segment, attribute category, and value. The source query can see several matching images for one post, but aggregates use distinct post and author IDs. One carousel therefore contributes one post to a given trend dimension.

The local PostgreSQL schema is created by Alembic (`alembic upgrade head`). SQLAlchemy metadata is the initial migration's source, while later schema changes should use forward-only Alembic revisions.