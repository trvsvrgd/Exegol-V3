'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function Navbar() {
  const pathname = usePathname();

  const navLinks = [
    { href: '/', label: 'Dashboard' },
    { href: '/fleet', label: 'Fleet Dashboard' },
    { href: '/settings', label: 'Agent Settings' },
    { href: '/costs', label: 'Cost Management' },
    { href: '/status', label: 'Fleet Status' },
    { href: '/metrics', label: 'A/B Testing / Metrics' },
    { href: '/tools', label: 'Tool Registry' },
  ];

  return (
    <nav className="nav-container">
      <div className="nav-content container">
        <div className="logo">
          <span className="title-glow">EXEGOL</span> V3
        </div>
        <div className="nav-links">
          {navLinks.map((link) => {
            const isActive = link.href === '/' 
              ? pathname === '/' 
              : pathname.startsWith(link.href);
            
            return (
              <Link
                key={link.href}
                href={link.href}
                className={isActive ? 'active' : ''}
              >
                {link.label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
