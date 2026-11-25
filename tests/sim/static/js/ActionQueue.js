/**
 * FIFO action queue: each item runs `times` repetitions serially.
 */
export class ActionQueue {
  /**
   * @param {{
   *   play: (fn: string, params: object, durationSec: number) => Promise<void>,
   *   onChange?: (snapshot: object[]) => void,
   * }} opts
   */
  constructor(opts) {
    this.play = opts.play;
    this.onChange = opts.onChange || (() => {});
    /** @type {{ id: number, label: string, function: string, params: object, times: number, cost: number, remaining: number, status: string }[]} */
    this.items = [];
    this._running = false;
    this._idSeq = 1;
  }

  enqueue(actionDef, params, times) {
    const n = Math.max(1, Math.floor(Number(times) || 1));
    const item = {
      id: this._idSeq++,
      label: actionDef.action,
      function: actionDef.function,
      params: { ...params },
      times: n,
      remaining: n,
      cost: actionDef.cost_time_sec,
      status: "pending",
    };
    this.items.push(item);
    this._emit();
    this._pump();
    return item;
  }

  clear() {
    // Keep currently running item finishing; drop pending ones.
    this.items = this.items.filter((it) => it.status === "running");
    this._emit();
  }

  get snapshot() {
    return this.items.map((it) => ({ ...it }));
  }

  _emit() {
    this.onChange(this.snapshot);
  }

  async _pump() {
    if (this._running) return;
    this._running = true;
    try {
      while (this.items.length) {
        const item = this.items[0];
        item.status = "running";
        this._emit();
        while (item.remaining > 0) {
          await this.play(item.function, item.params, item.cost);
          item.remaining -= 1;
          this._emit();
        }
        this.items.shift();
        this._emit();
      }
    } finally {
      this._running = false;
      // If something was enqueued during the last action, continue.
      if (this.items.length) this._pump();
    }
  }
}
