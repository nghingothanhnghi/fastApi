# CMS Module

Headless CMS for the platform: categories, tags, media library, posts/pages (with scheduled publishing) and navigation menus. It reuses the existing `users` table and role system for authors and permissions.

```
app/cms/
├── config.py        # media dir/url, allowed extensions, size limit, pagination defaults
├── models/          # SQLAlchemy: category, tag, media, post, menu
├── schemas/         # Pydantic request/response models
├── services/        # business logic (singletons: post_service, media_service, ...)
├── controllers/     # thin layer: 404 mapping, response shaping
├── routes/          # FastAPI routers, aggregated into `cms_router`
├── jobs/            # scheduled_publish_job.py (runs every 60s)
└── utils/slugify.py # slugify + make_unique_slug
```

Layering: `routes -> controllers -> services -> models`. Routes handle HTTP and auth, services own all logic and DB access.

## Wiring (main.py)

- `app.include_router(cms_router)` exposes all `/cms/*` endpoints.
- `app.mount(CMS_MEDIA_URL, StaticFiles(directory=CMS_MEDIA_DIR))` serves uploaded files (default `/static/cms_media`).
- `add_job(publish_scheduled_posts_job, seconds=60)` auto-publishes due posts.
- Models are imported in `app/init_db.py` so tables are created with the rest of the schema.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `CMS_MEDIA_DIR` | `uploads/cms_media` | Where uploads are stored on disk |
| `CMS_MEDIA_URL` | `/static/cms_media` | Public URL prefix |
| `CMS_MAX_MEDIA_SIZE_MB` | `20` | Upload size limit |

Allowed extensions: `.jpg .jpeg .png .gif .webp .svg .pdf .mp4 .webm`.

## Data model

| Table | Notes |
|---|---|
| `cms_categories` | Self-referential `parent_id` (unlimited nesting), unique `slug` |
| `cms_tags` | Unique `name` and `slug`; many-to-many with posts via `cms_post_tags` |
| `cms_media` | One row per uploaded file: `url`, `mime_type`, `file_size`, `alt_text`, `uploaded_by_id` |
| `cms_posts` | `post_type` (post/page), `status` (draft/published/scheduled/archived), SEO fields, `is_featured`, `view_count`, `scheduled_at`, `published_at`, FK to author, category, featured image |
| `cms_menus` / `cms_menu_items` | Menu with optional unique `location` (e.g. `header`); items are a tree, target is `custom` URL, `category` or `post` |

## API

Auth legend: **public** = no auth, **user** = any logged-in user, **mod** = ADMIN/MODERATOR (SUPER_ADMIN always passes), **admin** = ADMIN.

### Categories `/cms/categories`
| Method | Path | Auth |
|---|---|---|
| GET | `` (`?parent_id=`) | public |
| GET | `/{id}` | public |
| POST | `` | mod |
| PUT | `/{id}` | mod |
| DELETE | `/{id}` | admin |

### Tags `/cms/tags`
| Method | Path | Auth |
|---|---|---|
| GET | `` | public |
| POST | `` | mod |
| DELETE | `/{id}` | admin |

### Media `/cms/media`
| Method | Path | Auth |
|---|---|---|
| POST | `/upload` (multipart `file`, `alt_text`) | user |
| GET | `` (`skip`, `limit`) | public |
| GET | `/{id}` | public |
| PATCH | `/{id}` (form `alt_text`) | user |
| DELETE | `/{id}` | user |

### Posts `/cms/posts`
| Method | Path | Auth |
|---|---|---|
| POST | `` | user |
| GET | `` (`status, post_type, category_id, tag_id, author_id, search, page, page_size`) | public |
| GET | `/slug/{slug}` (`track_view`) | public |
| GET | `/{id}` | public |
| PUT / DELETE | `/{id}` | author or editor |
| POST | `/{id}/publish`, `/archive` | author or editor |
| POST | `/{id}/schedule` (`{"scheduled_at": ...}`) | author or editor |

