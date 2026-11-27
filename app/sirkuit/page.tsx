import type { Metadata } from 'next';
import Circuits from '@/components/circuits';

export const metadata: Metadata = { title: 'Pilih Sirkuit' };

export default function CircuitPage() {
  return <Circuits />;
}
