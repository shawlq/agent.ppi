/**
 * FIFO action queue: each item runs `times` repetitions serially.
 */
export class ActionQueue {
  /**
   * @param {{
   *   play: (fn: string, params: object, durationSec: number) => Promise<any>,
   *   onChange?: (snapshot: object[]) => void,
   *   onSuccess?: (item: object, result: any) => void,
   *   onError?: (err: Error, item: object) => void,
   * }} opts
   */
  constructor(opts) {
    this.play = opts.play;
    this.onChange = opts.onChange || (() => {});
    this.onSuccess = opts.onSuccess || (() => {});
    this.onError = opts.onError || (() => {});
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
        try {
          while (item.remaining > 0) {
            const result = await this.play(item.function, item.params, item.cost);
            this.onSuccess(item, result);
            item.remaining -= 1;
            this._emit();
          }
          this.items.shift();
          this._emit();
        } catch (err) {
          this.onError(err, item);
          this.items.shift();
          this._emit();
        }
      }
    } finally {
      this._running = false;
      if (this.items.length) this._pump();
    }
  }
}
