/* Jalannya balapan: fisika mobil pemain, lawan, hitung mundur, kamera, dan peta kecil. */
import { carUrl, createCar } from '@/lib/car-loader';
import { loadTrackScene } from '@/lib/load-track';
import { createArena, lookFor, prepareTrack } from './arena';
import { createAudio } from './audio';
import { buildCourse, clamp, loadCourse, speedProfile, wrapAngle } from './course';

export type Stats = { speed: number; acceleration: number; handling: number };
export type Entrant = { file: string; car: string; driver: string; color: string | null };

export type RaceOptions = {
  trackId: number;
  title: string;
  laps: number;
  weather: string;
  player: Entrant & { stats: Stats };
  rivals: Entrant[];
  muted: boolean;
  signal?: AbortSignal;
  onProgress: (message: string, percent: number) => void;
  onHud: (hud: Hud) => void;
};

export type Result = { driver: string; car: string; time: number; you: boolean };

export type Hud = {
  phase: 'countdown' | 'racing' | 'finished';
  lights: number;
  go: boolean;
  lap: number;
  position: number;
  total: number;
  speed: number;
  gear: string;
  rpm: number;
  lapTime: number;
  bestLap: number | null;
  raceTime: number;
  wrongWay: boolean;
  brakeNow: boolean;
  paused: boolean;
  camera: string;
  muted: boolean;
  assist: boolean;
  results: Result[] | null;
};

export type Control = 'gas' | 'brake' | 'left' | 'right';

const CAMERAS = ['Belakang dekat', 'Belakang jauh', 'Kap mesin', 'Helikopter', 'Kokpit'];
const KEYS: Record<string, Control> = {
  ArrowUp: 'gas', KeyW: 'gas', ArrowDown: 'brake', KeyS: 'brake',
  ArrowLeft: 'left', KeyA: 'left', ArrowRight: 'right', KeyD: 'right',
};
const BRAKE = 34;
const CAR_LENGTH = 4.7;

const disposeTree = (root: any) => root?.traverse((object: any) => {
  object.geometry?.dispose();
  [object.material].flat().forEach((material: any) => {
    if (!material) return;
    Object.values(material).forEach((value: any) => value?.isTexture && value.dispose());
    material.dispose();
  });
});

