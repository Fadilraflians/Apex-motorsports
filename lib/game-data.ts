export type Track = { id: number; name: string; country: string; region: string; length: string; turns: number; laps: number; difficulty: string; weather: string; tag: string; description: string };

export const tracks: Track[] = [
  { id: 1, name: 'Circuit of the Americas', country: 'AMERIKA SERIKAT', region: 'Austin · Texas', length: '5.51 km', turns: 20, laps: 3, difficulty: 'AHLI', weather: 'CERAH', tag: 'GRAND PRIX', description: 'Lintasan Austin dengan tanjakan menuju tikungan pertama dan sektor teknis yang mengalir.' },
  { id: 2, name: 'Autodromo Nazionale Monza', country: 'ITALIA', region: 'Monza · Lombardia', length: '5.79 km', turns: 11, laps: 3, difficulty: 'PRO', weather: 'CERAH', tag: 'TEMPLE OF SPEED', description: 'Lintasan berkecepatan tinggi dengan chicane tajam dan lintasan lurus panjang di taman Monza.' },
  { id: 3, name: 'Circuit de Barcelona-Catalunya', country: 'SPANYOL', region: 'Montmeló · Barcelona', length: '4.66 km', turns: 16, laps: 3, difficulty: 'AHLI', weather: 'CERAH', tag: 'GRAND PRIX', description: 'Kombinasi tikungan cepat dan teknis di lintasan Catalunya.' },
  { id: 4, name: 'Bugatti Circuit', country: 'PRANCIS', region: 'Le Mans · Pays de la Loire', length: '4.19 km', turns: 11, laps: 3, difficulty: 'PRO', weather: 'BERAWAN', tag: 'LE MANS', description: 'Lintasan permanen Le Mans dengan chicane, tikungan rapat, dan tribun besar.' },
  { id: 5, name: 'Spa-Francorchamps 2009', country: 'BELGIA', region: 'Stavelot · Ardennes', length: '7.00 km', turns: 20, laps: 3, difficulty: 'LEGENDA', weather: 'HUJAN RINGAN', tag: 'ARDENNES', description: 'Lintasan panjang bergelombang melewati hutan Ardennes dan tanjakan Eau Rouge.' },
  { id: 6, name: 'Spa-Francorchamps 2022', country: 'BELGIA', region: 'Stavelot · Ardennes', length: '7.00 km', turns: 19, laps: 3, difficulty: 'LEGENDA', weather: 'BERAWAN', tag: 'ARDENNES', description: 'Tata lintasan Spa era modern dengan perubahan elevasi dan rangkaian tikungan cepat.' },
  { id: 7, name: 'Hungaroring', country: 'HUNGARIA', region: 'Mogyoród · Budapest', length: '4.38 km', turns: 14, laps: 3, difficulty: 'AHLI', weather: 'CERAH', tag: 'GRAND PRIX', description: 'Sirkuit berliku di lembah dekat Budapest dengan sedikit lintasan lurus panjang.' },
  { id: 8, name: 'Nürburgring GP 2016', country: 'JERMAN', region: 'Nürburg · Eifel', length: '5.15 km', turns: 17, laps: 3, difficulty: 'AHLI', weather: 'BERAWAN', tag: 'EIFEL', description: 'Lintasan Grand Prix Nürburgring dengan tikungan teknis dan zona pengereman berat.' },
  { id: 9, name: 'Nürburgring GP 2022', country: 'JERMAN', region: 'Nürburg · Eifel', length: '5.15 km', turns: 17, laps: 3, difficulty: 'AHLI', weather: 'BERAWAN', tag: 'EIFEL', description: 'Model tata arena Nürburgring versi 2022, dikelilingi suasana hutan Eifel.' },
  { id: 10, name: 'Silverstone Circuit', country: 'INGGRIS', region: 'Silverstone · Northamptonshire', length: '5.89 km', turns: 18, laps: 3, difficulty: 'AHLI', weather: 'BERAWAN', tag: 'HOME OF BRITISH RACING', description: 'Sirkuit cepat Inggris dengan rangkaian Maggotts-Becketts dan lintasan lurus Hangar.' },
  { id: 11, name: 'Aventador Racing Circuit', country: 'ITALIA', region: 'APEX ? Test Circuit', length: '4.31 km', turns: 12, laps: 3, difficulty: 'PRO', weather: 'CERAH', tag: 'AVENTADOR RACING', description: 'Sirkuit teknis dari Lamborghini Aventador Racing dengan tribun besar, paddock, dan rangkaian tikungan cepat.' },
];

export const difficultyLevel: Record<string, number> = { PRO: 2, AHLI: 3, EKSTREM: 4, LEGENDA: 5 };

