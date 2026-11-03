import { DOWNLOAD_URL, type ApiRequest, type ApiResponse } from "./engine";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

async function status() {
  const res: ApiResponse = await chrome.runtime.sendMessage({ type: "api", path: "/api/setup" } as ApiRequest);
  const box = $("status");
  if (!res.ok) {
    box.className = "status bad";
    $("status-title").textContent = "The app isn't running";
    $("status-detail").textContent = "Open BriefLectures on your Mac, or install it.";
    const dl = $<HTMLAnchorElement>("download");
    dl.href = DOWNLOAD_URL;
    dl.hidden = false;
    return;
  }
  const setup = res.data as { model_ready: boolean; model: string };
  box.className = "status ok";
  $("status-title").textContent = "Connected to the app";
  $("status-detail").textContent = setup.model_ready
    ? `Local AI ready (${setup.model}).`
    : "Local AI isn't set up yet; lectures get a rough estimate. Finish setup in the app.";
}

chrome.storage.sync.get({ cut: "no-filler", autoSkip: true }).then((s) => {
  $<HTMLSelectElement>("cut").value = s.cut as string;
  $<HTMLInputElement>("autoskip").checked = s.autoSkip as boolean;
});
$("cut").addEventListener("change", (e) => chrome.storage.sync.set({ cut: (e.target as HTMLSelectElement).value }));
$("autoskip").addEventListener("change", (e) => chrome.storage.sync.set({ autoSkip: (e.target as HTMLInputElement).checked }));
status();