export async function createRace(host: HTMLElement, map: HTMLCanvasElement, options: RaceOptions, cancelled: () => boolean) {
  options.onProgress('Menyiapkan sirkuit', 3);
  const [THREE, { RoomEnvironment }] = await Promise.all([
    import('three'),
    import('three/addons/environments/RoomEnvironment.js'),
  ]);
  if (cancelled()) return null;

  // Mobil, data lintasan (garis tengah, lebar, dinding, tinggi), dan model arena dimuat bersamaan.
  const entrants = [...options.rivals, options.player];
  let loaded = 0;
  let trackPercent = 0;
  const report = () => options.onProgress(
    trackPercent < 100 ? 'Memuat sirkuit' : `Memuat mobil di grid (${loaded}/${entrants.length})`,
    3 + trackPercent * 0.72 + (loaded / entrants.length) * 15,
  );
  const carsPromise = Promise.all(
    entrants.map(async entrant => {
      const car = await createCar(carUrl(entrant.file));
      loaded++;
      report();
      return car;
    }),
  );
  carsPromise.catch(() => {});
  const coursePromise = loadCourse(options.trackId, options.signal);
  const trackPromise = loadTrackScene(options.trackId, percent => {
    trackPercent = percent;
    report();
  }, options.signal);
  const [courseData, gltf] = await Promise.all([coursePromise, trackPromise]);
  if (cancelled()) {
    disposeTree(gltf.scene);
    return null;
  }
  const course = buildCourse(courseData);
  const track = gltf.scene;
  const trackTextures = prepareTrack(THREE, track);
  const rainy = lookFor(options.weather).rain;

  const touchDevice = window.matchMedia('(pointer: coarse)').matches;
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance', stencil: false });
  // Resolusi dibatasi agar frame rate mulus tanpa membebani GPU.
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.0));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.shadowMap.enabled = false;
  const pmrem = new THREE.PMREMGenerator(renderer);
  const room = new RoomEnvironment();
  const environment = pmrem.fromScene(room, 0.04).texture;
  room.dispose?.();
  const camera = new THREE.PerspectiveCamera(62, 1, 0.4, 3200);
  const cockpit = new THREE.Group();
  cockpit.visible = false;
  const cockpitBlack = new THREE.MeshStandardMaterial({ color: 0x111317, roughness: 0.72, metalness: 0.22 });
  const cockpitRed = new THREE.MeshStandardMaterial({ color: 0xd51525, roughness: 0.55, metalness: 0.2 });
  const skin = new THREE.MeshStandardMaterial({ color: 0xc8875f, roughness: 0.82 });
  const sleeve = new THREE.MeshStandardMaterial({ color: 0x17191e, roughness: 0.78 });
  const cockpitPart = (geometry: any, material: any, position: [number, number, number]) => {
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(...position);
    mesh.frustumCulled = false;
    cockpit.add(mesh);
    return mesh;
  };
  cockpitPart(new THREE.BoxGeometry(1.35, 0.16, 0.38), cockpitBlack, [0, -0.49, -0.92]);
  cockpitPart(new THREE.BoxGeometry(0.78, 0.035, 0.08), cockpitRed, [0, -0.405, -0.82]);
  const steeringWheel = cockpitPart(new THREE.TorusGeometry(0.235, 0.027, 12, 48), cockpitBlack, [0, -0.275, -0.72]);
  cockpitPart(new THREE.BoxGeometry(0.035, 0.27, 0.04), cockpitBlack, [0, -0.265, -0.72]);
  cockpitPart(new THREE.BoxGeometry(0.3, 0.035, 0.04), cockpitBlack, [0, -0.39, -0.72]);
  cockpitPart(new THREE.CylinderGeometry(0.057, 0.057, 0.055, 24), cockpitRed, [0, -0.275, -0.75]).rotation.x = Math.PI / 2;
  const segment = (material: any, from: [number, number, number], to: [number, number, number], radius: number) => {
    const a = new THREE.Vector3(...from), b = new THREE.Vector3(...to);
    const mesh = cockpitPart(new THREE.CapsuleGeometry(radius, a.distanceTo(b), 5, 10), material, [0, 0, 0]);
    mesh.position.copy(a).add(b).multiplyScalar(0.5);
    mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.sub(a).normalize());
    return mesh;
  };
  for (const side of [-1, 1]) {
    const wrist: [number, number, number] = [side * 0.16, -0.105, -0.725];
    segment(sleeve, [side * 0.49, -0.53, -0.83], [side * 0.28, -0.35, -0.76], 0.075);
    segment(skin, [side * 0.28, -0.35, -0.76], wrist, 0.052);
    cockpitPart(new THREE.SphereGeometry(0.075, 16, 12), skin, wrist);
    for (let finger = 0; finger < 4; finger++) {
      const x = side * (0.115 + finger * 0.026);
      segment(skin, [x, -0.105, -0.77], [x - side * 0.012, -0.18, -0.75], 0.018);
    }
    segment(skin, [side * 0.11, -0.09, -0.72], [side * 0.07, -0.17, -0.72], 0.02);
  }
  camera.add(cockpit);
  const arena = createArena(THREE, renderer, track, options.weather);
  const world = arena;
  world.scene.add(camera);
  world.scene.environment = environment;
  world.scene.environmentIntensity = 0.55;

  const destroyScene = () => {
    disposeTree(cockpit);
    world.dispose();
    environment.dispose();
    pmrem.dispose();
    renderer.dispose();
    renderer.forceContextLoss();
    renderer.domElement.remove();
  };

  /* ---------- Mobil ---------- */
  const shadowCanvas = document.createElement('canvas');
  shadowCanvas.width = shadowCanvas.height = 128;
  {
    const ctx = shadowCanvas.getContext('2d')!;
    const gradient = ctx.createRadialGradient(64, 64, 8, 64, 64, 64);
    gradient.addColorStop(0, 'rgba(0,0,0,.8)');
    gradient.addColorStop(0.6, 'rgba(0,0,0,.55)');
    gradient.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 128, 128);
  }
  const shadowTexture = new THREE.CanvasTexture(shadowCanvas);

  const models = await carsPromise.catch(error => {
    destroyScene();
    throw error;
  });
  if (cancelled()) {
    destroyScene();
    return null;
  }

  const bodies = models.map((model, index) => {
    model.setColor(entrants[index].color);
    const object = model.object;
    object.traverse((part: any) => { if (part.isMesh) part.castShadow = true; });
    object.updateMatrixWorld(true);
    const bounds = new THREE.Box3().setFromObject(object);
    const size = bounds.getSize(new THREE.Vector3());
    const center = bounds.getCenter(new THREE.Vector3());
    const scale = CAR_LENGTH / Math.max(size.x, size.z);
    const holder = new THREE.Group();
    object.position.set(object.position.x - center.x, object.position.y - bounds.min.y, object.position.z - center.z);
    holder.add(object);
    holder.scale.setScalar(scale);
    const group = new THREE.Group();
    group.rotation.order = 'YXZ';
    group.add(holder);
    const shadow = new THREE.Mesh(
      new THREE.PlaneGeometry(size.x * scale * 1.5, size.z * scale * 1.25).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({ map: shadowTexture, transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -3 }),
    );
    shadow.position.y = 0.04;
    group.add(shadow);
    world.scene.add(group);
    return { group, height: size.y * scale };
  });

  /* ---------- Keadaan pembalap ---------- */
  const { stats } = options.player;
  const top = 76 + (stats.speed - 84) * 0.9;
  const accel = 13 + (stats.acceleration - 77) * 0.2;
  const grip = 25 + (stats.handling - 72) * 0.25;
  // Batas aspal kiri/kanan berbeda di tiap titik lintasan.
  const roomLeft = (i: number) => course.roadLeft[i];
  const roomRight = (i: number) => course.roadRight[i];
  const playerProfile = speedProfile(course, top, grip, BRAKE * 0.85);

  const racers = entrants.map((entrant, index) => {
    const you = index === entrants.length - 1;
    const skill = you ? 0.97 : [0.965, 0.94, 0.915][index % 3];
    return {
      ...entrant, you, skill, body: bodies[index],
      profile: you ? playerProfile : speedProfile(course, top * skill, grip * skill, BRAKE * 0.72),
      x: 0, z: 0, heading: 0, v: 0, s: 0, lane: 0, laneRate: 0, progress: 0, index: 0,
      laps: 0, lapStart: 0, best: null as number | null, finish: null as number | null, delay: 0,
    };
  });
  type Racer = (typeof racers)[number];
  const player = racers[racers.length - 1];

  const input: Record<Control, boolean> = { gas: false, brake: false, left: false, right: false };
  const audio = createAudio(rainy);
  let muted = options.muted;
  let paused = false;
  let assist = true;
  let cameraMode = 0;
  let phase: Hud['phase'] = 'countdown';
  let countdown = 0;
  let lights = 0;
  let hold = 1;
  let raceTime = 0;
  let steer = 0;
  let touching = false;
  let results: Result[] | null = null;
  let cameraHeading = 0;
  let time = 0;
  audio.setMuted(muted);

  const pose = (racer: Racer, y: number, slope: number, roll = 0, bank = 0) => {
    const along = Math.cos(wrapAngle(racer.heading - course.at(racer.s).heading));
    const safeSlope = clamp(slope, -0.25, 0.25);
    const safeBank = clamp(bank, -0.16, 0.16);
    racer.body.group.position.set(racer.x, y, racer.z);
    racer.body.group.rotation.set(-Math.atan(safeSlope * along), racer.heading, roll - Math.atan(safeBank * along));
  };

  /** Kendali otomatis: mengikuti garis balap dan menghindari mobil di depan. */
  const drive = (racer: Racer, dt: number, pace: number) => {
    const here = course.at(racer.s);
    const ahead = course.at(racer.s + 18 + racer.v * 0.5);
    let wanted = clamp(-ahead.curve * 240, -(roomLeft(here.i) - 2), roomRight(here.i) - 2);
    let limit = Infinity;
    for (const other of racers) {
      if (other === racer) continue;
      let gap = other.progress - racer.progress;
      gap -= Math.round(gap / course.length) * course.length;
      if (gap > 0 && gap < 9 + racer.v * 0.25 && Math.abs(other.lane - racer.lane) < 2.7) {
        wanted = other.lane + (other.lane > 0 ? -3.3 : 3.3);
        if (gap < CAR_LENGTH + 1.5 && Math.abs(other.lane - racer.lane) < 2.1) limit = Math.max(0, other.v - 1);
      }
    }
    const change = clamp(clamp(wanted, -(roomLeft(here.i) - 1.3), roomRight(here.i) - 1.3) - racer.lane, -3.2 * dt, 3.2 * dt);
    racer.lane += change;
    racer.laneRate = change / Math.max(dt, 1e-3);
    const target = Math.min(limit, racer.profile[here.i] * pace);
    const gain = accel * racer.skill * Math.max(0, 1 - (racer.v / (top * 1.06)) ** 2);
    racer.v = Math.max(0, racer.v + clamp(target - racer.v, -BRAKE * dt, gain * dt));
    racer.progress += racer.v * dt;
    racer.s = ((racer.progress % course.length) + course.length) % course.length;
    const p = course.at(racer.s, racer.lane);
    racer.x = p.x;
    racer.z = p.z;
    racer.index = p.i;
    racer.heading = p.heading - Math.atan(racer.laneRate / Math.max(racer.v, 8));
    pose(racer, p.y, p.slope, clamp(p.curve * racer.v * racer.v * 0.0012, -0.035, 0.035), p.bank);
  };

  const drivePlayer = (dt: number) => {
    const p = player;
    const turning = (input.left ? 1 : 0) - (input.right ? 1 : 0);
    steer += (turning - steer) * Math.min(1, dt * (turning ? 5.5 : 10));
    const gas = input.gas;
    const surface = p.lane < -(roomLeft(p.index) + 1.4) || p.lane > roomRight(p.index) + 1.4;
    let a = 0;
    if (gas) a = accel * Math.max(0, 1 - (p.v / (top * 1.07)) ** 2) * (surface ? 0.55 : 1);
    if (input.brake) a = p.v > 0.5 ? -BRAKE : -9;
    a -= Math.sign(p.v) * (0.45 + 0.00045 * p.v * p.v);
    if (surface) a -= Math.sign(p.v) * Math.min(14, Math.abs(p.v) * 0.28);
    p.v = Math.max(-12, p.v + a * dt);
    if (!gas && !input.brake && Math.abs(p.v) < 0.5) p.v = 0;

    const traction = grip * (rainy ? 0.92 : 1) * (surface ? 0.6 : 1);
    const rate = Math.min(Math.abs(p.v) / 8, traction / Math.max(Math.abs(p.v), 1));
    p.heading += steer * rate * Math.sign(p.v) * dt;
    // Bantuan kemudi: saat tombol belok dilepas, hidung mobil mengikuti arah lintasan.
    if (assist && !turning && p.v > 4) {
      const aim = course.at(p.s + 6 + p.v * 0.22, p.lane).heading;
      const error = wrapAngle(aim - p.heading);
      if (Math.abs(error) < 0.75) p.heading += clamp(error * 2.2, -rate, rate) * dt;
    }
    p.x += Math.sin(p.heading) * p.v * dt;
    p.z += Math.cos(p.heading) * p.v * dt;

    const found = course.locate(p.x, p.z, p.index);
    const i = found.i;
    p.index = i;
    p.lane = found.lateral;
    const side = Math.sign(p.lane) || 1;
    const limit = (side < 0 ? course.wallLeft : course.wallRight)[i] - 1.1;
    if (Math.abs(p.lane) > limit) {
      const excess = Math.abs(p.lane) - limit;
      p.x += course.tz[i] * side * excess;
      p.z -= course.tx[i] * side * excess;
      const into = (-Math.sin(p.heading) * course.tz[i] + Math.cos(p.heading) * course.tx[i]) * side * Math.sign(p.v);
      if (into > 0.02) {
        p.v *= touching ? 1 - dt * 0.7 : Math.max(0.35, 1 - into * into * 1.5);
        const facing = Math.cos(wrapAngle(p.heading - course.heading[i])) >= 0 ? 0 : Math.PI;
        p.heading += wrapAngle(course.heading[i] + facing - p.heading) * Math.min(1, 0.25 + into);
      }
      p.lane = side * limit;
      touching = true;
    } else touching = false;

    let moved = found.s - p.s;
    moved -= Math.round(moved / course.length) * course.length;
    p.progress += moved;
    p.s = found.s;
    const here = course.at(p.s, p.lane);
    pose(p, here.y, here.slope, clamp(-steer * p.v * 0.0006, -0.035, 0.035), here.bank);
  };

  const collide = () => {
    const sin = Math.sin(player.heading);
    const cos = Math.cos(player.heading);
    for (const other of racers) {
      if (other.you) continue;
      const dx = other.x - player.x;
      const dz = other.z - player.z;
      const forward = dx * sin + dz * cos;
      const sideways = dx * cos - dz * sin; // positif = kiri pemain
      const overlapLong = CAR_LENGTH - Math.abs(forward);
      const overlapSide = 2.15 - Math.abs(sideways);
      if (overlapLong <= 0 || overlapSide <= 0) continue;
      if (overlapSide < overlapLong * 0.7) {
        const away = Math.sign(sideways) || 1;
        player.x -= cos * away * overlapSide * 0.5;
        player.z += sin * away * overlapSide * 0.5;
        // Jalur positif = kanan, jadi mobil di kiri pemain didorong ke nilai negatif.
        other.lane = clamp(other.lane - away * overlapSide * 0.5, -(roomLeft(other.index) - 1), roomRight(other.index) - 1);
        player.v *= 0.996;
      } else if (forward > 0) {
        player.v = Math.min(player.v, other.v * 0.92);
        player.x -= sin * overlapLong * 0.5;
        player.z -= cos * overlapLong * 0.5;
        other.progress += overlapLong * 0.3;
      } else {
        other.v = Math.min(other.v, Math.max(0, player.v * 0.9));
        other.progress -= overlapLong * 0.5;
      }
    }
  };

  const place = () => {
    racers.forEach((racer, index) => {
      // Pemain selalu start paling belakang.
      const slot = racer.you ? racers.length - 1 : index;
      racer.progress = -5 - slot * 8 - 2.4;
      racer.s = course.length + racer.progress;
      racer.lane = slot % 2 ? -3 : 3;
      const p = course.at(racer.s, racer.lane);
      Object.assign(racer, { x: p.x, z: p.z, heading: p.heading, index: p.i, v: 0, laneRate: 0, laps: 0, lapStart: 0, best: null, finish: null });
      racer.delay = 0.12 + Math.random() * 0.3;
      pose(racer, p.y, p.slope, 0, p.bank);
    });
    cameraHeading = player.heading;
    phase = 'countdown';
    countdown = 0;
    lights = 0;
    hold = 0.6 + Math.random() * 1.2;
    raceTime = 0;
    steer = 0;
    results = null;
    paused = false;
  };

  const ordered = () =>
    [...racers].sort((a, b) =>
      a.finish !== null || b.finish !== null ? (a.finish ?? Infinity) - (b.finish ?? Infinity) : b.progress - a.progress);

  const goal = () => options.laps * course.length;

  const step = (dt: number) => {
    if (phase === 'countdown') {
      countdown += dt;
      const next = clamp(Math.floor((countdown - 1.4) / 0.85) + 1, 0, 5);
      if (next > lights) {
        lights = next;
        audio.beep(440);
      }
      // Lampu padam = mulai.
      if (countdown > 1.4 + 4 * 0.85 + hold) {
        phase = 'racing';
        lights = 0;
        audio.beep(880, 0.5);
      }
      return;
    }
    raceTime += dt;
    for (const racer of racers) {
      if (racer.you && phase === 'racing') drivePlayer(dt);
      else if (racer.you) drive(racer, dt, 0.55);
      else if (raceTime > racer.delay) {
        // Lawan sedikit menyesuaikan diri agar persaingan tetap rapat.
        const gap = clamp((player.progress - racer.progress) / 2500, -0.05, 0.045);
        drive(racer, dt, racer.finish === null ? 1 + gap : 0.55);
      }
    }
    if (phase === 'racing') collide();

    for (const racer of racers) {
      if (racer.finish !== null || racer.progress < (racer.laps + 1) * course.length) continue;
      const lapTime = raceTime - racer.lapStart;
      racer.laps++;
      racer.lapStart = raceTime;
      racer.best = racer.best === null ? lapTime : Math.min(racer.best, lapTime);
      if (racer.laps >= options.laps) {
        racer.finish = raceTime;
        if (racer.you) {
          phase = 'finished';
          audio.beep(660, 0.6);
          player.lane = clamp(player.lane, -(roomLeft(player.index) - 1.3), roomRight(player.index) - 1.3);
        }
      }
    }
    if (phase === 'finished') {
      // Waktu pembalap yang belum finis diperkirakan dari kecepatan rata-ratanya.
      results = racers
        .map(racer => ({
          driver: racer.driver,
          car: racer.car,
          you: racer.you,
          time: racer.finish ?? raceTime + (goal() - racer.progress) / Math.max(20, racer.progress / raceTime),
        }))
        .sort((a, b) => a.time - b.time);
    }
  };

  /* ---------- Kamera ---------- */
  const eye = new THREE.Vector3();
  const look = new THREE.Vector3();
  const moveCamera = (dt: number) => {
    const car = player.body.group.position;
    const speed = Math.min(1, Math.abs(player.v) / top);
    cameraHeading += wrapAngle(player.heading - cameraHeading) * (1 - Math.exp(-dt * 7));
    const sin = Math.sin(cameraHeading);
    const cos = Math.cos(cameraHeading);
    const slope = clamp(course.at(player.s).slope, -0.2, 0.2);
    cockpit.visible = cameraMode === 4 && !(phase === 'countdown' && countdown < 3.2);
    steeringWheel.rotation.z = -steer * 0.48;
    let fov = 60 + speed * 18;
    if (phase === 'countdown' && countdown < 3.2) {
      // Pembukaan: kamera mengitari grid.
      const t = countdown / 3.2;
      const ease = t * t * (3 - 2 * t);
      const angle = player.heading + Math.PI * (0.25 + 0.75 * ease);
      const distance = 13 - 5.8 * ease;
      eye.set(car.x + Math.sin(angle) * distance, car.y + 5 - 2.5 * ease, car.z + Math.cos(angle) * distance);
      look.set(car.x + Math.sin(player.heading) * 8 * ease, car.y + 0.9 + ease, car.z + Math.cos(player.heading) * 8 * ease);
      fov = 55;
    } else if (cameraMode === 2) {
      const h = player.body.height;
      eye.set(car.x + Math.sin(player.heading) * 0.45, car.y + h * 1.02 + 0.08, car.z + Math.cos(player.heading) * 0.45);
      look.set(eye.x + Math.sin(player.heading) * 30, eye.y - 2.4 + slope * 30, eye.z + Math.cos(player.heading) * 30);
      fov = 68 + speed * 16;
    } else if (cameraMode === 3) {
      eye.set(car.x - sin * 20, car.y + 30, car.z - cos * 20);
      look.set(car.x + sin * 8, car.y, car.z + cos * 8);
      fov = 55;
    } else if (cameraMode === 4) {
      const h = player.body.height;
      eye.set(car.x + sin * 0.22, car.y + h * 0.76, car.z + cos * 0.22);
      look.set(eye.x + sin * 120, eye.y - 1.2 + slope * 120, eye.z + cos * 120);
      fov = 76 + speed * 5;
    } else {
      const distance = cameraMode === 1 ? 13 : 5.2;
      const height = cameraMode === 1 ? 5 : 1.9;
      eye.set(car.x - sin * distance, car.y + height - slope * distance * 0.6, car.z - cos * distance);
      look.set(car.x + sin * 6, car.y + 0.85 + slope * 6, car.z + cos * 6);
    }
    camera.position.copy(eye);
    camera.lookAt(look);
    if (Math.abs(camera.fov - fov) > 0.05) {
      camera.fov = fov;
      camera.updateProjectionMatrix();
    }
  };

  /* ---------- Peta kecil ---------- */
  const mapContext = map.getContext('2d')!;
  const SIZE = 220;
  map.width = map.height = SIZE;
  let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
  for (let i = 0; i < course.n; i++) {
    minX = Math.min(minX, course.x[i]);
    maxX = Math.max(maxX, course.x[i]);
    minZ = Math.min(minZ, course.z[i]);
    maxZ = Math.max(maxZ, course.z[i]);
  }
  const mapScale = (SIZE - 24) / Math.max(maxX - minX, maxZ - minZ);
  const toMap = (x: number, z: number): [number, number] => [
    SIZE / 2 + (x - (minX + maxX) / 2) * mapScale,
    SIZE / 2 + (z - (minZ + maxZ) / 2) * mapScale,
  ];
  const outline = new Path2D();
  for (let i = 0; i < course.n; i += 3) {
    const [x, y] = toMap(course.x[i], course.z[i]);
    if (i) outline.lineTo(x, y);
    else outline.moveTo(x, y);
  }
  outline.closePath();
  const drawMap = () => {
    mapContext.clearRect(0, 0, SIZE, SIZE);
    mapContext.lineJoin = 'round';
    mapContext.strokeStyle = 'rgba(0,0,0,.65)';
    mapContext.lineWidth = 9;
    mapContext.stroke(outline);
    mapContext.strokeStyle = '#ffffff';
    mapContext.lineWidth = 3.5;
    mapContext.stroke(outline);
    const start = toMap(course.x[0], course.z[0]);
    mapContext.fillStyle = '#ff2d3b';
    mapContext.fillRect(start[0] - 3, start[1] - 3, 6, 6);
    racers.forEach(racer => {
      mapContext.beginPath();
      mapContext.arc(...toMap(racer.x, racer.z), racer.you ? 6.5 : 5, 0, Math.PI * 2);
      mapContext.fillStyle = racer.you ? '#ff2d3b' : '#ffd21c';
      mapContext.fill();
      mapContext.lineWidth = 2;
      mapContext.strokeStyle = '#08090d';
      mapContext.stroke();
    });
  };

  /* ---------- Data untuk layar ---------- */
  const publish = () => {
    const speed = Math.abs(player.v);
    const gearSize = top / 7;
    const gear = Math.min(7, 1 + Math.floor(speed / gearSize));
    const rpm = phase === 'countdown' ? (input.gas ? 0.75 : 0.12) : Math.min(1, 0.25 + ((speed - (gear - 1) * gearSize) / gearSize) * 0.75);
    const aim = playerProfile[course.indexAt(player.s + speed * 0.55).i];
    options.onHud({
      phase,
      lights,
      go: phase === 'racing' && raceTime < 1.4,
      lap: clamp(player.laps + 1, 1, options.laps),
      position: ordered().indexOf(player) + 1,
      total: racers.length,
      speed: Math.round(speed * 3.6),
      gear: player.v < -0.5 ? 'R' : speed < 0.5 ? 'N' : String(gear),
      rpm,
      lapTime: phase === 'racing' ? raceTime - player.lapStart : 0,
      bestLap: player.best,
      raceTime: player.finish ?? raceTime,
      wrongWay: phase === 'racing' && player.v > 4 && Math.cos(wrapAngle(player.heading - course.heading[player.index])) < -0.2,
      brakeNow: phase === 'racing' && speed > aim * 1.1 + 4,
      paused,
      camera: CAMERAS[cameraMode],
      muted,
      assist,
      results,
    });
  };

  /* ---------- Masukan ---------- */
  const release = () => (Object.keys(input) as Control[]).forEach(key => (input[key] = false));
  const setPaused = (value: boolean) => {
    if (phase === 'finished') return;
    paused = value;
    release();
    audio.setMuted(muted || paused);
    publish();
  };
  const recover = () => {
    if (phase !== 'racing') return;
    const p = course.at(player.s, 0);
    Object.assign(player, { x: p.x, z: p.z, heading: p.heading, v: 0, lane: 0, index: p.i });
    cameraHeading = p.heading;
    pose(player, p.y, p.slope, 0, p.bank);
  };
  const cycleCamera = () => {
    cameraMode = (cameraMode + 1) % CAMERAS.length;
    publish();
  };
  const toggleMuted = () => {
    muted = !muted;
    audio.setMuted(muted || paused);
    publish();
    return muted;
  };
  const toggleAssist = () => {
    assist = !assist;
    publish();
  };

  const keydown = (event: KeyboardEvent) => {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    audio.resume();
    const control = KEYS[event.code];
    if (control) {
      event.preventDefault();
      if (!paused) input[control] = true;
      return;
    }
    if (event.repeat) return;
    if (event.code === 'Escape' || event.code === 'KeyP') {
      event.preventDefault();
      setPaused(!paused);
    }
    if (event.code === 'KeyC') cycleCamera();
    if (event.code === 'KeyR') recover();
    if (event.code === 'KeyM') toggleMuted();
  };
  const keyup = (event: KeyboardEvent) => {
    const control = KEYS[event.code];
    if (control) input[control] = false;
  };
  const hidden = () => document.hidden && !paused && setPaused(true);
  window.addEventListener('keydown', keydown);
  window.addEventListener('keyup', keyup);
  window.addEventListener('blur', release);
  document.addEventListener('visibilitychange', hidden);

  host.appendChild(renderer.domElement);
  const resize = () => {
    const width = Math.max(1, host.clientWidth);
    const height = Math.max(1, host.clientHeight);
    renderer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  };
  const observer = new ResizeObserver(resize);
  observer.observe(host);
  resize();

  place();
  moveCamera(0);
  options.onProgress('Menyalakan mesin', 92);
  // Unggah semua tekstur dan kompilasi shader sekarang, bukan saat pertama terlihat di tengah balapan (penyebab tersendat).
  options.onProgress('Menyiapkan grafis', 94);
  trackTextures.forEach(texture => renderer.initTexture(texture));
  await renderer.compileAsync(world.scene, camera).catch(() => {});

  let frame = 0;
  let previous = performance.now();
  let sinceHud = 1;
  const loop = (now: number) => {
    const dt = Math.min(0.05, Math.max(0, (now - previous) / 1000));
    previous = now;
    if (!paused) {
      time += dt;
      // Dua langkah kecil per bingkai agar tabrakan dinding tetap stabil.
      step(dt / 2);
      step(dt / 2);
      moveCamera(dt);
      world.update(camera, dt);
      audio.engine(
        phase === 'countdown' ? (input.gas ? 0.75 : 0.12) : (Math.abs(player.v) % (top / 7)) / (top / 7) * 0.65 + (Math.abs(player.v) / top) * 0.35,
        input.gas ? 1 : 0,
      );
    }
    renderer.render(world.scene, camera);
    sinceHud += dt;
    if (sinceHud > 0.066) {
      sinceHud = 0;
      publish();
      drawMap();
    }
    frame = requestAnimationFrame(loop);
  };

  const dispose = () => {
    cancelAnimationFrame(frame);
    observer.disconnect();
    window.removeEventListener('keydown', keydown);
    window.removeEventListener('keyup', keyup);
    window.removeEventListener('blur', release);
    document.removeEventListener('visibilitychange', hidden);
    audio.close();
    shadowTexture.dispose();
    destroyScene();
  };

  if (cancelled()) {
    dispose();
    return null;
  }
  frame = requestAnimationFrame(loop);

  return {
    setControl(control: Control, pressed: boolean) {
      audio.resume();
      input[control] = pressed && !paused;
    },
    setPaused,
    recover,
    cycleCamera,
    toggleMuted,
    toggleAssist,
    restart() {
      release();
      place();
      audio.setMuted(muted);
    },
    dispose,
  };
}

export type Race = NonNullable<Awaited<ReturnType<typeof createRace>>>;
