import * as THREE from "three";
import { lerpAngle, yawToForward } from "./CollisionWorld.js";

function meshBox(w, h, d, color) {
  const m = new THREE.Mesh(
    new THREE.BoxGeometry(w, h, d),
    new THREE.MeshStandardMaterial({ color, roughness: 0.45, metalness: 0.25 })
  );
  m.castShadow = true;
  m.receiveShadow = true;
  return m;
}

function easeInOut(t) {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
}

/**
 * Procedural quadruped robot dog with timed action animations.
 */
export class RobotDog {
  constructor(options = {}) {
    this.stepLength = options.stepLength ?? 0.4;
    this.collision = options.collision ?? null;
    this.radius = options.radius ?? 0.28;
    this.steerRate = options.steerRate ?? 2.2;
    this.group = new THREE.Group();
    this.group.name = "robot_dog";
    this._lastNow = null;

    this.body = new THREE.Group();
    this.head = new THREE.Group();
    this.legs = {
      fl: new THREE.Group(),
      fr: new THREE.Group(),
      bl: new THREE.Group(),
      br: new THREE.Group(),
    };

    const bodyMesh = meshBox(0.45, 0.18, 0.28, "#2f6fed");
    bodyMesh.position.y = 0.28;
    this.body.add(bodyMesh);

    const neck = meshBox(0.08, 0.1, 0.08, "#2558c7");
    neck.position.set(0.22, 0.34, 0);
    this.body.add(neck);

    const headMesh = meshBox(0.18, 0.14, 0.16, "#3b82f6");
    headMesh.position.set(0.08, 0.02, 0);
    const snout = meshBox(0.1, 0.08, 0.1, "#93c5fd");
    snout.position.set(0.16, -0.02, 0);
    const earL = meshBox(0.04, 0.08, 0.03, "#1e40af");
    earL.position.set(0.02, 0.1, 0.05);
    const earR = meshBox(0.04, 0.08, 0.03, "#1e40af");
    earR.position.set(0.02, 0.1, -0.05);
    const eyeL = meshBox(0.02, 0.02, 0.02, "#fef08a");
    eyeL.position.set(0.14, 0.04, 0.05);
    const eyeR = meshBox(0.02, 0.02, 0.02, "#fef08a");
    eyeR.position.set(0.14, 0.04, -0.05);
    this.head.add(headMesh, snout, earL, earR, eyeL, eyeR);
    this.head.position.set(0.26, 0.38, 0);
    this.body.add(this.head);

    const legDefs = [
      ["fl", 0.14, 0.1],
      ["fr", 0.14, -0.1],
      ["bl", -0.14, 0.1],
      ["br", -0.14, -0.1],
    ];
    for (const [key, x, z] of legDefs) {
      const upper = meshBox(0.06, 0.14, 0.06, "#1d4ed8");
      upper.position.y = -0.07;
      const lower = meshBox(0.05, 0.12, 0.05, "#1e3a8a");
      lower.position.y = -0.18;
      const paw = meshBox(0.07, 0.04, 0.08, "#0f172a");
      paw.position.y = -0.26;
      this.legs[key].add(upper, lower, paw);
      this.legs[key].position.set(x, 0.28, z);
      this.legs[key].userData = { upper, lower, paw };
      this.body.add(this.legs[key]);
    }

    this.group.add(this.body);
    this._restPose = this._capturePose();
    this._anim = null;
    this._pose = "stand";
  }

  setTransform(position, rotationY = 0, scale = 1) {
    this.group.position.set(position[0], position[1] ?? 0, position[2]);
    this.group.rotation.y = rotationY;
    this.group.scale.setScalar(scale);
  }

  _capturePose() {
    const pose = {
      bodyY: this.body.position.y,
      bodyRotX: this.body.rotation.x,
      headRotX: this.head.rotation.x,
      headRotZ: this.head.rotation.z,
      legs: {},
    };
    for (const [k, leg] of Object.entries(this.legs)) {
      pose.legs[k] = { rotX: leg.rotation.x, rotZ: leg.rotation.z };
    }
    return pose;
  }

  _applyStandPose(amount = 1) {
    this.body.position.y = THREE.MathUtils.lerp(this.body.position.y, 0, amount);
    this.body.rotation.x = THREE.MathUtils.lerp(this.body.rotation.x, 0, amount);
    this.head.rotation.x = THREE.MathUtils.lerp(this.head.rotation.x, 0, amount);
    this.head.rotation.z = THREE.MathUtils.lerp(this.head.rotation.z, 0, amount);
    for (const leg of Object.values(this.legs)) {
      leg.rotation.x = THREE.MathUtils.lerp(leg.rotation.x, 0, amount);
      leg.rotation.z = THREE.MathUtils.lerp(leg.rotation.z, 0, amount);
    }
  }

