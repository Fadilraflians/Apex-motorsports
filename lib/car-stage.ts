/* Panggung 3D untuk menampilkan satu mobil. `three` tidak punya tipe, jadi objeknya bertipe any. */
import { createCar } from './car-loader';

export type CarInfo = { paintable: boolean };

export type CarStage = {
  /** Memuat mobil baru. Hasilnya null jika permintaan ini sudah digantikan yang lebih baru. */
  setCar: (url: string, onProgress?: (percent: number) => void) => Promise<CarInfo | null>;
  /** null = warna asli dari model. */
  setColor: (color: string | null) => void;
  snapshot: () => string;
  dispose: () => void;
};

export async function createCarStage(
  host: HTMLElement,
  { zoom = true, thumbnail = false }: { zoom?: boolean; thumbnail?: boolean } = {},
): Promise<CarStage> {
  const [THREE, { OrbitControls }, { RoomEnvironment }] = await Promise.all([
    import('three'),
    import('three/addons/controls/OrbitControls.js'),
    import('three/addons/environments/RoomEnvironment.js'),
  ]);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(thumbnail ? 1 : Math.min(window.devicePixelRatio, 1.35));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(thumbnail ? 28 : 32, 1, 0.1, 100);
  const pmrem = new THREE.PMREMGenerator(renderer);
  const room = new RoomEnvironment();
  const environment = pmrem.fromScene(room, 0.04);
  scene.environment = environment.texture;
  scene.environmentIntensity = 0.8;

  const key = new THREE.DirectionalLight(0xfff1de, 2.2);
  key.position.set(4, 7, 5);
  const rim = new THREE.DirectionalLight(0x6ea4ff, 2);
  rim.position.set(-6, 3, -4);
  const accent = new THREE.DirectionalLight(0xff3347, 1.1);
  accent.position.set(5, 1.5, -5);
  scene.add(key, rim, accent);

  const radialTexture = (stops: [number, string][]) => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 256;
    const ctx = canvas.getContext('2d')!;
    const gradient = ctx.createRadialGradient(128, 128, 0, 128, 128, 128);
    stops.forEach(([offset, color]) => gradient.addColorStop(offset, color));
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 256, 256);
    return new THREE.CanvasTexture(canvas);
  };

  const flat = (geometry: unknown, material: unknown, y: number) => {
    const mesh = new THREE.Mesh(geometry, material);
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.y = y;
    scene.add(mesh);
    return mesh;
  };

  if (!thumbnail) {
    flat(
      new THREE.CircleGeometry(3.7, 96),
      new THREE.MeshBasicMaterial({
        map: radialTexture([[0, 'rgba(92,100,120,.6)'], [0.65, 'rgba(32,36,46,.55)'], [1, 'rgba(10,12,16,0)']]),
        transparent: true,
        depthWrite: false,
      }),
      -0.02,
    );
    flat(new THREE.RingGeometry(2.72, 2.75, 128), new THREE.MeshBasicMaterial({ color: 0xff2d3b, transparent: true, opacity: 0.75 }), -0.01);
    flat(new THREE.RingGeometry(3.12, 3.128, 128), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.14 }), -0.01);
  }

  const shadow = flat(
    new THREE.PlaneGeometry(1, 1),
    new THREE.MeshBasicMaterial({
      map: radialTexture([[0, 'rgba(0,0,0,.85)'], [0.55, 'rgba(0,0,0,.55)'], [1, 'rgba(0,0,0,0)']]),
      transparent: true,
      depthWrite: false,
    }),
    0,
  );
  shadow.visible = false;

  host.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enabled = !thumbnail;
  controls.enablePan = false;
  controls.enableZoom = zoom;
  controls.enableDamping = true;
  controls.minPolarAngle = Math.PI * 0.22;
  controls.maxPolarAngle = Math.PI * 0.49;
  controls.autoRotate = !thumbnail && !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  controls.autoRotateSpeed = 0.9;
  controls.target.set(0, thumbnail ? 0.55 : 0.5, 0);
  // Tanpa zoom (menu utama), geser vertikal di layar sentuh tetap menggulir halaman.
  if (!zoom) renderer.domElement.style.touchAction = 'pan-y';

  const direction = new THREE.Vector3(0.74, 0.3, 0.86).normalize();
  let baseDistance = 0;
  const resize = () => {
    const width = Math.max(1, host.clientWidth);
    const height = Math.max(1, host.clientHeight);
    renderer.setSize(width, height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    const next = (thumbnail ? 6.1 : 7.2) * Math.max(1, 1.45 / camera.aspect);
    if (Math.abs(next - baseDistance) < 0.01) return;
    baseDistance = next;
    controls.minDistance = next * 0.7;
    controls.maxDistance = next * 1.35;
    camera.position.copy(direction).multiplyScalar(next).add(controls.target);
    controls.update();
  };
  resize();
  const observer = new ResizeObserver(resize);
  observer.observe(host);

  let dead = false;
  let frame = 0;
  const loop = () => {
    controls.update();
    renderer.render(scene, camera);
    frame = requestAnimationFrame(loop);
  };
  if (!thumbnail) loop();

  const disposeObject = (root: any) => {
    root.traverse((object: any) => {
      if (!object.isMesh) return;
      object.geometry?.dispose();
      [object.material].flat().forEach((material: any) => {
        Object.values(material).forEach((value: any) => value?.isTexture && value.dispose());
        material.dispose();
      });
    });
  };

  let current: any = null;
  let car: Awaited<ReturnType<typeof createCar>> | null = null;
  let color: string | null = null;
  let request = 0;

  const clearCar = () => {
    if (!current) return;
    scene.remove(current);
    // Clone berbagi geometri dan tekstur dengan cache GLTF.
    car?.dispose();
    current = null;
    car = null;
    shadow.visible = false;
  };

  return {
    async setCar(url, onProgress) {
      const id = ++request;
      clearCar();
      const next = await createCar(url, percent => id === request && onProgress?.(percent));
      if (dead || id !== request) {
        next.dispose();
        return null;
      }

      const model = next.object;
      model.updateMatrixWorld(true);
      const bounds = new THREE.Box3().setFromObject(model);
      const size = bounds.getSize(new THREE.Vector3());
      const center = bounds.getCenter(new THREE.Vector3());
      const scale = 4 / Math.max(size.x, size.y, size.z);
      model.position.x -= center.x;
      model.position.y -= bounds.min.y;
      model.position.z -= center.z;
      const group = new THREE.Group();
      group.add(model);
      group.scale.setScalar(scale);
      next.setColor(color);
      // Kompilasi shader sebelum model baru ditampilkan agar kemunculan 3D stabil.
      try {
        await renderer.compileAsync(group, camera, scene);
      } catch {}
      if (dead || id !== request) {
        next.dispose();
        return null;
      }

      const previous = current;
      const previousCar = car;
      scene.add(group);
      if (previous) scene.remove(previous);
      previousCar?.dispose();
      current = group;
      car = next;
      car.setColor(color);
      shadow.scale.set(size.x * scale * 1.35, size.z * scale * 1.25, 1);
      shadow.visible = true;
      return { paintable: car.paintable };
    },
    setColor(next) {
      color = next;
      car?.setColor(color);
    },
    snapshot() {
      renderer.render(scene, camera);
      return renderer.domElement.toDataURL('image/webp', 0.86);
    },
    dispose() {
      dead = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      clearCar();
      disposeObject(scene);
      disposeObject(room);
      environment.dispose();
      pmrem.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    },
  };
}
