# CMS Frontend Integration Guide

Audience: senior frontend developers integrating a web/mobile client (SPA, SSR/Next/Nuxt, React Native) with the CMS module in `app/cms`.
Backend reference: [`README.md`](./README.md). This guide covers what the client needs to know: contracts, flows, pitfalls and known gaps.

Everything here was verified against the code and the generated OpenAPI (`GET /openapi.json`, tag prefix `CMS - *`). If this guide and `/openapi.json` ever disagree, the OpenAPI wins; generate types from it (see [Types](#3-types)).

---

## 1. Quick facts

| Topic | Fact |
|---|---|
| Base path | `/cms/*` on the API origin (e.g. `https://<api>/cms/posts`) |
| Auth | `Authorization: Bearer <jwt>`; public endpoints need none |
| Content type | JSON, except media upload (`multipart/form-data`), media PATCH (`application/x-www-form-urlencoded`) and login (form-encoded) |
| Errors | `{"detail": "<message>"}`; validation errors are 422 with `detail: [{loc, msg, type}]` |
| Dates | ISO 8601. Send timezone-aware values; a value without offset is treated as **UTC** |
| IDs / slugs | Integer ids. Slugs are unique per resource, server-generated, and may get a `-2`, `-3` suffix |
| CORS | Origins come from env `CORS_ALLOWED_ORIGINS` (comma list) or `FRONTEND_URL`, default `http://localhost:5173`. Credentials allowed, all methods/headers |
| Media files | Served as static files from the API origin at `/static/cms_media/<uuid>.<ext>` (`MediaOut.url` is **relative**) |
| Pagination | Posts: `page` + `page_size` (default 20, max 100) with `total`. Media: `skip` + `limit` (default 50, max 200), no total. Categories/tags/menus: not paginated |

---

## 2. What changed (read this if you integrated earlier)

These are behaviour changes since the module's first version. Update clients accordingly.

| Area | Before | Now |
|---|---|---|
| Unpublished posts | Anyone could list/read drafts | Anonymous and non-editor users only get `published`. `GET /cms/posts?status=draft` → **403**; reading an unpublished post by id/slug → **404** (authors and editors can) |
| Post references | Bad `category_id` / `featured_image_id` / `tag_ids` → 500 | **400** with a message |
| Scheduling | `scheduled_at` only checked on create | Must be in the future on create, update and `/schedule` (**400**) |
| Post HTML | Stored raw | **Sanitized on write**; the response `content` is what was stored (see [§8](#8-rich-text-editor-integration)) |
| Media upload | Extension check only; `.svg` allowed | Magic-byte check; **`.svg` rejected**; mismatched content → 400 |
| Media edit/delete | Any logged-in user | Uploader or editor only (**403**); deleting a file used as a featured image → **409** |
| Category delete | Orphaned children/posts silently | Children and posts move to the parent (or `?reassign_to=`); **409** if a menu item links to it |
| Tag delete | Silently detached from posts | **409** if used, unless `?force=true` or `?merge_into=<id>` |
| Tag create | Duplicate name → 500 | **409** |
| Parent loops | Possible | Category and menu-item cycles → **400** |
| Menus | Untyped responses; list included items | Typed. `GET /cms/menus` returns **summaries without `items`**. Links to unpublished posts have `resolved_url: null` |
| Slug races | Occasional 500 | Retried server-side; at worst **409** |
| Delete responses | `{detail}` | Category/tag deletes also return move/affected counts |
| `GET /auth/me` | No roles | Includes `roles` (active roles only) |
| Category / tag lookup | By id only (tags: none) | `GET /cms/categories/slug/{slug}` and `GET /cms/tags/slug/{slug}` (public) |
| Post list | Always newest-created first | New `is_featured`, `sort` (`created_at` default, `published_at`, `title`, `view_count`) and `order` (`desc` default, `asc`) params; defaults unchanged |

---

## 3. Types

Prefer generating types from the live schema so they never drift:

```text
npx openapi-typescript https://<api>/openapi.json -o src/api/schema.d.ts
```

Hand-written equivalents (verified against `app/cms/schemas/*`), useful for reading and as a fallback:

```ts
export type PostStatus = "draft" | "published" | "scheduled" | "archived";
export type PostType = "post" | "page";
export type MenuItemTargetType = "custom" | "category" | "post";

export interface Category {
  id: number; name: string; slug: string;
  description: string | null; parent_id: number | null;
  created_at: string; updated_at: string | null;
}
export interface Tag { id: number; name: string; slug: string; created_at: string }
export interface Media {
  id: number; filename: string;
  url: string;                       // RELATIVE, e.g. "/static/cms_media/ab12.png"
  mime_type: string | null; file_size: number | null;
  alt_text: string | null; uploaded_by_id: number | null; created_at: string;
}
export interface Author { id: number; username: string }

export interface PostListItem {      // list/grid views: no `content`, no tags
  id: number; title: string; slug: string; excerpt: string | null;
  status: PostStatus; post_type: PostType;
  author: Author | null; category: Category | null; featured_image: Media | null;
  is_featured: boolean; view_count: number;
  scheduled_at: string | null; published_at: string | null; created_at: string;
}
export interface Post extends PostListItem {
  content: string;                   // sanitized HTML
  category_id: number | null; featured_image_id: number | null;
  meta_title: string | null; meta_description: string | null;
  tags: Tag[]; updated_at: string | null;
}
export interface Paginated<T> { results: T[]; total: number; page: number; page_size: number }

export interface PostCreate {
  title: string;                     // required, 1..255
  slug?: string | null;              // auto from title when omitted
  excerpt?: string | null;           // max 500
  content?: string;
  post_type?: PostType;              // default "post"
  status?: PostStatus;               // default "draft"
  category_id?: number | null;
  featured_image_id?: number | null; // id from POST /cms/media/upload
  meta_title?: string | null; meta_description?: string | null;
  is_featured?: boolean;
  scheduled_at?: string | null;      // REQUIRED when status === "scheduled"
  tag_ids?: number[];
}
export type PostUpdate = Partial<PostCreate>; // partial: send only changed fields

export interface MenuItem {
  id: number; menu_id: number; label: string;
  target_type: MenuItemTargetType;
  url: string | null; target_id: number | null;
  parent_id: number | null; order: number;
  open_in_new_tab: boolean; is_active: boolean;
  resolved_url: string | null;       // computed by the server; null = do not render a link
  children: MenuItem[];
}
export interface MenuSummary {
  id: number; name: string; slug: string; location: string | null;
  created_at: string; updated_at: string | null;
}
export interface Menu extends MenuSummary { items: MenuItem[] }

export interface Role { id: number; name: string; display_name: string; is_active: boolean; permissions: string[] | null }
export interface Me { id: number; username: string; email: string; roles: Role[] }  // trimmed: more profile fields exist

export interface ApiErrorBody { detail: string | { loc: (string | number)[]; msg: string; type: string }[] }
```

---

## 4. Authentication and roles

### Login

`POST /auth/login` is the standard OAuth2 password form (**not JSON**):

```ts
export async function login(base: string, username: string, password: string) {
  const res = await fetch(`${base}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username, password }),
  });
  if (!res.ok) throw new Error("Invalid credentials");
  return (await res.json()) as { access_token: string; token_type: "bearer" };
}
```

- Token lifetime defaults to **30 days** (`ACCESS_TOKEN_EXPIRE_MINUTES=43200`). There is **no refresh token**; on `401` send the user to login.
- Store the token in memory plus a persistent store appropriate to your platform (secure storage on mobile). Since auth is a bearer header, no cookies/CSRF handling is needed.

### Finding out the user's roles

`GET /auth/me` returns the profile **with the caller's active roles**:

```ts
export async function loadSession(api: Api) {
  const me = await api.get<Me>("/auth/me");
  const names = new Set(me.roles.map((r) => r.name));       // "super_admin" | "admin" | "moderator" | "user" | "manager"
  const isEditor = ["super_admin", "admin", "moderator"].some((r) => names.has(r));
  const isAdmin = ["super_admin", "admin"].some((r) => names.has(r));
  return { me, isEditor, isAdmin };
}
```

Inactive roles are not listed. Use roles only to **show or hide UI**. The backend is the source of truth and returns 403.

### Permission matrix (as enforced today)

`editor` = `super_admin`, `admin` or `moderator`. `admin` = `super_admin` or `admin`. `super_admin` passes every role check.

| Resource | Anonymous | Any logged-in user | Editor | Admin |
|---|---|---|---|---|
| Categories, tags, menus (read) | yes | yes | yes | yes |
| Posts (read) | published only | published + **own** posts | all | all |
| Posts create | no | **yes** | yes | yes |
| Post update/delete/publish/archive/schedule | no | own posts | all | all |
| Media read | yes | yes | yes | yes |
| Media upload | no | **yes** | yes | yes |
| Media edit/delete | no | own uploads | all | all |
| Category/tag/menu create & update, menu items | no | no | yes | yes |
| Category/tag/menu **delete** | no | no | no | yes |
| Menu item delete | no | no | yes | yes |

Note: any authenticated user can create **and publish their own** posts. If the product needs "only editors publish", that is a backend policy change (see [§11](#11-known-gaps-and-suggested-backend-additions)); do not rely on hiding the button.

---

## 5. API client

One thin typed wrapper; everything else builds on it.

```ts
export class ApiError extends Error {
  constructor(public status: number, public body: ApiErrorBody | null) {
    super(typeof body?.detail === "string" ? body.detail : `HTTP ${status}`);
  }
  /** field-level messages for 422 */
  get fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    if (Array.isArray(this.body?.detail)) {
      for (const e of this.body!.detail) out[e.loc.filter((p) => p !== "body").join(".")] = e.msg;
    }
    return out;
  }
}

