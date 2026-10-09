/** Reconnecting WebSocket bridge for live DevSprint events. */

/** Connect to the status stream and dispatch each server event on document. */
export function connectStatus() {
  let attempts = 0;
  let socket;
  /** Open one connection and schedule a bounded backoff after disconnect. */
  function open() {
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(scheme + "//" + location.host + "/ws/status");
    socket.addEventListener("open", () => { attempts = 0; });
    socket.addEventListener("message", (message) => {
      try {
        const detail = JSON.parse(message.data);
        document.dispatchEvent(new CustomEvent(detail.type || "agent-status", { detail }));
      } catch {
        document.dispatchEvent(new CustomEvent("connection-error"));
      }
    });
    socket.addEventListener("close", () => {
      attempts += 1;
      setTimeout(open, Math.min(1000 * 2 ** Math.min(attempts, 5), 30000));
    });
  }
  open();
  return () => socket?.close();
}
