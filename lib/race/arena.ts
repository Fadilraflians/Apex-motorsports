/* Dunia balap: model sirkuit GLB asli dari folder Track ditambah langit, cahaya, dan cuaca.
 * Tidak ada lagi lintasan atau pemandangan buatan; semua yang terlihat berasal dari model. */

type Look = {
  top: number; horizon: number; fog: [number, number];
  sun: number; sunIntensity: number; sky: number; ground: number; ambient: number;
  exposure: number; rain: boolean;
};

const LOOKS: Record<string, Look> = {
  CERAH: { top: 0x3f7fd0, horizon: 0xcfe2f2, fog: [500, 2600], sun: 0xfff0d8, sunIntensity: 2.6, sky: 0xdcecff, ground: 0x6d6450, ambient: 1.5, exposure: 1.05, rain: false },
  BERAWAN: { top: 0x7d8ea3, horizon: 0xc9d1da, fog: [380, 2100], sun: 0xf2f2f2, sunIntensity: 1.6, sky: 0xdfe6ee, ground: 0x5f5a50, ambient: 1.9, exposure: 1.08, rain: false },
  HUJAN: { top: 0x4c5662, horizon: 0x9aa3ad, fog: [200, 1300], sun: 0xdfe6ee, sunIntensity: 0.9, sky: 0xc5ced8, ground: 0x4b4a46, ambient: 2.1, exposure: 1.12, rain: true },
};

export const lookFor = (weather: string) => (weather.includes('HUJAN') ? LOOKS.HUJAN : weather === 'CERAH' ? LOOKS.CERAH : LOOKS.BERAWAN);

/** Siapkan model sirkuit: statis (tanpa hitung matriks tiap bingkai) dan material yang aman. */
export function prepareTrack(THREE: any, track: any) {
  const textures = new Set<any>();
  track.traverse((object: any) => {
    object.matrixAutoUpdate = false;
    object.updateMatrix();
    if (!object.isMesh) return;
    object.castShadow = false;
    object.receiveShadow = false;
    [object.material].flat().forEach((material: any) => {
      if (!material) return;
      // Ekspor Sketchfab kadang memakai metalness 1 tanpa peta logam: tampak hitam tanpa pantulan.
      if (material.metalness > 0.5 && !material.metalnessMap) material.metalness = 0.05;
      if (material.alphaTest > 0) material.transparent = false;
      for (const value of Object.values(material)) if ((value as any)?.isTexture) textures.add(value);
      material.side = material.side ?? THREE.FrontSide;
    });
  });
  track.updateMatrixWorld(true);
  return textures;
}