export class Api {
  constructor(
    private base: string,
    private getToken: () => string | null,
    private onUnauthorized: () => void = () => {},
  ) {}

  /** Turn a relative media URL ("/static/cms_media/x.png") into an absolute one. */
  asset(url: string): string {
    return /^https?:\/\//i.test(url) ? url : `${this.base}${url}`;
  }

  async request<T>(method: string, path: string, init: { json?: unknown; form?: FormData | URLSearchParams; query?: Record<string, unknown> } = {}): Promise<T> {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(init.query ?? {})) if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    const headers: Record<string, string> = {};
    const token = this.getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    let body: BodyInit | undefined;
    if (init.json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(init.json); }
    else if (init.form) body = init.form; // browser sets the multipart boundary / urlencoded type itself

    const res = await fetch(`${this.base}${path}${qs.size ? `?${qs}` : ""}`, { method, headers, body });
    if (res.status === 401) this.onUnauthorized();
    if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => null));
    return (res.status === 204 ? undefined : await res.json()) as T;
  }

  get<T>(path: string, query?: Record<string, unknown>) { return this.request<T>("GET", path, { query }); }
  post<T>(path: string, json?: unknown) { return this.request<T>("POST", path, { json }); }
  put<T>(path: string, json: unknown) { return this.request<T>("PUT", path, { json }); }
  del<T>(path: string, query?: Record<string, unknown>) { return this.request<T>("DELETE", path, { query }); }
}
```

Anonymous requests: pass `getToken: () => null`. For SSR, build one `Api` per request so tokens never leak between users.

### Error handling map

| Status | Meaning in the CMS | Suggested UI |
|---|---|---|
| 400 | Business validation: unknown category/media/tag, `scheduled_at` not in the future, bad upload (type/size/content), parent cycle, bad `reassign_to`/`merge_into`, menu `location` already in use | Show `detail` next to the field/action |
| 401 | Missing/expired token | Clear session, go to login |
| 403 | Role/ownership; also `status=draft` listing as non-editor | Hide the action, show "not allowed" |
| 404 | Not found, **or an unpublished post you may not see** | Not-found page |
| 409 | Duplicate tag name, media/category/tag in use, slug allocation failed (rare race) | Show `detail` (it says what to do); offer the `force`/`merge_into`/`reassign_to` option where applicable |
| 422 | Request shape/validation (e.g. `scheduled_at` missing for `scheduled`) | Map `fieldErrors` to the form |

All CMS messages are English literals (not localized by the i18n middleware); map by status/context in your own i18n layer if you need Vietnamese UI text.

---

## 6. Public site flows

### Home / blog feed

```ts
export const loadFeed = (api: Api, page = 1) =>
  api.get<Paginated<PostListItem>>("/cms/posts", {
    status: "published", post_type: "post", sort: "published_at", order: "desc", page, page_size: 12,
  });