export const weatherIcon = (weather: string) =>
  weather.includes('HUJAN') ? '☂' : weather === 'CERAH' ? '☀' : weather === 'MALAM' ? '☾' : weather === 'SENJA' ? '◒' : '☁';

export const paintColors = [
  { name: 'Rosso', value: '#d1121f' },
  { name: 'Perak', value: '#c9ccd1' },
  { name: 'Biru', value: '#0f5fc4' },
  { name: 'Emas', value: '#e2a017' },
  { name: 'Hitam', value: '#15171c' },
  { name: 'Hijau', value: '#2f8f5f' },
];

const rawCars = [
  '1962_ferrari_250_gto','2012_koenigsegg_agera_r','2013_ferrari_458_spider','2014_ferrari_laferrari','2014_koenigsegg_one-1','2014_mclaren_p1_gtr_concept','2015_mclaren_650s_gt3','2016_bugatti_chiron','2016_mclaren_mp4-x','2018_ferrari_fxx-k_evo','2018_mclaren_720s_silverstone_aero_by_vorsteiner','2019_bugatti_divo','2019_bugatti_la_voiture_noire','2019_ferrari_488_pista','2019_lamborghini_sc18_alston','2019_mclaren_600lt','2019_mclaren_720s_gt3','2019_mclaren_senna','2020_bugatti_centodieci','2020_ferrari_sf90_stradale','2020_lamborghini_sian_fkp_37','2020_mclaren_senna_gtr','2021_bugatti_chiron_super_sport_300','2021_koenigsegg_jesko_absolut','2023_ferrari_sf90_xx_stradale','2023_koenigsegg_jesko_attack','2023_koenigsegg_regera_0-400-0_world_record','2025_bugatti_bolide','2025_mclaren_w1',
  '2015_ferrari_fxx_k','amg_w14_s1__www.vecarz.com','aston_martin_f1_amr23_2023','f1_2021_mclaren_mcl35m','scuderia_ferrari_f1_sf23_2023',
];
// Penulisan nama model yang tidak bisa ditebak dari nama file.
const spelling: Record<string, string> = {
  gto: 'GTO', gt3: 'GT3', gtr: 'GTR', fkp: 'FKP', xx: 'XX', fxx: 'FXX', mclaren: 'McLaren', laferrari: 'LaFerrari',
  sc18: 'SC18', sf90: 'SF90', 'fxx-k': 'FXX-K', 'mp4-x': 'MP4-X', '600lt': '600LT', '720s': '720S',
  '650s': '650S', 'one-1': 'One:1', '0-400-0': '0–400–0',
};
const brandName = (slug: string) =>
  slug.split('_').slice(1).map(s => spelling[s] ?? s[0].toUpperCase() + s.slice(1)).join(' ');
const carOverrides: Record<string, { name: string; year: string; brand: string; category: string }> = {
  '2015_ferrari_fxx_k': { name: 'Ferrari FXX K', year: '2015', brand: 'FERRARI', category: 'TRACK' },
  'amg_w14_s1__www.vecarz.com': { name: 'Mercedes-AMG W14', year: '2023', brand: 'MERCEDES-AMG', category: 'TRACK' },
  'aston_martin_f1_amr23_2023': { name: 'Aston Martin AMR23', year: '2023', brand: 'ASTON MARTIN', category: 'TRACK' },
  'f1_2021_mclaren_mcl35m': { name: 'McLaren MCL35M', year: '2021', brand: 'MCLAREN', category: 'TRACK' },
  'scuderia_ferrari_f1_sf23_2023': { name: 'Ferrari SF-23', year: '2023', brand: 'FERRARI', category: 'TRACK' },
};
export const cars = rawCars.map((slug, i) => ({
  slug,
  file: `${slug}.glb`,
  thumb: `/thumbs/${slug}.webp`,
  livePreview: Boolean(carOverrides[slug]),
  name: carOverrides[slug]?.name ?? brandName(slug),
  year: carOverrides[slug]?.year ?? slug.slice(0, 4),
  brand: carOverrides[slug]?.brand ?? slug.split('_')[1].toUpperCase(),
  category: carOverrides[slug]?.category ?? (/gt3|gtr|bolide|attack|fxx|mp4-x/i.test(slug) ? 'TRACK' : i === 0 ? 'CLASSIC' : 'HYPERCAR'),
  // Nilai permainan, bukan data pabrikan.
  stats: { speed: 84 + (i % 15), acceleration: 77 + (i % 20), handling: 72 + (i % 22) },
}));

export const categories = ['SEMUA', 'HYPERCAR', 'TRACK', 'CLASSIC'];
export const brands = ['SEMUA', ...Array.from(new Set(cars.map(car => car.brand))).sort()];
