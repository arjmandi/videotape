import "./style.css";
import { Player } from "./player";

const root = document.getElementById("vt");
if (root) {
  const params = new URLSearchParams(location.search);
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const player = new Player(root, { url: `${scheme}://${location.host}/vtp`, debug: params.has("debug") });
  player.start();
  // Exposed for end-to-end tests and the console; the player holds no secrets.
  (window as unknown as { videotape?: Player }).videotape = player;
}