### Menus `/cms/menus`
| Method | Path | Auth |
|---|---|---|
| GET | `` | public |
| GET | `/location/{location}` (`active_only`) | public |
| GET | `/{id}` (`active_only`) | public |
| POST / PUT / DELETE | `` / `/{id}` | mod / mod / admin |
| POST | `/{id}/items` | mod |
| PUT / DELETE | `/items/{item_id}` | mod |
| POST | `/{id}/items/reorder` | mod |

## Typical flows

**Publish a post with an image**
1. `POST /cms/media/upload` -> note `id`.
2. `POST /cms/posts` with `featured_image_id`, `tag_ids`, `category_id`, `status`.
3. Frontend renders via `GET /cms/posts/slug/{slug}`.

**Schedule a post**: `POST /cms/posts/{id}/schedule` -> status becomes `scheduled`; the job flips it to `published` within ~60s after `scheduled_at`.

**Site navigation**: create a menu with `location="header"`, add items, fetch with `GET /cms/menus/location/header`. Category/post items get a `resolved_url` (`/categories/{slug}`, `/posts/{slug}`).

---

## Review: gaps and recommended improvements

Findings from reading the code, ordered by priority. None of these have been applied yet.

### P0 - Bugs / security

1. **Drafts, scheduled and archived posts are publicly readable.** `GET /cms/posts`, `/{id}` and `/slug/{slug}` have no auth and no status filter, so anyone can list `status=draft` or open an unpublished post by slug. Fix: public endpoints should force `status=published` (and `published_at <= now`); only authenticated editors/authors may see other statuses (e.g. add `/cms/posts/admin` or check the optional user).
2. **Menu reorder 500s on an unknown menu.** `reorder_items` calls `self.get_menu(db, menu_id).items` without a None check, and `create_item` correctly 404s but `reorder` does not. Also `menu_controller` builds responses with `{**menu.__dict__, ...}`, which leaks SQLAlchemy internals (`_sa_instance_state`) and breaks on expired/lazy attributes; build a `MenuOut` explicitly instead.
3. **Media: any logged-in user can edit/delete any file.** `PATCH`/`DELETE /cms/media/{id}` only require `get_current_user`. Restrict to the uploader or a moderator, and block deletion of media still referenced by a post (`featured_image_id`) or embedded in content.
4. **Upload validation is extension-only.** A renamed file passes. Check magic bytes / `content_type` against the extension. `.svg` can carry scripts (stored XSS when served from your own origin): sanitize it or serve with `Content-Disposition: attachment` / a CSP header, or drop it from the allow-list.
5. **Delete-media path handling.** The filename is taken from `media.url` and joined to `CMS_MEDIA_DIR`; safe today because URLs are server-generated, but store the stored filename in its own column instead of parsing the URL.
6. **Unsafe `content` HTML.** Post `content` is stored raw. If the frontend renders HTML, sanitize on write (e.g. `bleach`/`nh3`) or document that the client must.
7. **`PostUpdate` can break the scheduling invariant.** `scheduled_at` is not checked to be in the future on update (only on create and `/schedule`), and naive datetimes are treated as UTC silently. Reuse one helper (`_ensure_future_utc`) in all three places.
8. **Category cycles.** `CategoryUpdate.parent_id` can set a category as its own parent or create a loop (A -> B -> A); `parent_id` existence is also unchecked. Validate in `category_service`. Same for `parent_id` on menu items (`update_item` only blocks self-parenting, not deeper loops, and does not check the parent is in the same menu).
9. **Referential checks missing on create/update post.** `category_id`, `featured_image_id` and unknown `tag_ids` are silently ignored or fail with a raw FK `IntegrityError` (500). Return 400/404 with a clear message.
10. **Slug race + unique constraints.** `make_unique_slug` is check-then-insert; concurrent requests can hit the unique index and return 500. Catch `IntegrityError` and retry. `TagCreate` with an existing name also 500s (unique `name`): use `get_or_create_tag` semantics or return 409.

### P1 - Correctness / quality