export function createArena(THREE: any, renderer: any, track: any, weather: string) {
  const look = lookFor(weather);
  const scene = new THREE.Scene();
  const horizon = new THREE.Color(look.horizon);
  scene.background = horizon;
  scene.fog = new THREE.Fog(horizon, look.fog[0], look.fog[1]);
  renderer.toneMappingExposure = look.exposure;

  scene.add(new THREE.HemisphereLight(look.sky, look.ground, look.ambient));
  const sun = new THREE.DirectionalLight(look.sun, look.sunIntensity);
  sun.position.set(0.45, 1, 0.3);
  scene.add(sun);
  const bounce = new THREE.DirectionalLight(look.sky, look.sunIntensity * 0.24);
  bounce.position.set(-0.5, 0.35, -0.45);
  scene.add(bounce);

  /* Langit: kubah atmosfer realistis dengan awan prosedural & pendar matahari. */
  const sunDir = sun.position.clone().normalize();
  const skyMaterial = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    fog: false,
    uniforms: {
      top: { value: new THREE.Color(look.top) },
      horizon: { value: horizon.clone() },
      sunDir: { value: sunDir },
      sunColor: { value: new THREE.Color(look.sun) },
      sunGlow: { value: weather === 'CERAH' ? 1.0 : weather.includes('HUJAN') ? 0.1 : 0.38 },
      cloudCover: { value: weather === 'CERAH' ? 0.38 : weather.includes('HUJAN') ? 0.78 : 0.62 },
      time: { value: 0 },
    },
    vertexShader: 'varying vec3 vDir; void main(){ vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); gl_Position.z = gl_Position.w; }',
    fragmentShader: `
      uniform vec3 top; uniform vec3 horizon; uniform vec3 sunDir; uniform vec3 sunColor;
      uniform float sunGlow; uniform float cloudCover; uniform float time;
      varying vec3 vDir;
      float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123); }
      float noise(vec2 p){
        vec2 i = floor(p); vec2 f = fract(p);
        vec2 u = f * f * (3.0 - 2.0 * f);
        return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x),
                   mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
      }
      float fbm(vec2 p){
        float v = 0.0; float a = 0.5;
        for (int i = 0; i < 4; i++) { v += a * noise(p); p *= 2.05; a *= 0.5; }
        return v;
      }
      void main(){
        vec3 d = normalize(vDir);
        float h = clamp(d.y, 0.0, 1.0);
        vec3 col = mix(horizon, top, pow(h, 0.52));
        float mu = max(dot(d, sunDir), 0.0);
        col += sunColor * (pow(mu, 10.0) * 0.22 + pow(mu, 180.0) * 0.9) * sunGlow;
        if (d.y > 0.015) {
          vec2 uv = d.xz / (d.y + 0.16) * 1.15 + vec2(time * 0.008, time * 0.004);
          float n = fbm(uv);
          float wisp = smoothstep(1.0 - cloudCover, 0.96, n) * smoothstep(0.015, 0.14, d.y);
          vec3 cloudCol = mix(vec3(0.95, 0.96, 0.98), sunColor * 1.04, 0.18 + 0.25 * pow(mu, 4.0) * sunGlow);
          cloudCol = mix(horizon * 0.92, cloudCol, smoothstep(0.02, 0.28, d.y));
          col = mix(col, cloudCol, wisp * 0.72);
        }
        gl_FragColor = vec4(col, 1.0);
      }`,
  });
  const sky = new THREE.Mesh(new THREE.SphereGeometry(100, 24, 12), skyMaterial);
  sky.frustumCulled = false;
  sky.renderOrder = -1;
  scene.add(sky);

  scene.add(track);

  /* Hujan: garis-garis yang digerakkan GPU di sekitar kamera. */
  let rain: any = null;
  if (look.rain) {
    const count = 2600;
    const positions = new Float32Array(count * 6);
    for (let i = 0; i < count; i++) {
      const px = (Math.random() - 0.5) * 60;
      const py = Math.random() * 30;
      const pz = (Math.random() - 0.5) * 60;
      positions.set([px, py, pz, px + 0.05, py - 0.7, pz], i * 6);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const material = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      uniforms: { time: { value: 0 }, origin: { value: new THREE.Vector3() } },
      vertexShader: `uniform float time; uniform vec3 origin;
        void main(){
          vec3 p = position;
          p.y = mod(p.y - time * 22.0, 30.0) - 12.0 + origin.y;
          p.x = mod(p.x - origin.x + 30.0, 60.0) - 30.0 + origin.x;
          p.z = mod(p.z - origin.z + 30.0, 60.0) - 30.0 + origin.z;
          gl_Position = projectionMatrix * viewMatrix * vec4(p, 1.0);
        }`,
      fragmentShader: 'void main(){ gl_FragColor = vec4(0.82, 0.86, 0.92, 0.32); }',
    });
    rain = new THREE.LineSegments(geometry, material);
    rain.frustumCulled = false;
    scene.add(rain);
  }

  let time = 0;
  return {
    scene,
    rain: look.rain,
    update(camera: any, dt: number) {
      time += dt;
      sky.position.copy(camera.position);
      skyMaterial.uniforms.time.value = time;
      if (rain) {
        rain.material.uniforms.time.value = time;
        rain.material.uniforms.origin.value.copy(camera.position);
      }
    },
    dispose() {
      scene.traverse((object: any) => {
        object.geometry?.dispose();
        [object.material].flat().forEach((material: any) => {
          if (!material) return;
          Object.values(material).forEach((value: any) => value?.isTexture && value.dispose());
          material.dispose();
        });
      });
    },
  };
}