export const loadFeatured = (api: Api, limit = 3) =>
  api.get<Paginated<PostListItem>>("/cms/posts", {
    status: "published", is_featured: true, sort: "published_at", page_size: limit,
  });
```

- Anonymous callers always get published posts; the `status` param is optional for them (passing `published` is fine, anything else is 403).
- **Default sort is still `created_at` descending** (kept for backward compatibility). For a public feed pass **`sort=published_at`** so scheduled and re-published posts appear by go-live date. Other keys: `title`, `view_count`; `order=asc|desc`. Posts without a publish date (drafts, visible to editors only) sort last under `published_at`. Ties are broken by id, so paging is stable. Unknown `sort`/`order` values are rejected with 422.
- Filters: `category_id` (exact category, **does not include descendants**), `tag_id`, `author_id`, `search` (case-insensitive match on **title and excerpt only**, not content).
- `is_featured=true|false` filters featured posts (omit for no filter); see `loadFeatured` above for a hero block.

### Post / page detail (SEO-critical)

```ts
export const loadPost = (api: Api, slug: string) =>
  api.get<Post>(`/cms/posts/slug/${encodeURIComponent(slug)}`, { track_view: false });
```

- Both blog posts and static pages (`post_type: "page"`) are fetched by slug from the same endpoint.
- `track_view` defaults to **true** and increments `view_count` on every call (no de-duplication, bots included). **Pass `track_view=false` for SSR/prefetch, crawlers and previews.** There is no separate "register a view" endpoint yet; see gaps.
- A non-published slug returns **404** to the public, which is the correct response for crawlers.
- SEO fields: use `meta_title ?? title`, `meta_description ?? excerpt`, `featured_image` (make the URL absolute with `api.asset()`), `published_at` for `article:published_time`.
- Render `content` as HTML. It is sanitized server-side, but still render it inside a prose container and avoid injecting it anywhere other than normal HTML.
- Rewrite relative media URLs in `content` (see [§8](#8-rich-text-editor-integration)).

### Navigation menus

```ts
export const loadMenu = (api: Api, location: string) =>
  api.get<Menu>(`/cms/menus/location/${encodeURIComponent(location)}`); // active items only by default
