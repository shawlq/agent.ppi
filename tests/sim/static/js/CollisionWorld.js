import * as THREE from "three";

/**
 * Axis-aligned in local space, rotated by yaw in XZ. Circle (dog footprint) vs OBB.
 */
export class CollisionWorld {
  constructor(opts = {}) {
    /** @type {{ cx: number, cz: number, hx: number, hz: number, yaw: number, cos: number, sin: number, kind: string }[]} */
    this.boxes = [];
    this.headOnDot = opts.headOnDot ?? Math.cos(THREE.MathUtils.degToRad(40));
    this.steerRate = opts.steerRate ?? 2.2; // rad/s toward wall tangent
  }

  /**
   * @param {{ x: number, z: number, width: number, depth: number, yaw?: number, kind?: string }} box
   * width along local X, depth along local Z (full sizes).
   */
  addBox({ x, z, width, depth, yaw = 0, kind = "obstacle" }) {
    const y = yaw || 0;
    this.boxes.push({
      cx: x,
      cz: z,
      hx: width * 0.5,
      hz: depth * 0.5,
      yaw: y,
      cos: Math.cos(y),
      sin: Math.sin(y),
      kind,
    });
  }

  clear() {
    this.boxes.length = 0;
  }

  /**
   * Move a circle; resolve overlaps. Head-on stops into-wall motion;
   * glancing slides and suggests a steer yaw along the wall.
   *
   * @param {THREE.Vector3} from
   * @param {THREE.Vector3} delta  intended XZ displacement (y ignored)
   * @param {number} radius
   * @returns {{
   *   pos: THREE.Vector3,
   *   hit: boolean,
   *   headOn: boolean,
   *   glancing: boolean,
   *   normal: THREE.Vector3 | null,
   *   steerYaw: number | null,
   *   moved: number
   * }}
   */
  tryMove(from, delta, radius) {
    const moveLen = Math.hypot(delta.x, delta.z);
    const moveDir =
      moveLen > 1e-8
        ? new THREE.Vector3(delta.x / moveLen, 0, delta.z / moveLen)
        : new THREE.Vector3(0, 0, 0);

    // Free move first
    let pos = from.clone();
    pos.x += delta.x;
    pos.z += delta.z;

    let hit = false;
    let headOn = false;
    let glancing = false;
    let bestNormal = null;
    let bestPen = 0;
    let steerYaw = null;

    const resolveOverlaps = (p) => {
      for (let pass = 0; pass < 3; pass++) {
        let pushed = false;
        for (const box of this.boxes) {
          const info = circleVsObb(p.x, p.z, radius, box);
          if (!info) continue;
          hit = true;
          pushed = true;
          p.x += info.nx * info.pen;
          p.z += info.nz * info.pen;
          if (info.pen >= bestPen) {
            bestPen = info.pen;
            bestNormal = new THREE.Vector3(info.nx, 0, info.nz);
          }
        }
        if (!pushed) break;
      }
      return p;
    };

    pos = resolveOverlaps(pos);

    if (hit && bestNormal && moveLen > 1e-8) {
      const into = -moveDir.dot(bestNormal);
      if (into > this.headOnDot) {
        headOn = true;
        // Stay at resolved position (no further push into obstacle)
      } else if (into > 0.05) {
        glancing = true;
        const t1 = new THREE.Vector3(-bestNormal.z, 0, bestNormal.x);
        const t2 = t1.clone().multiplyScalar(-1);
        const tangent = t1.dot(moveDir) >= t2.dot(moveDir) ? t1 : t2;
        steerYaw = Math.atan2(-tangent.z, tangent.x);

        // Slide remaining intended motion along the wall tangent
        const slideAmt = moveLen * Math.max(0, tangent.dot(moveDir));
        if (slideAmt > 1e-5) {
          const base = pos.clone();
          pos.x = base.x + tangent.x * slideAmt;
          pos.z = base.z + tangent.z * slideAmt;
          bestPen = 0;
          pos = resolveOverlaps(pos);
        }
      }
    }

    const moved = Math.hypot(pos.x - from.x, pos.z - from.z);
    return { pos, hit, headOn, glancing, normal: bestNormal, steerYaw, moved };
  }
}

