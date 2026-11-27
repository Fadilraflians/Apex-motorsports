import type { Metadata } from 'next';
import RaceBrief from '@/components/race-brief';

export const metadata: Metadata = { title: 'Balapan' };

export default function RacePage() {
  return <RaceBrief />;
}
