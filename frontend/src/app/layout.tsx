import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/toast";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const display = Space_Grotesk({ subsets: ["latin"], variable: "--font-display", weight: ["500", "600", "700"] });

export const metadata: Metadata = {
  title: "HypeSift AI — Find the Hype. Create the Highlight.",
  description:
    "Turn long videos into captioned, reframed, ready-to-post shorts with explainable AI highlight scoring.",
};

const themeScript = `try{var t=localStorage.getItem('hs-theme');if(t==='dark')document.documentElement.classList.add('dark')}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className={`${inter.variable} ${display.variable} min-h-screen`}>
        <Toaster>{children}</Toaster>
      </body>
    </html>
  );
}
