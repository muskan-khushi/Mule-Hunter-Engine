// middleware.ts
import NextAuth from "next-auth";
import { authConfig } from "./auth.config";
import { NextResponse } from "next/server";

// 1. Initialize auth specifically for middleware
const { auth } = NextAuth(authConfig);

export default auth((req) => {
  const { nextUrl } = req;
  const isLoggedIn = !!req.auth;
  const role = (req.auth?.user as any)?.role;

  console.log("MIDDLEWARE CHECK:", { 
    path: nextUrl.pathname, 
    isLoggedIn, 
    role 
  });

  const isAdminPage = nextUrl.pathname.startsWith("/admin");

  if (isAdminPage) {
    if (!isLoggedIn) return NextResponse.redirect(new URL("/login", nextUrl));
    if (role !== "admin") return NextResponse.redirect(new URL("/", nextUrl));
  }
  
  return NextResponse.next();
});

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};