```

- Locations are free-form keys you agree on with the CMS admins (`header`, `footer`, ...). Each location maps to at most one menu; `404` when none exists, so handle it and render a fallback.
- Items are returned as a **ready-made tree** (`children`), already sorted by `order`.
- Use `resolved_url`, not `url`. For category items it is `/categories/<slug>`, for post items `/posts/<slug>`. These are **frontend route paths hard-coded in the backend**, so your router needs `/categories/:slug` and `/posts/:slug` (pages are also under `/posts/:slug`), or you must map them.
- `resolved_url === null` means the target is missing or unpublished: **skip the item**.
- `open_in_new_tab` → `target="_blank" rel="noopener"`.

### Category and tag pages

- Categories are a **flat list** with `parent_id`; build the tree on the client (`GET /cms/categories`). The list endpoint cannot return top-level only (see gaps).
- Resolve slugs with `GET /cms/categories/slug/{slug}` and `GET /cms/tags/slug/{slug}` (public, 404 when unknown), then list posts with `category_id` / `tag_id`:

```ts
export async function loadCategoryPage(api: Api, slug: string, page = 1) {
  const category = await api.get<Category>(`/cms/categories/slug/${encodeURIComponent(slug)}`);
  const posts = await api.get<Paginated<PostListItem>>("/cms/posts", {
    status: "published", category_id: category.id, sort: "published_at", page,
  });
  return { category, posts };
}
```

### Caching

- Responses differ by caller (drafts/own posts for authenticated users). Do not cache authenticated responses on a shared CDN; if you cache anonymous responses, key by `Authorization` or only cache requests without it (`Vary: Authorization`).
- The API sets no `Cache-Control`/`ETag`. For ISR/SSG use time-based revalidation. Scheduled posts go live within about **60 seconds** after `scheduled_at` (background job), so a revalidate window of 60s or less keeps scheduled releases timely.

---

## 7. Editor / admin flows

### Post lifecycle

```text
        create (status=draft|published|scheduled)
draft ───────────────► published ◄──────── scheduled (job flips it at scheduled_at, within ~60s)
  ▲  \__ POST /schedule ──────────────────────┘   │
  │                                                │
  └──────────── archived ◄─────────────────────────┘   (PUT status or POST /archive)
