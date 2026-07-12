# ROADMAP.md - Project Phase Roadmap for litethaus

Tracks what's shipped, phase by phase. For architecture rules and dev commands, see [CLAUDE.md](CLAUDE.md). For what changed and why within a phase, `git log` has detailed commit messages — each one documents the fix/feature, the reasoning, and how it was verified (including live browser testing via Playwright, not just typechecking).

Backend foundation (done):
- [x] **Phase 1: Foundation & Local Dev Sandbox** (Backend/Frontend skeleton + Caddy API linkage via Compose)
- [x] **Phase 2: Global Configuration Management** (Implementing `config.yaml` with `ruamel.yaml` formatting safety)
- [x] **Phase 3: The YAML Engine & File Watcher** (Scanning folders, reading `x-litethaus` blocks)
- [x] **Phase 4: Docker SDK & Caddy Automation** (Executing compose commands and piping internal routing variables to Caddy)
- [x] **Phase 5: Real-time Terminal Logs** (FastAPI WebSockets streaming output logs continuously to UI)

UI/UX build-out on top of the working backend:
- [x] **Phase 6: App Shell & Sidebar Nav** (left sidebar, folder-style "Stacks" listing, select-to-filter)
- [x] **Phase 7: Stack Detail View** (dedicated per-stack page, real `/stacks/:name` URLs via the native History API, embedded live logs replacing the old modal)
- [x] **Phase 8: Settings Page** (UI for the existing `GET`/`PATCH /config` endpoints; also fixed `stacks_dir` changes to apply live instead of requiring a restart)
- [x] **Phase 9: Polish** (loading/empty/error states, theme toggle wired to the `theme` config field via a class-based dark mode strategy, responsive mobile sidebar drawer)

- [x] **Phase 10: Stack Authoring** (create/edit/delete stacks from the UI via a raw-YAML editor)
- [x] **Phase 11: HTTPS Automation** (`https_mode` config setting drives Caddy's automatic TLS — internal self-signed or real ACME)
- [x] **Phase 12: Health & Notifications** (per-container health/restart-loop status in the UI, optional webhook alerts)
- [x] **Phase 13: Dashboard Auth** (single-user login backed by `config.yaml`, PBKDF2 hash, in-memory sessions)
- [x] **Phase 14: Stack Detail 3-way Split** (compose editor, live terminal, and logs side by side on the stack page)
- [x] **Phase 15: YAML Editor Upgrade** (CodeMirror-based syntax highlighting and linting for the compose editor - generic YAML syntax plus `x-litethaus` schema checks - a format button, a diff-on-save confirmation view, and syntax colors matched to the app's own palette instead of CodeMirror's stock theme)
- [x] **Phase 16: Stack Page Layout & Space** (uppercase sidebar wordmark, containers table moved beside the stack metadata instead of below it, the "Compose file" path row dropped, a viewport-height app shell so the editor/terminal/logs area fills whatever room is left instead of a fixed height, and that area is now user-resizable via draggable panels that stay attached to each other)
