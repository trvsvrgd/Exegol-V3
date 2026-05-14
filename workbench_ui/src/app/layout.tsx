import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Exegol V3 | Model Workbench",
  description: "Autonomous Agent Fleet Command & A/B Testing",
};

import Navbar from "@/components/Navbar";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Navbar />
        <main>{children}</main>
      </body>
    </html>
  );
}