```

- Endpoints: `POST /cms/posts/{id}/publish`, `/archive`, `/schedule` (`{ scheduled_at }`), or `PUT` with `status`.
- `status: "scheduled"` requires a **future** `scheduled_at` (422 if missing, 400 if not in the future). Convert the user's local time to ISO with an offset before sending (`date.toISOString()`).
- Leaving `scheduled` clears `scheduled_at`. Publishing stamps `published_at` (server time).
- Only the author or an editor may change a post (403 otherwise).

### Create / update a post with an image

```ts
export async function uploadMedia(api: Api, file: File, altText?: string): Promise<Media> {
  const form = new FormData();
  form.append("file", file);
  if (altText) form.append("alt_text", altText);
  return api.request<Media>("POST", "/cms/media/upload", { form }); // do NOT set Content-Type yourself
}

export async function savePost(api: Api, id: number | null, data: PostUpdate & { title?: string }) {
  return id === null
    ? api.post<Post>("/cms/posts", data)
    : api.put<Post>(`/cms/posts/${id}`, data);
}
```

Update semantics (important for forms):

- `PUT /cms/posts/{id}` is a **partial update**: only fields present in the JSON are changed. Omit untouched fields; to clear an optional field send `null` explicitly (`category_id`, `featured_image_id`, `excerpt`, `meta_*`, `scheduled_at`).
- Never send `null` for `title`, `content`, `post_type` or `status`.
- `tag_ids` **replaces** the whole tag set. Send the full desired list; omit the key to leave tags alone.
- Changing `slug` changes the public URL and there is **no redirect support**. Warn editors, and handle the returned slug (it may have been suffixed `-2`).
- After saving, **replace local state with the response**: `content` may differ from what was sent (sanitization) and `slug` may be adjusted.
- There is no optimistic locking (no ETag or version check): last write wins. If several editors work on one post, compare `updated_at` yourself before overwriting.

### Media library

- Upload: `POST /cms/media/upload` (multipart: `file`, optional `alt_text`). Any logged-in user.
- Allowed: `.jpg .jpeg .png .gif .webp .pdf .mp4 .webm`, max **20 MB** by default (server env `CMS_MAX_MEDIA_SIZE_MB`). The file's actual bytes must match its extension. Pre-validate extension and size in the UI; surface the 400 `detail` otherwise.
- List: `GET /cms/media?skip=0&limit=50` (newest first, no total; page until a short page comes back).
- Edit alt text: `PATCH /cms/media/{id}` with **form-encoded** body (`alt_text=...`), not JSON:

```ts
export const setAlt = (api: Api, id: number, alt: string) =>
  api.request<Media>("PATCH", `/cms/media/${id}`, { form: new URLSearchParams({ alt_text: alt }) });