- **`delete_category` / `delete_tag` have no usage protection.** Deleting a parent category sets children and posts to `NULL` silently; decide on policy (block, reassign, or cascade) and document it.
- **`view_count` is incremented on every hit**, including bots and refreshes, and the response returned is the pre-increment object. Consider de-duplicating (IP/session + short TTL) or moving to async/batched counting.
- **`slugify` drops non-ASCII text** (`NFKD` + ASCII). Vietnamese titles like "Hệ thống thủy canh" lose characters and "đ" disappears. Add an explicit `đ -> d` mapping (and optionally `python-slugify` / `unidecode`). Titles that fully reduce to nothing become `n-a`, which then collides as `n-a-2`, `n-a-3`.
- **Search is a plain `ILIKE` on title/excerpt** only. Not searching `content`, and unindexed. For Postgres add `tsvector` + GIN index.
- **List endpoints are inconsistent.** Posts are paginated with a total; media/categories/tags are not, and `DEFAULT_PAGE_SIZE`/`MAX_PAGE_SIZE` in `config.py` are not used (routes hardcode 20/100/50/200). Use the config values and one shared `Paginated[T]` schema.
- **Menu endpoints have no `response_model`.** Responses are untyped dicts, so OpenAPI docs show nothing and `MenuOut` is unused. Declare `response_model` on every menu route.
- **Menu tree N+1.** `resolve_item_url` queries per item. Prefetch all referenced categories/posts in two queries, then resolve from dicts. Also resolve only `published` posts, otherwise menus can link to drafts.
- **Dead/unused code.** `from app.cms.models import post` in `post_service.py` shadows the local variable name `post`; `PostBase` has a validator while `PostUpdate` duplicates it; `Path(...).mkdir` runs at import time in `config.py` and again in `main.py` and the service.
- **`updated_at` uses `onupdate`** only, so it is `NULL` until the first edit. Prefer `server_default=func.now()` too.
- **Timezone handling**: `scheduled_at` stored `timezone=True`, but the API accepts naive values and assumes UTC. Document it, or reject naive datetimes.
- **Scheduler is single-process only.** If the app runs several workers/instances, each runs the job. The update is idempotent, but use `SELECT ... FOR UPDATE SKIP LOCKED` to avoid duplicate work and notifications.

### P2 - Features worth adding

- **Revisions / autosave** (`cms_post_revisions`) with restore.
- **Post translations (i18n)**: `locale` + `translation_group_id` (useful for vi/en).
- **Comments** or a hook to the existing user system; **related posts**.
- **Bulk actions** (publish/archive/delete many, bulk tag), and `PATCH` for partial updates.
- **Media**: image thumbnails/resizing (Pillow), width/height, folders/collections, storage backend abstraction (local -> S3/R2) since Render's disk is ephemeral unless a persistent disk is attached (`render.yaml`).
- **SEO**: `canonical_url`, `og_image`, `/cms/sitemap.xml`, RSS feed, `noindex` flag.
- **Pages**: `parent_id` + `template`/`order` for hierarchical static pages (About > Team).
- **Custom fields / blocks**: a `JSON` column for structured content (e.g. product highlights, hydroponic recipe guides) instead of one HTML blob.
- **Content for the Hydroponic app**: a `knowledge base` category with links from recipes/stages to CMS posts, and a mobile-friendly `GET /cms/posts/feed` (published only, lightweight fields, ETag/cache headers).
- **Audit log** for create/update/delete by editors.
- **Caching**: `Cache-Control`/ETag on public GETs and menu-by-location.

### P3 - Testing and tooling

- **No CMS tests exist** (`app/tests` has none). Start with: slug uniqueness, schedule validation (past/naive/None), scheduled job flips due posts only, draft not visible publicly (after fix), permission matrix per role, menu reorder + cycle prevention, upload rejects bad type/size.
- **No migrations**: the repo uses ad-hoc `migrate_*.py` scripts. Adopt Alembic (or add a `migrate_cms.py`) so schema changes such as new columns do not depend on `create_all`.
- Add `pyproject`-level lint (ruff) and type checks for this package; remove emoji comments (`✅`, `⏰`) in code for consistency if desired.

## Suggested order of work

1. Public/draft visibility fix (P0 #1) and media permissions (P0 #3, #4).
2. Referential/cycle validation and error mapping (P0 #8-#10).
3. Tests for posts/scheduling/menus (P3).
4. Vietnamese-aware slugs, pagination/response_model cleanup, menu N+1 (P1).
5. Feature work (P2): revisions, i18n, storage abstraction, sitemap/RSS.
