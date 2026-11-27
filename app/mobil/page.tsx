import type { Metadata } from 'next';
import Garage from '@/components/garage';

export const metadata: Metadata = { title: 'Pilih Mobil' };

export default function CarPage() {
  return <Garage />;
}
