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
              <a href="/ab-test" className="active">A/B Testing</a>
              <a href="/fleet">Fleet Status</a>
            </div>
          </div>
        </nav>
        <main>{children}</main>
        
        <style jsx>{`
          .nav-container {
            width: 100%;
            height: 70px;
            background: rgba(10, 10, 10, 0.8);
            backdrop-filter: blur(10px);
            border-bottom: 1px solid rgba(255, 0, 0, 0.1);
            position: sticky;
            top: 0;
            z-index: 100;
          }
          .nav-content {
            display: flex;
            justify-content: space-between;
            align-items: center;
            height: 100%;
          }
          .logo {
            font-size: 1.5rem;
            font-weight: 800;
            letter-spacing: 2px;
          }
          .nav-links {
            display: flex;
            gap: 2rem;
          }
          .nav-links a {
            font-size: 0.9rem;
            font-weight: 500;
            color: #888;
            transition: color 0.3s ease;
            text-transform: uppercase;
            letter-spacing: 1px;
          }
          .nav-links a:hover {
            color: var(--accent-color);
          }
          .nav-links a.active {
            color: white;
            border-bottom: 2px solid var(--accent-color);
          }
        `}</style>
      </body>
    </html>
  );
}