  _setSitPose(t) {
    const e = easeInOut(t);
    this.body.position.y = THREE.MathUtils.lerp(0, -0.08, e);
    this.body.rotation.x = THREE.MathUtils.lerp(0, -0.35, e);
    this.legs.bl.rotation.x = THREE.MathUtils.lerp(0, -1.1, e);
    this.legs.br.rotation.x = THREE.MathUtils.lerp(0, -1.1, e);
    this.legs.fl.rotation.x = THREE.MathUtils.lerp(0, 0.2, e);
    this.legs.fr.rotation.x = THREE.MathUtils.lerp(0, 0.2, e);
  }

  _setLiePose(t) {
    const e = easeInOut(t);
    this.body.position.y = THREE.MathUtils.lerp(0, -0.16, e);
    this.body.rotation.x = 0;
    for (const leg of Object.values(this.legs)) {
      leg.rotation.x = THREE.MathUtils.lerp(0, Math.PI / 2, e);
    }
  }

  setCollision(world) {
    this.collision = world;
  }

  /**
   * Play a named action. Resolves when animation finishes.
   * @param {string} fn function name from actions.json
   * @param {object} params
   * @param {number} durationSec
   */
  play(fn, params = {}, durationSec = 1) {
    return new Promise((resolve) => {
      const start = performance.now();
      const durationMs = Math.max(0.05, durationSec) * 1000;
      const startPos = this.group.position.clone();
      const startYaw = this.group.rotation.y;
      const angleDeg = Number(params.angle_deg ?? 90);
      const angleRad = THREE.MathUtils.degToRad(angleDeg);

      // Reset dynamic wobble from previous frame loops
      this._applyStandPose(1);
      if (this._pose === "sit") this._setSitPose(1);
      if (this._pose === "lie") this._setLiePose(1);

      const fromPose = this._pose;
      const isLoco = fn === "forward" || fn === "back" || fn === "moonwalk";
      let moveSign = 1;
      let travelPlan = this.stepLength;
      if (fn === "back") moveSign = -1;
      if (fn === "moonwalk") {
        moveSign = -1;
        travelPlan = this.stepLength * 1.5;
      }

      this._anim = {
        fn,
        start,
        durationMs,
        startPos,
        startYaw,
        angleRad,
        fromPose,
        params,
        resolve,
        isLoco,
        moveSign,
        travelPlan,
        traveled: 0,
        blocked: false,
        lastNow: start,
      };
    });
  }

  /**
   * Incremental locomotion with collision: head-on stops; glancing slides + steers.
   */
  _updateLoco(a, raw, dt) {
    this._pose = "stand";
    this._applyStandPose(1);

    const durationSec = a.durationMs / 1000;
    // Ease-shaped speed so motion still feels eased over the action window
    const easeDeriv =
      raw <= 0
        ? 0
        : raw >= 1
          ? 0
          : raw < 0.5
            ? 4 * raw
            : 4 * (1 - raw);
    const nominalSpeed = a.travelPlan / Math.max(0.05, durationSec);
    let stepBudget = nominalSpeed * Math.max(easeDeriv, 0.35) * dt;
    stepBudget = Math.min(stepBudget, a.travelPlan - a.traveled);

    if (!a.blocked && stepBudget > 1e-5) {
      const facing = yawToForward(this.group.rotation.y);
      const intent = facing.multiplyScalar(a.moveSign * stepBudget);
      const from = this.group.position.clone();

      if (this.collision) {
        const result = this.collision.tryMove(from, intent, this.radius);
        this.group.position.x = result.pos.x;
        this.group.position.z = result.pos.z;

        if (result.headOn) {
          a.blocked = true;
          a.traveled = a.travelPlan;
        } else {
          const along = result.moved;
          a.traveled = Math.min(a.travelPlan, a.traveled + along);
          if (result.glancing && result.steerYaw != null) {
            this.group.rotation.y = lerpAngle(
              this.group.rotation.y,
              result.steerYaw,
              Math.min(1, this.steerRate * dt)
            );
          }
        }
      } else {
        this.group.position.x += intent.x;
        this.group.position.z += intent.z;
        a.traveled = Math.min(a.travelPlan, a.traveled + stepBudget);
      }
    }

    if (a.fn === "moonwalk") {
      const glide = Math.sin(raw * Math.PI * 6) * 0.35;
      this.legs.fl.rotation.x = glide;
      this.legs.fr.rotation.x = -glide;
      this.legs.bl.rotation.x = -glide * 0.5;
      this.legs.br.rotation.x = glide * 0.5;
      this.body.position.y = 0.02;
    } else {
      const gait = Math.sin(raw * Math.PI * 2) * 0.45;
      this.legs.fl.rotation.x = gait;
      this.legs.br.rotation.x = gait;
      this.legs.fr.rotation.x = -gait;
      this.legs.bl.rotation.x = -gait;
      this.body.position.y = Math.abs(Math.sin(raw * Math.PI * 2)) * 0.02;
    }
  }

