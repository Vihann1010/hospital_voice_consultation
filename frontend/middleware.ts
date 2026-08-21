import { NextResponse, type NextRequest } from "next/server";

const TOKEN_COOKIE = "satya_staff_token";

/**
 * Route guard for the clinical dashboard. This is a UX convenience: the API
 * independently validates the JWT on every request, so a forged cookie gains
 * nothing beyond seeing an empty shell.
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasToken = Boolean(request.cookies.get(TOKEN_COOKIE)?.value);

  if (!hasToken) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/waiting/:path*",
    "/active/:path*",
    "/completed/:path*",
    "/patients/:path*",
    "/consultations/:path*",
    // The counter and the finance screens were reachable without a cookie
    // until now. The API refused them, so nothing leaked, but an unsigned-in
    // clerk got an empty shell and no explanation instead of a login page.
    "/reception/:path*",
    "/finance/:path*",
    "/intake/:path*",
    "/ipd/:path*",
  ],
};
