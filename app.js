/* ============================================================
   AjeetTV — live stream player
   DASH (mpd) playback via Shaka Player + ClearKey DRM.
   Akamai auth: __hdnea__ token appended as query param.
   ============================================================ */

// Shared Akamai access token (authenticates all channels below).
const HDNEA = "__hdnea__=st=1792652401~exp=1792674001~acl=/*~hmac=2c3a3b67acf1da0043dfd5fa8ad2ec24090da5fec6522957f4a25a2d06c08b72";

const CHANNELS = [
  {
    id: "so1",
    name: "Sony Ten 1",
    meta: "Sports · HD",
    color: "#7c3aed",
    url: "https://jiotvmblive.cdn.jio.com/bpk-tv/Ten_HD_MOB/WDVLive/index.mpd",
    keyId: "3525c924e54154b39533d86b1c7a428a",
    key: "8548b566fc6608a7d3bd601ee5f3d889",
  },
  {
    id: "so2",
    name: "Sony Ten 2",
    meta: "Sports · HD",
    color: "#2563eb",
    url: "https://jiotvmblive.cdn.jio.com/bpk-tv/Ten2_HD_MOB/WDVLive/index.mpd",
    keyId: "91fce77f2f8056f084ed961c7ebe86ed",
    key: "8214bd5eb6c21444e8ea644824affd79",
  },
  {
    id: "so3",
    name: "Sony Ten 3",
    meta: "Sports · HD",
    color: "#0891b2",
    url: "https://jiotvmblive.cdn.jio.com/bpk-tv/Ten3_HD_MOB/WDVLive/index.mpd",
    keyId: "111e6908b965566e97139efddf7ef459",
    key: "c87903abbc052e1f21e51ebd928d9cb1",
  },
  {
    id: "so5",
    name: "Sony Ten 5",
    meta: "Sports · HD",
    color: "#dc2626",
    url: "https://jiotvmblive.cdn.jio.com/bpk-tv/Six_HD_MOB/WDVLive/index.mpd",
    keyId: "8cb7b40cefe053ea91895e3194bb9912",
    key: "467cf6d740b7212fcfc648644fb79943",
  },
];

const $ = (id) => document.getElementById(id);
const video = $("video");
const container = $("playerContainer");

let player = null;
let ui = null;
let currentChannel = null;
let toastTimer = null;

function toast(msg, ms = 2500) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), ms);
}

function showLoading(on) {
  $("loadingOverlay").classList.toggle("hidden", !on);
}

function showError(msg) {
  $("errorMsg").textContent = msg || "Something went wrong. Please try again.";
  $("errorOverlay").classList.remove("hidden");
  showLoading(false);
}

function hideError() {
  $("errorOverlay").classList.add("hidden");
}

/* ---------- Channel list ---------- */
function renderChannels() {
  const list = $("channelList");
  list.innerHTML = "";
  CHANNELS.forEach((ch) => {
    const btn = document.createElement("button");
    btn.className = "ch-card";
    btn.dataset.id = ch.id;
    btn.innerHTML = `
      <span class="ch-badge" style="background:${ch.color}">${ch.name.replace("Sony ", "").slice(0, 5)}</span>
      <span>
        <span class="ch-name">${ch.name}</span>
        <div class="ch-meta">${ch.meta}</div>
      </span>`;
    btn.addEventListener("click", () => playChannel(ch.id, true));
    list.appendChild(btn);
  });
}

function markActive(id) {
  document.querySelectorAll(".ch-card").forEach((el) =>
    el.classList.toggle("active", el.dataset.id === id)
  );
}

