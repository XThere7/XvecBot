import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { Providers } from "@/components/providers";
import { ConfigError } from "@/components/config-error";
import { APP_NAME, SITE_URL } from "@/lib/constants";

/**
 * Fonts are self-hosted woff2 (latin subset, variable weight axis) so there is
 * no third-party request on a low-bandwidth connection. `display: swap` and
 * `preload` keep first paint fast. Only the weights actually used — 400, 500
 * and 600 — are rendered.
 */
const inter = localFont({
  src: "./fonts/inter-latin-variable.woff2",
  variable: "--font-inter",
  display: "swap",
  weight: "100 900",
  style: "normal",
  preload: true,
  fallback: ["system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
  adjustFontFallback: false,
});

const jetbrains = localFont({
  src: "./fonts/jetbrains-mono-latin-variable.woff2",
  variable: "--font-jetbrains",
  display: "swap",
  weight: "100 800",
  style: "normal",
  preload: false,
  fallback: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
  adjustFontFallback: false,
});

export const metadata: Metadata = {
  title: {
    default: `${APP_NAME} Dashboard`,
    template: `%s · ${APP_NAME}`,
  },
  description: "Turn your documents into an embeddable AI chat widget.",
  // Declared explicitly so the browser does not fall back to /favicon.ico.
  icons: { icon: "/favicon.svg" },
  ...(SITE_URL ? { metadataBase: new URL(SITE_URL) } : {}),
};

export const viewport: Viewport = {
  themeColor: "#0b0d12",
  colorScheme: "dark",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL;

  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrains.variable}`}
      suppressHydrationWarning
    >
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem("xvecbot-theme");if(t==="light"){document.documentElement.dataset.theme="light";}}catch(e){}})();`,
          }}
        />
      </head>
      <body className="bg-canvas text-primary antialiased">
        {apiBase ? <Providers>{children}</Providers> : <ConfigError />}
      </body>
    </html>
  );
}