import type { Metadata } from 'next';
import './globals.css';
import './workspace.css';

export const metadata: Metadata = { title: 'Carelane | Hospital OPD', description: 'Local hospital OPD administration' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