```

- Delete: `DELETE /cms/media/{id}` → **409** while a post uses it as featured image (detach it first). Images referenced only inside post `content` are **not** tracked, so deleting such a file breaks the page silently; warn the user.
- Always display with `api.asset(media.url)`.

### Categories

- Create/update need an editor; delete needs an admin.
- `parent_id` must exist and cannot be the category itself or a descendant (400).
- Delete: `DELETE /cms/categories/{id}[?reassign_to=<id>]`. Default behaviour moves child categories and posts up to the parent (top-level: children become top-level, posts become uncategorised). Response `{detail, moved_children, moved_posts, moved_to_category_id}`; show a confirmation naming the counts. 409 if a menu item links to it.

### Tags

- Only list, create and delete exist (no update, no get-by-id).
- Duplicate name (case-insensitive) → 409; for free-text tag inputs, check your cached tag list first and reuse the existing tag's id.
- Delete: 409 when the tag is in use; offer **"Merge into…"** (`?merge_into=<id>`) or **"Remove from all posts and delete"** (`?force=true`). Response `{detail, posts_affected, merged_into_tag_id, posts_moved}`.

### Menu builder

- `GET /cms/menus` → `MenuSummary[]` (no items). Load one with `GET /cms/menus/{id}?active_only=false` to edit (include inactive items).
- Create an item: `POST /cms/menus/{menuId}/items`:
  - `target_type: "custom"` → `url` required.
  - `target_type: "category" | "post"` → `target_id` required (validated server-side).
  - `parent_id` must belong to the same menu.
- Drag and drop: send the **entire flat list** in one call; the response is the new tree:

```ts
export function reorder(api: Api, menuId: number, flat: { id: number; parent_id: number | null; order: number }[]) {
  return api.post<MenuItem[]>(`/cms/menus/${menuId}/items/reorder`, { items: flat });
}
```

- Cycles (an item under its own descendant) → 400; unknown menu → 404.
- `location` is unique across menus (400 if already used); changing a menu's location changes which menu the site renders.
- Deleting a menu deletes its items; deleting an item deletes its children.

---

## 8. Rich-text editor integration

Post `content` goes through an allow-list sanitizer on every create/update. Configure the editor (TipTap, Quill, CKEditor, ...) to produce only what survives.

**Kept:** `p br hr div span h1-h6 strong b em i u s del ins sub sup mark small blockquote pre code ul ol li a img figure figcaption table thead tbody tfoot tr th td caption`.
Attributes: `class id lang dir title` on everything; `a[href target hreflang]`; `img[src alt width height loading]`; `th[colspan rowspan scope]`; `td[colspan rowspan]`.
Link/image URL schemes: `http`, `https`, `mailto`, `tel` (plus relative URLs). Links get `rel="noopener noreferrer"` automatically.

**Removed:** `script style iframe object embed form input svg`, all event handlers (`onclick`, ...), and inline `style`.

Consequences to design around:

1. **No inline styles.** Alignment, colour and font-size from editors that emit `style="..."` are stripped. Configure the editor to use CSS classes (e.g. `text-center`) and style them in your site CSS.
2. **No base64 images.** `data:` URLs are dropped. Intercept paste/drop in the editor, upload through `/cms/media/upload`, and insert the returned URL.
3. **No iframe embeds** (YouTube etc.). Either store a plain link and render the embed in your frontend, or ask for a host allow-list on the backend.
4. **Absolute vs relative image URLs.** `MediaOut.url` is relative (`/static/cms_media/x.png`). If the frontend is on a different origin than the API, a relative `src` stored in `content` resolves against the *frontend* origin and breaks. Pick one:
   - Insert `api.asset(media.url)` (absolute) when the editor adds an image. Simple; breaks if the API domain changes.
   - Store relative and rewrite at render time: `html.replaceAll('src="/static/cms_media/', `src="${API_BASE}/static/cms_media/`)`.
5. The server output is authoritative: after save, re-initialise the editor from the response if it differs.
6. Titles, excerpts and meta fields are **plain text** and are not sanitized; always render them escaped (default in React/Vue templates).

---

## 9. Reference: endpoints used by a client

| Purpose | Request | Response |
|---|---|---|
| Current user | `GET /auth/me` | `Me` (with `roles`) |
| List posts | `GET /cms/posts?status&post_type&category_id&tag_id&author_id&search&is_featured&sort&order&page&page_size` | `Paginated<PostListItem>` |
| Post by slug | `GET /cms/posts/slug/{slug}?track_view` | `Post` |
| Post by id | `GET /cms/posts/{id}` | `Post` |
| Create / update / delete post | `POST /cms/posts` · `PUT /cms/posts/{id}` · `DELETE /cms/posts/{id}` | `Post` / `Post` / `{detail}` |
| Publish / archive / schedule | `POST /cms/posts/{id}/publish` · `/archive` · `/schedule {scheduled_at}` | `Post` |
| Categories | `GET /cms/categories[?parent_id]` · `GET /{id}` · `GET /slug/{slug}` · `POST` · `PUT /{id}` · `DELETE /{id}[?reassign_to]` | `Category[]` / `Category` / `{detail, moved_*}` |
| Tags | `GET /cms/tags` · `GET /slug/{slug}` · `POST` · `DELETE /{id}[?force][&merge_into]` | `Tag[]` / `Tag` / `{detail, posts_*}` |
| Media | `POST /cms/media/upload` · `GET /cms/media?skip&limit` · `GET /{id}` · `PATCH /{id}` · `DELETE /{id}` | `Media` |
| Menus | `GET /cms/menus` · `GET /cms/menus/location/{loc}` · `GET /cms/menus/{id}` · `POST` · `PUT /{id}` · `DELETE /{id}` | `MenuSummary[]` / `Menu` |
| Menu items | `POST /cms/menus/{id}/items` · `PUT /cms/menus/items/{itemId}` · `DELETE /cms/menus/items/{itemId}` · `POST /cms/menus/{id}/items/reorder` | `MenuItem` / `MenuItem[]` |

---

## 10. Deployment and environment notes for the frontend team

- **CORS:** add your frontend origins to the API's `CORS_ALLOWED_ORIGINS` (comma-separated, no trailing slash) or set `FRONTEND_URL`. Without it only `http://localhost:5173` works. Images loaded via `<img>` are not subject to CORS, but `fetch` calls are.
- **Uploaded files on Render:** media is written to `uploads/cms_media` on the service's local disk, and `render.yaml` does not define a persistent disk. Without one, **uploaded files disappear on every redeploy/restart** while the database rows remain, giving broken image links. Attach a persistent disk (and point `CMS_MEDIA_DIR` at it) or move to object storage before relying on the media library in production.
- **Environment separation:** use a separate API base URL per environment; never hard-code `localhost` URLs into stored `content`.
- **Types in CI:** regenerate `schema.d.ts` from `/openapi.json` in CI and fail on diff to catch backend contract changes.

