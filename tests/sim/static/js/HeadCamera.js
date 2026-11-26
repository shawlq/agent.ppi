import * as THREE from "three";

/** Layer for robot-dog meshes; head camera stays on default layer 0. */
export const DOG_LAYER = 1;

const IMAGE_TOPIC = "/sim_dog/image_raw";

/**
 * Head-mounted forward camera: projects the same 3D scene into a 2D JPEG
 * stream at a fixed rate and POSTs frames to the sim image gateway.
 */
export class HeadCamera {
  /**
   * @param {object} opts
   * @param {THREE.WebGLRenderer} opts.renderer
   * @param {THREE.Scene} opts.scene
   * @param {import("./RobotDog.js").RobotDog} opts.dog
   * @param {object} [opts.config]
   */
  constructor({ renderer, scene, dog, config = {} }) {
    this.renderer = renderer;
    this.scene = scene;
    this.dog = dog;

    this.width = Math.max(16, Math.floor(config.width ?? 640));
    this.height = Math.max(16, Math.floor(config.height ?? 480));
    this.fov = config.fov_deg ?? 60;
    this.jpegQuality = config.jpeg_quality ?? 0.75;
    this.hz = config.hz ?? 10;
    this.topic = config.topic || IMAGE_TOPIC;
    this.uploadUrl = config.upload_url || "/api/ros/image";

    this.camera = new THREE.PerspectiveCamera(
      this.fov,
      this.width / this.height,
      0.05,
      40
    );
    // Local +X is dog forward; Three camera looks down -Z → yaw -90° (not +90°,
    // which would face -X / behind the head).
    this.camera.position.set(0.22, 0.02, 0);
    this.camera.rotation.order = "YXZ";
    this.camera.rotation.y = -Math.PI / 2;
    this.camera.layers.set(0);
    this.camera.layers.disable(DOG_LAYER);

    dog.head.add(this.camera);

    this.target = new THREE.WebGLRenderTarget(this.width, this.height, {
      minFilter: THREE.LinearFilter,
      magFilter: THREE.LinearFilter,
      format: THREE.RGBAFormat,
      type: THREE.UnsignedByteType,
    });

    this._pixels = new Uint8Array(this.width * this.height * 4);
    this._canvas = document.createElement("canvas");
    this._canvas.width = this.width;
    this._canvas.height = this.height;
    this._ctx = this._canvas.getContext("2d", { willReadFrequently: true });
    this._imageData = this._ctx.createImageData(this.width, this.height);

    this._uploading = false;
    this._lastCapture = 0;
    this._periodMs = Math.max(50, Math.round(1000 / this.hz));
    this._lastOk = 0;
    this._running = false;
  }

  /** Put dog meshes on DOG_LAYER so the head camera does not see them. */
  static applyDogLayers(dog) {
    dog.group.traverse((obj) => {
      obj.layers.set(DOG_LAYER);
    });
  }

  /** Enable dog layer on the observer camera so the main view still shows the dog. */
  static enableDogOnCamera(camera) {
    camera.layers.enable(DOG_LAYER);
  }

  start() {
    this._running = true;
    this._lastCapture = 0;
  }

  stop() {
    this._running = false;
  }

  dispose() {
    this.stop();
    this.dog.head.remove(this.camera);
    this.target.dispose();
  }

  /**
   * Call from the animation loop after dog.update, before the main viewport render.
   * Captures at ~hz without racing the shared WebGLRenderer.
   */
  tick(now = performance.now()) {
    if (!this._running || this._uploading) return;
    if (now - this._lastCapture < this._periodMs) return;
    this._lastCapture = now;
    this.captureAndUpload();
  }

  /**
   * Render scene from head camera into RTT, encode JPEG, POST to gateway.
   * Skips if a previous upload is still in flight.
   */
  captureAndUpload() {
    if (this._uploading) return;
    try {
      const blob = this._renderToJpegSync();
      if (!blob) return;
      this._uploading = true;
      this._postFrame(blob).finally(() => {
        this._uploading = false;
      });
    } catch (err) {
      console.warn("[HeadCamera] capture failed", err);
      this._uploading = false;
    }
  }

  _renderToJpegSync() {
    const { renderer, scene, camera, target, width, height } = this;
    const prevTarget = renderer.getRenderTarget();
    const prevXr = renderer.xr?.enabled;
    if (renderer.xr) renderer.xr.enabled = false;

    renderer.setRenderTarget(target);
    renderer.clear();
    renderer.render(scene, camera);
    renderer.readRenderTargetPixels(target, 0, 0, width, height, this._pixels);
    renderer.setRenderTarget(prevTarget);
    if (renderer.xr) renderer.xr.enabled = prevXr;

    // WebGL origin is bottom-left; flip vertically into ImageData.
    const src = this._pixels;
    const dst = this._imageData.data;
    const row = width * 4;
    for (let y = 0; y < height; y++) {
      const srcOff = (height - 1 - y) * row;
      const dstOff = y * row;
      dst.set(src.subarray(srcOff, srcOff + row), dstOff);
    }
    this._ctx.putImageData(this._imageData, 0, 0);

    // Synchronous path via dataURL → Blob for reliable upload without await race.
    const dataUrl = this._canvas.toDataURL("image/jpeg", this.jpegQuality);
    const comma = dataUrl.indexOf(",");
    if (comma < 0) return null;
    const bin = atob(dataUrl.slice(comma + 1));
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: "image/jpeg" });
  }

  async _postFrame(blob) {
    const form = new FormData();
    form.append("topic", this.topic);
    form.append("encoding", "jpeg");
    form.append("width", String(this.width));
    form.append("height", String(this.height));
    form.append("frame", blob, "frame.jpg");
    try {
      const res = await fetch(this.uploadUrl, { method: "POST", body: form });
      if (!res.ok) {
        console.warn("[HeadCamera] upload HTTP", res.status);
        return;
      }
      this._lastOk = performance.now();
    } catch (err) {
      console.warn("[HeadCamera] upload failed", err);
    }
  }
}
