import type { Metadata } from "next";
import { Poppins } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/toast";

const poppins = Poppins({ subsets: ["latin"], variable: "--font-poppins", weight: ["400", "500", "600", "700"] });

export const metadata: Metadata = {
  title: "HypeSift AI — Find the Hype. Create the Highlight.",
  description:
    "Turn long videos into captioned, reframed, ready-to-post shorts with explainable AI highlight scoring.",
};

// Light (the wallet look) is the default; dark only when the user picked it.
const themeScript = `try{if(localStorage.getItem('hs-theme2')==='dark')document.documentElement.classList.add('dark')}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className={`${poppins.variable} min-h-screen`}>
        <Toaster>{children}</Toaster>
      </body>
    </html>
  );
}