---

## 11. Known gaps and suggested backend additions

Things a frontend will run into today, with the workaround and the backend change that would remove it. Items marked **(policy)** need a product decision.

| # | Gap | Workaround today | Suggested backend change |
|---|---|---|---|
| ~~1~~ | ~~`/auth/me` has no roles~~ **Resolved** | | |
| ~~2~~ | ~~No category or tag lookup by slug~~ **Resolved** | | |
| 3 | Category list is flat; cannot request top-level only; no tree endpoint | Build tree client-side | `?tree=true` using the existing `CategoryWithChildren` schema; `?root=true` |
| ~~4~~ | ~~Post list only sortable by `created_at`~~ **Resolved** with `sort`/`order` (the default is still `created_at desc`, so pass `sort=published_at`) | | |
| ~~5~~ | ~~No `is_featured` filter~~ **Resolved** | | |
| 6 | Category filter excludes descendants | Fetch child ids from the tree and call per id | `include_children=true` |
| 7 | View counting only via `GET .../slug` (`track_view`), no de-duplication | `track_view=false` on SSR/bots | `POST /cms/posts/{id}/view` with de-dup |
| 8 | Search covers title and excerpt only | Accept | Full-text search (PostgreSQL `tsvector`) |
| 9 | Any logged-in user can create and publish posts **(policy)** | Gate UI by role | Restrict create/publish to editors, or add an "author submits, editor publishes" review state |
| 10 | No slug redirects when a slug changes | Avoid renaming published posts | Slug history table + 301 handling |
| 11 | No optimistic locking | Compare `updated_at` client-side | `If-Match`/version field |
| 12 | Media list has no `total`; unused-in-content files are not tracked | Page until short | Add `total`; usage tracking |
| 13 | Menu links to unpublished or deleted posts silently become `resolved_url: null`; deleting a post does not warn about menu items | Hide null items | Block post delete (409) while a menu item references it, like categories |
| 14 | Uploads on ephemeral disk | See [§10](#10-deployment-and-environment-notes-for-the-frontend-team) | Persistent disk or S3/R2 backend |

Items 1, 2, 4 and 5 are done. Item 7 (view endpoint) is the next small, low-risk one.

---

## 12. Integration checklist

- [ ] Types generated from `/openapi.json`; CI diff check
- [ ] Single `Api` wrapper with 401 handling and `ApiError` → form mapping
- [ ] Login via form-encoded `/auth/login`; roles read from `/auth/me`
- [ ] Public pages use `status=published`, `sort=published_at`, `track_view=false` on SSR, and absolute media URLs
- [ ] Menu renderer uses `resolved_url`, skips `null`, supports nested children
- [ ] `/categories/:slug` and `/posts/:slug` routes exist (menu links point to them) and resolve slugs via the `/slug/{slug}` endpoints
- [ ] Editor: classes instead of inline styles, uploads instead of base64, no iframes
- [ ] Post form sends partial updates; replaces state from the response; handles 409/400/422
- [ ] Delete dialogs for categories/tags offer `reassign_to` / `merge_into` / `force`
- [ ] Media upload pre-validates extension and size; `PATCH` alt text is form-encoded
- [ ] Frontend origin added to `CORS_ALLOWED_ORIGINS`
- [ ] Persistent storage decided for uploaded media
