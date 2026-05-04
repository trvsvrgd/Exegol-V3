import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Exegol V3 | Model Workbench",
  description: "Autonomous Agent Fleet Command & A/B Testing",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <nav className="nav-container">
          <div className="nav-content container">
            <div className="logo">
              <span className="title-glow">EXEGOL</span> V3
            </div>
            <div className="nav-links">
              <a href="/">Dashboard</a>
              <a href="/evaluations">Evaluations</a>
              <a href="/ab-test" className="active">A/B Testing</a>
              <a href="/fleet">Fleet Status</a>
              <a href="/metrics">Metrics</a>
              <a href="/tools">Tool Registry</a>
            </div>
          </div>
        </nav>
        <main>{children}</main>
      </body>
    </html>
  );
}
