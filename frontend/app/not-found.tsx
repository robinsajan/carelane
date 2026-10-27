import Link from 'next/link';
import { ArrowLeft, Activity } from 'lucide-react';

export default function NotFound() {
  return <div className="not-found-page">
    <Link href="/" className="not-found-brand" aria-label="Carelane home"><Activity size={23}/>Carelane</Link>
    <main className="not-found-content">
      <span className="not-found-code">404</span>
      <h1>This page couldn’t be found.</h1>
      <p>The link may have changed, or the address may be incorrect. Return to OPD to continue.</p>
      <Link href="/" className="btn primary"><ArrowLeft size={16}/>Back to OPD</Link>
    </main>
    <footer>Carelane · Hospital administration</footer>
  </div>;
}
