import * as THREE from "three";
import { buildScene } from "./SceneBuilder.js";
import { buildColliders } from "./CollisionWorld.js";
import { RobotDog } from "./RobotDog.js";
import { CameraFocus } from "./CameraFocus.js";
import { ActionQueue } from "./ActionQueue.js";
import { setupUI } from "./ui.js";

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  return res.json();
}

async function main() {
  const viewport = document.getElementById("viewport");

  const [sceneConfig, actionsConfig, uiConfig] = await Promise.all([
    fetchJson("/api/scene"),
    fetchJson("/api/actions"),
    fetchJson("/api/ui"),
  ]);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(viewport.clientWidth, viewport.clientHeight);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.setClearColor(0x87a0b8, 1);
  viewport.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x87a0b8, 12, 28);

  const camera = new THREE.PerspectiveCamera(
    50,
    viewport.clientWidth / Math.max(1, viewport.clientHeight),
    0.1,
    100
  );

  const { root, ground, lights } = buildScene(sceneConfig);
  scene.add(root);
  for (const light of lights) scene.add(light);

  const collision = buildColliders(sceneConfig, {
    headOnDot: Math.cos(
      THREE.MathUtils.degToRad(uiConfig.collision_head_on_deg ?? 40)
    ),
    steerRate: uiConfig.collision_steer_rate ?? 2.2,
  });

  const dog = new RobotDog({
    stepLength: uiConfig.step_length_m ?? 0.4,
    collision,
    radius: uiConfig.collision_radius_m ?? 0.28,
    steerRate: uiConfig.collision_steer_rate ?? 2.2,
  });
  const robotCfg = sceneConfig.robot || {};
  dog.setTransform(
    robotCfg.position || [0, 0, 0],
    robotCfg.rotation_y || 0,
    robotCfg.scale || 1
  );
  scene.add(dog.group);

  const camCtrl = new CameraFocus(camera, renderer.domElement, ground, {
    focusHeight: uiConfig.focus_height_m ?? 1.7,
    distance: uiConfig.camera_distance ?? 4.5,
  });
  // Start looking near the dog
  camCtrl.focus.x = dog.group.position.x;
  camCtrl.focus.z = dog.group.position.z;
  camCtrl.updateCamera();
  scene.add(camCtrl.marker);

  const queue = new ActionQueue({
    play: (fn, params, durationSec) => dog.play(fn, params, durationSec),
  });

  setupUI({
    actions: actionsConfig.actions || [],
    uiConfig,
    cameraFocus: camCtrl,
    queue,
  });

  // Receive ROS-shaped commands from console/sim_agent via local gateway.
  function connectCommandSocket() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${location.host}/ws/commands`;
    const ws = new WebSocket(url);
    const bar = document.getElementById("hint-bar");

    ws.onopen = () => {
      if (bar) bar.textContent = "已连接命令通道 · /sim_dog/command";
    };
    ws.onmessage = (ev) => {
      let msg;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      const fn = msg.function;
      if (!fn) return;
      const params = msg.params || {};
      const cost = Number(msg.cost_time_sec) || 1;
      const actionDef = (actionsConfig.actions || []).find((a) => a.function === fn) || {
        action: fn,
        function: fn,
        cost_time_sec: cost,
      };
      queue.enqueue(actionDef, params, 1);
      if (bar) bar.textContent = `远程指令: ${actionDef.action || fn}`;
    };
    ws.onclose = () => {
      if (bar) bar.textContent = "命令通道断开 · 3s 后重连";
      setTimeout(connectCommandSocket, 3000);
    };
    ws.onerror = () => {
      try {
        ws.close();
      } catch {
        /* ignore */
      }
    };
  }
  connectCommandSocket();

  function onResize() {
    const w = viewport.clientWidth;
    const h = Math.max(1, viewport.clientHeight);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  }
  window.addEventListener("resize", onResize);

  function tick() {
    dog.update(performance.now());
    renderer.render(scene, camera);
    requestAnimationFrame(tick);
  }
  tick();
}

main().catch((err) => {
  console.error(err);
  const bar = document.getElementById("hint-bar");
  if (bar) bar.textContent = `加载失败: ${err.message}`;
});
