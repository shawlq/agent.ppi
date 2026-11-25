import * as THREE from "three";

function mat(color, opts = {}) {
  return new THREE.MeshStandardMaterial({
    color,
    roughness: opts.roughness ?? 0.65,
    metalness: opts.metalness ?? 0.05,
  });
}

function box(w, h, d, color, opts) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(color, opts));
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  return mesh;
}

function cyl(rTop, rBot, h, color, opts) {
  const mesh = new THREE.Mesh(
    new THREE.CylinderGeometry(rTop, rBot, h, 16),
    mat(color, opts)
  );
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  return mesh;
}

function place(group, position, rotationY = 0) {
  group.position.set(position[0], position[1] ?? 0, position[2]);
  group.rotation.y = rotationY;
  return group;
}

const builders = {
  sofa(obj) {
    const color = obj.color || "#3d5a80";
    const g = new THREE.Group();
    const seat = box(2.2, 0.35, 0.9, color);
    seat.position.y = 0.35;
    const back = box(2.2, 0.7, 0.22, color);
    back.position.set(0, 0.7, -0.34);
    const armL = box(0.18, 0.45, 0.9, color);
    armL.position.set(-1.01, 0.45, 0);
    const armR = box(0.18, 0.45, 0.9, color);
    armR.position.set(1.01, 0.45, 0);
    const cushion = box(2.0, 0.12, 0.75, "#5a7a9a");
    cushion.position.set(0, 0.58, 0.05);
    g.add(seat, back, armL, armR, cushion);
    return place(g, obj.position, obj.rotation_y || 0);
  },

  chair(obj) {
    const color = obj.color || "#6b4f3a";
    const g = new THREE.Group();
    const seat = box(0.45, 0.06, 0.45, color);
    seat.position.y = 0.45;
    const back = box(0.45, 0.5, 0.06, color);
    back.position.set(0, 0.72, -0.2);
    const legs = [
      [-0.18, 0.22, -0.18],
      [0.18, 0.22, -0.18],
      [-0.18, 0.22, 0.18],
      [0.18, 0.22, 0.18],
    ];
    for (const [x, y, z] of legs) {
      const leg = box(0.05, 0.44, 0.05, "#3a2a1f");
      leg.position.set(x, y, z);
      g.add(leg);
    }
    g.add(seat, back);
    return place(g, obj.position, obj.rotation_y || 0);
  },

  table(obj) {
    const color = obj.color || "#a0522d";
    const g = new THREE.Group();
    const top = box(1.4, 0.06, 0.9, color);
    top.position.y = 0.75;
    const legs = [
      [-0.6, 0.36, -0.35],
      [0.6, 0.36, -0.35],
      [-0.6, 0.36, 0.35],
      [0.6, 0.36, 0.35],
    ];
    for (const [x, y, z] of legs) {
      const leg = box(0.07, 0.72, 0.07, "#4a2f1f");
      leg.position.set(x, y, z);
      g.add(leg);
    }
    g.add(top);
    return place(g, obj.position, obj.rotation_y || 0);
  },

  coffee_table(obj) {
    const color = obj.color || "#8b5a2b";
    const g = new THREE.Group();
    const top = box(1.2, 0.05, 0.7, color);
    top.position.y = 0.4;
    const base = box(0.9, 0.08, 0.5, "#5c3a1e");
    base.position.y = 0.08;
    const pillar = box(0.2, 0.28, 0.2, "#6b4423");
    pillar.position.y = 0.24;
    g.add(top, base, pillar);
    return place(g, obj.position, obj.rotation_y || 0);
  },

  bench(obj) {
    const color = obj.color || "#7a5c45";
    const g = new THREE.Group();
    const seat = box(1.2, 0.08, 0.35, color);
    seat.position.y = 0.42;
    const legL = box(0.08, 0.4, 0.3, "#4a3728");
    legL.position.set(-0.5, 0.2, 0);
    const legR = box(0.08, 0.4, 0.3, "#4a3728");
    legR.position.set(0.5, 0.2, 0);
    g.add(seat, legL, legR);
    return place(g, obj.position, obj.rotation_y || 0);
  },

  tv(obj) {
    const g = new THREE.Group();
    const stand = box(0.9, 0.08, 0.35, "#333");
    stand.position.y = 0.04;
    const neck = box(0.12, 0.55, 0.12, "#222");
    neck.position.y = 0.35;
    const screen = box(1.4, 0.8, 0.06, "#111", { roughness: 0.3, metalness: 0.4 });
    screen.position.y = 1.05;
    const bezel = box(1.5, 0.9, 0.05, "#1a1a1a");
    bezel.position.y = 1.05;
    bezel.position.z = -0.01;
    const glow = box(1.3, 0.7, 0.02, "#1e3a5f", { roughness: 0.2, metalness: 0.1 });
    glow.position.set(0, 1.05, 0.04);
    g.add(stand, neck, bezel, screen, glow);
    return place(g, obj.position, obj.rotation_y || 0);
  },

  cabinet(obj) {
    const color = obj.color || "#5c4033";
    const g = new THREE.Group();
    const body = box(1.0, 1.2, 0.45, color);
    body.position.y = 0.6;
    const top = box(1.05, 0.05, 0.5, "#3e2a20");
    top.position.y = 1.22;
    for (let i = 0; i < 5; i++) {
      const drawer = box(0.9, 0.18, 0.02, "#6e4e3a");
      drawer.position.set(0, 0.22 + i * 0.22, 0.235);
      const knob = cyl(0.015, 0.015, 0.03, "#c9a227", { metalness: 0.6 });
      knob.rotation.x = Math.PI / 2;
      knob.position.set(0.3, 0.22 + i * 0.22, 0.26);
      g.add(drawer, knob);
    }
    g.add(body, top);
    return place(g, obj.position, obj.rotation_y || 0);
  },

  tea_set(obj) {
    const g = new THREE.Group();
    const tray = box(0.45, 0.02, 0.3, "#d4c4a8");
    tray.position.y = 0.01;
    const pot = cyl(0.06, 0.08, 0.12, "#e8e0d0");
    pot.position.set(-0.08, 0.08, 0);
    const lid = cyl(0.05, 0.05, 0.02, "#c9b8a0");
    lid.position.set(-0.08, 0.15, 0);
    const cupPositions = [
      [0.12, 0.05, 0.06],
      [0.12, 0.05, -0.06],
      [0.02, 0.05, 0.1],
    ];
    for (const [x, y, z] of cupPositions) {
      const cup = cyl(0.03, 0.025, 0.05, "#f2efe8");
      cup.position.set(x, y, z);
      g.add(cup);
    }
    g.add(tray, pot, lid);
    return place(g, obj.position, obj.rotation_y || 0);
  },
};

