import type { Metadata } from "next";
import { Inter, Manrope } from "next/font/google";
import { Providers } from "@/app/Providers";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-manrope",
  display: "swap",
});

export const metadata: Metadata = {
  title: "AI calling agent",
  description: "AI calling agent - Orchestrating sophisticated voice data.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} ${manrope.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col h-screen font-sans text-on-surface bg-background overflow-hidden">
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );
}
