/* Suara mesin, bunyi lampu start, dan hujan yang dibuat langsung dengan Web Audio. */

export function createAudio(rain: boolean) {
  let context: AudioContext | null = null;
  try {
    context = new AudioContext();
  } catch {
    return { engine() {}, beep() {}, setMuted() {}, resume() {}, close() {} };
  }
  const audio = context;
  const master = audio.createGain();
  master.gain.value = 0;
  master.connect(audio.destination);

  const filter = audio.createBiquadFilter();
  filter.type = 'lowpass';
  filter.frequency.value = 900;
  const engineGain = audio.createGain();
  engineGain.gain.value = 0.05;
  filter.connect(engineGain).connect(master);
  const voices = ([['sawtooth', 1], ['square', 0.5], ['sawtooth', 2.01]] as const).map(([type, ratio]) => {
    const oscillator = audio.createOscillator();
    oscillator.type = type;
    oscillator.frequency.value = 60 * ratio;
    oscillator.connect(filter);
    oscillator.start();
    return { oscillator, ratio };
  });

  if (rain) {
    const buffer = audio.createBuffer(1, audio.sampleRate * 2, audio.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
    const source = audio.createBufferSource();
    source.buffer = buffer;
    source.loop = true;
    const high = audio.createBiquadFilter();
    high.type = 'highpass';
    high.frequency.value = 2500;
    const gain = audio.createGain();
    gain.gain.value = 0.025;
    source.connect(high).connect(gain).connect(master);
    source.start();
  }

  return {
    /** rpm dan gas bernilai 0..1. */
    engine(rpm: number, throttle: number) {
      const frequency = 55 + rpm * 190;
      voices.forEach(({ oscillator, ratio }) => oscillator.frequency.setTargetAtTime(frequency * ratio, audio.currentTime, 0.03));
      filter.frequency.setTargetAtTime(500 + rpm * 1800 + throttle * 700, audio.currentTime, 0.05);
      engineGain.gain.setTargetAtTime(0.035 + throttle * 0.045, audio.currentTime, 0.08);
    },
    beep(frequency: number, duration = 0.18) {
      const oscillator = audio.createOscillator();
      const gain = audio.createGain();
      oscillator.frequency.value = frequency;
      gain.gain.setValueAtTime(0.25, audio.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + duration);
      oscillator.connect(gain).connect(master);
      oscillator.start();
      oscillator.stop(audio.currentTime + duration);
    },
    setMuted(muted: boolean) {
      master.gain.setTargetAtTime(muted ? 0 : 1, audio.currentTime, 0.05);
    },
    resume() {
      if (audio.state === 'suspended') audio.resume().catch(() => {});
    },
    close() {
      audio.close().catch(() => {});
    },
  };
}