export function buildScene(sceneConfig) {
  const root = new THREE.Group();
  root.name = sceneConfig.name || "home";

  const [fw, fd] = sceneConfig.floor?.size || [8, 8];
  const floorColor = sceneConfig.floor?.color || "#d2b48c";
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(fw, fd),
    mat(floorColor, { roughness: 0.9 })
  );
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  floor.name = "floor";
  root.add(floor);

  // Invisible ground plane helper for raycasting (same as floor)
  const ground = floor;

  for (const wall of sceneConfig.walls || []) {
    const [w, h] = wall.size || [8, 2.8];
    const mesh = box(w, h, 0.08, wall.color || "#f5f0e8", { roughness: 0.85 });
    mesh.position.y = h / 2;
    if (wall.axis === "z") {
      mesh.position.z = wall.pos;
    } else {
      mesh.rotation.y = Math.PI / 2;
      mesh.position.x = wall.pos;
    }
    root.add(mesh);
  }

  for (const obj of sceneConfig.objects || []) {
    const builder = builders[obj.type];
    if (!builder) {
      console.warn(`Unknown furniture type: ${obj.type}`);
      continue;
    }
    const mesh = builder(obj);
    mesh.name = obj.id || obj.type;
    root.add(mesh);
  }

  // Soft ambient fill + key light
  const ambient = new THREE.AmbientLight(0xffffff, 0.45);
  const hemi = new THREE.HemisphereLight(0xfff2e0, 0x445566, 0.55);
  const key = new THREE.DirectionalLight(0xffffff, 0.9);
  key.position.set(3, 6, 2);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.camera.near = 0.5;
  key.shadow.camera.far = 20;
  key.shadow.camera.left = -6;
  key.shadow.camera.right = 6;
  key.shadow.camera.top = 6;
  key.shadow.camera.bottom = -6;

  return { root, ground, lights: [ambient, hemi, key] };
}