function circleVsObb(px, pz, radius, box) {
  // World → local
  const dx = px - box.cx;
  const dz = pz - box.cz;
  const lx = dx * box.cos + dz * box.sin;
  const lz = -dx * box.sin + dz * box.cos;

  const cx = THREE.MathUtils.clamp(lx, -box.hx, box.hx);
  const cz = THREE.MathUtils.clamp(lz, -box.hz, box.hz);
  const ox = lx - cx;
  const oz = lz - cz;
  const d2 = ox * ox + oz * oz;

  if (d2 > radius * radius) return null;

  let nx;
  let nz;
  let pen;

  if (d2 > 1e-10) {
    const d = Math.sqrt(d2);
    pen = radius - d;
    // local normal
    const lnx = ox / d;
    const lnz = oz / d;
    // local → world
    nx = lnx * box.cos - lnz * box.sin;
    nz = lnx * box.sin + lnz * box.cos;
  } else {
    // Center inside OBB: push out along least penetration axis
    const penX = box.hx - Math.abs(lx) + radius;
    const penZ = box.hz - Math.abs(lz) + radius;
    if (penX < penZ) {
      pen = penX;
      const lnx = lx >= 0 ? 1 : -1;
      nx = lnx * box.cos;
      nz = lnx * box.sin;
    } else {
      pen = penZ;
      const lnz = lz >= 0 ? 1 : -1;
      nx = -lnz * box.sin;
      nz = lnz * box.cos;
    }
  }

  return { nx, nz, pen };
}

/** Approximate footprint colliders for procedural furniture (full width × depth). */
export const FURNITURE_COLLIDERS = {
  sofa: { width: 2.2, depth: 0.95 },
  chair: { width: 0.5, depth: 0.5 },
  table: { width: 1.4, depth: 0.9 },
  coffee_table: { width: 1.2, depth: 0.7 },
  bench: { width: 1.2, depth: 0.4 },
  tv: { width: 1.5, depth: 0.45 },
  cabinet: { width: 1.05, depth: 0.5 },
  // tea_set sits on table — no floor collider
};

/**
 * Build CollisionWorld from scene JSON (same units as SceneBuilder).
 * @param {object} sceneConfig
 * @param {object} [opts]
 */
export function buildColliders(sceneConfig, opts = {}) {
  const world = new CollisionWorld(opts);

  for (const wall of sceneConfig.walls || []) {
    const [w] = wall.size || [8, 2.8];
    const thickness = 0.12;
    if (wall.axis === "z") {
      world.addBox({
        x: 0,
        z: wall.pos,
        width: w,
        depth: thickness,
        yaw: 0,
        kind: "wall",
      });
    } else {
      world.addBox({
        x: wall.pos,
        z: 0,
        width: w,
        depth: thickness,
        yaw: Math.PI / 2,
        kind: "wall",
      });
    }
  }

  for (const obj of sceneConfig.objects || []) {
    const size = FURNITURE_COLLIDERS[obj.type];
    if (!size) continue;
    const [x, , z] = obj.position || [0, 0, 0];
    world.addBox({
      x,
      z,
      width: size.width,
      depth: size.depth,
      yaw: obj.rotation_y || 0,
      kind: obj.type,
    });
  }

  return world;
}

export function lerpAngle(a, b, t) {
  let d = b - a;
  while (d > Math.PI) d -= Math.PI * 2;
  while (d < -Math.PI) d += Math.PI * 2;
  return a + d * THREE.MathUtils.clamp(t, 0, 1);
}

export function yawToForward(yaw) {
  return new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw));
}
