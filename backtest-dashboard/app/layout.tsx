import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

const themeBootstrap = `(() => { try { const saved = localStorage.getItem("backtest-theme"); const theme = saved === "dark" || saved === "light" ? saved : matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; document.documentElement.dataset.theme = theme; document.documentElement.style.colorScheme = theme; } catch {} })();`;

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "localhost:3000";
  const protocol = requestHeaders.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const metadataBase = new URL(`${protocol}://${host}`);
  const title = "Backtest Intelligence";
  const description = "Rank every fund strategy, compare it with buy and hold, and inspect the complete backtest evidence trail.";
  return {
    metadataBase,
    title,
    description,
    icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
    openGraph: { title, description, type: "website", images: [{ url: "/og.png", width: 1536, height: 909, alt: "Backtest Intelligence — Every strategy. One evidence trail." }] },
    twitter: { card: "summary_large_image", title, description, images: ["/og.png"] },
  };
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{ __html: themeBootstrap }} /></head><body>{children}</body></html>;
}
