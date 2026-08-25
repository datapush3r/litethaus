import { describe, expect, it } from "vitest";
import { parseRoute, routePath } from "./routing";

describe("parseRoute", () => {
  it("maps top-level paths to their views", () => {
    expect(parseRoute("/stacks")).toEqual({ view: "stacks" });
    expect(parseRoute("/settings")).toEqual({ view: "settings" });
    expect(parseRoute("/caddy")).toEqual({ view: "caddy" });
    expect(parseRoute("/updates")).toEqual({ view: "updates" });
    expect(parseRoute("/new")).toEqual({ view: "new" });
  });

  it("falls back to home for unknown paths", () => {
    expect(parseRoute("/")).toEqual({ view: "home" });
    expect(parseRoute("/nope")).toEqual({ view: "home" });
  });

  it("parses stack routes, decoding the name", () => {
    expect(parseRoute("/stacks/plex")).toEqual({ view: "stack", name: "plex" });
    expect(parseRoute("/stacks/my%20stack")).toEqual({
      view: "stack",
      name: "my stack",
    });
  });

  it("treats a bare /stacks/ prefix as home, not a stack", () => {
    expect(parseRoute("/stacks/")).toEqual({ view: "home" });
  });
});

describe("routePath round-trip", () => {
  const routes = [
    { view: "home" },
    { view: "stacks" },
    { view: "settings" },
    { view: "caddy" },
    { view: "updates" },
    { view: "new" },
    { view: "stack", name: "plex" },
    { view: "stack", name: "my stack" },
  ] as const;

  it.each(routes)("$0 round-trips through parseRoute", (route) => {
    expect(parseRoute(routePath(route))).toEqual(route);
  });
});
