import type { Metadata } from "next";
import "./globals.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
export const metadata: Metadata = {title: "Conceptualize · Context runtime", description: "Inspect how agents navigate and consume project context."};
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="en" className="dark"><body>{children}</body></html>;
}