  update(now = performance.now()) {
    if (!this._anim) {
      this._lastNow = now;
      return;
    }
    const a = this._anim;
    const dt = Math.min(0.05, Math.max(0, (now - a.lastNow) / 1000));
    a.lastNow = now;
    const raw = Math.min(1, (now - a.start) / a.durationMs);
    const t = easeInOut(raw);

    switch (a.fn) {
      case "stand": {
        if (a.fromPose === "sit") this._setSitPose(1 - t);
        else if (a.fromPose === "lie") this._setLiePose(1 - t);
        else this._applyStandPose(t);
        if (raw >= 1) this._pose = "stand";
        break;
      }
      case "sit": {
        this._applyStandPose(1);
        this._setSitPose(t);
        if (raw >= 1) this._pose = "sit";
        break;
      }
      case "lie_down": {
        this._applyStandPose(1);
        this._setLiePose(t);
        if (raw >= 1) this._pose = "lie";
        break;
      }
      case "forward":
      case "back":
      case "moonwalk": {
        this._updateLoco(a, raw, dt);
        break;
      }
      case "turn_left":
      case "turn_right": {
        this._pose = "stand";
        this._applyStandPose(1);
        const sign = a.fn === "turn_left" ? 1 : -1;
        this.group.rotation.y = a.startYaw + sign * a.angleRad * t;
        const spin = Math.sin(raw * Math.PI) * 0.25;
        this.legs.fl.rotation.z = spin;
        this.legs.fr.rotation.z = -spin;
        this.legs.bl.rotation.z = spin;
        this.legs.br.rotation.z = -spin;
        break;
      }
      case "nod": {
        this._applyStandPose(1);
        this.head.rotation.x = Math.sin(raw * Math.PI * 2) * 0.45;
        break;
      }
      case "bow": {
        this._applyStandPose(1);
        const bow = Math.sin(raw * Math.PI) * 0.7;
        this.body.rotation.x = bow;
        this.head.rotation.x = bow * 0.5;
        this.legs.fl.rotation.x = -bow * 0.4;
        this.legs.fr.rotation.x = -bow * 0.4;
        break;
      }
      case "shake_hands": {
        this._applyStandPose(1);
        this.legs.fr.rotation.x = -1.2 + Math.sin(raw * Math.PI * 4) * 0.5;
        this.legs.fr.rotation.z = -0.3;
        this.head.rotation.z = Math.sin(raw * Math.PI * 2) * 0.1;
        break;
      }
      case "boxing": {
        this._applyStandPose(1);
        const punch = Math.sin(raw * Math.PI * 6);
        this.legs.fl.rotation.x = -0.9 + Math.max(0, punch) * 0.8;
        this.legs.fr.rotation.x = -0.9 + Math.max(0, -punch) * 0.8;
        this.body.rotation.x = -0.15;
        this.head.rotation.x = 0.15;
        break;
      }
      case "push_up": {
        this._applyStandPose(1);
        const dip = (Math.sin(raw * Math.PI * 4) + 1) * 0.5;
        this.body.position.y = -0.06 - dip * 0.08;
        this.body.rotation.x = -0.25;
        this.legs.fl.rotation.x = 0.6;
        this.legs.fr.rotation.x = 0.6;
        this.legs.bl.rotation.x = -0.3;
        this.legs.br.rotation.x = -0.3;
        break;
      }
      case "kick_ball_left": {
        this._applyStandPose(1);
        const kick = Math.sin(raw * Math.PI);
        this.legs.fl.rotation.x = -kick * 1.4;
        this.body.rotation.z = kick * 0.15;
        break;
      }
      case "kick_ball_right": {
        this._applyStandPose(1);
        const kick = Math.sin(raw * Math.PI);
        this.legs.fr.rotation.x = -kick * 1.4;
        this.body.rotation.z = -kick * 0.15;
        break;
      }
      case "temp": {
        // stretch (伸懒腰)
        this._applyStandPose(1);
        const s = Math.sin(raw * Math.PI);
        this.body.rotation.x = -s * 0.35;
        this.head.rotation.x = -s * 0.4;
        this.legs.fl.rotation.x = -s * 0.6;
        this.legs.fr.rotation.x = -s * 0.6;
        this.legs.bl.rotation.x = s * 0.5;
        this.legs.br.rotation.x = s * 0.5;
        this.body.position.y = s * 0.03;
        break;
      }
      default: {
        this._applyStandPose(1);
        break;
      }
    }

    if (raw >= 1) {
      const done = a.resolve;
      // settle legs after locomotion
      if (["forward", "back", "turn_left", "turn_right", "moonwalk"].includes(a.fn)) {
        this._applyStandPose(1);
        this.body.position.y = 0;
      }
      this._anim = null;
      done();
    }
  }
}