/* ---------- Player ---------- */
async function initPlayer() {
  shaka.polyfill.installAll();

  if (!shaka.Player.isBrowserSupported()) {
    showError("This browser does not support the required playback features.");
    return false;
  }

  ui = new shaka.ui.Overlay(new shaka.Player(video), container, video);
  player = ui.getControls().getPlayer();

  player.addEventListener("error", (e) => {
    const code = e.detail && e.detail.code ? e.detail.code : "unknown";
    showError(`Playback error (${code}). Tap Retry — the stream token may have expired.`);
  });

  // Append the Akamai token to every request (manifest, segments, license).
  player.getNetworkingEngine().registerRequestFilter((type, request) => {
    const u = request.uris[0];
    if (u && !u.includes("__hdnea__=")) {
      request.uris[0] = u + (u.includes("?") ? "&" : "?") + HDNEA;
    }
  });

  // The MPD only advertises Widevine, so browsers with a Widevine CDM pick it
  // and die with 6007 (no license server). Rewrite the manifest to declare
  // ClearKey instead so the locally-configured clearKeys are used.
  const WIDEVINE_UUID = "edef8ba9-79d6-4ace-a3c8-27dcd51d21ed";
  const CLEARKEY_CP =
    '<ContentProtection schemeIdUri="urn:uuid:e2719d58-a985-b3c9-781a-b030af78d30e"/>';
  player.getNetworkingEngine().registerResponseFilter((type, response) => {
    if (type !== shaka.net.NetworkingEngine.RequestType.MANIFEST) return;
    let text = shaka.util.StringUtils.fromUTF8(response.data);
    text = text
      .replace(
        new RegExp(
          `<ContentProtection[^>]*${WIDEVINE_UUID}[^>]*/>|<ContentProtection[^>]*${WIDEVINE_UUID}[^>]*>[\\s\\S]*?</ContentProtection>`,
          "gi"
        ),
        CLEARKEY_CP
      );
    response.data = shaka.util.StringUtils.toUTF8(text);
  });

  return true;
}

async function playChannel(id, pushState) {
  const ch = CHANNELS.find((c) => c.id === id);
  if (!ch) return;
  currentChannel = ch;

  markActive(id);
  hideError();
  showLoading(true);
  $("npName").textContent = ch.name;
  $("npMeta").textContent = ch.meta;
  document.title = `${ch.name} — AjeetTV`;

  if (pushState) {
    const u = new URL(location.href);
    u.searchParams.set("id", id);
    history.pushState({ id }, "", u);
  }

  player.configure({ drm: { clearKeys: { [ch.keyId]: ch.key } } });

  try {
    await player.load(ch.url);
    showLoading(false);
    populateQuality();
    toast(`${ch.name} playing`);
  } catch (err) {
    showError(`Failed to load ${ch.name} (error ${err.code || "unknown"}).`);
  }
}

/* ---------- Quality selector ---------- */
function populateQuality() {
  const sel = $("qualitySelect");
  sel.innerHTML = `<option value="auto">Auto</option>`;
  const heights = new Set();
  player
    .getVariantTracks()
    .filter((t) => t.height)
    .sort((a, b) => b.height - a.height)
    .forEach((t) => {
      if (heights.has(t.height)) return;
      heights.add(t.height);
      const opt = document.createElement("option");
      opt.value = t.id;
      opt.textContent = `${t.height}p`;
      sel.appendChild(opt);
    });
}

$("qualitySelect").addEventListener("change", (e) => {
  if (!player) return;
  if (e.target.value === "auto") {
    player.configure({ abr: { enabled: true } });
  } else {
    player.configure({ abr: { enabled: false } });
    const track = player.getVariantTracks().find((t) => t.id === Number(e.target.value));
    if (track) player.selectVariantTrack(track, true);
  }
});

/* ---------- Controls ---------- */
$("retryBtn").addEventListener("click", () => currentChannel && playChannel(currentChannel.id, false));
$("reloadBtn").addEventListener("click", () => currentChannel && playChannel(currentChannel.id, false));

$("fsBtn").addEventListener("click", () => {
  if (document.fullscreenElement) document.exitFullscreen();
  else container.requestFullscreen().catch(() => {});
});

$("pipBtn").addEventListener("click", async () => {
  try {
    if (document.pictureInPictureElement) await document.exitPictureInPicture();
    else await video.requestPictureInPicture();
  } catch (_) {
    toast("PiP not available");
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "f") $("fsBtn").click();
  if (e.key === " ") { e.preventDefault(); video.paused ? video.play() : video.pause(); }
});

window.addEventListener("popstate", () => {
  const id = new URLSearchParams(location.search).get("id");
  if (id && id !== (currentChannel && currentChannel.id)) playChannel(id, false);
});

/* ---------- Clock ---------- */
setInterval(() => {
  $("clock").textContent = new Date().toLocaleTimeString();
}, 1000);

/* ---------- Boot ---------- */
(async () => {
  renderChannels();
  if (!(await initPlayer())) return;
  const id = new URLSearchParams(location.search).get("id") || CHANNELS[0].id;
  playChannel(id, false);
})();
