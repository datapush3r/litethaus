#!/usr/bin/env python3
"""
Proper verification of caddy routes by directly inspecting app.routes.
This avoids auth middleware interference and directly proves route registration
without needing a running container or config directory.
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from main import app

def verify_route_registration():
    """Verify routes are registered in app.routes by inspecting the app object directly"""
    print("=" * 70)
    print("ROUTE REGISTRATION VERIFICATION - Direct app.routes inspection")
    print("=" * 70)

    print("\nAll registered Caddy routes in app.routes:")
    print("-" * 70)

    # Check app.routes directly to find our routes
    version_route_found = False
    reload_route_found = False

    for route in app.routes:
        if hasattr(route, 'path') and 'caddy' in route.path:
            methods = route.methods if hasattr(route, 'methods') else 'N/A'
            print(f"  {route.path:<30} Methods: {methods}")

            # Check for our specific routes
            if route.path == '/caddy/version' and hasattr(route, 'methods') and 'GET' in route.methods:
                version_route_found = True
            if route.path == '/caddy/reload' and hasattr(route, 'methods') and 'POST' in route.methods:
                reload_route_found = True

    print("-" * 70)

    # Report results
    print("\nVerification Results:")
    if version_route_found:
        print("  ✓ GET /caddy/version route is REGISTERED")
    else:
        print("  ✗ GET /caddy/version route is NOT registered")

    if reload_route_found:
        print("  ✓ POST /caddy/reload route is REGISTERED")
    else:
        print("  ✗ POST /caddy/reload route is NOT registered")

    return version_route_found and reload_route_found

if __name__ == "__main__":
    print("\nCaddy Routes Implementation Verification\n")

    registration_ok = verify_route_registration()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    if registration_ok:
        print("✓ Both new routes are properly registered in the FastAPI app")
        print("  - GET /caddy/version: Returns {'version': str | None}")
        print("  - POST /caddy/reload: Triggers sync and returns status")
        sys.exit(0)
    else:
        print("✗ Route registration verification failed")
        sys.exit(1)
